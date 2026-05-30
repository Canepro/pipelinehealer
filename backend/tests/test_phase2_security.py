"""Phase 2 security tests: API auth, webhook policy, and config parsing."""

import hashlib
import hmac
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from src import __version__
from src.api import dashboard, security
from src.api.security import AuthPrincipal
from src.config import Settings, get_settings, reset_settings
from src.main import app
from src.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep this module deterministic regardless of local backend/.env auth mode.
    # Individual tests still override AUTH_MODE when exercising entra/hybrid paths.
    monkeypatch.setenv("AUTH_MODE", "api_key")
    dashboard.clear_admin_settings_audit()
    dashboard.clear_settings_runtime_provenance()
    reset_settings()
    yield
    dashboard.clear_admin_settings_audit()
    dashboard.clear_settings_runtime_provenance()
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


async def _get_secret_settings(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings/secrets", headers=headers or {})


async def _patch_settings(
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.patch("/api/settings", json=payload, headers=headers or {})


async def _patch_secret_settings(
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.patch("/api/settings/secrets", json=payload, headers=headers or {})


async def _get_settings_audit(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings/audit", headers=headers or {})


async def _get_llm_provider_health(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings/llm/provider-health", headers=headers or {})


async def _get_mcp_provider_health(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/settings/mcp/provider-health", headers=headers or {})


async def _get_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/health")


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
async def test_settings_endpoint_returns_non_secret_fields(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv(
        "PIPELINEHEALER_ENV_FILE_PATH",
        str(tmp_path / "missing-settings.env"),
    )
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "super-secret-key")
    monkeypatch.setenv("AGENT_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("AGENT_HANDOFF_MODE", "webhook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://agent.example.com/hook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_ALLOWLIST", "agent.example.com")
    reset_settings()
    app.state.storage = InMemoryStorage()

    response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200

    data = response.json()
    assert data["azure_openai_deployment_name"] == "gpt-5-mini"
    assert data["llm_provider"] == "azure_openai"
    assert data["llm_model_analysis"] == ""
    assert data["llm_model_diagnosis"] == ""
    assert data["llm_model_remediation"] == ""
    assert data["agent_handoff_webhook_host"] == "agent.example.com"
    assert data["agent_handoff_webhook_allowlist"] == ["agent.example.com"]
    assert data["settings_metadata"]["azure_openai_deployment_name"]["source"] == "env"
    assert data["settings_metadata"]["heal_mode"]["source"] == "default"
    assert data["settings_metadata"]["storage_mode"]["source"] == "computed"
    assert data["settings_metadata"]["agent_handoff_enabled"]["mutable"] is True
    assert data["settings_metadata"]["agent_handoff_webhook_configured"]["source"] == "env"
    assert data["settings_metadata"]["agent_handoff_webhook_configured"]["sensitive"] is True
    assert (
        data["settings_metadata"]["agent_handoff_webhook_host"]["note"]
        == "Derived from the Assign-to-Agent webhook URL secret; only the destination host is exposed."
    )
    assert data["settings_metadata"]["openai_compatible_api_key_configured"]["sensitive"] is True
    assert data["setup_status"]["storage_bootstrap"]["ready"] is True
    assert "azure_openai_api_key" not in data


@pytest.mark.asyncio
async def test_settings_env_file_override_controls_startup_provenance(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    env_file = tmp_path / ".env"
    env_file.write_text("HEAL_MODE=freestyle\n", encoding="utf-8")
    monkeypatch.setenv("PIPELINEHEALER_ENV_FILE_PATH", str(env_file))
    reset_settings()
    app.state.storage = InMemoryStorage()

    response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["heal_mode"] == "freestyle"
    assert body["settings_metadata"]["heal_mode"]["source"] == "env"


def test_startup_configured_fields_caches_env_file_until_file_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("HEAL_MODE=freestyle\n", encoding="utf-8")
    monkeypatch.setenv("PIPELINEHEALER_ENV_FILE_PATH", str(env_file))
    dashboard.clear_settings_runtime_provenance()

    call_count = 0
    original_dotenv_values = dashboard.dotenv_values

    def _counting_dotenv_values(path: Path):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return original_dotenv_values(path)

    monkeypatch.setattr(dashboard, "dotenv_values", _counting_dotenv_values)

    assert "heal_mode" in dashboard._startup_configured_fields()
    assert "heal_mode" in dashboard._startup_configured_fields()
    assert call_count == 1

    env_file.write_text("HEAL_MODE=demo\n", encoding="utf-8")

    assert "heal_mode" in dashboard._startup_configured_fields()
    assert call_count == 2


@pytest.mark.asyncio
async def test_settings_distinguish_github_app_configuration_from_live_pat_runtime(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----test")
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    reset_settings()
    app.state.storage = InMemoryStorage()

    response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200

    body = response.json()
    assert body["github_app_configured"] is True
    assert body["github_pat_configured"] is False
    assert body["github_auth_mode"] == "app configured (inactive)"
    assert body["setup_status"]["github_runtime"]["ready"] is False
    assert "requires a PAT" in body["setup_status"]["github_runtime"]["detail"]


@pytest.mark.asyncio
async def test_secret_settings_endpoint_redacts_values_and_supports_runtime_writes(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("SETTINGS_DB_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "env-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    initial = await _get_secret_settings(headers={"X-Admin-Key": "admin-secret"})
    assert initial.status_code == 200
    secrets = {item["key"]: item for item in initial.json()}
    assert secrets["github_webhook_secret"]["overridden_by_env"] is True
    assert secrets["github_webhook_secret"]["source"] == "env"

    patch_response = await _patch_secret_settings(
        {
            "secrets": {
                "openai_compatible_api_key": {"value": "sk-test-1234567890"},
                "agent_handoff_webhook_url": {"value": "https://agent.example.com/api/agent-handoff"},
            }
        },
        headers={"X-Admin-Key": "admin-secret", "X-Request-Id": "req-secret-1"},
    )
    assert patch_response.status_code == 200
    body = {item["key"]: item for item in patch_response.json()}
    assert body["openai_compatible_api_key"]["configured"] is True
    assert body["openai_compatible_api_key"]["source"] == "secret_store"
    assert body["agent_handoff_webhook_url"]["safe_hint"] == "agent.example.com"

    settings_response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert settings_response.status_code == 200
    settings_body = settings_response.json()
    assert settings_body["openai_compatible_api_key_configured"] is True
    assert settings_body["agent_handoff_webhook_host"] == "agent.example.com"

    audit = await _get_settings_audit(headers={"X-Admin-Key": "admin-secret"})
    entries = audit.json()
    assert entries[0]["request_id"] == "req-secret-1"
    assert "sk-test-1234567890" not in str(entries[0])


def test_dashboard_paths_default_to_backend_env_in_repo_checkout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    backend_root = repo_root / "backend"
    fake_dashboard = backend_root / "src" / "api" / "dashboard.py"
    fake_dashboard.parent.mkdir(parents=True)
    fake_dashboard.write_text("# test fixture\n", encoding="utf-8")
    (backend_root / "pyproject.toml").write_text("[project]\nname='pipelinehealer'\n", encoding="utf-8")
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "ph.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    monkeypatch.delenv("PIPELINEHEALER_REPO_ROOT", raising=False)
    monkeypatch.delenv("PIPELINEHEALER_ENV_FILE_PATH", raising=False)
    monkeypatch.setattr(dashboard, "__file__", str(fake_dashboard))

    assert dashboard._backend_root() == backend_root
    assert dashboard._repo_root() == repo_root
    assert dashboard._env_file_path() == backend_root / ".env"


def test_dashboard_paths_default_to_backend_env_in_container_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend_root = tmp_path / "app"
    fake_dashboard = backend_root / "src" / "api" / "dashboard.py"
    fake_dashboard.parent.mkdir(parents=True)
    fake_dashboard.write_text("# test fixture\n", encoding="utf-8")
    (backend_root / "pyproject.toml").write_text("[project]\nname='pipelinehealer'\n", encoding="utf-8")

    monkeypatch.delenv("PIPELINEHEALER_REPO_ROOT", raising=False)
    monkeypatch.delenv("PIPELINEHEALER_ENV_FILE_PATH", raising=False)
    monkeypatch.setattr(dashboard, "__file__", str(fake_dashboard))

    assert dashboard._backend_root() == backend_root
    assert dashboard._repo_root() == backend_root
    assert dashboard._env_file_path() == backend_root / ".env"


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
async def test_admin_can_patch_agent_handoff_runtime_settings(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://agent.example.com/hook")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "agent_handoff_enabled": True,
            "agent_handoff_mode": "webhook",
            "agent_handoff_webhook_allowlist": ["AGENT.example.com", "agent.example.com"],
            "agent_handoff_timeout_seconds": 12,
            "agent_handoff_max_retries": 3,
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_handoff_enabled"] is True
    assert body["agent_handoff_mode"] == "webhook"
    assert body["agent_handoff_webhook_allowlist"] == ["agent.example.com"]
    assert body["agent_handoff_timeout_seconds"] == 12
    assert body["agent_handoff_max_retries"] == 3
    assert body["settings_metadata"]["agent_handoff_enabled"]["source"] == "persisted_runtime_override"
    assert body["settings_metadata"]["agent_handoff_enabled"]["durable"] is True
    assert body["settings_metadata"]["agent_handoff_mode"]["source"] == "persisted_runtime_override"


@pytest.mark.asyncio
async def test_admin_patch_rejects_handoff_allowlist_that_excludes_configured_host(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "https://agent.example.com/hook")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_ALLOWLIST", "agent.example.com")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"agent_handoff_webhook_allowlist": ["other.example.com"]},
        headers={"X-Admin-Key": "admin-secret"},
    )

    assert response.status_code == 422
    assert "AGENT_HANDOFF_WEBHOOK_URL host" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_patch_tolerates_invalid_startup_handoff_webhook_url(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("AGENT_HANDOFF_WEBHOOK_URL", "agent.example.com/hook-without-scheme")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"heal_mode": "demo"},
        headers={"X-Admin-Key": "admin-secret"},
    )

    assert response.status_code == 200
    assert response.json()["heal_mode"] == "demo"


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
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_WAIT_SECONDS", "75")
    monkeypatch.setenv("EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS", "15")
    reset_settings()
    app.state.storage = InMemoryStorage()

    response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200
    data = response.json()
    assert data["gh_aw_tools_enabled"] is True
    assert data["gh_aw_ingestion_mode"] == "passive"
    assert data["storage_mode"] == "memory"
    assert data["gh_aw_known_workflows"] == [
        "ci-doctor",
        "schema-consistency-checker",
    ]
    assert data["external_diagnostics_wait_seconds"] == 75.0
    assert data["external_diagnostics_poll_interval_seconds"] == 15.0


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
            "external_diagnostics_wait_seconds": 45,
            "external_diagnostics_poll_interval_seconds": 15,
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["gh_aw_tools_enabled"] is True
    assert data["gh_aw_ingestion_mode"] == "passive"
    assert data["gh_aw_known_workflows"] == ["ci-doctor", "schema-consistency-checker"]
    assert data["external_diagnostics_wait_seconds"] == 45.0
    assert data["external_diagnostics_poll_interval_seconds"] == 15.0


@pytest.mark.asyncio
async def test_admin_patch_rejects_poll_interval_above_wait_budget(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "external_diagnostics_wait_seconds": 30,
            "external_diagnostics_poll_interval_seconds": 45,
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 422
    assert "external_diagnostics_poll_interval_seconds" in response.json()["detail"]


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
async def test_admin_can_patch_llm_task_model_overrides(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "llm_model_analysis": " gpt-5-mini-fast ",
            "llm_model_diagnosis": "gpt-5-mini-reasoner",
            "llm_model_remediation": "",
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm_model_analysis"] == "gpt-5-mini-fast"
    assert body["llm_model_diagnosis"] == "gpt-5-mini-reasoner"
    assert body["llm_model_remediation"] == ""


@pytest.mark.asyncio
async def test_admin_patch_requires_default_handoff_target_to_be_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.delenv("AGENT_HANDOFF_DEFAULT_TARGET", raising=False)
    monkeypatch.delenv("AGENT_HANDOFF_ENABLED_TARGETS", raising=False)
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"agent_handoff_enabled_targets": ["openclaw"]},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 422
    assert "agent_handoff_default_target" in response.json()["detail"]

    response = await _patch_settings(
        {
            "agent_handoff_default_target": "openclaw",
            "agent_handoff_enabled_targets": ["openclaw"],
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_handoff_default_target"] == "openclaw"
    assert body["agent_handoff_enabled_targets"] == ["openclaw"]


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
async def test_settings_exposes_mcp_provider_health(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    reset_settings()

    response = await _get_mcp_provider_health(headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "github"
    assert body["enabled"] is True
    assert body["available"] is False
    assert body["reason"] == "missing_github_token"


@pytest.mark.asyncio
async def test_health_exposes_environment_and_storage_backend(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    reset_settings()
    app.state.storage = InMemoryStorage()

    response = await _get_health()
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "PipelineHealer"
    assert body["version"] == __version__
    assert body["status"] == "healthy"
    assert body["environment"] == "development"
    assert body["storage_backend"] == "in_memory"


@pytest.mark.asyncio
async def test_admin_can_patch_mcp_guardrail_settings(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "mcp_enabled": True,
            "mcp_provider": "github",
            "mcp_read_only": True,
            "mcp_tool_policies": {
                "fetch_failure_context": "read_only",
                "publish_artifact": "disabled",
                "rerun_pipeline": "write_with_approval",
            },
            "mcp_repo_allowlist": ["Canepro/PipelineHealer", "canepro/pipelinehealer"],
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mcp_enabled"] is True
    assert body["mcp_provider"] == "github"
    assert body["mcp_read_only"] is True
    assert body["mcp_tool_policies"] == {
        "fetch_failure_context": "read_only",
        "publish_artifact": "disabled",
        "rerun_pipeline": "write_with_approval",
    }
    assert body["mcp_repo_allowlist"] == ["canepro/pipelinehealer"]


@pytest.mark.asyncio
async def test_admin_patch_rejects_invalid_mcp_tool_policy(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "mcp_tool_policies": {
                "fetch_failure_context": "invalid_mode",
            }
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 422
    assert "mcp_tool_policies" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_patch_allows_clearing_azure_openai_deployment_name(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"azure_openai_deployment_name": "   "},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    assert response.json()["azure_openai_deployment_name"] == ""


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
async def test_admin_patch_accepts_hybrid_gh_aw_ingestion_mode(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {"gh_aw_ingestion_mode": "hybrid"},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    assert response.json()["gh_aw_ingestion_mode"] == "hybrid"


@pytest.mark.asyncio
async def test_hybrid_admin_key_can_override_non_admin_bearer_session(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "hybrid")
    monkeypatch.setenv("API_AUTH_KEY", "hybrid-api-key")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-123")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client-123")
    monkeypatch.setenv("ENTRA_ADMIN_ROLES", "PipelineHealer.Admin")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    def _fake_validate(authorization: str | None) -> AuthPrincipal:
        if authorization != "Bearer user-token":
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        return AuthPrincipal(
            subject="regular-user",
            roles=frozenset({"PipelineHealer.Reader"}),
            scopes=frozenset({"PipelineHealer.Access"}),
            claims={"sub": "regular-user"},
        )

    monkeypatch.setattr(security, "_validate_bearer_token", _fake_validate)

    response = await _patch_settings(
        {"heal_mode": "safe"},
        headers={"Authorization": "Bearer user-token", "X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200

    audit = await _get_settings_audit(
        headers={"Authorization": "Bearer user-token", "X-Admin-Key": "admin-secret"},
    )
    assert audit.status_code == 200
    entries = audit.json()
    assert entries
    assert entries[0]["actor"].startswith("admin_key:")


@pytest.mark.asyncio
async def test_hybrid_empty_admin_key_header_falls_back_to_bearer_auth(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "hybrid")
    monkeypatch.setenv("API_AUTH_KEY", "hybrid-api-key")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-123")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client-123")
    monkeypatch.setenv("ENTRA_ADMIN_ROLES", "PipelineHealer.Admin")
    reset_settings()

    app.state.storage = InMemoryStorage()

    def _fake_validate(authorization: str | None) -> AuthPrincipal:
        if authorization != "Bearer admin-token":
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        return AuthPrincipal(
            subject="admin-user",
            roles=frozenset({"PipelineHealer.Admin"}),
            scopes=frozenset({"PipelineHealer.Access"}),
            claims={"sub": "admin-user"},
        )

    monkeypatch.setattr(security, "_validate_bearer_token", _fake_validate)

    response = await _get_settings(
        headers={"Authorization": "Bearer admin-token", "X-Admin-Key": "   "}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_patch_accepts_freestyle_and_runtime_action_toggles(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    response = await _patch_settings(
        {
            "heal_mode": "freestyle",
            "auto_apply_remediation": False,
            "auto_create_pr": False,
            "jenkins_bridge_allow_pr": True,
            "auto_create_issue": True,
            "auto_retry_workflow": False,
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["heal_mode"] == "freestyle"
    assert body["auto_apply_remediation"] is False
    assert body["auto_create_pr"] is False
    assert body["jenkins_bridge_allow_pr"] is True
    assert body["auto_create_issue"] is True
    assert body["auto_retry_workflow"] is False


@pytest.mark.asyncio
async def test_admin_settings_persist_endpoint_is_deprecated_noop(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    reset_settings()

    monkeypatch.setenv("PIPELINEHEALER_ENV_FILE_PATH", str(tmp_path / "missing-settings.env"))

    app.state.storage = InMemoryStorage()
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]

    patch_response = await _patch_settings(
        {
            "heal_mode": "freestyle",
            "auto_apply_remediation": True,
            "auto_create_pr": False,
            "jenkins_bridge_allow_pr": True,
            "gh_aw_tools_enabled": True,
            "gh_aw_ingestion_mode": "passive",
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert patch_response.status_code == 200

    persist_response = await _post_settings_persist(
        payload={"skip_redeploy": True},
        headers={"X-Admin-Key": "admin-secret", "X-Request-Id": "req-persist-settings"},
    )
    assert persist_response.status_code == 200
    body = persist_response.json()
    assert body["deprecated"] is True
    assert body["env_file"] == ""
    assert body["redeploy_attempted"] is False
    assert body["redeploy_started"] is False
    assert "already persist" in body["redeploy_message"]

    audit = await _get_settings_audit(headers={"X-Admin-Key": "admin-secret"})
    assert audit.status_code == 200
    entries = audit.json()
    assert entries
    assert entries[0]["changed_keys"] == ["persist_settings"]
    assert entries[0]["request_id"] == "req-persist-settings"


@pytest.mark.asyncio
async def test_admin_patch_persists_runtime_settings_without_explicit_persist(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv(
        "PIPELINEHEALER_ENV_FILE_PATH",
        str(tmp_path / "missing-settings.env"),
    )
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

    runtime = await app.state.storage.get_runtime_settings()
    assert runtime == {
        "heal_mode": "demo",
        "gh_aw_tools_enabled": True,
        "gh_aw_ingestion_mode": "passive",
    }


@pytest.mark.asyncio
async def test_apply_persisted_runtime_settings_restores_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv(
        "PIPELINEHEALER_ENV_FILE_PATH",
        str(tmp_path / "missing-settings.env"),
    )
    reset_settings()

    storage = InMemoryStorage()
    app.state.storage = storage
    workflow = _DummyWorkflow()
    app.state.workflow = workflow  # type: ignore[assignment]

    patch_response = await _patch_settings(
        {
            "heal_mode": "demo",
            "llm_provider": "codex_app_server",
            "gh_aw_tools_enabled": True,
            "gh_aw_ingestion_mode": "passive",
            "agent_handoff_enabled": True,
            "agent_handoff_mode": "webhook",
            "agent_handoff_webhook_allowlist": ["agent.example.com"],
            "agent_handoff_timeout_seconds": 15,
            "agent_handoff_max_retries": 2,
            "ph_allowed_repos": ["Canepro/PipelineHealer"],
            "mcp_enabled": True,
            "mcp_provider": "github",
            "mcp_tool_policies": {"fetch_failure_context": "read_only"},
            "mcp_repo_allowlist": ["Canepro/PipelineHealer"],
        },
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert patch_response.status_code == 200

    runtime_settings = get_settings()
    runtime_settings.heal_mode = "safe"
    runtime_settings.llm_provider = "azure_openai"
    runtime_settings.gh_aw_tools_enabled = False
    runtime_settings.gh_aw_ingestion_mode = "disabled"
    runtime_settings.agent_handoff_enabled = False
    runtime_settings.agent_handoff_mode = "copy_only"
    runtime_settings.agent_handoff_webhook_allowlist = []
    runtime_settings.agent_handoff_timeout_seconds = 8.0
    runtime_settings.agent_handoff_max_retries = 1
    runtime_settings.ph_allowed_repos = []
    runtime_settings.mcp_enabled = False
    runtime_settings.mcp_provider = "disabled"
    runtime_settings.mcp_tool_policies = {}
    runtime_settings.mcp_repo_allowlist = []

    await dashboard.apply_persisted_runtime_settings(storage, workflow)  # type: ignore[arg-type]

    assert runtime_settings.heal_mode == "demo"
    assert runtime_settings.llm_provider == "codex_app_server"
    assert runtime_settings.gh_aw_tools_enabled is True
    assert runtime_settings.gh_aw_ingestion_mode == "passive"
    assert runtime_settings.agent_handoff_enabled is True
    assert runtime_settings.agent_handoff_mode == "webhook"
    assert runtime_settings.agent_handoff_webhook_allowlist == ["agent.example.com"]
    assert runtime_settings.agent_handoff_timeout_seconds == 15.0
    assert runtime_settings.agent_handoff_max_retries == 2
    assert runtime_settings.ph_allowed_repos == ["canepro/pipelinehealer"]
    assert runtime_settings.mcp_enabled is True
    assert runtime_settings.mcp_provider == "github"
    assert runtime_settings.mcp_tool_policies == {"fetch_failure_context": "read_only"}
    assert runtime_settings.mcp_repo_allowlist == ["canepro/pipelinehealer"]

    settings_response = await _get_settings(headers={"X-Admin-Key": "admin-secret"})
    assert settings_response.status_code == 200
    settings_body = settings_response.json()
    assert (
        settings_body["settings_metadata"]["agent_handoff_enabled"]["source"]
        == "persisted_runtime_override"
    )
    assert settings_body["settings_metadata"]["agent_handoff_enabled"]["durable"] is True


@pytest.mark.asyncio
async def test_env_overrides_win_over_persisted_runtime_settings_and_secrets(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("HEAL_MODE", "safe")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "env-openai-key")
    monkeypatch.setenv("SETTINGS_DB_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
    reset_settings()

    storage = InMemoryStorage()
    await storage.upsert_runtime_settings({"heal_mode": "demo"})
    app.state.storage = storage
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]
    settings = get_settings()
    settings.heal_mode = "debug"
    settings.openai_compatible_api_key = ""
    settings.settings_db_encryption_key = "0123456789abcdef0123456789abcdef"

    secret_patch = await _patch_secret_settings(
        {"secrets": {"openai_compatible_api_key": {"value": "ui-openai-key"}}},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert secret_patch.status_code == 200

    await dashboard.apply_persisted_runtime_settings(storage, app.state.workflow)  # type: ignore[arg-type]

    assert settings.heal_mode == "safe"
    assert settings.openai_compatible_api_key == "env-openai-key"


@pytest.mark.asyncio
async def test_default_env_file_wins_over_persisted_runtime_settings_and_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.delenv("PIPELINEHEALER_ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("HEAL_MODE", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.delenv("SETTINGS_DB_ENCRYPTION_KEY", raising=False)
    reset_settings()

    env_file = tmp_path / "default-backend.env"
    env_file.write_text(
        "\n".join(
            [
                "HEAL_MODE=safe",
                "OPENAI_COMPATIBLE_API_KEY=env-file-openai-key",
                "SETTINGS_DB_ENCRYPTION_KEY=0123456789abcdef0123456789abcdef",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(dashboard, "_env_file_path", lambda: env_file)
    monkeypatch.setattr(
        dashboard,
        "load_settings_snapshot",
        lambda: Settings(_env_file=env_file),  # type: ignore[call-arg]
    )

    storage = InMemoryStorage()
    await storage.upsert_runtime_settings({"heal_mode": "demo"})
    app.state.storage = storage
    app.state.workflow = _DummyWorkflow()  # type: ignore[assignment]
    settings = get_settings()
    settings.heal_mode = "debug"
    settings.openai_compatible_api_key = ""
    settings.settings_db_encryption_key = "0123456789abcdef0123456789abcdef"

    secret_patch = await _patch_secret_settings(
        {"secrets": {"openai_compatible_api_key": {"value": "ui-openai-key"}}},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert secret_patch.status_code == 200

    await dashboard.apply_persisted_runtime_settings(storage, app.state.workflow)  # type: ignore[arg-type]

    assert settings.heal_mode == "safe"
    assert settings.openai_compatible_api_key == "env-file-openai-key"
