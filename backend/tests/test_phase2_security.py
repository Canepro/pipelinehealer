"""Phase 2 security tests: API auth, webhook policy, and config parsing."""

import hashlib
import hmac
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from src.api import dashboard, security
from src.api.security import AuthPrincipal
from src.config import Settings, get_settings, reset_settings
from src.main import app
from src.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    dashboard.clear_admin_settings_audit()
    reset_settings()
    yield
    dashboard.clear_admin_settings_audit()
    reset_settings()


class _DummyWorkflow:
    async def start(self, event) -> str:  # type: ignore[no-untyped-def]
        _ = event
        return "activity-test-123"

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


async def _get_settings_audit(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings/audit", headers=headers or {})


async def _get_llm_provider_health(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings/llm/provider-health", headers=headers or {})


async def _post_settings_persist(
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/settings/persist",
            json=payload or {},
            headers=headers or {},
        )


async def _post_ping(
    headers: dict[str, str] | None = None,
    raw_payload: bytes | None = None,
) -> httpx.Response:
    if not hasattr(app.state, "workflow"):
        app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]
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


async def _post_workflow_run(
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    if not hasattr(app.state, "workflow"):
        app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]
    transport = httpx.ASGITransport(app=app)
    merged_headers = {
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "delivery-workflow-1",
        "Content-Type": "application/json",
    }
    if headers:
        merged_headers.update(headers)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/webhook/github", json=payload, headers=merged_headers)


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_api_routes_allow_development_without_key(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    reset_settings()

    app.state.storage = InMemoryStorage()

    response = await _get_activities()
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_routes_require_key_in_non_development(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_AUTH_KEY", "secret-123")
    reset_settings()

    app.state.storage = InMemoryStorage()

    missing = await _get_activities()
    assert missing.status_code == 401

    invalid = await _get_activities(headers={"X-API-Key": "wrong"})
    assert invalid.status_code == 401

    valid = await _get_activities(headers={"X-API-Key": "secret-123"})
    assert valid.status_code == 200


@pytest.mark.asyncio
async def test_api_routes_require_bearer_token_in_entra_mode(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-123")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client-123")
    reset_settings()

    app.state.storage = InMemoryStorage()

    def _fake_validate(authorization: str | None) -> AuthPrincipal:
        if authorization != "Bearer valid-token":
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        return AuthPrincipal(
            subject="user-123",
            roles=frozenset(),
            scopes=frozenset({"PipelineHealer.Access"}),
            claims={"sub": "user-123"},
        )

    monkeypatch.setattr(security, "_validate_bearer_token", _fake_validate)

    missing = await _get_activities()
    assert missing.status_code == 401

    invalid = await _get_activities(headers={"Authorization": "Bearer wrong-token"})
    assert invalid.status_code == 401

    valid = await _get_activities(headers={"Authorization": "Bearer valid-token"})
    assert valid.status_code == 200


@pytest.mark.asyncio
async def test_api_routes_accept_key_or_bearer_in_hybrid_mode(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "hybrid")
    monkeypatch.setenv("API_AUTH_KEY", "hybrid-api-key")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-123")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client-123")
    reset_settings()

    app.state.storage = InMemoryStorage()

    def _fake_validate(authorization: str | None) -> AuthPrincipal:
        if authorization != "Bearer hybrid-token":
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        return AuthPrincipal(
            subject="user-456",
            roles=frozenset(),
            scopes=frozenset({"PipelineHealer.Access"}),
            claims={"sub": "user-456"},
        )

    monkeypatch.setattr(security, "_validate_bearer_token", _fake_validate)

    missing = await _get_activities()
    assert missing.status_code == 401

    with_key = await _get_activities(headers={"X-API-Key": "hybrid-api-key"})
    assert with_key.status_code == 200

    with_bearer = await _get_activities(headers={"Authorization": "Bearer hybrid-token"})
    assert with_bearer.status_code == 200


@pytest.mark.asyncio
async def test_settings_admin_route_accepts_entra_admin_role(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-123")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client-123")
    monkeypatch.setenv("ENTRA_ADMIN_ROLES", "PipelineHealer.Admin")
    reset_settings()

    app.state.storage = InMemoryStorage()

    def _fake_validate(authorization: str | None) -> AuthPrincipal:
        if authorization == "Bearer admin-token":
            return AuthPrincipal(
                subject="admin-user",
                roles=frozenset({"PipelineHealer.Admin"}),
                scopes=frozenset(),
                claims={"sub": "admin-user"},
            )
        if authorization == "Bearer user-token":
            return AuthPrincipal(
                subject="regular-user",
                roles=frozenset({"PipelineHealer.Reader"}),
                scopes=frozenset(),
                claims={"sub": "regular-user"},
            )
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    monkeypatch.setattr(security, "_validate_bearer_token", _fake_validate)

    forbidden = await _get_settings(headers={"Authorization": "Bearer user-token"})
    assert forbidden.status_code == 403

    allowed = await _get_settings(headers={"Authorization": "Bearer admin-token"})
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_webhook_requires_signature_when_enabled_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "true")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "top-secret")
    reset_settings()

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
    reset_settings()

    response = await _post_ping()
    assert response.status_code == 200


def test_cors_origins_parse_from_csv() -> None:
    settings = Settings(cors_allowed_origins="http://a.example.com, http://b.example.com")
    assert settings.cors_allowed_origins == [
        "http://a.example.com",
        "http://b.example.com",
    ]


def test_allowed_repos_parse_from_csv() -> None:
    settings = Settings(ph_allowed_repos="owner/repo1, owner/repo2")
    assert settings.ph_allowed_repos == ["owner/repo1", "owner/repo2"]


@pytest.mark.asyncio
async def test_workflow_run_ignored_when_repo_not_in_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT", "false")
    monkeypatch.setenv("PH_ALLOWED_REPOS", "Canepro/allowed-repo")
    reset_settings()

    payload = {
        "action": "completed",
        "workflow_run": {
            "id": 123456,
            "name": "CI",
            "workflow_id": 987654,
            "head_branch": "main",
            "head_sha": "abc123def",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "https://github.com/Canepro/not-allowed/actions/runs/123456",
            "created_at": "2026-02-13T00:00:00Z",
            "updated_at": "2026-02-13T00:01:00Z",
            "run_attempt": 1,
            "run_number": 10,
        },
        "repository": {
            "id": 123,
            "name": "not-allowed",
            "full_name": "Canepro/not-allowed",
            "owner": {"login": "Canepro", "id": 1},
            "default_branch": "main",
            "html_url": "https://github.com/Canepro/not-allowed",
        },
        "sender": {"login": "github-actions[bot]"},
    }

    response = await _post_workflow_run(payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert "outside PH_ALLOWED_REPOS" in data["reason"]


@pytest.mark.asyncio
async def test_settings_endpoint_returns_non_secret_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "super-secret-key")
    reset_settings()

    response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200

    data = response.json()
    assert data["azure_openai_deployment_name"] == "gpt-5-mini"
    assert data["llm_provider"] == "azure_openai"
    assert "azure_openai_api_key" not in data


@pytest.mark.asyncio
async def test_settings_endpoint_requires_admin_key(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_AUTH_KEY", "api-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()

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
    monkeypatch.setenv("AUDIT_SALT", "audit-salt-1")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

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
        headers={"X-Admin-Key": "admin-secret", "X-Request-Id": "req-abc-123"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "req-abc-123"

    data = response.json()
    assert data["heal_mode"] == "demo"
    assert data["max_remediation_attempts"] == 7
    assert data["pipeline_step_timeout_seconds"] == 45
    assert data["github_api_max_retries"] == 5

    audit = await _get_settings_audit(headers={"X-Admin-Key": "admin-secret"})
    assert audit.status_code == 200
    entries = audit.json()
    assert len(entries) >= 1
    latest = entries[0]
    assert "heal_mode" in latest["changed_keys"]
    assert latest["changes"]["heal_mode"]["new"] == "demo"
    assert latest["request_id"] == "req-abc-123"
    assert str(latest["actor"]).startswith("admin_key:sha256:")


@pytest.mark.asyncio
async def test_admin_settings_audit_persists_beyond_in_memory_buffer(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"heal_mode": "demo"},
        headers={"X-Admin-Key": "admin-secret", "X-Request-Id": "req-audit-persist"},
    )
    assert response.status_code == 200

    # Simulate process-local buffer loss; durable storage copy should still be returned.
    dashboard.clear_admin_settings_audit()

    audit = await _get_settings_audit(headers={"X-Admin-Key": "admin-secret"})
    assert audit.status_code == 200
    entries = audit.json()
    assert len(entries) >= 1
    assert entries[0]["request_id"] == "req-audit-persist"
    assert entries[0]["changes"]["heal_mode"]["new"] == "demo"


@pytest.mark.asyncio
async def test_admin_patch_normalizes_and_deduplicates_allowed_repos(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "ph_allowed_repos": [
                "https://github.com/Canepro/PipelineHealer",
                "canepro/pipelinehealer",
                "git@github.com:Canepro/PipelineHealer.git",
            ]
        },
        headers={"X-Admin-Key": "admin-secret"},
    )

    assert response.status_code == 200
    assert response.json()["ph_allowed_repos"] == ["canepro/pipelinehealer"]


@pytest.mark.asyncio
async def test_admin_patch_rejects_invalid_allowed_repo_format(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"ph_allowed_repos": ["not-a-repo-name"]},
        headers={"X-Admin-Key": "admin-secret"},
    )

    assert response.status_code == 422
    assert "expected 'owner/repo'" in response.json()["detail"]


@pytest.mark.asyncio
async def test_allowlist_patch_is_effective_for_webhook_scope(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    patch_response = await _patch_settings(
        {"ph_allowed_repos": ["Canepro/allowed-repo"]},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["ph_allowed_repos"] == ["canepro/allowed-repo"]

    payload = {
        "action": "completed",
        "workflow_run": {
            "id": 123456,
            "name": "CI",
            "workflow_id": 987654,
            "head_branch": "main",
            "head_sha": "abc123def",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "https://github.com/Canepro/not-allowed/actions/runs/123456",
            "created_at": "2026-02-13T00:00:00Z",
            "updated_at": "2026-02-13T00:01:00Z",
            "run_attempt": 1,
            "run_number": 10,
        },
        "repository": {
            "id": 123,
            "name": "not-allowed",
            "full_name": "Canepro/not-allowed",
            "owner": {"login": "Canepro", "id": 1},
            "default_branch": "main",
            "html_url": "https://github.com/Canepro/not-allowed",
        },
        "sender": {"login": "github-actions[bot]"},
    }

    response = await _post_workflow_run(payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert "outside PH_ALLOWED_REPOS" in data["reason"]


@pytest.mark.asyncio
async def test_settings_endpoint_includes_gh_aw_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("GH_AW_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GH_AW_INGESTION_MODE", "passive")
    monkeypatch.setenv("GH_AW_KNOWN_WORKFLOWS", "ci-doctor, schema-consistency-checker")
    reset_settings()

    response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200
    data = response.json()
    assert data["gh_aw_tools_enabled"] is True
    assert data["gh_aw_ingestion_mode"] == "passive"
    assert data["gh_aw_known_workflows"] == [
        "ci-doctor",
        "schema-consistency-checker",
    ]


@pytest.mark.asyncio
async def test_admin_can_patch_gh_aw_runtime_settings(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "gh_aw_tools_enabled": True,
            "gh_aw_ingestion_mode": "passive",
            "gh_aw_known_workflows": ["ci-doctor", "ci-doctor", "schema-consistency-checker"],
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["gh_aw_tools_enabled"] is True
    assert data["gh_aw_ingestion_mode"] == "passive"
    assert data["gh_aw_known_workflows"] == ["ci-doctor", "schema-consistency-checker"]


@pytest.mark.asyncio
async def test_admin_can_patch_azure_openai_deployment_name(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"azure_openai_deployment_name": "gpt-5-mini-fast"},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    assert response.json()["azure_openai_deployment_name"] == "gpt-5-mini-fast"


@pytest.mark.asyncio
async def test_admin_can_patch_llm_provider(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"llm_provider": "openai_compatible"},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    assert response.json()["llm_provider"] == "openai_compatible"


@pytest.mark.asyncio
async def test_admin_patch_rejects_invalid_llm_provider(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"llm_provider": "bad_provider"},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 422
    assert "llm_provider" in response.json()["detail"]


@pytest.mark.asyncio
async def test_settings_exposes_llm_provider_health(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    reset_settings()

    response = await _get_llm_provider_health(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "azure_openai"
    assert body["implemented"] is True
    assert body["available"] is True


@pytest.mark.asyncio
async def test_admin_patch_rejects_empty_azure_openai_deployment_name(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"azure_openai_deployment_name": "   "},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 422
    assert "azure_openai_deployment_name" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_patch_rejects_invalid_gh_aw_ingestion_mode(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"gh_aw_ingestion_mode": "active"},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 422
    assert "gh_aw_ingestion_mode" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_persist_mutable_runtime_settings_to_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    env_file = tmp_path / ".env"
    env_file.write_text(
        "HEAL_MODE=safe\n"
        "AUTO_CREATE_PR=true\n"
        "GH_AW_TOOLS_ENABLED=false\n"
        "PH_ALLOWED_REPOS=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PIPELINEHEALER_ENV_FILE_PATH", str(env_file))

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    patch_response = await _patch_settings(
        {
            "heal_mode": "demo",
            "auto_create_pr": False,
            "auto_create_tracking_issue_for_prs": False,
            "max_remediation_attempts": 9,
            "verify_webhook_signature_in_development": True,
            "pipeline_step_timeout_seconds": 45,
            "github_api_max_retries": 4,
            "github_api_retry_base_seconds": 0.7,
            "github_api_retry_max_seconds": 9.5,
            "log_prompt_max_chars": 14000,
            "log_prompt_head_chars": 7000,
            "log_prompt_tail_chars": 7000,
            "gh_aw_tools_enabled": True,
            "gh_aw_ingestion_mode": "passive",
            "gh_aw_known_workflows": ["ci-doctor", "schema-consistency-checker"],
            "ph_allowed_repos": ["Canepro/PipelineHealer", "canepro/pipelinehealer-demo"],
            "azure_openai_deployment_name": "gpt-5-mini-fast",
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert patch_response.status_code == 200

    persist_response = await _post_settings_persist(
        payload={"skip_redeploy": True},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert persist_response.status_code == 200
    body = persist_response.json()
    assert body["env_file"] == str(env_file)
    assert body["redeploy_attempted"] is False
    assert body["redeploy_started"] is False
    assert "GH_AW_KNOWN_WORKFLOWS" in body["persisted_keys"]
    assert "PH_ALLOWED_REPOS" in body["persisted_keys"]

    persisted_text = env_file.read_text(encoding="utf-8")
    assert "HEAL_MODE=demo" in persisted_text
    assert "AUTO_CREATE_PR=false" in persisted_text
    assert "AUTO_CREATE_TRACKING_ISSUE_FOR_PRS=false" in persisted_text
    assert "MAX_REMEDIATION_ATTEMPTS=9" in persisted_text
    assert "VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT=true" in persisted_text
    assert "PIPELINE_STEP_TIMEOUT_SECONDS=45.0" in persisted_text
    assert "GITHUB_API_MAX_RETRIES=4" in persisted_text
    assert "GITHUB_API_RETRY_BASE_SECONDS=0.7" in persisted_text
    assert "GITHUB_API_RETRY_MAX_SECONDS=9.5" in persisted_text
    assert "LOG_PROMPT_MAX_CHARS=14000" in persisted_text
    assert "LOG_PROMPT_HEAD_CHARS=7000" in persisted_text
    assert "LOG_PROMPT_TAIL_CHARS=7000" in persisted_text
    assert "GH_AW_TOOLS_ENABLED=true" in persisted_text
    assert "GH_AW_INGESTION_MODE=passive" in persisted_text
    assert "GH_AW_KNOWN_WORKFLOWS=ci-doctor,schema-consistency-checker" in persisted_text
    assert "PH_ALLOWED_REPOS=canepro/pipelinehealer,canepro/pipelinehealer-demo" in persisted_text
    assert "AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5-mini-fast" in persisted_text


@pytest.mark.asyncio
async def test_admin_persist_succeeds_without_env_file(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("PIPELINEHEALER_ENV_FILE_PATH", "/tmp/nonexistent-ph-env-file")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    patch_response = await _patch_settings(
        {
            "heal_mode": "demo",
            "gh_aw_tools_enabled": True,
            "gh_aw_ingestion_mode": "passive",
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert patch_response.status_code == 200

    persist_response = await _post_settings_persist(
        payload={},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert persist_response.status_code == 200
    body = persist_response.json()
    assert body["env_file"] == ""
    assert body["redeploy_attempted"] is False
    assert body["redeploy_started"] is False
    assert "durable storage" in body["redeploy_message"]


@pytest.mark.asyncio
async def test_apply_persisted_runtime_settings_restores_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("PIPELINEHEALER_ENV_FILE_PATH", "/tmp/nonexistent-ph-env-file")
    reset_settings()

    storage = InMemoryStorage()
    app.state.storage = storage
    workflow = _DummyWorkflow()
    app.state.workflow = workflow  # type: ignore[assignment]

    patch_response = await _patch_settings(
        {
            "heal_mode": "demo",
            "gh_aw_tools_enabled": True,
            "gh_aw_ingestion_mode": "passive",
            "ph_allowed_repos": ["Canepro/PipelineHealer"],
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert patch_response.status_code == 200

    persist_response = await _post_settings_persist(
        payload={"skip_redeploy": True},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert persist_response.status_code == 200

    runtime_settings = get_settings()
    runtime_settings.heal_mode = "safe"
    runtime_settings.gh_aw_tools_enabled = False
    runtime_settings.gh_aw_ingestion_mode = "disabled"
    runtime_settings.ph_allowed_repos = []

    await dashboard.apply_persisted_runtime_settings(storage, workflow)  # type: ignore[arg-type]

    assert runtime_settings.heal_mode == "demo"
    assert runtime_settings.gh_aw_tools_enabled is True
    assert runtime_settings.gh_aw_ingestion_mode == "passive"
    assert runtime_settings.ph_allowed_repos == ["canepro/pipelinehealer"]
