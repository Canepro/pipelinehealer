"""Tests for signed Jenkins bridge ingestion webhook."""

import hashlib
import hmac
import json
import time

import httpx
import pytest

from src.api import webhook as webhook_api
from src.config import reset_settings
from src.main import app


class _DummyBridgeWorkflow:
    def __init__(self) -> None:
        self.last_payload: dict[str, object] | None = None

    async def start_bridge_failure(self, payload, *, request_id=None):  # type: ignore[no-untyped-def]
        self.last_payload = {
            "repository": payload.repository,
            "delivery_id": payload.delivery_id,
            "request_id": request_id,
        }
        return "bridge-activity-123"


class _FlakyBridgeWorkflow:
    def __init__(self) -> None:
        self.calls = 0

    async def start_bridge_failure(self, payload, *, request_id=None):  # type: ignore[no-untyped-def]
        _ = payload, request_id
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient enqueue failure")
        return "bridge-activity-retry-ok"


def _bridge_payload(delivery_id: str = "jenkins:job/path#1234") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "provider": "jenkins",
        "delivery_id": delivery_id,
        "sent_at": "2026-03-04T10:10:10Z",
        "repository": "canepro/pipelinehealer-demo",
        "branch": "main",
        "commit_sha": "a" * 40,
        "job": {
            "name": "security-validation",
            "url": "https://jenkins.example/job/security-validation/23/",
            "build_number": 23,
            "result": "FAILURE",
            "duration_ms": 1000,
        },
        "failure": {
            "stage": "Trivy Scan",
            "step": "run-trivy",
            "command": "trivy image ...",
            "summary": "Critical vulnerabilities found",
            "log_excerpt": "critical vulnerability threshold exceeded",
        },
        "artifacts": [],
        "metadata": {"jenkins_instance": "jenkins.example"},
    }


def _sign_bridge_payload(
    *,
    body: bytes,
    timestamp: str,
    nonce: str,
    secret: str,
) -> str:
    canonical = webhook_api._build_jenkins_canonical_string(  # noqa: SLF001
        method="POST",
        path="/webhook/jenkins",
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture(autouse=True)
def _reset_bridge_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JENKINS_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("JENKINS_BRIDGE_SHARED_SECRET", "bridge-secret")
    monkeypatch.setenv("PH_ALLOWED_REPOS", "canepro/pipelinehealer-demo")
    reset_settings()
    webhook_api._jenkins_nonce_replay.clear()  # noqa: SLF001
    webhook_api._jenkins_delivery_replay.clear()  # noqa: SLF001
    app.state.workflow = _DummyBridgeWorkflow()  # type: ignore[assignment]
    yield
    webhook_api._jenkins_nonce_replay.clear()  # noqa: SLF001
    webhook_api._jenkins_delivery_replay.clear()  # noqa: SLF001
    reset_settings()


@pytest.mark.asyncio
async def test_jenkins_bridge_accepts_valid_signed_payload() -> None:
    payload = _bridge_payload()
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = "nonce-1"
    signature = _sign_bridge_payload(
        body=body,
        timestamp=timestamp,
        nonce=nonce,
        secret="bridge-secret",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": nonce,
                "X-PH-Bridge-Signature": signature,
            },
        )

    assert response.status_code == 200
    body_json = response.json()
    assert body_json["status"] == "processing"
    assert body_json["source"] == "jenkins_bridge"
    assert body_json["activity_id"] == "bridge-activity-123"


@pytest.mark.asyncio
async def test_jenkins_bridge_rejects_invalid_signature() -> None:
    payload = _bridge_payload()
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": "nonce-invalid-signature",
                "X-PH-Bridge-Signature": "sha256=bad",
            },
        )

    assert response.status_code == 401
    assert "Invalid bridge signature" in response.text


@pytest.mark.asyncio
async def test_jenkins_bridge_ignores_duplicate_nonce() -> None:
    payload = _bridge_payload()
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = "nonce-duplicate"
    signature = _sign_bridge_payload(
        body=body,
        timestamp=timestamp,
        nonce=nonce,
        secret="bridge-secret",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": nonce,
                "X-PH-Bridge-Signature": signature,
            },
        )
        second = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": nonce,
                "X-PH-Bridge-Signature": signature,
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "ignored"
    assert second.json()["reason"] == "duplicate_nonce"


@pytest.mark.asyncio
async def test_jenkins_bridge_rejects_empty_nonce_header() -> None:
    payload = _bridge_payload()
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = _sign_bridge_payload(
        body=body,
        timestamp=timestamp,
        nonce="",
        secret="bridge-secret",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": "   ",
                "X-PH-Bridge-Signature": signature,
            },
        )

    assert response.status_code == 422
    assert "Missing bridge nonce header" in response.text


@pytest.mark.asyncio
async def test_jenkins_bridge_allows_retry_after_enqueue_failure() -> None:
    payload = _bridge_payload()
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = "nonce-retry-after-failure"
    signature = _sign_bridge_payload(
        body=body,
        timestamp=timestamp,
        nonce=nonce,
        secret="bridge-secret",
    )

    app.state.workflow = _FlakyBridgeWorkflow()  # type: ignore[assignment]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": nonce,
                "X-PH-Bridge-Signature": signature,
            },
        )
        second = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": nonce,
                "X-PH-Bridge-Signature": signature,
            },
        )

    assert first.status_code == 500
    assert second.status_code == 200
    assert second.json()["status"] == "processing"
    assert second.json()["activity_id"] == "bridge-activity-retry-ok"


@pytest.mark.asyncio
async def test_jenkins_bridge_enforces_repo_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PH_ALLOWED_REPOS", "canepro/other-repo")
    reset_settings()
    payload = _bridge_payload()
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = "nonce-allowlist"
    signature = _sign_bridge_payload(
        body=body,
        timestamp=timestamp,
        nonce=nonce,
        secret="bridge-secret",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhook/jenkins",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PH-Bridge-Provider": "jenkins",
                "X-PH-Bridge-Timestamp": timestamp,
                "X-PH-Bridge-Nonce": nonce,
                "X-PH-Bridge-Signature": signature,
            },
        )

    assert response.status_code == 403


def test_cleanup_replay_store_caps_entry_count() -> None:
    now = time.time()
    max_entries = webhook_api._JENKINS_REPLAY_MAX_ENTRIES  # noqa: SLF001
    for i in range(max_entries + 7):
        webhook_api._jenkins_nonce_replay[f"nonce-{i}"] = now
        webhook_api._jenkins_delivery_replay[f"delivery-{i}"] = now

    webhook_api._cleanup_replay_store(now, ttl_seconds=86400)  # noqa: SLF001

    assert len(webhook_api._jenkins_nonce_replay) <= max_entries  # noqa: SLF001
    assert len(webhook_api._jenkins_delivery_replay) <= max_entries  # noqa: SLF001
