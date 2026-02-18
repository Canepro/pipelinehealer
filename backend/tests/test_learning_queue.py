"""Learning queue API tests (0.2 governance slice)."""

import httpx
import pytest

from src.api import dashboard
from src.config import reset_settings
from src.main import app
from src.models import (
    ActivityRecord,
    Diagnosis,
    FailureType,
    RemediationAction,
    RemediationResult,
    RemediationStatus,
)
from src.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.setenv("API_AUTH_KEY", "api-key")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-key")
    dashboard.clear_admin_settings_audit()
    reset_settings()
    app.state.storage = InMemoryStorage()
    yield
    dashboard.clear_admin_settings_audit()
    reset_settings()


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": "api-key", "X-Admin-Key": "admin-key"}


async def _get_learning_queue() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings/learning/queue?limit=20", headers=_auth_headers())


async def _refresh_learning_queue() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/settings/learning/queue/refresh?lookback_hours=24&min_occurrences=2",
            headers=_auth_headers(),
        )


async def _decide(candidate_id: str, action: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            f"/api/settings/learning/queue/{candidate_id}/decision",
            headers=_auth_headers(),
            json={"action": action},
        )


@pytest.mark.asyncio
async def test_learning_queue_empty_by_default() -> None:
    response = await _get_learning_queue()
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_learning_queue_refresh_generates_candidate_for_repeated_success() -> None:
    storage = app.state.storage

    for index in (1, 2):
        activity = ActivityRecord(
            repositoryId="repo-1",
            repository_name="owner/repo",
            workflow_run_id=100 + index,
            workflow_name="CI",
            status=RemediationStatus.COMPLETED,
            failure_type=FailureType.BUILD_CONFIG,
            diagnosis=Diagnosis(
                failure_type=FailureType.BUILD_CONFIG,
                confidence=0.9,
                root_cause="Missing required environment variable",
                is_auto_fixable=False,
                suggested_fix="Add missing env var to workflow.",
                error_details={"reason_code": "REQUIRES_ENV_CONTEXT"},
            ),
            remediation_result=RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_ISSUE,
                details={"reason_code": "REQUIRES_ENV_CONTEXT"},
            ),
        )
        await storage.create_activity(activity)

    refreshed = await _refresh_learning_queue()
    assert refreshed.status_code == 200
    payload = refreshed.json()
    assert payload["generated_candidates"] >= 1
    assert payload["upserted_candidates"] >= 1

    queue = await _get_learning_queue()
    assert queue.status_code == 200
    items = queue.json()
    assert len(items) >= 1
    first = items[0]
    assert first["status"] == "candidate"
    assert first["failure_type"] == "build_config"
    assert first["occurrence_count"] >= 2


@pytest.mark.asyncio
async def test_learning_queue_decision_updates_status_and_is_audited() -> None:
    storage = app.state.storage
    for index in (1, 2):
        activity = ActivityRecord(
            repositoryId="repo-1",
            repository_name="owner/repo",
            workflow_run_id=200 + index,
            workflow_name="CI",
            status=RemediationStatus.COMPLETED,
            failure_type=FailureType.LINT,
            diagnosis=Diagnosis(
                failure_type=FailureType.LINT,
                confidence=0.88,
                root_cause="Lint config mismatch",
                is_auto_fixable=True,
                suggested_fix="Align lint config",
                error_details={"reason_code": "LINT_RULE_UPDATE"},
            ),
            remediation_result=RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_PR,
                details={"reason_code": "LINT_RULE_UPDATE"},
            ),
        )
        await storage.create_activity(activity)
    refreshed = await _refresh_learning_queue()
    assert refreshed.status_code == 200

    queue = await _get_learning_queue()
    candidate_id = queue.json()[0]["id"]

    decision = await _decide(candidate_id, "approve")
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    queue_after = await _get_learning_queue()
    assert queue_after.status_code == 200
    assert queue_after.json()[0]["status"] == "approved"

    audit = await storage.list_admin_settings_audit_entries(limit=5)
    assert any("learning_queue_decision" in item.get("changed_keys", []) for item in audit)
