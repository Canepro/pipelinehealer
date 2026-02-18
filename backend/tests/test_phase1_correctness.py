"""Phase 1 correctness tests (IDs, retry, and remediation file change rendering)."""

import base64

import httpx
import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.agents.remediation import RemediationAgent
from src.config import reset_settings
from src.main import app
from src.models import (
    ActivityRecord,
    Diagnosis,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    FailureType,
    GitHubRepository,
    GitHubWorkflowRun,
    LogAnalysis,
    RemediationAction,
    RemediationPlan,
    RemediationResult,
    RemediationStatus,
    WorkflowRunEvent,
)
from src.storage import InMemoryStorage
from src.tools.fix_generators import NotAutoApplyReason


class FakeGitHubTools:
    """Minimal fake GitHubTools for unit testing."""

    def __init__(self) -> None:
        self.rerun_calls: list[tuple[str, str, int]] = []
        self.issue_calls: list[dict[str, str]] = []

    async def get_file_contents(self, owner: str, repo: str, path: str, ref: str | None = None):
        raise NotImplementedError

    async def get_workflow_run(self, owner: str, repo: str, run_id: int):
        _ = owner, repo
        return {
            "id": run_id,
            "html_url": f"https://github.com/Canepro/repo/actions/runs/{run_id}",
            "run_attempt": 1,
            "pull_requests": [],
        }

    async def get_workflow_jobs(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return [
            {"id": 1, "name": "test", "conclusion": "failure"},
        ]

    async def get_recent_commits(
        self,
        owner: str,
        repo: str,
        since: str | None = None,
        per_page: int = 10,
    ):
        _ = owner, repo, since, per_page
        return []

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        head: str | None = None,
        base: str | None = None,
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
    ):
        _ = owner, repo, state, head, base, sort, direction, per_page
        return []

    async def get_pull_request_files(self, owner: str, repo: str, pr_number: int, per_page: int = 100):
        _ = owner, repo, pr_number, per_page
        return []

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        labels: str | None = None,
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
    ):
        _ = owner, repo, state, labels, sort, direction, per_page
        return []

    async def create_branch(self, owner: str, repo: str, branch_name: str, from_ref: str = "HEAD"):
        _ = owner, repo, branch_name, from_ref
        return {}

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ):
        _ = owner, repo, path, content, message, branch, sha
        return {}

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
    ):
        _ = owner, repo, title, body, head, base, draft
        return {"number": 123, "html_url": f"https://github.com/{owner}/{repo}/pull/123"}

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


def _http_error(status_code: int, method: str, url: str, message: str) -> httpx.HTTPStatusError:
    request = httpx.Request(method, url)
    response = httpx.Response(status_code, request=request, json={"message": message})
    return httpx.HTTPStatusError(message, request=request, response=response)


class FakeGitHubToolsIssuesDisabled(FakeGitHubTools):
    async def create_issue(self, owner: str, repo: str, title: str, body: str, labels: list[str]):
        _ = title, body, labels
        raise _http_error(
            410,
            "POST",
            f"https://api.github.com/repos/{owner}/{repo}/issues",
            "Issues are disabled for this repo",
        )


class FakeGitHubToolsReadOnlyRepo(FakeGitHubTools):
    async def get_file_contents(self, owner: str, repo: str, path: str, ref: str | None = None):
        _ = owner, repo, path, ref
        raise _http_error(404, "GET", "https://api.github.com/fake", "Not Found")

    async def create_branch(self, owner: str, repo: str, branch_name: str, from_ref: str):
        _ = branch_name, from_ref
        raise _http_error(
            403,
            "POST",
            f"https://api.github.com/repos/{owner}/{repo}/git/refs",
            "Repository was archived so is read-only.",
        )


class FakeGitHubToolsBranchExistsReuse(FakeGitHubToolsWithFiles):
    def __init__(self) -> None:
        super().__init__(files={"README.md": "hello\n"})
        self.create_branch_calls: list[str] = []
        self.created_pr = False

    async def create_branch(self, owner: str, repo: str, branch_name: str, from_ref: str = "HEAD"):
        _ = owner, repo, from_ref
        self.create_branch_calls.append(branch_name)
        raise _http_error(
            422,
            "POST",
            f"https://api.github.com/repos/{owner}/{repo}/git/refs",
            "Reference already exists",
        )

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        head: str | None = None,
        base: str | None = None,
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
    ):
        _ = owner, repo, state, base, sort, direction, per_page
        if head and head.endswith("fix/dependency-run-777"):
            return [
                {
                    "number": 88,
                    "html_url": f"https://github.com/{owner}/{repo}/pull/88",
                    "head": {"ref": "fix/dependency-run-777"},
                    "body": "previous remediation",
                }
            ]
        return []

    async def get_pull_request_files(self, owner: str, repo: str, pr_number: int, per_page: int = 100):
        _ = owner, repo, pr_number, per_page
        return [{"filename": "README.md"}]

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
    ):
        _ = owner, repo, title, body, head, base, draft
        self.created_pr = True
        return {"number": 99, "html_url": f"https://github.com/{owner}/{repo}/pull/99"}


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

    async def fake_diagnose(log_analyses, workflow_info=None, external_diagnostics=None):
        _ = external_diagnostics
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
async def test_orchestrator_records_mcp_model_path_and_source_attribution(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    reset_settings()

    storage = InMemoryStorage()
    gh = FakeGitHubTools()
    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)

    async def fake_analyze(owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return [
            LogAnalysis(
                job_id=1,
                job_name="build",
                raw_logs="FAIL",
                error_lines=["FAIL"],
                summary="failed",
            )
        ]

    async def fake_diagnose(log_analyses, workflow_info=None, external_diagnostics=None):
        _ = log_analyses, workflow_info, external_diagnostics
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
        )

    async def fake_remediate(diagnosis, repository_info, workflow_run_id, dry_run=False):
        _ = diagnosis, repository_info, workflow_run_id, dry_run
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    async def fake_collect_external(owner: str, repo: str, event: WorkflowRunEvent, activity: ActivityRecord):
        _ = owner, repo, event, activity
        return [
            ExternalDiagnostic(
                source="gh_aw",
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary="external findings",
            ),
            ExternalDiagnostic(
                source="ci_doctor",
                status=ExternalDiagnosticStatus.UNAVAILABLE,
                summary="no confidence change",
            ),
        ]

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]
    orchestrator._collect_external_diagnostics = fake_collect_external  # type: ignore[method-assign]

    try:
        result = await orchestrator.process_workflow_failure(_make_event())
        assert result.mcp_model_path is not None
        assert result.mcp_model_path.provider == "github"
        assert result.mcp_model_path.enabled is True
        assert result.mcp_model_path.available is True
        assert "fetch_failure_context" in result.mcp_model_path.configured_tools
        assert result.mcp_model_path.tool_invocations.get("fetch_failure_context") == 1
        assert result.mcp_model_path.source_attribution == {"gh_aw": 1, "ci_doctor": 1}
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_orchestrator_records_mcp_tool_invocation_without_gh_aw(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "false")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "disabled")
    reset_settings()

    storage = InMemoryStorage()
    gh = FakeGitHubTools()
    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)

    async def fake_analyze(owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return [
            LogAnalysis(
                job_id=1,
                job_name="build",
                raw_logs="FAIL",
                error_lines=["FAIL"],
                summary="failed",
            )
        ]

    async def fake_diagnose(log_analyses, workflow_info=None, external_diagnostics=None):
        _ = log_analyses, workflow_info, external_diagnostics
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
        )

    async def fake_remediate(diagnosis, repository_info, workflow_run_id, dry_run=False):
        _ = diagnosis, repository_info, workflow_run_id, dry_run
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]

    try:
        result = await orchestrator.process_workflow_failure(_make_event())
        assert result.mcp_model_path is not None
        assert result.mcp_model_path.tool_invocations.get("fetch_failure_context") == 1
        assert result.mcp_model_path.source_attribution == {"github-mcp": 1}
        assert result.external_diagnostics[0].source == "github-mcp"
    finally:
        reset_settings()


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

    app.state.storage = storage
    app.state.workflow = FakeWorkflow()  # type: ignore[assignment]

    activity = ActivityRecord(
        id="a1",
        repositoryId="1",
        repository_name="octo/demo",
        workflow_run_id=123,
        workflow_name="CI",
        status=RemediationStatus.FAILED,
    )
    await storage.create_activity(activity)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/activities/a1/retry")
    assert response.status_code == 200
    resp = response.json()
    assert resp["status"] == "queued"
    assert gh.rerun_calls == [("octo", "demo", 123)]
    updated = await storage.get_activity("a1")
    assert updated is not None
    # Retry should keep the original activity immutable; webhook retries create
    # a new activity record keyed by run_attempt.
    assert updated.status == RemediationStatus.FAILED


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
    assert result.details.get("includes_proposed_fix") is True
    assert result.details.get("not_auto_reason_code") == NotAutoApplyReason.LOW_CONFIDENCE.value
    assert isinstance(result.details.get("not_auto_reason_detail"), str)
    assert gh.issue_calls
    body = gh.issue_calls[0]["body"]
    assert "### Proposed Fix (For Review Only)" in body
    assert "### Why Not Auto-Applied" in body
    assert "### How to Validate" in body
    assert f"Reason Code: {NotAutoApplyReason.LOW_CONFIDENCE.value}" in body


@pytest.mark.asyncio
async def test_create_issue_when_issues_disabled_returns_skip() -> None:
    gh = FakeGitHubToolsIssuesDisabled()
    agent = RemediationAgent(github_tools=gh)
    plan = RemediationPlan(
        action=RemediationAction.CREATE_ISSUE,
        description="Escalate for manual fix",
        issue_title="[PipelineHealer] CI Failure Analysis",
        issue_body="Root cause summary",
    )

    result = await agent._create_issue(plan, owner="octo", repo="demo", workflow_run_id=123)
    assert result.success is True
    assert result.action_taken == RemediationAction.SKIP
    assert result.error_message is None
    assert result.details.get("reason_code") == "OUTPUT_ISSUES_DISABLED"
    assert result.details.get("attempted_action") == RemediationAction.CREATE_ISSUE.value


@pytest.mark.asyncio
async def test_create_pr_when_repo_read_only_returns_skip() -> None:
    gh = FakeGitHubToolsReadOnlyRepo()
    agent = RemediationAgent(github_tools=gh)
    plan = RemediationPlan(
        action=RemediationAction.CREATE_PR,
        description="Apply deterministic fix",
        branch_name="fix/read-only-test",
        pr_title="[PipelineHealer] test",
        pr_body="body",
        file_changes=[{"file": "README.md", "content": "updated"}],
    )

    result = await agent._create_pull_request(
        plan=plan,
        owner="octo",
        repo="demo",
        base_branch="main",
        workflow_run_id=123,
    )
    assert result.success is True
    assert result.action_taken == RemediationAction.SKIP
    assert result.error_message is None
    assert result.details.get("reason_code") == "OUTPUT_REPOSITORY_READ_ONLY"
    assert result.details.get("attempted_action") == RemediationAction.CREATE_PR.value


@pytest.mark.asyncio
async def test_create_pr_reuses_existing_open_pr_on_ref_collision() -> None:
    gh = FakeGitHubToolsBranchExistsReuse()
    agent = RemediationAgent(github_tools=gh)
    plan = RemediationPlan(
        action=RemediationAction.CREATE_PR,
        description="Install missing dependency",
        branch_name="fix/dependency",
        pr_title="[PipelineHealer] dependency fix",
        pr_body="body",
        file_changes=[{"file": "README.md", "content": "updated"}],
    )

    result = await agent._create_pull_request(
        plan=plan,
        owner="octo",
        repo="demo",
        base_branch="main",
        workflow_run_id=777,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_PR
    assert result.pr_url == "https://github.com/octo/demo/pull/88"
    assert result.details.get("reused_existing_pr") is True
    assert gh.created_pr is False


# ---------------------------------------------------------------------------
# Dedupe and should_process tests
# ---------------------------------------------------------------------------


def _make_event_with_run_id(
    run_id: int,
    workflow_name: str = "CI",
    run_attempt: int = 1,
) -> WorkflowRunEvent:
    repo = GitHubRepository(
        id=1,
        name="demo",
        full_name="octo/demo",
        owner={"login": "octo"},
        default_branch="main",
        html_url="https://github.com/octo/demo",
    )
    run = GitHubWorkflowRun(
        id=run_id,
        name=workflow_name,
        workflow_id=1,
        head_branch="main",
        head_sha="deadbeef",
        status="completed",
        conclusion="failure",
        html_url=f"https://github.com/octo/demo/actions/runs/{run_id}",
        created_at="2026-02-10T00:00:00Z",
        updated_at="2026-02-10T00:01:00Z",
        run_attempt=run_attempt,
        run_number=run_id,
    )
    return WorkflowRunEvent(action="completed", workflow_run=run, repository=repo, sender={})


@pytest.mark.asyncio
async def test_should_process_deduplicates_beyond_10_activities() -> None:
    """Dedupe should find a matching run even if >10 activities exist for the repo."""
    storage = InMemoryStorage()
    gh = FakeGitHubTools()
    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)

    # Seed 15 activities with different run IDs
    for i in range(15):
        await storage.create_activity(
            ActivityRecord(
                id=f"a-{i}",
                repositoryId="1",
                repository_name="octo/demo",
                workflow_run_id=1000 + i,
                workflow_name="CI",
                status=RemediationStatus.COMPLETED,
            )
        )

    # Now add the specific run we want to detect as duplicate
    await storage.create_activity(
        ActivityRecord(
            id="a-target",
            repositoryId="1",
            repository_name="octo/demo",
            workflow_run_id=999,
            workflow_name="CI",
            status=RemediationStatus.COMPLETED,
        )
    )

    event = _make_event_with_run_id(999)
    should, reason = await orchestrator.should_process(event)

    assert should is False
    assert "Already processed" in reason


@pytest.mark.asyncio
async def test_should_process_max_attempts_is_per_workflow() -> None:
    """Max remediation attempts should be scoped to the specific workflow, not the whole repo."""
    storage = InMemoryStorage()
    gh = FakeGitHubTools()
    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)
    orchestrator._settings.max_remediation_attempts = 3

    # Seed 3 failures for workflow "Lint" (should hit the limit)
    for i in range(3):
        await storage.create_activity(
            ActivityRecord(
                id=f"lint-{i}",
                repositoryId="1",
                repository_name="octo/demo",
                workflow_run_id=2000 + i,
                workflow_name="Lint",
                status=RemediationStatus.FAILED,
            )
        )

    # A new failure for the "CI" workflow should still be processed
    event = _make_event_with_run_id(3000, workflow_name="CI")
    should, reason = await orchestrator.should_process(event)

    assert should is True
    assert reason == "New failure to process"

    # But a new failure for "Lint" should be blocked
    event_lint = _make_event_with_run_id(3001, workflow_name="Lint")
    should_lint, reason_lint = await orchestrator.should_process(event_lint)

    assert should_lint is False
    assert "Max remediation attempts" in reason_lint
    assert "Lint" in reason_lint
