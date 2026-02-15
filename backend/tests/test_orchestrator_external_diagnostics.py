"""Tests for orchestrator passive external diagnostics polling behavior."""

import asyncio

import pytest

from src.agents.orchestrator import (
    OrchestratorAgent,
    _EXTERNAL_DIAGNOSTICS_POLL_DELAYS_SECONDS,
)
from src.config import get_settings
from src.models import (
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    GitHubRepository,
    GitHubWorkflowRun,
    WorkflowRunEvent,
)
from src.storage import InMemoryStorage
from src.tools.gh_aw_adapter import GHAWCapability


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
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha
        return []


class _EventuallyAvailableAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        _ = owner, repo
        return GHAWCapability(repo_full_name="Canepro/repo", is_available=True)

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha
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
        return GHAWCapability(repo_full_name="Canepro/repo", is_available=True)

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
    ) -> list[ExternalDiagnostic]:
        _ = owner, repo, run_id, head_sha
        self.calls += 1
        return []


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_collect_external_diagnostics_reports_capability_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    get_settings.cache_clear()

    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=InMemoryStorage())  # type: ignore[arg-type]
    orchestrator._gh_aw_adapter = _UnavailableAdapter()  # type: ignore[assignment]

    diagnostics = await orchestrator._collect_external_diagnostics("Canepro", "repo", _event())
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.UNAVAILABLE
    assert diagnostics[0].metadata.get("reason_code") == "capability_unavailable"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_uses_bounded_polling(monkeypatch) -> None:
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    get_settings.cache_clear()

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
    get_settings.cache_clear()

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
    # Initial attempt + each scheduled delay attempt + final immediate fetch.
    assert adapter.calls == len((0.0, *_EXTERNAL_DIAGNOSTICS_POLL_DELAYS_SECONDS)) + 1
