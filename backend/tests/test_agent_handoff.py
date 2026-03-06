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


async def _get_handoff_integration_status() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/agent-handoff/integration-status")


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
async def test_handoff_integration_status_reports_copy_only_mode(
    monkeypatch: pytest.MonkeyPatch, _storage: InMemoryStorage
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "copy_only")
    reset_settings()

    response = await _get_handoff_integration_status()
    assert response.status_code == 200
    body = response.json()
    assert body["receiver_status"] == "not_required"
    assert body["reason"] == "copy_only_mode"


@pytest.mark.asyncio
async def test_handoff_integration_status_reports_receiver_health(
    monkeypatch: pytest.MonkeyPatch, _storage: InMemoryStorage
) -> None:
    from src.api import dashboard

    async def _fake_probe(_health_url: str):  # type: ignore[no-untyped-def]
        return dashboard.NotificationTargetHealthView(
            configured_targets=2,
            enabled_targets=1,
            invalid_targets=1,
            supported_target_types=["webhook", "slack_webhook", "email"],
            errors=["target 2: invalid"],
        )

    monkeypatch.setattr(dashboard, "_probe_agent_handoff_receiver_health", _fake_probe)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://receiver.example/api/agent-handoff")
    reset_settings()

    response = await _get_handoff_integration_status()
    assert response.status_code == 200
    body = response.json()
    assert body["receiver_status"] == "degraded"
    assert body["reason"] == "invalid_notification_targets"
    assert body["receiver_health_url"] == "https://receiver.example/api/healthz"
    assert body["notifications"]["configured_targets"] == 2
    assert body["notifications"]["invalid_targets"] == 1
    assert "email" in body["notifications"]["supported_target_types"]


@pytest.mark.asyncio
async def test_handoff_integration_status_handles_receiver_probe_failure(
    monkeypatch: pytest.MonkeyPatch, _storage: InMemoryStorage
) -> None:
    from src.api import dashboard

    async def _failing_probe(health_url: str):  # type: ignore[no-untyped-def]
        request = httpx.Request("GET", health_url)
        raise httpx.ConnectError("network down", request=request)

    monkeypatch.setattr(dashboard, "_probe_agent_handoff_receiver_health", _failing_probe)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://receiver.example/api/agent-handoff")
    reset_settings()

    response = await _get_handoff_integration_status()
    assert response.status_code == 200
    body = response.json()
    assert body["receiver_status"] == "unreachable"
    assert body["reason"] == "receiver_probe_failed"


@pytest.mark.asyncio
async def test_handoff_integration_status_redacts_basic_auth_from_health_url(
    monkeypatch: pytest.MonkeyPatch, _storage: InMemoryStorage
) -> None:
    from src.api import dashboard

    async def _fake_probe(_health_url: str):  # type: ignore[no-untyped-def]
        return dashboard.NotificationTargetHealthView(
            configured_targets=0,
            enabled_targets=0,
            invalid_targets=0,
            supported_target_types=["webhook"],
            errors=[],
        )

    monkeypatch.setattr(dashboard, "_probe_agent_handoff_receiver_health", _fake_probe)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv(
        "AGENT_HANDOFF_WEBHOOK_URL",
        "https://user:secret@receiver.example/api/agent-handoff",
    )
    reset_settings()

    response = await _get_handoff_integration_status()
    assert response.status_code == 200
    body = response.json()
    assert body["receiver_health_url"] == "https://receiver.example/api/healthz"


@pytest.mark.asyncio
async def test_handoff_integration_status_respects_allowlist_before_probe(
    monkeypatch: pytest.MonkeyPatch, _storage: InMemoryStorage
) -> None:
    from src.api import dashboard

    async def _unexpected_probe(_health_url: str):  # type: ignore[no-untyped-def]
        raise AssertionError("probe should not run for non-allowlisted host")

    monkeypatch.setattr(dashboard, "_probe_agent_handoff_receiver_health", _unexpected_probe)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://blocked.example/api/agent-handoff")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_ALLOWLIST", "allowed.example")
    reset_settings()

    response = await _get_handoff_integration_status()
    assert response.status_code == 200
    body = response.json()
    assert body["receiver_status"] == "invalid_configuration"
    assert body["reason"] == "destination_not_allowlisted"


@pytest.mark.asyncio
async def test_handoff_integration_status_handles_malformed_notification_lists(
    monkeypatch: pytest.MonkeyPatch, _storage: InMemoryStorage
) -> None:
    from src.api import dashboard

    async def _fake_probe(_health_url: str):  # type: ignore[no-untyped-def]
        raise ValueError("receiver notifications.supported_target_types must be a list")

    monkeypatch.setattr(dashboard, "_probe_agent_handoff_receiver_health", _fake_probe)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://receiver.example/api/agent-handoff")
    reset_settings()

    response = await _get_handoff_integration_status()
    assert response.status_code == 200
    body = response.json()
    assert body["receiver_status"] == "unreachable"
    assert body["reason"] == "receiver_probe_failed"


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

    captured_payload: dict[str, object] = {}

    async def _fake_deliver(**kwargs):  # type: ignore[no-untyped-def]
        captured_payload.update(kwargs["payload"])
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
    summary = captured_payload["summary"]
    assert summary["root_cause"] == ""
    assert summary["activity_url"] is None


@pytest.mark.asyncio
async def test_webhook_handoff_payload_includes_summary_and_activity_link(
    monkeypatch: pytest.MonkeyPatch,
    _storage: InMemoryStorage,
) -> None:
    from src.api import dashboard
    from src.models import Diagnosis, FailureType, RemediationAction, RemediationResult

    captured_payload: dict[str, object] = {}

    async def _fake_deliver(**kwargs):  # type: ignore[no-untyped-def]
        captured_payload.update(kwargs["payload"])
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
        workflow_run_id=126,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
        failure_type=FailureType.DEPENDENCY,
        diagnosis=Diagnosis(
            failure_type=FailureType.DEPENDENCY,
            confidence=0.92,
            root_cause="left-pad dependency is missing from package.json",
            suggested_fix="Add left-pad to dependencies and rebuild the lockfile.",
        ),
        remediation_result=RemediationResult(
            success=True,
            action_taken=RemediationAction.CREATE_ISSUE,
            issue_url="https://github.com/Canepro/pipelinehealer/issues/999",
        ),
    )
    activity_id = await _storage.create_activity(activity)
    response = await _post_handoff(
        activity_id,
        {"context": "context text"},
        headers={"Origin": "https://frontend.example"},
    )
    assert response.status_code == 200

    summary = captured_payload["summary"]
    assert summary["activity_url"] == f"https://frontend.example/app/activities/{activity_id}"
    assert summary["root_cause"] == "left-pad dependency is missing from package.json"
    assert summary["suggested_fix"] == "Add left-pad to dependencies and rebuild the lockfile."
    assert summary["remediation_action"] == "create_issue"
    assert summary["issue_url"] == "https://github.com/Canepro/pipelinehealer/issues/999"


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
