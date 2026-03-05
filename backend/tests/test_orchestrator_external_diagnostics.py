"""Tests for orchestrator passive external diagnostics polling behavior."""

import asyncio

import pytest

from src.agents.orchestrator import (
    OrchestratorAgent,
    _build_external_diagnostics_poll_delays,
)
from src.config import reset_settings
from src.models import (
    ActivityRecord,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    GitHubRepository,
    GitHubWorkflowRun,
    MCPModelPath,
    RemediationStatus,
    WorkflowRunEvent,
)
from src.storage import InMemoryStorage
from src.tools.gh_aw_adapter import (
    KNOWN_ISSUE_SOURCES,
    DiagnosticSourceConfig,
    GHAWCapability,
)

_CI_DOCTOR_SOURCE = next(s for s in KNOWN_ISSUE_SOURCES if s.name == "ci-doctor")


def _event() -> WorkflowRunEvent:
    return WorkflowRunEvent(
        action="completed",
        workflow_run=GitHubWorkflowRun(
            id=4242,
            workflow_id=77,
            name="CI",
            head_branch="main",
            head_sha="abcdef1234567890",
            status="completed",
            conclusion="failure",
            html_url="https://github.com/Canepro/repo/actions/runs/4242",
            created_at="2026-02-15T00:00:00Z",
            updated_at="2026-02-15T00:01:00Z",
            run_number=7,
            run_attempt=1,
        ),
        repository=GitHubRepository(
            id=1,
            name="repo",
            full_name="Canepro/repo",
            owner={"login": "Canepro"},
            html_url="https://github.com/Canepro/repo",
        ),
        sender={"login": "github-actions[bot]"},
    )


def _activity() -> ActivityRecord:
    return ActivityRecord(
        repositoryId="1",
        repository_name="Canepro/repo",
        workflow_run_id=4242,
        workflow_name="CI",
        status=RemediationStatus.PENDING,
    )


class _DummyGitHubTools:
    async def get_workflow_run(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return {}

    async def get_workflow_jobs(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return []

    async def get_recent_commits(self, owner: str, repo: str, since: str | None = None, per_page: int = 10):
        _ = owner, repo, since, per_page
        return []

    def refresh_runtime_settings(self) -> None:
        return None


class _MCPGitHubTools(_DummyGitHubTools):
    async def get_workflow_run(self, owner: str, repo: str, run_id: int):
        _ = owner, repo
        return {
            "id": run_id,
            "html_url": f"https://github.com/Canepro/repo/actions/runs/{run_id}",
            "run_attempt": 1,
            "pull_requests": [
                {"number": 12},
            ],
        }

    async def get_workflow_jobs(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return [
            {"id": 1, "name": "test", "conclusion": "failure"},
            {"id": 2, "name": "lint", "conclusion": "success"},
        ]

    async def get_check_run_annotations(self, owner: str, repo: str, check_run_id: int):
        _ = owner, repo, check_run_id
        return []


class _RunnerAcquisitionGitHubTools(_DummyGitHubTools):
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
            {"id": 101, "name": "Frontend Lint and Build", "conclusion": "cancelled"},
            {"id": 102, "name": "Version Sync", "conclusion": "cancelled"},
        ]

    async def get_check_run_annotations(self, owner: str, repo: str, check_run_id: int):
        _ = owner, repo, check_run_id
        return [
            {
                "message": "The job was not acquired by Runner of type hosted even after multiple attempts"
            }
        ]


class _UnavailableAdapter:
    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        return GHAWCapability(repo_full_name="Canepro/repo", is_available=False, reason="missing")

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha, run_number, sources
        return []


class _EventuallyAvailableAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        return GHAWCapability(
            repo_full_name="Canepro/repo",
            is_available=True,
            available_sources=[_CI_DOCTOR_SOURCE],
        )

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha, run_number, sources
        self.calls += 1
        if self.calls < 2:
            return []
        return [
            ExternalDiagnostic(
                source="ci-doctor",
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary="found",
                matched_run_id=run_id,
            )
        ]


class _AlwaysAvailableAdapter:
    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        return GHAWCapability(
            repo_full_name="Canepro/repo",
            is_available=True,
            available_sources=[_CI_DOCTOR_SOURCE],
        )

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, head_sha, run_number, sources
        return [
            ExternalDiagnostic(
                source="ci-doctor",
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary="ci-doctor finding",
                matched_run_id=run_id,
            )
        ]


class _NeverAvailableAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        return GHAWCapability(
            repo_full_name="Canepro/repo",
            is_available=True,
            available_sources=[_CI_DOCTOR_SOURCE],
        )

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha, run_number, sources
        self.calls += 1
        return []


class _TransientErrorThenAvailableAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        return GHAWCapability(
            repo_full_name="Canepro/repo",
            is_available=True,
            available_sources=[_CI_DOCTOR_SOURCE],
        )

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha, run_number, sources
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        return [
            ExternalDiagnostic(
                source="ci-doctor",
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary="found after transient error",
                matched_run_id=run_id,
            )
        ]


class _SkipListAdapter:
    """Returns ci-doctor as available source so discovery succeeds,
    but collect should never be called when the skip list triggers."""

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        return GHAWCapability(
            repo_full_name="Canepro/repo",
            is_available=True,
            available_sources=[_CI_DOCTOR_SOURCE],
        )

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha, run_number, sources
        raise AssertionError("collect should not be called for skipped ci-doctor")


class _ShouldNotCallAdapter:
    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        raise AssertionError("gh-aw adapter should not be called in MCP-only mode")

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha, run_number, sources
        raise AssertionError("gh-aw adapter should not be called in MCP-only mode")


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PH_ALLOWED_REPOS", raising=False)
    monkeypatch.delenv("MCP_REPO_ALLOWLIST", raising=False)
    reset_settings()
    yield
    reset_settings()


@pytest.mark.asyncio
async def test_collect_external_diagnostics_reports_capability_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    orchestrator._gh_aw_adapter = _UnavailableAdapter()  # type: ignore[assignment]

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert diagnostics[0].metadata.get("reason_code") == "capability_unavailable"
    assert diagnostics[0].metadata.get("source_selection_path") == "gh_aw_passive"
    assert diagnostics[0].metadata.get("source_selection_reason") == "capability_unavailable"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_skips_known_gh_aw_workflow(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    monkeypatch.setenv(
        "GH_AW_KNOWN_WORKFLOWS",
        "ci-doctor,schema-consistency-checker,breaking-change-checker",
    )
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    orchestrator._gh_aw_adapter = _SkipListAdapter()  # type: ignore[assignment]
    event = _event()
    event.workflow_run.name = "Schema Consistency Checker"

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", event, _activity())
    # ci-doctor is the only source; when the skip list triggers,
    # the orchestrator records a skip diagnostic without calling collect.
    skip_diags = [d for d in diagnostics if d.metadata.get("reason_code") == "skip_known_gh_aw_workflow"]
    assert len(skip_diags) == 1
    assert skip_diags[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert skip_diags[0].metadata.get("workflow_identifier") == "schema-consistency-checker"
    assert skip_diags[0].metadata.get("source_selection_path") == "gh_aw_passive"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_uses_bounded_polling(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    adapter = _EventuallyAvailableAdapter()
    orchestrator._gh_aw_adapter = adapter  # type: ignore[assignment]

    async def no_sleep(delay: float) -> None:
        _ = delay
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_collect_external_diagnostics_final_fetch_before_timeout(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    adapter = _NeverAvailableAdapter()
    orchestrator._gh_aw_adapter = adapter  # type: ignore[assignment]

    async def no_sleep(delay: float) -> None:
        _ = delay
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())

    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert diagnostics[0].metadata.get("reason_code") == "poll_window_exhausted"
    expected_delays = _build_external_diagnostics_poll_delays(
        wait_budget_seconds=orchestrator._settings.external_diagnostics_wait_seconds,
        poll_interval_seconds=orchestrator._settings.external_diagnostics_poll_interval_seconds,
    )
    # Initial attempt + each scheduled delay attempt + final immediate fetch.
    assert adapter.calls == len((0.0, *expected_delays)) + 1


@pytest.mark.asyncio
async def test_collect_external_diagnostics_uses_configurable_wait_budget(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_WAIT_SECONDS", "30")
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS", "10")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    adapter = _NeverAvailableAdapter()
    orchestrator._gh_aw_adapter = adapter  # type: ignore[assignment]

    async def no_sleep(delay: float) -> None:
        _ = delay
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert diagnostics[0].metadata.get("poll_delays_seconds") == [10.0, 10.0, 10.0]
    # Initial attempt + 3 bounded retries + final immediate read.
    assert adapter.calls == 5


@pytest.mark.asyncio
async def test_collect_external_diagnostics_wait_zero_is_async_first(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_WAIT_SECONDS", "0")
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS", "15")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    adapter = _NeverAvailableAdapter()
    orchestrator._gh_aw_adapter = adapter  # type: ignore[assignment]

    sleep_calls: list[float] = []

    async def track_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        return None

    monkeypatch.setattr(asyncio, "sleep", track_sleep)

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert diagnostics[0].metadata.get("poll_delays_seconds") == []
    # Initial attempt + final immediate read only.
    assert adapter.calls == 2
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_collect_external_diagnostics_retries_after_transient_error(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    adapter = _TransientErrorThenAvailableAdapter()
    orchestrator._gh_aw_adapter = adapter  # type: ignore[assignment]

    async def no_sleep(delay: float) -> None:
        _ = delay
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_collect_external_diagnostics_uses_github_mcp_without_gh_aw(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "canepro/repo")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "false")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "disabled")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_MCPGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    orchestrator._gh_aw_adapter = _ShouldNotCallAdapter()  # type: ignore[assignment]

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.source == "github-mcp"
    assert diagnostic.status == ExternalDiagnosticStatus.AVAILABLE
    assert diagnostic.confidence_delta > 0
    assert diagnostic.metadata.get("reason_code") == "github_mcp_context"
    assert diagnostic.metadata.get("source_selection_path") == "github_mcp_direct"
    assert diagnostic.metadata.get("source_selection_reason") == "gh_aw_passive_disabled"
    assert diagnostic.metadata.get("failed_jobs_count") == 1
    assert diagnostic.metadata.get("changed_files") == []
    assert isinstance(diagnostic.metadata.get("details"), dict)


@pytest.mark.asyncio
async def test_collect_external_diagnostics_surfaces_runner_acquisition_failures(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "canepro/repo")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "false")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "disabled")
    reset_settings()

    orchestrator = OrchestratorAgent(
        github_tools=_RunnerAcquisitionGitHubTools(),
        storage=InMemoryStorage(),
    )  # type: ignore[arg-type]
    orchestrator._gh_aw_adapter = _ShouldNotCallAdapter()  # type: ignore[assignment]

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    runner_diag = next(
        diag for diag in diagnostics if diag.metadata.get("reason_code") == "github_runner_acquisition_failed"
    )
    assert runner_diag.status == ExternalDiagnosticStatus.AVAILABLE
    assert "Frontend Lint and Build" in runner_diag.summary
    assert runner_diag.metadata.get("failed_jobs") == ["Frontend Lint and Build", "Version Sync"]
    assert runner_diag.metadata.get("messages") == [
        "The job was not acquired by Runner of type hosted even after multiple attempts"
    ]


@pytest.mark.asyncio
async def test_collect_external_diagnostics_hybrid_includes_gh_aw_and_mcp(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "canepro/repo")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "hybrid")
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_WAIT_SECONDS", "0")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_MCPGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    orchestrator._gh_aw_adapter = _AlwaysAvailableAdapter()  # type: ignore[assignment]

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), _activity())
    sources = {diag.source for diag in diagnostics}
    assert "ci-doctor" in sources
    assert "github-mcp" in sources
    gh_aw_diag = next(diag for diag in diagnostics if diag.source == "ci-doctor")
    mcp_diag = next(diag for diag in diagnostics if diag.source == "github-mcp")
    assert gh_aw_diag.metadata.get("source_selection_path") == "gh_aw_passive"
    assert mcp_diag.metadata.get("source_selection_path") == "github_mcp_direct"
    assert mcp_diag.metadata.get("source_selection_reason") == "hybrid_mode_enabled"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_hybrid_keeps_gh_aw_when_mcp_blocked(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "canepro/other-repo")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "hybrid")
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_WAIT_SECONDS", "0")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_MCPGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    activity = _activity()
    activity.mcp_model_path = MCPModelPath(
        provider="github",
        enabled=True,
        available=True,
        read_only=True,
        reason="ok",
    )
    orchestrator._gh_aw_adapter = _AlwaysAvailableAdapter()  # type: ignore[assignment]

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), activity)
    sources = {diag.source for diag in diagnostics}
    assert "ci-doctor" in sources
    blocked = next(diag for diag in diagnostics if diag.source == "github-mcp")
    assert blocked.status == ExternalDiagnosticStatus.UNAVAILABLE
    assert blocked.metadata.get("reason_code") == "repo_not_allowlisted"
    assert blocked.metadata.get("source_selection_path") == "github_mcp_blocked"
    assert blocked.metadata.get("source_selection_reason") == "hybrid_mode:repo_not_allowlisted"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_blocks_github_mcp_for_repo_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "canepro/another-repo")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "false")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "disabled")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_MCPGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    activity = _activity()
    activity.mcp_model_path = MCPModelPath(
        provider="github",
        enabled=True,
        available=True,
        read_only=True,
        reason="ok",
    )

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), activity)
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.source == "github-mcp"
    assert diagnostic.status == ExternalDiagnosticStatus.UNAVAILABLE
    assert diagnostic.metadata.get("reason_code") == "repo_not_allowlisted"
    assert diagnostic.metadata.get("source_selection_path") == "github_mcp_blocked"
    assert activity.mcp_model_path.action_audit[-1].result == "blocked:repo_not_allowlisted"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_records_mcp_action_audit(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MCP_REPO_ALLOWLIST", "canepro/repo")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "false")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "disabled")
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("MCP_MAX_RETRIES", "0")
    reset_settings()

    orchestrator = OrchestratorAgent(github_tools=_MCPGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    activity = _activity()
    activity.mcp_model_path = MCPModelPath(
        provider="github",
        enabled=True,
        available=True,
        read_only=True,
        reason="ok",
    )

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event(), activity)
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    action_audit = activity.mcp_model_path.action_audit
    assert action_audit
    assert action_audit[-1].tool == "fetch_failure_context"
    assert action_audit[-1].request_id == activity.id
