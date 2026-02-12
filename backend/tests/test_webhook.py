"""Tests for the webhook handler."""

import hashlib
import hmac

import httpx
import pytest

from src.api.webhook import verify_github_signature
from src.config import get_settings
from src.main import app


class TestGitHubSignatureVerification:
    """Test GitHub webhook signature verification."""

    def test_valid_signature(self) -> None:
        """Test that valid signatures are accepted."""
        secret = "test-secret"
        payload = b'{"action": "completed"}'

        expected_sig = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        signature = f"sha256={expected_sig}"

        assert verify_github_signature(payload, signature, secret) is True

    def test_invalid_signature(self) -> None:
        """Test that invalid signatures are rejected."""
        secret = "test-secret"
        payload = b'{"action": "completed"}'
        signature = "sha256=invalid"

        assert verify_github_signature(payload, signature, secret) is False

    def test_missing_signature_prefix(self) -> None:
        """Test that signatures without sha256= prefix are rejected."""
        secret = "test-secret"
        payload = b'{"action": "completed"}'
        signature = "abc123"

        assert verify_github_signature(payload, signature, secret) is False

    def test_empty_signature(self) -> None:
        """Test that empty signatures are rejected."""
        secret = "test-secret"
        payload = b'{"action": "completed"}'

        assert verify_github_signature(payload, "", secret) is False


class TestWebhookEndpoint:
    """Test the webhook endpoint."""

    @pytest.fixture(autouse=True)
    def _default_webhook_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ensure baseline webhook policy for tests is explicit and stable."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "true")
        monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT", "false")
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_ping_event(self) -> None:
        """Test handling of ping events."""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/webhook/github",
                json={"zen": "test"},
                headers={
                    "X-GitHub-Event": "ping",
                    "X-GitHub-Delivery": "test-delivery-id",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "pong"

    @pytest.mark.asyncio
    async def test_ignored_event_type(self) -> None:
        """Test that non-workflow_run events are ignored."""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/webhook/github",
                json={"action": "opened"},
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": "test-delivery-id",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        """Test the health check endpoint."""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/webhook/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
