"""Tests for retrieval-backed learning context injection."""

import pytest

from src.agents.diagnosis import DiagnosisAgent
from src.agents.orchestrator import OrchestratorAgent
from src.agents.remediation import RemediationAgent
from src.models import (
    Diagnosis,
    DiagnosisSource,
    FailureType,
    GitHubRepository,
    GitHubWorkflowRun,
    LearningContextMatch,
    LearningQueueItem,
    LearningQueueStatus,
    LogAnalysis,
    RemediationAction,
    RemediationResult,
    WorkflowRunEvent,
)
from src.storage import InMemoryStorage
from src.tools.learning_context import LearningContextRetriever


class _DummyGitHubTools:
    async def get_workflow_run(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return {"pull_requests": []}


def _make_event() -> WorkflowRunEvent:
    repo = GitHubRepository(
        id=1,
        name="demo",
        full_name="octo/demo",
        owner={"login": "octo"},
        default_branch="main",
        html_url="https://github.com/octo/demo",
    )
    run = GitHubWorkflowRun(
        id=123,
        name="CI",
        workflow_id=1,
        head_branch="main",
        head_sha="deadbeef",
        status="completed",
        conclusion="failure",
        html_url="https://github.com/octo/demo/actions/runs/123",
        created_at="2026-02-10T00:00:00Z",
        updated_at="2026-02-10T00:01:00Z",
        run_attempt=1,
        run_number=1,
    )
    return WorkflowRunEvent(action="completed", workflow_run=run, repository=repo, sender={})


@pytest.mark.asyncio
async def test_learning_context_retriever_prefers_active_repo_and_reason_matches() -> None:
    storage = InMemoryStorage()
    await storage.initialize()
    await storage.upsert_learning_queue_item(
        LearningQueueItem(
            id="learning-best",
            fingerprint="fp-best",
            title="Dependency: missing requests",
            failure_type=FailureType.DEPENDENCY,
            reason_code="missing_python_module",
            suggested_playbook="Add requests to pyproject.toml and reinstall dependencies.",
            repositories=["octo/demo"],
            occurrence_count=4,
            success_count=4,
            verification_pass_rate=1.0,
            status=LearningQueueStatus.ACTIVE,
        ).model_dump(mode="json")
    )
    await storage.upsert_learning_queue_item(
        LearningQueueItem(
            id="learning-weaker",
            fingerprint="fp-weaker",
            title="Dependency: general package fix",
            failure_type=FailureType.DEPENDENCY,
            reason_code="version_conflict",
            suggested_playbook="Refresh dependency versions.",
            repositories=["octo/other"],
            occurrence_count=2,
            success_count=2,
            verification_pass_rate=0.5,
            status=LearningQueueStatus.ACTIVE,
        ).model_dump(mode="json")
    )
    await storage.upsert_learning_queue_item(
        LearningQueueItem(
            id="learning-approved",
            fingerprint="fp-approved",
            title="Dependency: approved but inactive",
            failure_type=FailureType.DEPENDENCY,
            reason_code="missing_python_module",
            suggested_playbook="Should not be retrieved before activation.",
            repositories=["octo/demo"],
            occurrence_count=3,
            success_count=3,
            verification_pass_rate=1.0,
            status=LearningQueueStatus.APPROVED,
        ).model_dump(mode="json")
    )

    retriever = LearningContextRetriever(storage)
    matches = await retriever.retrieve(
        repository_name="octo/demo",
        failure_type="dependency",
        reason_code="missing python module",
    )

    assert [match.id for match in matches] == ["learning-best", "learning-weaker"]
    assert matches[0].match_rank == 1
    assert "failure_type exact" in matches[0].match_basis
    assert "reason_code exact" in matches[0].match_basis
    assert "repository exact" in matches[0].match_basis
    assert matches[0].match_score > matches[1].match_score


@pytest.mark.asyncio
async def test_learning_context_retriever_logs_invalid_rows(caplog: pytest.LogCaptureFixture) -> None:
    storage = InMemoryStorage()
    await storage.initialize()
    await storage.upsert_learning_queue_item(
        {
            "id": "invalid-item",
            "status": "active",
            "title": "invalid payload",
        }
    )

    retriever = LearningContextRetriever(storage)
    with caplog.at_level("WARNING"):
        matches = await retriever.retrieve(
            repository_name="octo/demo",
            failure_type="dependency",
        )

    assert matches == []
    assert "Skipping invalid learning queue item during runtime retrieval" in caplog.text
    assert "invalid-item" in caplog.text


@pytest.mark.asyncio
async def test_diagnosis_prompt_includes_learning_context(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = DiagnosisAgent()
    log_analysis = LogAnalysis(
        job_id=1,
        job_name="ci",
        raw_logs="workflow failed unexpectedly",
        error_lines=["workflow failed unexpectedly"],
        summary="unknown failure",
    )
    captured_prompt: dict[str, str] = {}

    class _FakeAgent:
        async def run(self, prompt: str) -> str:
            captured_prompt["value"] = prompt
            return (
                '{"failure_type":"unknown","confidence":0.4,"root_cause":"need more info",'
                '"affected_files":[],"is_auto_fixable":false,"suggested_fix":"inspect logs",'
                '"error_details":{"additional":""}}'
            )

    async def _fake_get_agent() -> _FakeAgent:
        return _FakeAgent()

    monkeypatch.setattr(agent, "_get_agent", _fake_get_agent)

    diagnosis = await agent.diagnose(
        [log_analysis],
        learning_context=[
            LearningContextMatch(
                id="learning-best",
                title="Dependency: missing requests",
                failure_type=FailureType.DEPENDENCY,
                reason_code="missing_python_module",
                suggested_playbook="Add requests to pyproject.toml.",
                match_basis=["failure_type exact", "repository exact"],
                match_rank=1,
                match_score=0.91,
            )
        ],
    )

    assert diagnosis.failure_type == FailureType.UNKNOWN
    assert "Learning context:" in captured_prompt["value"]
    assert "learning-best" in captured_prompt["value"]
    assert "Add requests to pyproject.toml." in captured_prompt["value"]


@pytest.mark.asyncio
async def test_diagnose_reuses_pattern_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = DiagnosisAgent()
    hinted = Diagnosis(
        failure_type=FailureType.DEPENDENCY,
        confidence=0.85,
        root_cause="missing requests dependency",
        is_auto_fixable=True,
        suggested_fix="Add requests to pyproject.toml.",
        diagnosis_source=DiagnosisSource.PATTERN,
    )

    def _unexpected_pattern_pass(log_analyses):
        _ = log_analyses
        raise AssertionError("pattern pass should be reused from hint")

    async def _fake_search_similar_issues(log_analyses, workflow_info):
        _ = log_analyses, workflow_info
        return []

    monkeypatch.setattr(agent, "_pattern_based_diagnosis", _unexpected_pattern_pass)
    monkeypatch.setattr(agent, "_search_similar_issues", _fake_search_similar_issues)

    diagnosis = await agent.diagnose(
        [
            LogAnalysis(
                job_id=1,
                job_name="ci",
                raw_logs="ModuleNotFoundError: No module named 'requests'",
                error_lines=["ModuleNotFoundError: No module named 'requests'"],
                summary="Import failed",
            )
        ],
        pattern_diagnosis_hint=hinted,
    )

    assert diagnosis.failure_type == FailureType.DEPENDENCY
    assert diagnosis.diagnosis_source == DiagnosisSource.PATTERN
    assert diagnosis.root_cause == "missing requests dependency"


@pytest.mark.asyncio
async def test_orchestrator_persists_learning_context_trace_and_passes_matches() -> None:
    storage = InMemoryStorage()
    await storage.initialize()
    await storage.upsert_learning_queue_item(
        LearningQueueItem(
            id="learning-dependency",
            fingerprint="fp-dependency",
            title="Dependency: missing requests",
            failure_type=FailureType.DEPENDENCY,
            reason_code="missing_python_module",
            suggested_playbook="Add requests to pyproject.toml and reinstall dependencies.",
            repositories=["octo/demo"],
            occurrence_count=3,
            success_count=3,
            verification_pass_rate=1.0,
            status=LearningQueueStatus.ACTIVE,
        ).model_dump(mode="json")
    )

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=storage)  # type: ignore[arg-type]
    event = _make_event()
    captured: dict[str, list[LearningContextMatch]] = {}

    async def fake_analyze(owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return [
            LogAnalysis(
                job_id=1,
                job_name="test",
                raw_logs="ModuleNotFoundError: No module named 'requests'",
                error_lines=["ModuleNotFoundError: No module named 'requests'"],
                summary="Import failed",
            )
        ]

    async def fake_build_workflow_context(event: WorkflowRunEvent):
        _ = event
        return {}

    async def fake_collect_external_diagnostics(owner: str, repo: str, event: WorkflowRunEvent, activity):
        _ = owner, repo, event, activity
        return []

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = log_analyses, workflow_info, external_diagnostics
        captured["diagnosis"] = list(learning_context or [])
        captured["pattern_hint"] = [pattern_diagnosis_hint] if pattern_diagnosis_hint else []
        return Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.9,
            root_cause="missing requests dependency",
            is_auto_fixable=True,
            suggested_fix="Add requests to pyproject.toml.",
            error_details={
                "package_name": "requests",
                "package_manager": "pip",
                "manifest_file": "pyproject.toml",
                "current_version": "",
                "required_version": "",
                "resolution_kind": "missing",
                "reason_code": "missing_python_module",
            },
            diagnosis_source=DiagnosisSource.PATTERN,
        )

    async def fake_remediate(
        diagnosis,
        repository_info,
        workflow_run_id,
        dry_run=False,
        learning_context=None,
    ):
        _ = diagnosis, repository_info, workflow_run_id, dry_run
        captured["remediation"] = list(learning_context or [])
        return RemediationResult(
            success=True,
            action_taken=RemediationAction.CREATE_ISSUE,
            details={},
        )

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._build_workflow_context = fake_build_workflow_context  # type: ignore[method-assign]
    orchestrator._collect_external_diagnostics = fake_collect_external_diagnostics  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]

    activity = await orchestrator.process_workflow_failure(event)

    assert captured["diagnosis"]
    assert captured["remediation"]
    assert captured["diagnosis"][0].id == "learning-dependency"
    assert captured["remediation"][0].id == "learning-dependency"
    assert captured["pattern_hint"][0].failure_type == FailureType.DEPENDENCY
    assert activity.learning_context_trace is not None
    assert activity.learning_context_trace.diagnosis_injected is True
    assert activity.learning_context_trace.remediation_injected is True
    assert activity.learning_context_trace.diagnosis_matches[0].id == "learning-dependency"
    assert activity.learning_context_trace.remediation_matches[0].id == "learning-dependency"


def test_remediation_plan_gets_learning_context_section() -> None:
    agent = RemediationAgent(github_tools=_DummyGitHubTools())  # type: ignore[arg-type]
    plan = agent._augment_plan_with_learning_context(  # noqa: SLF001 - focused unit test
        plan=agent._fix_generators.generate_review_issue(
            diagnosis=Diagnosis(
                failure_type=FailureType.DEPENDENCY,
                confidence=0.4,
                root_cause="missing requests dependency",
                is_auto_fixable=False,
                suggested_fix="Inspect dependency manifest.",
                error_details={},
            ),
            repository_info={"full_name": "octo/demo"},
            not_auto_reason="Low confidence",
        ),
        learning_context=[
            LearningContextMatch(
                id="learning-dependency",
                title="Dependency: missing requests",
                failure_type=FailureType.DEPENDENCY,
                reason_code="missing_python_module",
                suggested_playbook="Add requests to pyproject.toml and reinstall dependencies.",
                match_basis=["failure_type exact", "repository exact"],
                match_rank=1,
                match_score=0.93,
            )
        ],
    )

    assert plan.issue_body is not None
    assert "## Related Active Playbooks" in plan.issue_body
    assert "learning-dependency" in plan.issue_body
