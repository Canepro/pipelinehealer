"""Phase 2 security tests: API auth, webhook policy, and config parsing."""

import hashlib
import hmac

import httpx
import pytest

from src.api import dashboard
from src.config import Settings, get_settings
from src.main import app
from src.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _DummyWorkflow:
    def refresh_runtime_settings(self) -> None:
        return None


async def _get_activities(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/activities?limit=1", headers=headers or {})


async def _get_settings(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings", headers=headers or {})


async def _patch_settings(
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.patch("/api/settings", json=payload, headers=headers or {})


async def _post_ping(
    headers: dict[str, str] | None = None,
    raw_payload: bytes | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    merged_headers = {
        "X-GitHub-Event": "ping",
        "X-GitHub-Delivery": "delivery-1",
    }
    if headers:
        merged_headers.update(headers)
    payload = raw_payload if raw_payload is not None else b'{"zen":"ok"}'
    merged_headers.setdefault("Content-Type", "application/json")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/webhook/github", content=payload, headers=merged_headers)


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_api_routes_allow_development_without_key(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    get_settings.cache_clear()

    dashboard.set_storage(InMemoryStorage())

    response = await _get_activities()
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_routes_require_key_in_non_development(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_AUTH_KEY", "secret-123")
    get_settings.cache_clear()

    dashboard.set_storage(InMemoryStorage())

    missing = await _get_activities()
    assert missing.status_code == 401

    invalid = await _get_activities(headers={"X-API-Key": "wrong"})
    assert invalid.status_code == 401

    valid = await _get_activities(headers={"X-API-Key": "secret-123"})
    assert valid.status_code == 200


@pytest.mark.asyncio
async def test_webhook_requires_signature_when_enabled_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "true")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "top-secret")
    get_settings.cache_clear()

    missing = await _post_ping()
    assert missing.status_code == 401

    payload = b'{"zen":"ok"}'
    signed = await _post_ping(
        headers={"X-Hub-Signature-256": _sign(payload, "top-secret")},
        raw_payload=payload,
    )
    assert signed.status_code == 200


@pytest.mark.asyncio
async def test_webhook_can_disable_signature_check_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "false")
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()

    response = await _post_ping()
    assert response.status_code == 200


def test_cors_origins_parse_from_csv() -> None:
    settings = Settings(cors_allowed_origins="http://a.example.com, http://b.example.com")
    assert settings.cors_allowed_origins == [
        "http://a.example.com",
        "http://b.example.com",
    ]


@pytest.mark.asyncio
async def test_settings_endpoint_returns_non_secret_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "super-secret-key")
    get_settings.cache_clear()

    response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200

    data = response.json()
    assert data["azure_openai_deployment_name"] == "gpt-5-mini"
    assert "azure_openai_api_key" not in data


@pytest.mark.asyncio
async def test_settings_endpoint_requires_admin_key(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_AUTH_KEY", "api-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    dashboard.set_storage(InMemoryStorage())

    missing_admin = await _get_settings(headers={"X-API-Key": "api-secret"})
    assert missing_admin.status_code == 401

    invalid_admin = await _get_settings(
        headers={"X-API-Key": "api-secret", "X-Admin-Key": "wrong"}
    )
    assert invalid_admin.status_code == 401

    valid = await _get_settings(
        headers={"X-API-Key": "api-secret", "X-Admin-Key": "admin-secret"}
    )
    assert valid.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_patch_runtime_settings(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    dashboard.set_storage(InMemoryStorage())
    dashboard.set_workflow(_DummyWorkflow())  # type: ignore[arg-type]

    response = await _patch_settings(
        {
            "heal_mode": "demo",
            "max_remediation_attempts": 7,
            "pipeline_step_timeout_seconds": 45,
            "github_api_max_retries": 5,
            "log_prompt_max_chars": 12000,
            "log_prompt_head_chars": 6000,
            "log_prompt_tail_chars": 6000,
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["heal_mode"] == "demo"
    assert data["max_remediation_attempts"] == 7
    assert data["pipeline_step_timeout_seconds"] == 45
    assert data["github_api_max_retries"] == 5
