"""Phase 1 correctness tests (IDs, retry, and remediation file change rendering)."""

import base64
import json

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
    LearningContextMatch,
    LogAnalysis,
    RemediationAction,
    RemediationPlan,
    RemediationResult,
    RemediationStatus,
    WorkflowRunEvent,
)
from src.storage import InMemoryStorage
from src.tools.fix_generators import NotAutoApplyReason

ESLINT_FLAT_CONFIG = (
    "export default [\n"
    "  {\n"
    "    files: [\"**/*.{js,mjs,cjs}\"],\n"
    "    languageOptions: {\n"
    "      ecmaVersion: \"latest\",\n"
    "      sourceType: \"module\",\n"
    "    },\n"
    "    rules: {},\n"
    "  },\n"
    "];\n"
)


@pytest.fixture(autouse=True)
def _reset_runtime_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PH_ALLOWED_REPOS", raising=False)
    monkeypatch.delenv("MCP_REPO_ALLOWLIST", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    reset_settings()
    yield
    reset_settings()


class FakeGitHubTools:
    """Minimal fake GitHubTools for unit testing."""

    def __init__(self) -> None:
        self.rerun_calls: list[tuple[str, str, int]] = []
        self.issue_calls: list[dict[str, str]] = []
        self.issue_comment_calls: list[dict[str, str | int]] = []
        self.issue_update_calls: list[dict[str, str | int]] = []
        self.pull_request_update_calls: list[dict[str, str | int]] = []
        self.pull_requests_by_number: dict[int, dict[str, object]] = {}

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

    async def get_repository_tree(
        self,
        owner: str,
        repo: str,
        tree_sha: str = "HEAD",
        recursive: bool = True,
    ):
        _ = owner, repo, tree_sha, recursive
        return []

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

    async def get_pull_request(self, owner: str, repo: str, pr_number: int):
        _ = owner, repo
        return self.pull_requests_by_number.get(
            pr_number,
            {
                "number": pr_number,
                "body": "",
                "html_url": f"https://github.com/{owner}/{repo}/pull/{pr_number}",
            },
        )

    async def update_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
    ):
        _ = owner, repo, title
        current = dict(await self.get_pull_request(owner, repo, pr_number))
        if body is not None:
            current["body"] = body
        self.pull_requests_by_number[pr_number] = current
        self.pull_request_update_calls.append(
            {
                "pr_number": pr_number,
                "body": str(body or ""),
            }
        )
        return current

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

    async def add_issue_comment(self, owner: str, repo: str, issue_number: int, body: str):
        self.issue_comment_calls.append(
            {
                "owner": owner,
                "repo": repo,
                "issue_number": issue_number,
                "body": body,
            }
        )
        return {"id": len(self.issue_comment_calls), "body": body}

    async def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        state_reason: str | None = None,
    ):
        _ = owner, repo, title, body
        self.issue_update_calls.append(
            {
                "issue_number": issue_number,
                "state": str(state or ""),
                "state_reason": str(state_reason or ""),
            }
        )
        return {"number": issue_number, "state": state, "state_reason": state_reason}


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

    async def get_repository_tree(
        self,
        owner: str,
        repo: str,
        tree_sha: str = "HEAD",
        recursive: bool = True,
    ):
        _ = owner, repo, tree_sha, recursive
        return [{"path": path, "type": "blob"} for path in self._files]


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


class FakeGitHubToolsCapturePR(FakeGitHubToolsWithFiles):
    def __init__(self, files: dict[str, str]) -> None:
        super().__init__(files=files)
        self.pr_calls: list[dict[str, str]] = []

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
        self.pr_calls.append(
            {
                "owner": owner,
                "repo": repo,
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": str(draft),
            }
        )
        return {"number": 321, "html_url": f"https://github.com/{owner}/{repo}/pull/321"}


class FakeGitHubToolsAutoMerge(FakeGitHubToolsCapturePR):
    def __init__(
        self,
        *,
        mergeable_state: str = "clean",
        check_summary: dict[str, object] | None = None,
    ) -> None:
        super().__init__(files={"README.md": "hello\n"})
        self.mergeable_state = mergeable_state
        self.check_summary = check_summary
        self.merge_calls: list[dict[str, object]] = []

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
        await super().create_pull_request(owner, repo, title, body, head, base, draft)
        return {
            "number": 321,
            "node_id": "PR_node_321",
            "html_url": f"https://github.com/{owner}/{repo}/pull/321",
            "head": {"ref": head, "sha": "abc123"},
        }

    async def get_pull_request(self, owner: str, repo: str, pr_number: int):
        _ = owner, repo
        return {
            "number": pr_number,
            "node_id": f"PR_node_{pr_number}",
            "html_url": f"https://github.com/{owner}/{repo}/pull/{pr_number}",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "mergeable_state": self.mergeable_state,
            "head": {"ref": "fix/dependency-run-901", "sha": "abc123"},
        }

    async def get_commit_check_summary(self, owner: str, repo: str, ref: str):
        _ = owner, repo, ref
        if self.check_summary is not None:
            return dict(self.check_summary)
        return {
            "ref": ref,
            "state": "success",
            "has_checks": True,
            "status_total": 0,
            "check_runs_total": 1,
            "pending": [],
            "failing": [],
            "successful": ["CI"],
        }

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        *,
        commit_title: str | None = None,
        commit_message: str | None = None,
        sha: str | None = None,
        merge_method: str = "squash",
    ):
        self.merge_calls.append(
            {
                "owner": owner,
                "repo": repo,
                "pr_number": pr_number,
                "commit_title": commit_title,
                "commit_message": commit_message,
                "sha": sha,
                "merge_method": merge_method,
            }
        )
        return {"merged": True, "sha": "merge123", "message": "Pull Request successfully merged"}


class FakeGitHubToolsExistingGeneratedIssue(FakeGitHubTools):
    def __init__(self) -> None:
        super().__init__()
        self._issues = [
            {
                "number": 9,
                "html_url": "https://github.com/octo/demo/issues/9",
                "title": "[PipelineHealer] Review required: lint",
                "body": (
                    "existing body\n\n"
                    "<!-- pipelinehealer:generated-issue:review -->\n"
                    "<!-- pipelinehealer:workflow-run:321 -->\n"
                    "<!-- pipelinehealer:fingerprint:fixedfp123456789 -->"
                ),
            }
        ]
        self.pull_requests_by_number[77] = {
            "number": 77,
            "body": "Human fix PR body",
            "html_url": "https://github.com/octo/demo/pull/77",
        }

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
        return list(self._issues)


class FakeGitHubToolsSupersededReviewIssue(FakeGitHubToolsWithFiles):
    def __init__(self) -> None:
        super().__init__(files={"README.md": "hello\n"})
        self._issues = [
            {
                "number": 41,
                "html_url": "https://github.com/octo/demo/issues/41",
                "title": "[PipelineHealer] Review required: dependency",
                "body": (
                    "review-only issue\n\n"
                    "<!-- pipelinehealer:generated-issue:review -->\n"
                    "<!-- pipelinehealer:workflow-run:555 -->\n"
                    "<!-- pipelinehealer:fingerprint:reviewfp555 -->"
                ),
            }
        ]

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
        return list(self._issues)


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

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = external_diagnostics, learning_context, pattern_diagnosis_hint
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
        )

    async def fake_remediate(
        diagnosis, repository_info, workflow_run_id, dry_run=False, learning_context=None
    ):
        _ = diagnosis, repository_info, workflow_run_id, dry_run, learning_context
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
async def test_orchestrator_dry_run_is_controlled_by_auto_apply_remediation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_APPLY_REMEDIATION", "false")
    monkeypatch.setenv("AUTO_CREATE_PR", "true")
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

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = log_analyses, workflow_info, external_diagnostics, learning_context, pattern_diagnosis_hint
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
        )

    seen: dict[str, bool] = {}

    async def fake_remediate(
        diagnosis, repository_info, workflow_run_id, dry_run=False, learning_context=None
    ):
        _ = diagnosis, repository_info, workflow_run_id, learning_context
        seen["dry_run"] = dry_run
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]

    await orchestrator.process_workflow_failure(_make_event())
    assert seen.get("dry_run") is True


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

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = log_analyses, workflow_info, external_diagnostics, learning_context, pattern_diagnosis_hint
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
        )

    async def fake_remediate(
        diagnosis, repository_info, workflow_run_id, dry_run=False, learning_context=None
    ):
        _ = diagnosis, repository_info, workflow_run_id, dry_run, learning_context
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
        assert result.mcp_model_path.tool_invocations == {}
        assert result.mcp_model_path.source_attribution == {"gh_aw": 1, "ci_doctor": 1}
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_orchestrator_records_mcp_tool_invocation_without_gh_aw(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "octo/demo")
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

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = log_analyses, workflow_info, external_diagnostics, learning_context, pattern_diagnosis_hint
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
        )

    async def fake_remediate(
        diagnosis, repository_info, workflow_run_id, dry_run=False, learning_context=None
    ):
        _ = diagnosis, repository_info, workflow_run_id, dry_run, learning_context
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]

    try:
        result = await orchestrator.process_workflow_failure(_make_event())
        assert result.mcp_model_path is not None
        assert result.mcp_model_path.tool_invocations.get("fetch_failure_context") == 2
        assert result.mcp_model_path.tool_invocations.get("fetch_runbook_context") == 1
        assert result.mcp_model_path.total_latency_ms >= 0
        assert result.mcp_model_path.action_audit
        first_audit = result.mcp_model_path.action_audit[0]
        assert first_audit.provider == "github"
        assert first_audit.request_id == result.id
        assert isinstance(first_audit.success, bool)
        assert first_audit.latency_ms >= 0
        assert result.mcp_model_path.source_attribution == {"github-mcp": 1}
        assert result.external_diagnostics[0].source == "github-mcp"
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_orchestrator_collects_runbook_context_from_github_mcp(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "octo/demo")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "false")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "disabled")
    reset_settings()

    storage = InMemoryStorage()
    gh = FakeGitHubToolsWithFiles(
        {
            "docs/RUNBOOK.md": (
                "# CI Runbook\n"
                "If lint fails in CI, run formatting locally and push again.\n"
                "If tests fail, inspect failing job and rerun failed jobs only.\n"
            )
        }
    )
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

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = log_analyses, workflow_info, external_diagnostics, learning_context, pattern_diagnosis_hint
        return Diagnosis(
            failure_type=FailureType.LINT,
            confidence=0.9,
            root_cause="lint failed",
            is_auto_fixable=False,
        )

    async def fake_remediate(
        diagnosis, repository_info, workflow_run_id, dry_run=False, learning_context=None
    ):
        _ = diagnosis, repository_info, workflow_run_id, dry_run, learning_context
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]

    try:
        result = await orchestrator.process_workflow_failure(_make_event())
        assert result.mcp_model_path is not None
        assert result.mcp_model_path.tool_invocations.get("fetch_runbook_context", 0) >= 2
        knowledge = [
            d for d in result.external_diagnostics if d.source == "knowledge-mcp"
        ]
        assert len(knowledge) == 1
        assert knowledge[0].status == ExternalDiagnosticStatus.AVAILABLE
        assert "runbook" in knowledge[0].summary.lower()
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_orchestrator_populates_failure_context_from_diagnosis_details() -> None:
    storage = InMemoryStorage()
    gh = FakeGitHubTools()
    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)

    async def fake_analyze(owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return [
            LogAnalysis(
                job_id=1,
                job_name="unit-tests",
                raw_logs="FAIL",
                error_lines=["Command npm test failed"],
                key_events=["Run npm test -- --watch=false"],
                summary="failed",
            )
        ]

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = log_analyses, workflow_info, external_diagnostics, learning_context, pattern_diagnosis_hint
        return Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="unit test failed",
            is_auto_fixable=False,
            error_details={
                "Job Name": "unit-tests",
                "Step Name": "Run npm test -- --watch=false",
                "signature": "pytest_command_failed",
            },
        )

    async def fake_remediate(
        diagnosis, repository_info, workflow_run_id, dry_run=False, learning_context=None
    ):
        _ = diagnosis, repository_info, workflow_run_id, dry_run, learning_context
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]

    result = await orchestrator.process_workflow_failure(_make_event())
    assert result.failure_context is not None
    assert result.failure_context.failing_job == "unit-tests"
    assert result.failure_context.failing_step == "Run npm test -- --watch=false"
    assert result.failure_context.failing_command == "npm test -- --watch=false"
    assert result.failure_context.signal == "pytest_command_failed"


@pytest.mark.asyncio
async def test_orchestrator_populates_failure_context_signal_from_external_reason() -> None:
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
                error_lines=["npm ERR! command npm run build"],
                summary="failed",
            )
        ]

    async def fake_diagnose(
        log_analyses,
        workflow_info=None,
        external_diagnostics=None,
        learning_context=None,
        pattern_diagnosis_hint=None,
    ):
        _ = log_analyses, workflow_info, external_diagnostics, learning_context, pattern_diagnosis_hint
        return Diagnosis(
            failure_type=FailureType.BUILD_CONFIG,
            confidence=0.85,
            root_cause="build failed",
            is_auto_fixable=False,
            error_details={},
        )

    async def fake_remediate(
        diagnosis, repository_info, workflow_run_id, dry_run=False, learning_context=None
    ):
        _ = diagnosis, repository_info, workflow_run_id, dry_run, learning_context
        return RemediationResult(success=True, action_taken=RemediationAction.CREATE_ISSUE)

    async def fake_collect_external(owner: str, repo: str, event: WorkflowRunEvent, activity: ActivityRecord):
        _ = owner, repo, event, activity
        return [
            ExternalDiagnostic(
                source="external-diagnostics",
                status=ExternalDiagnosticStatus.UNAVAILABLE,
                summary="no finding",
                metadata={"reason_code": "poll_window_exhausted"},
            )
        ]

    orchestrator._log_analyzer.analyze = fake_analyze  # type: ignore[method-assign]
    orchestrator._diagnosis_agent.diagnose = fake_diagnose  # type: ignore[method-assign]
    orchestrator._remediation_agent.remediate = fake_remediate  # type: ignore[method-assign]
    orchestrator._collect_external_diagnostics = fake_collect_external  # type: ignore[method-assign]

    result = await orchestrator.process_workflow_failure(_make_event())
    assert result.failure_context is not None
    assert result.failure_context.failing_job == "build"
    assert result.failure_context.failing_command == "npm run build"
    assert result.failure_context.signal == "poll_window_exhausted"


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
async def test_remediation_renders_bounded_patch_with_fallback_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubToolsWithFiles(files={})
    agent = RemediationAgent(github_tools=gh)

    class _EmptyPatchAgent:
        async def run(self, prompt: str) -> str:
            _ = prompt
            return ""

    async def _fake_get_patch_drafting_agent() -> _EmptyPatchAgent:
        return _EmptyPatchAgent()

    monkeypatch.setattr(agent, "_get_patch_drafting_agent", _fake_get_patch_drafting_agent)

    rendered = await agent._render_file_changes(
        owner="octo",
        repo="demo",
        base_ref="main",
        file_changes=[
            {
                "file": "eslint.config.js",
                "type": "bounded_patch",
                "draft_kind": "eslint_flat_config",
                "instructions": "Draft a minimal ESLint flat config.",
                "fallback_content": ESLINT_FLAT_CONFIG,
                "validation": {
                    "must_contain": ["export default", "rules: {}", 'ecmaVersion: "latest"'],
                    "max_bytes": 400,
                },
            }
        ],
    )

    assert len(rendered) == 1
    assert rendered[0]["file"] == "eslint.config.js"
    assert rendered[0]["content"] == ESLINT_FLAT_CONFIG
    trace = rendered[0]["patch_drafting_trace"]
    assert trace["task"] == "patch_drafting"
    assert trace["outcome"] == "fallback_content"
    assert trace["used_fallback"] is True


@pytest.mark.asyncio
async def test_remediation_bounded_patch_rejects_invalid_draft_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubToolsWithFiles(files={})
    agent = RemediationAgent(github_tools=gh)

    class _InvalidPatchAgent:
        async def run(self, prompt: str) -> str:
            _ = prompt
            return '{"content":"console.log(1)"}'

    async def _fake_get_patch_drafting_agent() -> _InvalidPatchAgent:
        return _InvalidPatchAgent()

    monkeypatch.setattr(agent, "_get_patch_drafting_agent", _fake_get_patch_drafting_agent)

    with pytest.raises(ValueError, match="missing required substrings"):
        await agent._render_file_changes(
            owner="octo",
            repo="demo",
            base_ref="main",
            file_changes=[
                {
                    "file": "eslint.config.js",
                    "type": "bounded_patch",
                    "draft_kind": "eslint_flat_config",
                    "instructions": "Draft a minimal ESLint flat config.",
                    "validation": {
                        "must_contain": ["export default", "rules: {}"],
                        "max_bytes": 200,
                    },
                }
            ],
        )


@pytest.mark.asyncio
async def test_remediation_bounded_patch_rejects_non_json_output_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubToolsWithFiles(files={})
    agent = RemediationAgent(github_tools=gh)

    class _NonJsonPatchAgent:
        async def run(self, prompt: str) -> str:
            _ = prompt
            return "here is your config draft"

    async def _fake_get_patch_drafting_agent() -> _NonJsonPatchAgent:
        return _NonJsonPatchAgent()

    monkeypatch.setattr(agent, "_get_patch_drafting_agent", _fake_get_patch_drafting_agent)

    with pytest.raises(ValueError, match="not valid JSON"):
        await agent._render_file_changes(
            owner="octo",
            repo="demo",
            base_ref="main",
            file_changes=[
                {
                    "file": "eslint.config.js",
                    "type": "bounded_patch",
                    "draft_kind": "eslint_flat_config",
                    "instructions": "Draft a minimal ESLint flat config.",
                    "validation": {
                        "must_contain": ["export default", "rules: {}"],
                        "max_bytes": 200,
                    },
                }
            ],
        )


@pytest.mark.asyncio
async def test_remediation_bounded_patch_rejects_invalid_eslint_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubToolsWithFiles(files={})
    agent = RemediationAgent(github_tools=gh)

    class _StructurallyInvalidPatchAgent:
        async def run(self, prompt: str) -> str:
            _ = prompt
            return (
                '{"content":"export default [{ files: [\\"**/*.{js,mjs,cjs}\\"], '
                'languageOptions: { ecmaVersion: latest, sourceType: \\"module\\" }, '
                'rules: {} }];"}'
            )

    async def _fake_get_patch_drafting_agent() -> _StructurallyInvalidPatchAgent:
        return _StructurallyInvalidPatchAgent()

    monkeypatch.setattr(agent, "_get_patch_drafting_agent", _fake_get_patch_drafting_agent)

    with pytest.raises(ValueError, match="eslint_flat_config checks"):
        await agent._render_file_changes(
            owner="octo",
            repo="demo",
            base_ref="main",
            file_changes=[
                {
                    "file": "eslint.config.js",
                    "type": "bounded_patch",
                    "draft_kind": "eslint_flat_config",
                    "instructions": "Draft a minimal ESLint flat config.",
                    "validation": {
                        "must_contain": [
                            "export default",
                            "**/*.{js,mjs,cjs}",
                            "rules: {}",
                        ],
                        "max_bytes": 400,
                    },
                }
            ],
        )


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
    assert "### PipelineHealer Assessment" in body
    assert "### Operator Verification Checklist" in body
    assert f"Reason Code: {NotAutoApplyReason.LOW_CONFIDENCE.value}" in body


@pytest.mark.asyncio
async def test_remediation_applies_strong_learning_guidance_to_pr_plan() -> None:
    gh = FakeGitHubTools()
    agent = RemediationAgent(github_tools=gh)

    result = await agent.remediate(
        diagnosis=Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.92,
            root_cause="Package `left-pad` is missing from dependencies.",
            is_auto_fixable=True,
            suggested_fix="Add the missing dependency.",
            error_details={
                "package_name": "left-pad",
                "package_manager": "npm",
                "required_version": "^1.3.0",
                "current_version": "",
                "manifest_file": "package.json",
                "resolution_kind": "missing",
                "reason_code": "missing_node_module",
            },
        ),
        repository_info={"owner": {"login": "octo"}, "name": "demo", "default_branch": "main"},
        workflow_run_id=123,
        dry_run=True,
        learning_context=[
            LearningContextMatch(
                id="playbook-node-dep",
                title="Restore missing npm dependency",
                failure_type=FailureType.DEPENDENCY,
                reason_code="missing_node_module",
                suggested_playbook="Add the missing package to package.json and rerun install before retrying CI.",
                match_basis=["failure_type exact", "reason_code exact", "repository exact"],
                match_rank=1,
                match_score=0.94,
                verification_pass_rate=1.0,
                occurrence_count=4,
            )
        ],
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_PR
    applied = result.details.get("applied_learning_context")
    assert isinstance(applied, dict)
    assert applied.get("id") == "playbook-node-dep"
    assert applied.get("application_mode") == "guidance_section"
    plan = result.details.get("plan")
    assert isinstance(plan, dict)
    assert "## Applied Learning Guidance" in str(plan.get("pr_body"))
    assert "## Related Active Playbooks" in str(plan.get("pr_body"))


@pytest.mark.asyncio
async def test_remediation_leaves_conflicting_learning_match_advisory_only() -> None:
    gh = FakeGitHubTools()
    agent = RemediationAgent(github_tools=gh)

    result = await agent.remediate(
        diagnosis=Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.92,
            root_cause="Package `requests` is missing from the Python environment.",
            is_auto_fixable=True,
            suggested_fix="Add the missing dependency.",
            error_details={
                "package_name": "requests",
                "package_manager": "pip",
                "required_version": "2.31.0",
                "current_version": "",
                "manifest_file": "requirements.txt",
                "resolution_kind": "missing",
                "reason_code": "missing_python_module",
            },
        ),
        repository_info={"owner": {"login": "octo"}, "name": "demo", "default_branch": "main"},
        workflow_run_id=124,
        dry_run=True,
        learning_context=[
            LearningContextMatch(
                id="playbook-version-conflict",
                title="Resolve Python version conflict",
                failure_type=FailureType.DEPENDENCY,
                reason_code="version_conflict",
                suggested_playbook="Pin the conflicting dependency versions and regenerate the lock file.",
                match_basis=["failure_type exact", "repository exact"],
                match_rank=1,
                match_score=0.95,
                verification_pass_rate=1.0,
                occurrence_count=5,
            )
        ],
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_PR
    assert result.details.get("applied_learning_context") is None
    plan = result.details.get("plan")
    assert isinstance(plan, dict)
    assert "## Applied Learning Guidance" not in str(plan.get("pr_body"))
    assert "## Related Active Playbooks" in str(plan.get("pr_body"))


@pytest.mark.asyncio
async def test_remediation_jenkins_issue_first_keeps_applied_learning_guidance() -> None:
    gh = FakeGitHubTools()
    agent = RemediationAgent(github_tools=gh)

    result = await agent.remediate(
        diagnosis=Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.92,
            root_cause="Package `left-pad` is missing from dependencies.",
            is_auto_fixable=True,
            suggested_fix="Add the missing dependency.",
            error_details={
                "package_name": "left-pad",
                "package_manager": "npm",
                "required_version": "^1.3.0",
                "current_version": "",
                "manifest_file": "package.json",
                "resolution_kind": "missing",
                "reason_code": "missing_node_module",
            },
        ),
        repository_info={
            "owner": {"login": "octo"},
            "name": "demo",
            "default_branch": "main",
            "source_selection_path": "jenkins_bridge",
        },
        workflow_run_id=125,
        dry_run=True,
        learning_context=[
            LearningContextMatch(
                id="playbook-node-dep",
                title="Restore missing npm dependency",
                failure_type=FailureType.DEPENDENCY,
                reason_code="missing_node_module",
                suggested_playbook="Add the missing package to package.json and rerun install before retrying CI.",
                match_basis=["failure_type exact", "reason_code exact", "repository exact"],
                match_rank=1,
                match_score=0.94,
                verification_pass_rate=1.0,
                occurrence_count=4,
            )
        ],
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_ISSUE
    applied = result.details.get("applied_learning_context")
    assert isinstance(applied, dict)
    plan = result.details.get("plan")
    assert isinstance(plan, dict)
    assert "## Applied Learning Guidance" in str(plan.get("issue_body"))
    assert "## Related Active Playbooks" in str(plan.get("issue_body"))


@pytest.mark.asyncio
async def test_remediation_skip_does_not_claim_applied_learning_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_CREATE_PR", "false")
    reset_settings()
    gh = FakeGitHubTools()
    agent = RemediationAgent(github_tools=gh)

    try:
        result = await agent.remediate(
            diagnosis=Diagnosis(
                failure_type=FailureType.DEPENDENCY,
                confidence=0.92,
                root_cause="Package `left-pad` is missing from dependencies.",
                is_auto_fixable=True,
                suggested_fix="Add the missing dependency.",
                error_details={
                    "package_name": "left-pad",
                    "package_manager": "npm",
                    "required_version": "^1.3.0",
                    "current_version": "",
                    "manifest_file": "package.json",
                    "resolution_kind": "missing",
                    "reason_code": "missing_node_module",
                },
            ),
            repository_info={"owner": {"login": "octo"}, "name": "demo", "default_branch": "main"},
            workflow_run_id=126,
            dry_run=False,
            learning_context=[
                LearningContextMatch(
                    id="playbook-node-dep",
                    title="Restore missing npm dependency",
                    failure_type=FailureType.DEPENDENCY,
                    reason_code="missing_node_module",
                    suggested_playbook="Add the missing package to package.json and rerun install before retrying CI.",
                    match_basis=["failure_type exact", "reason_code exact", "repository exact"],
                    match_rank=1,
                    match_score=0.94,
                    verification_pass_rate=1.0,
                    occurrence_count=4,
                )
            ],
        )
    finally:
        reset_settings()

    assert result.success is True
    assert result.action_taken == RemediationAction.SKIP
    assert result.details.get("applied_learning_context") is None


@pytest.mark.asyncio
async def test_remediation_jenkins_bridge_defaults_to_issue_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_CREATE_PR", "true")
    monkeypatch.setenv("JENKINS_BRIDGE_ALLOW_PR", "false")
    reset_settings()

    gh = FakeGitHubToolsCapturePR(files={"package.json": '{"dependencies":{"left-pad":"1.0.0"}}\n'})
    agent = RemediationAgent(github_tools=gh)

    result = await agent.remediate(
        diagnosis=Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.95,
            root_cause="Dependency version drift",
            is_auto_fixable=True,
            error_details={
                "package_name": "left-pad",
                "required_version": "^1.3.0",
                "package_manager": "npm",
            },
        ),
        repository_info={
            "owner": {"login": "octo"},
            "name": "demo",
            "default_branch": "main",
            "source_selection_path": "jenkins_bridge",
        },
        workflow_run_id=456,
        dry_run=False,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_ISSUE
    assert not gh.pr_calls
    assert result.details.get("not_auto_reason_code") == NotAutoApplyReason.SAFETY_BOUND.value


@pytest.mark.asyncio
async def test_remediation_jenkins_bridge_allows_pr_when_opted_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_CREATE_PR", "true")
    monkeypatch.setenv("JENKINS_BRIDGE_ALLOW_PR", "true")
    reset_settings()

    gh = FakeGitHubToolsCapturePR(files={"package.json": '{"dependencies":{"left-pad":"1.0.0"}}\n'})
    agent = RemediationAgent(github_tools=gh)

    result = await agent.remediate(
        diagnosis=Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.95,
            root_cause="Dependency version drift",
            is_auto_fixable=True,
            error_details={
                "package_name": "left-pad",
                "required_version": "^1.3.0",
                "package_manager": "npm",
            },
        ),
        repository_info={
            "owner": {"login": "octo"},
            "name": "demo",
            "default_branch": "main",
            "source_selection_path": "jenkins_bridge",
        },
        workflow_run_id=789,
        dry_run=False,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_PR
    assert result.pr_url == "https://github.com/octo/demo/pull/321"
    assert len(gh.pr_calls) == 1


@pytest.mark.asyncio
async def test_remediation_jenkins_bridge_stays_issue_first_when_auto_create_pr_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_CREATE_PR", "false")
    monkeypatch.setenv("JENKINS_BRIDGE_ALLOW_PR", "true")
    reset_settings()

    gh = FakeGitHubToolsCapturePR(files={"package.json": '{"dependencies":{"left-pad":"1.0.0"}}\n'})
    agent = RemediationAgent(github_tools=gh)

    result = await agent.remediate(
        diagnosis=Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.95,
            root_cause="Dependency version drift",
            is_auto_fixable=True,
            error_details={
                "package_name": "left-pad",
                "required_version": "^1.3.0",
                "package_manager": "npm",
            },
        ),
        repository_info={
            "owner": {"login": "octo"},
            "name": "demo",
            "default_branch": "main",
            "source_selection_path": "jenkins_bridge",
        },
        workflow_run_id=790,
        dry_run=False,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_ISSUE
    assert not gh.pr_calls
    assert result.details.get("not_auto_reason_code") == NotAutoApplyReason.SAFETY_BOUND.value


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
async def test_create_issue_links_active_pull_request_for_auto_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubTools()
    gh.pull_requests_by_number[22] = {
        "number": 22,
        "body": "Human fix PR body",
        "html_url": "https://github.com/octo/demo/pull/22",
    }
    agent = RemediationAgent(github_tools=gh)
    monkeypatch.setattr(agent, "_fingerprint_for_plan", lambda plan, workflow_run_id: "issuefp1234567890")
    plan = RemediationPlan(
        action=RemediationAction.CREATE_ISSUE,
        description="Escalate for manual fix",
        issue_title="[PipelineHealer] Review required: lint",
        issue_body="Root cause summary\n\n### Proposed Fix (For Review Only)",
    )

    result = await agent._create_issue(
        plan,
        owner="octo",
        repo="demo",
        workflow_run_id=123,
        repository_info={"pull_request_numbers": [22]},
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_ISSUE
    assert result.issue_url == "https://github.com/octo/demo/issues/1"
    assert result.details.get("linked_pull_request_numbers") == [22]
    assert result.details.get("reused_existing_issue") is False
    assert gh.issue_calls
    assert "<!-- pipelinehealer:generated-issue:review -->" in gh.issue_calls[0]["body"]
    assert "<!-- pipelinehealer:workflow-run:123 -->" in gh.issue_calls[0]["body"]
    assert "<!-- pipelinehealer:fingerprint:issuefp1234567890 -->" in gh.issue_calls[0]["body"]
    assert gh.pull_request_update_calls
    assert "Closes #1" in str(gh.pull_request_update_calls[0]["body"])
    assert gh.issue_comment_calls
    assert "#22" in str(gh.issue_comment_calls[0]["body"])


@pytest.mark.asyncio
async def test_create_issue_reuses_existing_generated_issue_and_links_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubToolsExistingGeneratedIssue()
    agent = RemediationAgent(github_tools=gh)
    monkeypatch.setattr(agent, "_fingerprint_for_plan", lambda plan, workflow_run_id: "fixedfp123456789")
    plan = RemediationPlan(
        action=RemediationAction.CREATE_ISSUE,
        description="Escalate for manual fix",
        issue_title="[PipelineHealer] Review required: lint",
        issue_body="Root cause summary",
    )

    result = await agent._create_issue(
        plan,
        owner="octo",
        repo="demo",
        workflow_run_id=321,
        repository_info={"pull_request_numbers": [77]},
    )

    assert result.success is True
    assert result.issue_url == "https://github.com/octo/demo/issues/9"
    assert result.details.get("issue_number") == 9
    assert result.details.get("reused_existing_issue") is True
    assert result.details.get("linked_pull_request_numbers") == [77]
    assert gh.issue_calls == []
    assert gh.pull_request_update_calls
    assert "Closes #9" in str(gh.pull_request_update_calls[0]["body"])


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


@pytest.mark.asyncio
async def test_create_pr_closes_superseded_review_issue() -> None:
    gh = FakeGitHubToolsSupersededReviewIssue()
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
        workflow_run_id=555,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_PR
    assert result.details.get("closed_superseded_issue_numbers") == [41]
    assert gh.issue_comment_calls
    assert "Superseded by a concrete remediation PR." in str(gh.issue_comment_calls[0]["body"])
    assert gh.issue_update_calls == [{"issue_number": 41, "state": "closed", "state_reason": "completed"}]


@pytest.mark.asyncio
async def test_create_pr_records_patch_drafting_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubToolsCapturePR(files={})
    agent = RemediationAgent(github_tools=gh)

    class _DraftingAgent:
        async def run(self, prompt: str) -> str:
            _ = prompt
            return json.dumps({"content": ESLINT_FLAT_CONFIG})

    async def _fake_get_patch_drafting_agent() -> _DraftingAgent:
        return _DraftingAgent()

    monkeypatch.setattr(agent, "_get_patch_drafting_agent", _fake_get_patch_drafting_agent)

    plan = RemediationPlan(
        action=RemediationAction.CREATE_PR,
        description="Add eslint flat config",
        branch_name="fix/lint-eslint-config",
        pr_title="fix(lint): add eslint.config.js",
        pr_body="body",
        file_changes=[
            {
                "file": "eslint.config.js",
                "type": "bounded_patch",
                "draft_kind": "eslint_flat_config",
                "instructions": "Draft a minimal ESLint flat config.",
                "fallback_content": ESLINT_FLAT_CONFIG,
                "validation": {
                    "must_contain": ["export default", "rules: {}", 'ecmaVersion: "latest"'],
                    "max_bytes": 400,
                },
            }
        ],
    )

    result = await agent._create_pull_request(
        plan=plan,
        owner="octo",
        repo="demo",
        base_branch="main",
        workflow_run_id=901,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_PR
    traces = result.details.get("patch_drafting_trace")
    assert isinstance(traces, list)
    assert traces[0]["file"] == "eslint.config.js"
    assert traces[0]["outcome"] == "drafted"
    assert traces[0]["used_fallback"] is False


@pytest.mark.asyncio
async def test_create_pr_auto_merges_when_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_MERGE_REMEDIATION_PRS", "true")
    monkeypatch.setenv("AUTO_MERGE_STRATEGY", "merge_when_clean")
    monkeypatch.setenv("AUTO_MERGE_POLL_SECONDS", "0")
    reset_settings()

    gh = FakeGitHubToolsAutoMerge()
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
        workflow_run_id=901,
    )

    assert result.success is True
    assert result.action_taken == RemediationAction.CREATE_PR
    auto_merge = result.details.get("auto_merge")
    assert isinstance(auto_merge, dict)
    assert auto_merge["requested"] is True
    assert auto_merge["strategy"] == "merge_when_clean"
    assert auto_merge["merged"] is True
    assert auto_merge["last_state"]["checks"]["state"] == "success"
    assert len(gh.merge_calls) == 1
    assert gh.merge_calls[0]["pr_number"] == 321
    assert gh.merge_calls[0]["commit_title"] == "fix: merge PipelineHealer remediation #321"
    assert gh.merge_calls[0]["sha"] == "abc123"
    assert gh.merge_calls[0]["merge_method"] == "squash"
    assert "Remediation fingerprint" in str(gh.merge_calls[0]["commit_message"])
    assert any(
        "PipelineHealer merged this remediation PR after required checks passed."
        in str(call["body"])
        for call in gh.issue_comment_calls
    )


@pytest.mark.asyncio
async def test_create_pr_auto_merges_when_required_checks_clean_with_optional_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_MERGE_REMEDIATION_PRS", "true")
    monkeypatch.setenv("AUTO_MERGE_STRATEGY", "merge_when_clean")
    monkeypatch.setenv("AUTO_MERGE_POLL_SECONDS", "0")
    reset_settings()

    gh = FakeGitHubToolsAutoMerge(
        mergeable_state="clean",
        check_summary={
            "ref": "abc123",
            "state": "failure",
            "has_checks": True,
            "status_total": 0,
            "check_runs_total": 2,
            "pending": [],
            "failing": ["optional-review"],
            "successful": ["build"],
        },
    )
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
        workflow_run_id=901,
    )

    auto_merge = result.details.get("auto_merge")
    assert isinstance(auto_merge, dict)
    assert auto_merge["merged"] is True
    checks = auto_merge["last_state"]["checks"]
    assert checks["state"] == "failure"
    assert checks["merge_gate"] == "github_required_checks_clean"
    assert checks["optional_failures_ignored"] == ["optional-review"]
    assert len(gh.merge_calls) == 1


@pytest.mark.asyncio
async def test_create_pr_auto_merge_does_not_ignore_failures_when_github_not_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_MERGE_REMEDIATION_PRS", "true")
    monkeypatch.setenv("AUTO_MERGE_STRATEGY", "merge_when_clean")
    monkeypatch.setenv("AUTO_MERGE_POLL_SECONDS", "0")
    reset_settings()

    gh = FakeGitHubToolsAutoMerge(
        mergeable_state="unstable",
        check_summary={
            "ref": "abc123",
            "state": "failure",
            "has_checks": True,
            "status_total": 0,
            "check_runs_total": 2,
            "pending": [],
            "failing": ["required-ci"],
            "successful": ["build"],
        },
    )
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
        workflow_run_id=901,
    )

    auto_merge = result.details.get("auto_merge")
    assert isinstance(auto_merge, dict)
    assert auto_merge["merged"] is False
    assert auto_merge["error"] == "Timed out waiting for mergeable PR with clean checks"
    assert gh.merge_calls == []


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


class FakeGitHubToolsOpenReviewIssues(FakeGitHubTools):
    def __init__(self) -> None:
        super().__init__()
        self._issues = [
            {
                "number": 12,
                "html_url": "https://github.com/octo/demo/issues/12",
                "title": "[PipelineHealer] Review required: lint",
                "body": (
                    "review-only issue\n\n"
                    "<!-- pipelinehealer:generated-issue:review -->\n"
                    "<!-- pipelinehealer:workflow-name:ci -->\n"
                    "<!-- pipelinehealer:head-branch:main -->"
                ),
            }
        ]

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
        _ = owner, repo, labels, sort, direction, per_page
        if state != "open":
            return []
        return list(self._issues)


class FakeGitHubToolsExistingSignatureIssue(FakeGitHubTools):
    def __init__(self, signature: str) -> None:
        super().__init__()
        self._issues = [
            {
                "number": 19,
                "html_url": "https://github.com/octo/demo/issues/19",
                "title": "[PipelineHealer] Review required: lint",
                "body": (
                    "existing review issue\n\n"
                    "<!-- pipelinehealer:generated-issue:review -->\n"
                    "<!-- pipelinehealer:workflow-run:999 -->\n"
                    f"<!-- pipelinehealer:signature:{signature} -->"
                ),
            }
        ]

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
        return list(self._issues)


@pytest.mark.asyncio
async def test_close_issues_on_workflow_success_closes_matching_review_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubToolsOpenReviewIssues()
    agent = RemediationAgent(github_tools=gh)
    monkeypatch.setattr(agent._settings, "auto_close_on_workflow_success", True)
    monkeypatch.setattr(agent._settings, "auto_apply_remediation", True)

    result = await agent.close_issues_on_workflow_success(
        owner="octo",
        repo="demo",
        workflow_name="CI",
        head_branch="main",
        workflow_run_id=456,
        head_sha="abc123",
    )

    assert result["status"] == "completed"
    assert result["closed_issue_numbers"] == [12]
    assert gh.issue_update_calls == [
        {"issue_number": 12, "state": "closed", "state_reason": "completed"}
    ]
    assert gh.issue_comment_calls
    assert "Closed automatically because the tracked workflow succeeded." in str(
        gh.issue_comment_calls[0]["body"]
    )


def test_signature_for_plan_distinguishes_workflow_and_branch() -> None:
    plan = RemediationPlan(
        action=RemediationAction.CREATE_ISSUE,
        description="Escalate for manual fix",
        issue_title="[PipelineHealer] Review required: lint",
        issue_body="Root cause summary",
    )
    base = RemediationAgent._signature_for_plan(plan)
    with_context = RemediationAgent._signature_for_plan(
        plan,
        workflow_name="CI",
        head_branch="main",
    )
    other_workflow = RemediationAgent._signature_for_plan(
        plan,
        workflow_name="Release",
        head_branch="main",
    )
    other_branch = RemediationAgent._signature_for_plan(
        plan,
        workflow_name="CI",
        head_branch="release/1.0",
    )
    same_normalized = RemediationAgent._signature_for_plan(
        plan,
        workflow_name="ci",
        head_branch="main",
    )

    assert base != with_context
    assert with_context != other_workflow
    assert with_context != other_branch
    assert with_context == same_normalized


@pytest.mark.asyncio
async def test_create_issue_reuses_existing_issue_by_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = RemediationPlan(
        action=RemediationAction.CREATE_ISSUE,
        description="Escalate for manual fix",
        issue_title="[PipelineHealer] Review required: lint",
        issue_body="Root cause summary",
    )
    signature = RemediationAgent._signature_for_plan(
        plan,
        workflow_name="CI",
        head_branch="main",
    )
    gh = FakeGitHubToolsExistingSignatureIssue(signature)
    agent = RemediationAgent(github_tools=gh)

    result = await agent._create_issue(
        plan,
        owner="octo",
        repo="demo",
        workflow_run_id=321,
        repository_info={
            "workflow_name": "CI",
            "head_branch": "main",
            "pull_request_numbers": [],
        },
    )

    assert result.success is True
    assert result.details.get("reused_existing_issue") is True
    assert result.details.get("issue_number") == 19
    assert gh.issue_calls == []


@pytest.mark.asyncio
async def test_create_issue_emits_signature_and_workflow_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGitHubTools()
    agent = RemediationAgent(github_tools=gh)
    plan = RemediationPlan(
        action=RemediationAction.CREATE_ISSUE,
        description="Escalate for manual fix",
        issue_title="[PipelineHealer] Review required: lint",
        issue_body="Root cause summary",
    )

    result = await agent._create_issue(
        plan,
        owner="octo",
        repo="demo",
        workflow_run_id=321,
        repository_info={
            "workflow_name": "CI",
            "head_branch": "main",
        },
    )

    assert result.success is True
    body = gh.issue_calls[0]["body"]
    assert "<!-- pipelinehealer:signature:" in body
    assert "<!-- pipelinehealer:workflow-name:ci -->" in body
    assert "<!-- pipelinehealer:head-branch:main -->" in body


@pytest.mark.asyncio
async def test_handle_successful_run_short_circuits_without_recent_issue_activity() -> None:
    storage = InMemoryStorage()
    gh = FakeGitHubTools()
    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)
    orchestrator._settings.auto_close_on_workflow_success = True

    event = _make_event()
    event.workflow_run.conclusion = "success"

    result = await orchestrator.handle_successful_run(event)

    assert result["status"] == "skipped"
    assert "no recent PipelineHealer review issues" in result["reason"]


@pytest.mark.asyncio
async def test_handle_successful_run_closes_when_recent_issue_activity_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = InMemoryStorage()
    gh = FakeGitHubToolsOpenReviewIssues()
    orchestrator = OrchestratorAgent(github_tools=gh, storage=storage)
    orchestrator._settings.auto_close_on_workflow_success = True
    orchestrator._settings.auto_apply_remediation = True

    await storage.create_activity(
        ActivityRecord(
            id="issue-activity",
            repositoryId="1",
            repository_name="octo/demo",
            workflow_run_id=100,
            workflow_name="CI",
            status=RemediationStatus.COMPLETED,
            remediation_result=RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_ISSUE,
                issue_url="https://github.com/octo/demo/issues/12",
            ),
        )
    )

    event = _make_event()
    event.workflow_run.conclusion = "success"
    event.workflow_run.id = 456

    result = await orchestrator.handle_successful_run(event)

    assert result["status"] == "completed"
    assert result["closed_issue_numbers"] == [12]
