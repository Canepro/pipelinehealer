"""Tests for external diagnostics backfill sweep."""

import asyncio

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.config import get_settings, reset_settings
from src.models import (
    ActivityRecord,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    RemediationStatus,
    utcnow,
)
from src.storage import InMemoryStorage
from src.tools.gh_aw_adapter import GHAWCapability
from src.workflows.pipeline_healer import PipelineHealerWorkflow


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class _DummyGitHubTools:
    """Minimal stub satisfying the GitHubTools interface for backfill tests."""

    def __init__(self, run_details: dict | None = None) -> None:
        self._run_details = run_details or {
            "head_sha": "abc123",
            "run_number": 42,
        }

    async def get_workflow_run(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return dict(self._run_details)

    async def get_recent_commits(self, *a, **kw):
        return []

    async def close(self):
        pass

    def refresh_runtime_settings(self) -> None:
        return None


class _FindingsAvailableAdapter:
    """Adapter that always returns findings on collect."""

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        return GHAWCapability(repo_full_name=f"{owner}/{repo}", is_available=True)

    async def collect_external_diagnostics(
        self, owner, repo, run_id, head_sha, run_number=None
    ) -> list[ExternalDiagnostic]:
        return [
            ExternalDiagnostic(
                source="ci-doctor",
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary="Backfilled finding",
                matched_run_id=run_id,
                url="https://github.com/example/demo/issues/99",
                confidence_delta=0.08,
            )
        ]


class _NoFindingsAdapter:
    """Adapter that never has findings."""

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        return GHAWCapability(repo_full_name=f"{owner}/{repo}", is_available=True)

    async def collect_external_diagnostics(
        self, owner, repo, run_id, head_sha, run_number=None
    ) -> list[ExternalDiagnostic]:
        return []


class _ErrorAdapter:
    """Adapter that raises on collect."""

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        return GHAWCapability(repo_full_name=f"{owner}/{repo}", is_available=True)

    async def collect_external_diagnostics(
        self, owner, repo, run_id, head_sha, run_number=None
    ) -> list[ExternalDiagnostic]:
        raise RuntimeError("GitHub API down")


def _make_exhausted_activity(
    activity_id: str = "act-1",
    run_id: int = 9999,
    repo_name: str = "Canepro/demo",
) -> ActivityRecord:
    """Create a completed activity with poll_window_exhausted diagnostics."""
    return ActivityRecord(
        id=activity_id,
        repositoryId="123",
        repository_name=repo_name,
        workflow_run_id=run_id,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
        external_diagnostics=[
            ExternalDiagnostic(
                source="ci-doctor",
                status=ExternalDiagnosticStatus.UNAVAILABLE,
                summary="No ci-doctor findings published within bounded polling window",
                matched_run_id=run_id,
                metadata={
                    "reason_code": "poll_window_exhausted",
                    "poll_delays_seconds": [15, 30, 45, 60, 75, 90, 90, 75],
                },
            )
        ],
    )


def _build_orchestrator(adapter, github_tools=None, storage=None):
    settings = get_settings()
    storage = storage or InMemoryStorage()
    gt = github_tools or _DummyGitHubTools()
    orch = OrchestratorAgent(
        github_tools=gt,
        storage=storage,
        azure_credential=None,
    )
    # Inject adapter directly
    orch._gh_aw_adapter = adapter
    return orch, storage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_gh_aw(monkeypatch):
    """Enable gh-aw tools and passive ingestion for all tests in this module."""
    reset_settings()
    settings = get_settings()
    settings.gh_aw_tools_enabled = True
    settings.gh_aw_ingestion_mode = "passive"
    yield
    reset_settings()


# ---------------------------------------------------------------------------
# Tests: orchestrator.backfill_activity_diagnostics()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_replaces_exhausted_entry():
    """When ci-doctor findings are available, backfill replaces poll_window_exhausted."""
    orch, storage = _build_orchestrator(_FindingsAvailableAdapter())
    activity = _make_exhausted_activity()
    await storage.create_activity(activity)

    result = await orch.backfill_activity_diagnostics(activity)

    assert result is True
    updated = await storage.get_activity("act-1")
    assert updated is not None
    # poll_window_exhausted entry should be gone
    assert all(
        d.metadata.get("reason_code") != "poll_window_exhausted"
        for d in updated.external_diagnostics
    )
    # Real finding should be present
    assert len(updated.external_diagnostics) == 1
    assert updated.external_diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert updated.external_diagnostics[0].summary == "Backfilled finding"


@pytest.mark.asyncio
async def test_backfill_returns_false_when_no_findings():
    """When ci-doctor still has no findings, backfill returns False and doesn't change activity."""
    orch, storage = _build_orchestrator(_NoFindingsAdapter())
    activity = _make_exhausted_activity()
    await storage.create_activity(activity)

    result = await orch.backfill_activity_diagnostics(activity)

    assert result is False
    updated = await storage.get_activity("act-1")
    assert updated is not None
    # Original entry should still be there
    assert any(
        d.metadata.get("reason_code") == "poll_window_exhausted"
        for d in updated.external_diagnostics
    )


@pytest.mark.asyncio
async def test_backfill_returns_false_on_collection_error():
    """When collection raises, backfill returns False gracefully."""
    orch, storage = _build_orchestrator(_ErrorAdapter())
    activity = _make_exhausted_activity()
    await storage.create_activity(activity)

    result = await orch.backfill_activity_diagnostics(activity)
    assert result is False


@pytest.mark.asyncio
async def test_backfill_skips_when_gh_aw_disabled(monkeypatch):
    """When gh_aw_tools is disabled, backfill does nothing."""
    settings = get_settings()
    settings.gh_aw_tools_enabled = False

    orch, storage = _build_orchestrator(_FindingsAvailableAdapter())
    activity = _make_exhausted_activity()
    await storage.create_activity(activity)

    result = await orch.backfill_activity_diagnostics(activity)
    assert result is False


@pytest.mark.asyncio
async def test_backfill_skips_invalid_repo_name():
    """When repository_name has no slash, backfill returns False."""
    orch, _ = _build_orchestrator(_FindingsAvailableAdapter())
    activity = _make_exhausted_activity(repo_name="noslash")

    result = await orch.backfill_activity_diagnostics(activity)
    assert result is False


# ---------------------------------------------------------------------------
# Tests: storage.get_backfill_candidates()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_backfill_candidates_returns_qualifying():
    """InMemoryStorage returns activities with poll_window_exhausted."""
    storage = InMemoryStorage()
    # Qualifying
    a1 = _make_exhausted_activity(activity_id="a1", run_id=1001)
    await storage.create_activity(a1)
    # Non-qualifying: no exhausted diagnostics
    a2 = ActivityRecord(
        id="a2",
        repositoryId="123",
        repository_name="Canepro/demo",
        workflow_run_id=1002,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
        external_diagnostics=[],
    )
    await storage.create_activity(a2)
    # Non-qualifying: still pending
    a3 = _make_exhausted_activity(activity_id="a3", run_id=1003)
    a3.status = RemediationStatus.PENDING
    await storage.create_activity(a3)

    candidates = await storage.get_backfill_candidates(limit=10)
    assert len(candidates) == 1
    assert candidates[0].id == "a1"


# ---------------------------------------------------------------------------
# Tests: workflow.run_backfill_sweep()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_sweep_backfills_candidates():
    """Full sweep via PipelineHealerWorkflow finds and backfills candidates."""
    storage = InMemoryStorage()
    gt = _DummyGitHubTools()
    workflow = PipelineHealerWorkflow(
        github_tools=gt,
        storage=storage,
        azure_credential=None,
    )
    # Inject adapter into the orchestrator
    workflow._orchestrator._gh_aw_adapter = _FindingsAvailableAdapter()

    activity = _make_exhausted_activity()
    await storage.create_activity(activity)

    count = await workflow.run_backfill_sweep(max_age_hours=24.0)
    assert count == 1

    updated = await storage.get_activity("act-1")
    assert updated is not None
    assert updated.external_diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE


@pytest.mark.asyncio
async def test_workflow_sweep_returns_zero_when_no_candidates():
    """Sweep returns 0 when no activities need backfill."""
    storage = InMemoryStorage()
    gt = _DummyGitHubTools()
    workflow = PipelineHealerWorkflow(
        github_tools=gt,
        storage=storage,
        azure_credential=None,
    )
    count = await workflow.run_backfill_sweep()
    assert count == 0


@pytest.mark.asyncio
async def test_workflow_close_handles_running_task_callback_mutation():
    """workflow.close should not fail when done-callback mutates running task map."""
    storage = InMemoryStorage()
    gt = _DummyGitHubTools()
    workflow = PipelineHealerWorkflow(
        github_tools=gt,
        storage=storage,
        azure_credential=None,
    )

    async def _never_finishes() -> None:
        await asyncio.sleep(300)

    task = asyncio.create_task(_never_finishes())
    workflow._running_tasks["task-1"] = task
    task.add_done_callback(lambda _: workflow._running_tasks.pop("task-1", None))

    await workflow.close()
    assert workflow._running_tasks == {}
