"""Tests for the webhook handler."""

import hashlib
import hmac
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.api.webhook import verify_github_signature


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

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = TestClient(app)

    def test_ping_event(self) -> None:
        """Test handling of ping events."""
        response = self.client.post(
            "/webhook/github",
            json={"zen": "test"},
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "test-delivery-id",
            },
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "pong"

    def test_ignored_event_type(self) -> None:
        """Test that non-workflow_run events are ignored."""
        response = self.client.post(
            "/webhook/github",
            json={"action": "opened"},
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "test-delivery-id",
            },
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_health_check(self) -> None:
        """Test the health check endpoint."""
        response = self.client.get("/webhook/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
