"""Tests for orchestrator passive external diagnostics polling behavior."""

import asyncio

import pytest

from src.agents.orchestrator import (
    OrchestratorAgent,
    _build_external_diagnostics_poll_delays,
)
from src.config import reset_settings
from src.models import (
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    GitHubRepository,
    GitHubWorkflowRun,
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


class _DummyGitHubTools:
    async def get_workflow_run(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return {}

    async def get_recent_commits(self, owner: str, repo: str, since: str | None = None, per_page: int = 10):
        _ = owner, repo, since, per_page
        return []

    def refresh_runtime_settings(self) -> None:
        return None


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


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
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

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert diagnostics[0].metadata.get("reason_code") == "capability_unavailable"


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

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", event)
    # ci-doctor is the only source; when the skip list triggers,
    # the orchestrator records a skip diagnostic without calling collect.
    skip_diags = [d for d in diagnostics if d.metadata.get("reason_code") == "skip_known_gh_aw_workflow"]
    assert len(skip_diags) == 1
    assert skip_diags[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert skip_diags[0].metadata.get("workflow_identifier") == "schema-consistency-checker"


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

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event())
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

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event())

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

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event())
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

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event())
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

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert adapter.calls == 2
