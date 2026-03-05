"""Tests for Assign-to-Agent API integration."""

import httpx
import pytest

from src.config import reset_settings
from src.main import app
from src.models import ActivityRecord, RemediationStatus
from src.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def _runtime_auth_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    reset_settings()
    yield
    reset_settings()


async def _get_handoff_config() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/agent-handoff/config")


async def _post_handoff(
    activity_id: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            f"/api/activities/{activity_id}/agent-handoff",
            json=payload,
            headers=headers or {},
        )


@pytest.fixture
async def _storage() -> InMemoryStorage:
    reset_settings()
    storage = InMemoryStorage()
    await storage.initialize()
    app.state.storage = storage
    yield storage
    reset_settings()
    app.state.storage = InMemoryStorage()


@pytest.mark.asyncio
async def test_handoff_config_defaults_to_disabled(monkeypatch: pytest.MonkeyPatch, _storage: InMemoryStorage) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "false")
    reset_settings()
    response = await _get_handoff_config()
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["reason"] == "disabled_by_runtime"


@pytest.mark.asyncio
async def test_copy_only_handoff_records_redacted_audit(
    monkeypatch: pytest.MonkeyPatch,
    _storage: InMemoryStorage,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "copy_only")
    reset_settings()

    activity = ActivityRecord(
        repositoryId="1",
        repository_name="canepro/pipelinehealer-demo",
        workflow_run_id=123,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
    )
    activity_id = await _storage.create_activity(activity)

    response = await _post_handoff(
        activity_id,
        {
            "context": "Authorization: Bearer secret-token-value\napi_key=supersecret123456",
            "context_format": "markdown",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "copied"

    updated = await _storage.get_activity(activity_id)
    assert updated is not None
    assert len(updated.agent_handoff_audit) == 1
    audit = updated.agent_handoff_audit[0]
    assert audit.status.value == "copied"
    assert "[REDACTED_TOKEN]" in audit.context_preview or "[REDACTED]" in audit.context_preview


@pytest.mark.asyncio
async def test_webhook_handoff_blocks_non_allowlisted_host(
    monkeypatch: pytest.MonkeyPatch,
    _storage: InMemoryStorage,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://blocked.example/hook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_ALLOWLIST", "allowed.example")
    reset_settings()

    activity = ActivityRecord(
        repositoryId="1",
        repository_name="canepro/pipelinehealer-demo",
        workflow_run_id=124,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
    )
    activity_id = await _storage.create_activity(activity)
    response = await _post_handoff(activity_id, {"context": "context text"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "not allowlisted" in body["message"]


@pytest.mark.asyncio
async def test_webhook_handoff_success_returns_queued(
    monkeypatch: pytest.MonkeyPatch,
    _storage: InMemoryStorage,
) -> None:
    from src.api import dashboard

    async def _fake_deliver(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return True, None

    monkeypatch.setattr(dashboard, "_deliver_handoff_webhook", _fake_deliver)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://allowed.example/hook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_ALLOWLIST", "allowed.example")
    reset_settings()

    activity = ActivityRecord(
        repositoryId="1",
        repository_name="canepro/pipelinehealer-demo",
        workflow_run_id=125,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
    )
    activity_id = await _storage.create_activity(activity)
    response = await _post_handoff(activity_id, {"context": "context text"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["delivery_id"].startswith("handoff:")


@pytest.mark.asyncio
async def test_handoff_actor_does_not_trust_raw_admin_key_header(
    monkeypatch: pytest.MonkeyPatch,
    _storage: InMemoryStorage,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "copy_only")
    reset_settings()

    activity = ActivityRecord(
        repositoryId="1",
        repository_name="canepro/pipelinehealer-demo",
        workflow_run_id=126,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
    )
    activity_id = await _storage.create_activity(activity)
    response = await _post_handoff(
        activity_id,
        {"context": "context text"},
        headers={"X-Admin-Key": "spoofed-value"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "copied"

    updated = await _storage.get_activity(activity_id)
    assert updated is not None
    assert len(updated.agent_handoff_audit) == 1
    assert updated.agent_handoff_audit[0].actor == "api_client"
