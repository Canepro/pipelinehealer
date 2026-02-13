"""Phase 1 correctness tests (IDs, retry, and remediation file change rendering)."""

import base64

import httpx
import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.agents.remediation import RemediationAgent
from src.api import dashboard
from src.models import (
    ActivityRecord,
    Diagnosis,
    FailureType,
    GitHubRepository,
    GitHubWorkflowRun,
    LogAnalysis,
    RemediationAction,
    RemediationResult,
    RemediationStatus,
    WorkflowRunEvent,
)
from src.storage import InMemoryStorage


class FakeGitHubTools:
    """Minimal fake GitHubTools for unit testing."""

    def __init__(self) -> None:
        self.rerun_calls: list[tuple[str, str, int]] = []
        self.issue_calls: list[dict[str, str]] = []

    async def get_file_contents(self, owner: str, repo: str, path: str, ref: str | None = None):
        raise NotImplementedError

    async def rerun_failed_jobs(self, owner: str, repo: str, run_id: int):
        self.rerun_calls.append((owner, repo, run_id))
        return {}

    async def create_issue(self, owner: str, repo: str, title: str, body: str, labels: list[str]):
        self.issue_calls.append(
            {
                "owner": owner,
                "repo": repo,
                "title": title,
                "body": body,
            }
        )
        return {"number": 1, "html_url": f"https://github.com/{owner}/{repo}/issues/1"}


class FakeGitHubToolsWithFiles(FakeGitHubTools):
    def __init__(self, files: dict[str, str]) -> None:
        super().__init__()
        self._files = files

    async def get_file_contents(self, owner: str, repo: str, path: str, ref: str | None = None):
        if path not in self._files:
            request = httpx.Request("GET", "https://api.github.com/fake")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

        raw = self._files[path].encode("utf-8")
        return {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii")}


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
async def test_orchestrator_uses_existing_activity_id() -> None:
    storage = InMemoryStorage()
    gh = FakeGitHubTools()

    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)

    # Pre-create activity with a known ID (this is what webhook/start() would return).
    existing = ActivityRecord(
        id="activity-1",
        repositoryId="1",
        repository_name="octo/demo",
        workflow_run_id=123,
        workflow_name="CI",
        status=RemediationStatus.PENDING,
    )
    await storage.create_activity(existing)

    # Stub sub-agents so we don't touch external services.
    async def fake_analyze(owner: str, repo: str, run_id: int):
        return [
            LogAnalysis(
                job_id=1,
                job_name="build",
                raw_logs="FAIL",
                error_lines=["FAIL"],
                summary="failed",
            )
        ]

    async def fake_diagnose(log_analyses, workflow_info=None):
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
        )

    async def fake_remediate(diagnosis, repository_info, workflow_run_id, dry_run=False):
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]

    event = _make_event()
    result = await orchestrator.process_workflow_failure(event, activity_id="activity-1")

    assert result.id == "activity-1"
    activities = await storage.get_activities(limit=10)
    assert len(activities) == 1
    assert activities[0].id == "activity-1"


@pytest.mark.asyncio
async def test_remediation_renders_json_update_into_content() -> None:
    gh = FakeGitHubToolsWithFiles(files={"package.json": '{"dependencies":{"foo":"1.0.0"}}\n'})
    agent = RemediationAgent(github_tools=gh)

    rendered = await agent._render_file_changes(
        owner="octo",
        repo="demo",
        base_ref="main",
        file_changes=[
            {
                "file": "package.json",
                "type": "json_update",
                "path": "dependencies.foo",
                "value": "^2.0.0",
            }
        ],
    )

    assert len(rendered) == 1
    assert rendered[0]["file"] == "package.json"
    assert '"foo": "^2.0.0"' in rendered[0]["content"]


@pytest.mark.asyncio
async def test_dashboard_retry_calls_rerun_failed_jobs() -> None:
    storage = InMemoryStorage()
    gh = FakeGitHubTools()

    class FakeWorkflow:
        def __init__(self) -> None:
            self.github_tools = gh

    dashboard.set_storage(storage)
    dashboard.set_workflow(FakeWorkflow())  # type: ignore[arg-type]

    activity = ActivityRecord(
        id="a1",
        repositoryId="1",
        repository_name="octo/demo",
        workflow_run_id=123,
        workflow_name="CI",
        status=RemediationStatus.FAILED,
    )
    await storage.create_activity(activity)

    resp = await dashboard.retry_activity("a1")
    assert resp["status"] == "queued"
    assert gh.rerun_calls == [("octo", "demo", 123)]


@pytest.mark.asyncio
async def test_remediation_low_confidence_creates_review_issue() -> None:
    gh = FakeGitHubTools()
    agent = RemediationAgent(github_tools=gh)

    result = await agent.remediate(
        diagnosis=Diagnosis(
            failure_type=FailureType.UNKNOWN,
            confidence=0.3,
            root_cause="Insufficient evidence for deterministic remediation",
            is_auto_fixable=False,
            suggested_fix="Inspect full logs and verify environment assumptions",
            error_details={},
        ),
        repository_info={"owner": {"login": "octo"}, "name": "demo", "default_branch": "main"},
        workflow_run_id=123,
        dry_run=False,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_ISSUE
    assert result.issue_url is not None
    assert gh.issue_calls
    body = gh.issue_calls[0]["body"]
    assert "### Proposed Fix (For Review Only)" in body
    assert "### Why Not Auto-Applied" in body
