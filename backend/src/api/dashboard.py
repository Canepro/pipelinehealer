"""Dashboard API endpoints for PipelineHealer."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..config import get_settings, load_settings_snapshot
from ..llm.adapters import get_llm_provider_adapter
from ..llm.capability import build_llm_capability_snapshot
from ..llm.providers import resolve_llm_provider
from ..models import (
    ActivityRecord,
    AdminSecretsUpdateRequest,
    AdminSettingsAuditEntry,
    AdminSettingsPersistRequest,
    AdminSettingsPersistResponse,
    AdminSettingsUpdateRequest,
    AgentHandoffAuditEntry,
    AgentHandoffConfigView,
    AgentHandoffIntegrationStatusView,
    AgentHandoffMode,
    AgentHandoffRequest,
    AgentHandoffResponse,
    AgentHandoffStatus,
    AppSettingMetadataView,
    AppSettingSource,
    AppSettingsView,
    DashboardStats,
    ExternalAgentTarget,
    FailureType,
    HandoffEventType,
    HandoffGitHubRefs,
    HandoffMessage,
    HandoffMessageDirection,
    HandoffSession,
    HandoffSessionCreateRequest,
    HandoffSessionCreateResponse,
    HandoffSessionEventRequest,
    HandoffSessionStatus,
    HandoffSessionView,
    LearningGuidanceEffectiveness,
    LearningPromotionReadiness,
    LearningQueueDecisionRequest,
    LearningQueueItem,
    LearningQueueRefreshResponse,
    LearningQueueStatus,
    LearningVerificationFeedbackRequest,
    LearningVerificationFeedbackResponse,
    LearningVerificationOutcome,
    LLMProviderHealthView,
    MCPProviderHealthView,
    NotificationTargetHealthView,
    RemediationStatus,
    SecretSettingView,
    SetupCheckView,
    SetupStatusView,
    utcnow,
)
from ..secret_store import SecretStoreError, build_secret_store
from ..settings_registry import (
    ALL_SETTING_SPECS_BY_KEY,
    RUNTIME_NON_SECRET_ENV_KEYS,
    SECRET_SETTING_SPECS,
    SECRET_SETTING_SPECS_BY_KEY,
)
from ..storage import ActivityStorage
from ..tools.mcp_provider import get_mcp_provider
from ..workflows.pipeline_healer import PipelineHealerWorkflow, resolve_storage_mode
from .deps import get_storage, get_workflow
from .security import get_request_principal, require_admin_key, require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"], dependencies=[Depends(require_api_key)])
_REPO_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_HOSTNAME_RE = re.compile(r"^[a-z0-9.-]+$")
_AGENT_HANDOFF_MAX_AUDIT_ENTRIES = 30
_runtime_override_keys: set[str] = set()
_persisted_runtime_override_keys: set[str] = set()
_startup_configured_fields_cache_signature: tuple[Any, ...] | None = None
_startup_configured_fields_cache_value: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _DerivedSettingMetadataSpec:
    """Metadata for operator-visible fields derived from hidden startup configuration."""

    source_fields: tuple[str, ...]
    sensitive: bool = False
    note: str = ""


def _normalize_repo_full_name(raw_value: Any) -> str:
    """Normalize supported repo inputs to canonical owner/repo form."""
    value = str(raw_value).strip()
    if not value:
        return ""

    parsed = urlparse(value)

    # Handle https://github.com/owner/repo(.git) form.
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        host = parsed.netloc.lower()
        if host not in {"github.com", "www.github.com"}:
            raise ValueError(
                f"Invalid repo '{value}'; only github.com repository URLs are supported"
            )
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = [part for part in path.split("/") if part]
        if len(parts) != 2:
            raise ValueError(
                f"Invalid repo URL '{value}'; expected 'https://github.com/owner/repo'"
            )
        value = f"{parts[0]}/{parts[1]}"

    # Handle git@github.com:owner/repo(.git) form.
    if value.startswith("git@github.com:"):
        path = value[len("git@github.com:") :].strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        value = path

    value = value.strip().strip("/")
    if value.endswith(".git"):
        value = value[:-4]

    if not _REPO_FULL_NAME_RE.fullmatch(value):
        raise ValueError(f"Invalid repo format '{value}'; expected 'owner/repo'")

    # GitHub owner/repo matching is case-insensitive; store canonical lowercase.
    return value.lower()


def _normalize_allowed_repo_list(raw_repos: list[Any]) -> list[str]:
    """Normalize repo allowlist and preserve insertion order while deduplicating."""
    normalized: list[str] = []
    seen: set[str] = set()
    for repo in raw_repos:
        repo_name = _normalize_repo_full_name(repo)
        if not repo_name or repo_name in seen:
            continue
        seen.add(repo_name)
        normalized.append(repo_name)
    return normalized


def _normalize_hostname_allowlist(raw_hosts: list[Any]) -> list[str]:
    """Normalize hostname allowlist entries while preserving insertion order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_host in raw_hosts:
        host = str(raw_host).strip().lower()
        if not host:
            continue
        if "://" in host or "/" in host or ":" in host or not _HOSTNAME_RE.fullmatch(host):
            raise ValueError(
                f"Invalid host '{raw_host}'; expected bare hostname like 'agent.example.com'"
            )
        if host in seen:
            continue
        seen.add(host)
        normalized.append(host)
    return normalized


def _validate_handoff_webhook_url(value: Any) -> str:
    """Normalize and validate Assign-to-Agent webhook URL when present."""
    webhook_url = str(value).strip()
    if not webhook_url:
        return ""
    parsed = urlparse(webhook_url)
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("agent_handoff_webhook_url must be a full http(s) URL")
    return webhook_url


def _get_storage_backend_name(storage: ActivityStorage | None) -> str:
    """Return a user-friendly name for the currently configured storage backend."""
    if storage is None:
        return "unknown"
    storage_class = type(storage).__name__
    if storage_class == "InMemoryStorage":
        return "in_memory"
    if storage_class == "ActivityStorage":
        return "cosmos_db"
    if storage_class == "PostgresStorage":
        return "postgresql"
    return storage_class.lower()


def _get_storage_mode_name(storage: ActivityStorage | None, environment: str) -> str:
    """Return effective storage mode name using active backend when available."""
    backend = _get_storage_backend_name(storage)
    if backend == "in_memory":
        return "memory"
    if backend == "cosmos_db":
        return "cosmos"
    if backend == "postgresql":
        return "postgres"
    # Fallback for cases where storage has not been initialized yet.
    return "memory" if environment == "development" else "cosmos"


def _safe_settings_allowlist(raw_repos: list[str]) -> list[str]:
    """Best-effort normalization for settings view without crashing on bad env values."""
    try:
        return _normalize_allowed_repo_list(raw_repos)
    except ValueError:
        logger.warning("Invalid PH_ALLOWED_REPOS entry detected; exposing raw values in settings view")
        return [str(repo).strip() for repo in raw_repos if str(repo).strip()]


def _safe_hostname_allowlist(raw_hosts: list[str]) -> list[str]:
    """Best-effort normalization for hostname allowlists without crashing settings view."""
    try:
        return _normalize_hostname_allowlist(raw_hosts)
    except ValueError:
        logger.warning(
            "Invalid AGENT_HANDOFF_WEBHOOK_ALLOWLIST entry detected; exposing raw values in settings view"
        )
        return [str(host).strip().lower() for host in raw_hosts if str(host).strip()]


def _normalize_workflow_names(raw_workflows: list[Any]) -> list[str]:
    """Normalize workflow identifiers and preserve insertion order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for workflow in raw_workflows:
        value = str(workflow).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_mcp_tool_policies(raw_policies: dict[Any, Any]) -> dict[str, str]:
    """Normalize per-tool MCP policy map and validate supported policy values."""
    allowed_modes = {"disabled", "read_only", "write_with_approval", "auto"}
    normalized: dict[str, str] = {}
    for tool, policy in raw_policies.items():
        tool_name = str(tool).strip().lower()
        policy_mode = str(policy).strip().lower()
        if not tool_name:
            continue
        if policy_mode not in allowed_modes:
            raise ValueError(
                "mcp_tool_policies values must be one of: "
                "disabled, read_only, write_with_approval, auto"
            )
        normalized[tool_name] = policy_mode
    return normalized


def _resolve_github_auth_mode() -> tuple[bool, bool, str]:
    """Return GitHub auth capabilities and active mode description."""
    settings = get_settings()
    has_pat = bool(settings.github_personal_access_token)
    has_app = bool(
        settings.github_app_id
        and (
            settings.github_app_private_key
            or (settings.key_vault_url and settings.github_private_key_secret_name)
        )
    )

    if has_pat and has_app:
        mode = "pat (app configured)"
    elif has_app:
        mode = "app configured (inactive)"
    elif has_pat:
        mode = "pat"
    else:
        mode = "none"

    return has_pat, has_app, mode


_DERIVED_SETTINGS_METADATA: dict[str, _DerivedSettingMetadataSpec] = {
    "github_pat_configured": _DerivedSettingMetadataSpec(
        source_fields=("github_personal_access_token",),
        sensitive=True,
        note="Presence-only signal for startup-managed GitHub PAT wiring.",
    ),
    "github_app_configured": _DerivedSettingMetadataSpec(
        source_fields=("github_app_id", "github_app_private_key", "key_vault_url"),
        note="Derived from GitHub App ID plus either a runtime-managed private key or legacy Key Vault wiring. This is configuration presence, not proof of an active live auth path.",
    ),
    "github_auth_mode": _DerivedSettingMetadataSpec(
        source_fields=("github_personal_access_token", "github_app_id", "github_app_private_key", "key_vault_url"),
        note="Derived from the active PAT runtime path plus any additional GitHub App configuration metadata.",
    ),
    "openai_compatible_api_key_configured": _DerivedSettingMetadataSpec(
        source_fields=("openai_compatible_api_key",),
        sensitive=True,
        note="Presence-only signal for a runtime-managed or env-overridden provider API key.",
    ),
    "agent_handoff_webhook_configured": _DerivedSettingMetadataSpec(
        source_fields=("agent_handoff_webhook_url",),
        sensitive=True,
        note="Derived from the Assign-to-Agent webhook URL secret; the full URL is intentionally hidden.",
    ),
    "agent_handoff_webhook_host": _DerivedSettingMetadataSpec(
        source_fields=("agent_handoff_webhook_url",),
        note="Derived from the Assign-to-Agent webhook URL secret; only the destination host is exposed.",
    ),
}

_COMPUTED_SETTINGS_FIELDS: frozenset[str] = frozenset(
    {
        "storage_mode",
        "storage_backend",
        "api_auth_enabled",
        "admin_api_auth_enabled",
        "entra_auth_enabled",
    }
)


def _setting_source_for_attr(attr_name: str, startup_fields_set: set[str]) -> AppSettingSource:
    """Resolve operator-visible provenance for one runtime settings attribute."""
    if attr_name in _runtime_override_keys:
        return AppSettingSource.RUNTIME_OVERRIDE
    if attr_name in _persisted_runtime_override_keys:
        return AppSettingSource.PERSISTED_RUNTIME_OVERRIDE
    if attr_name in startup_fields_set:
        return AppSettingSource.ENV
    return AppSettingSource.DEFAULT


def _startup_configured_fields() -> set[str]:
    """Return settings keys explicitly configured through env or the selected env file."""
    env_path = _env_file_path()
    try:
        env_stat = env_path.stat()
        env_file_marker: tuple[str, int | None, int | None] = (
            str(env_path),
            env_stat.st_mtime_ns,
            env_stat.st_size,
        )
    except FileNotFoundError:
        env_file_marker = (str(env_path), None, None)

    explicit_env = tuple(
        sorted(
            (spec.env_var, value)
            for spec in ALL_SETTING_SPECS_BY_KEY.values()
            if (value := os.getenv(spec.env_var)) is not None
        )
    )
    override_env = (
        os.getenv("PIPELINEHEALER_ENV_FILE_PATH"),
        os.getenv("PIPELINEHEALER_REPO_ROOT"),
    )
    signature = (override_env, env_file_marker, explicit_env)

    global _startup_configured_fields_cache_signature, _startup_configured_fields_cache_value
    if signature == _startup_configured_fields_cache_signature:
        return set(_startup_configured_fields_cache_value)

    configured = {
        key
        for key, spec in ALL_SETTING_SPECS_BY_KEY.items()
        if os.getenv(spec.env_var) is not None
    }

    if env_file_marker[1] is not None:
        try:
            values = dotenv_values(env_path)
        except Exception:
            values = {}
        for key, spec in ALL_SETTING_SPECS_BY_KEY.items():
            if spec.env_var in values:
                configured.add(key)

    _startup_configured_fields_cache_signature = signature
    _startup_configured_fields_cache_value = frozenset(configured)
    return configured


def _setting_source_for_derived_attr(
    source_fields: tuple[str, ...],
    startup_fields_set: set[str],
) -> AppSettingSource:
    """Resolve provenance for fields derived from hidden startup-only settings."""
    for source_field in source_fields:
        if source_field in _runtime_override_keys:
            return AppSettingSource.RUNTIME_OVERRIDE
        if source_field in _persisted_runtime_override_keys:
            return AppSettingSource.PERSISTED_RUNTIME_OVERRIDE
        if source_field in startup_fields_set:
            return AppSettingSource.ENV
    return AppSettingSource.DEFAULT


def _build_settings_metadata() -> dict[str, AppSettingMetadataView]:
    """Build per-field provenance metadata for the admin settings view."""
    settings = get_settings()
    startup_fields_set = _startup_configured_fields()
    mutable_attr_names = {attr_name for attr_name, _ in _MUTABLE_SETTINGS_ENV_KEYS}
    metadata: dict[str, AppSettingMetadataView] = {}

    for field_name in AppSettingsView.model_fields:
        if field_name == "settings_metadata":
            continue
        if field_name in _COMPUTED_SETTINGS_FIELDS:
            metadata[field_name] = AppSettingMetadataView(
                source=AppSettingSource.COMPUTED,
                mutable=False,
                requires_restart=False,
                durable=True,
            )
            continue

        derived_metadata = _DERIVED_SETTINGS_METADATA.get(field_name)
        if derived_metadata is not None:
            metadata[field_name] = AppSettingMetadataView(
                source=_setting_source_for_derived_attr(
                    derived_metadata.source_fields,
                    startup_fields_set,
                ),
                mutable=False,
                requires_restart=True,
                durable=True,
                sensitive=derived_metadata.sensitive,
                note=derived_metadata.note,
            )
            continue

        if not hasattr(settings, field_name):
            metadata[field_name] = AppSettingMetadataView(
                source=AppSettingSource.COMPUTED,
                mutable=False,
                requires_restart=False,
                durable=True,
            )
            continue

        mutable = field_name in mutable_attr_names
        source = _setting_source_for_attr(field_name, startup_fields_set)
        metadata[field_name] = AppSettingMetadataView(
            source=source,
            mutable=mutable,
            requires_restart=not mutable,
            durable=source != AppSettingSource.RUNTIME_OVERRIDE,
        )

    return metadata


def _build_setup_status(storage: ActivityStorage | None = None) -> SetupStatusView:
    """Build setup-readiness summary for UI-first runtime configuration."""
    settings = get_settings()

    try:
        resolve_storage_mode(settings)
        storage_bootstrap = SetupCheckView(ready=True, detail="Bootstrap storage configuration is valid.")
    except Exception as exc:
        storage_bootstrap = SetupCheckView(ready=False, detail=str(exc))

    auth_ready = True
    auth_detail = f"Auth mode: {settings.auth_mode}."
    if settings.auth_mode in {"entra", "hybrid"} and not (
        settings.entra_tenant_id and settings.entra_client_id
    ):
        auth_ready = False
        auth_detail = "ENTRA_TENANT_ID and ENTRA_CLIENT_ID are required for Entra-backed auth."
    auth_bootstrap = SetupCheckView(ready=auth_ready, detail=auth_detail)

    if settings.settings_secret_backend == "azure_key_vault":
        secret_backend_ready = SetupCheckView(
            ready=bool(settings.key_vault_url.strip()),
            detail=(
                "Azure Key Vault runtime secret backend is configured."
                if settings.key_vault_url.strip()
                else "KEY_VAULT_URL is required when SETTINGS_SECRET_BACKEND=azure_key_vault."
            ),
        )
    elif settings.settings_secret_backend == "infisical":
        infisical_ready = bool(settings.infisical_project_id.strip())
        secret_backend_ready = SetupCheckView(
            ready=infisical_ready,
            detail=(
                "Infisical runtime secret backend is configured."
                if infisical_ready
                else "INFISICAL_PROJECT_ID is required when SETTINGS_SECRET_BACKEND=infisical."
            ),
        )
    else:
        secret_backend_ready = SetupCheckView(
            ready=bool(settings.settings_db_encryption_key.strip()),
            detail=(
                "Encrypted database secret backend is configured."
                if settings.settings_db_encryption_key.strip()
                else "SETTINGS_DB_ENCRYPTION_KEY is required to manage runtime secrets in encrypted_db mode."
            ),
        )

    llm_ready = False
    llm_detail = "Provider runtime configuration is incomplete."
    if settings.llm_provider == "azure_openai":
        llm_ready = bool(settings.azure_openai_endpoint and settings.azure_openai_deployment_name)
        llm_detail = (
            "Azure OpenAI endpoint and deployment are configured."
            if llm_ready
            else "Configure Azure OpenAI endpoint and deployment in Settings or via env override."
        )
    elif settings.llm_provider == "openai_compatible":
        llm_ready = bool(
            settings.openai_compatible_base_url
            and settings.openai_compatible_model
            and settings.openai_compatible_api_key
        )
        llm_detail = (
            "OpenAI-compatible runtime and API key are configured."
            if llm_ready
            else "Configure the base URL, model, and API key for the OpenAI-compatible provider."
        )
    elif settings.llm_provider == "codex_app_server":
        llm_ready = True
        if settings.codex_app_server_transport == "websocket":
            llm_ready = bool(
                settings.codex_app_server_ws_url
                and (
                    settings.codex_app_server_ws_bearer_token
                    or settings.codex_app_server_ws_token_file
                    or settings.codex_app_server_ws_shared_secret_file
                )
            )
        llm_detail = (
            "Codex App Server provider configuration is present."
            if llm_ready
            else "Configure Codex App Server WebSocket URL and auth, or switch transport to stdio."
        )
    llm_runtime = SetupCheckView(ready=llm_ready, detail=llm_detail)

    has_pat, has_app, _ = _resolve_github_auth_mode()
    if has_pat:
        github_runtime = SetupCheckView(
            ready=True,
            detail=(
                "GitHub runtime auth is configured with a PAT."
                if not has_app
                else "GitHub runtime auth is configured with a PAT. GitHub App inputs are also present but are not the active live auth path."
            ),
        )
    elif has_app:
        github_runtime = SetupCheckView(
            ready=False,
            detail=(
                "GitHub App inputs are configured, but the current live GitHub API runtime still requires a PAT."
            ),
        )
    else:
        github_runtime = SetupCheckView(
            ready=False,
            detail="Configure a GitHub PAT for the current live GitHub API runtime path.",
        )

    webhook_ready = True
    webhook_messages: list[str] = []
    if settings.verify_webhook_signature and not settings.github_webhook_secret:
        webhook_ready = False
        webhook_messages.append("GitHub webhook secret is required while signature verification is enabled.")
    if settings.jenkins_bridge_enabled and not settings.jenkins_bridge_shared_secret:
        webhook_ready = False
        webhook_messages.append("Jenkins bridge shared secret is required while the bridge is enabled.")
    if (
        settings.agent_handoff_enabled
        and settings.agent_handoff_mode == "webhook"
        and not settings.agent_handoff_webhook_url
    ):
        webhook_ready = False
        webhook_messages.append("Assign-to-Agent webhook mode requires a destination URL secret.")
    if not webhook_messages:
        webhook_messages.append("Webhook and handoff secret dependencies are satisfied.")
    webhook_secrets = SetupCheckView(ready=webhook_ready, detail=" ".join(webhook_messages))

    overall_ready = all(
        check.ready
        for check in (
            storage_bootstrap,
            auth_bootstrap,
            secret_backend_ready,
            llm_runtime,
            github_runtime,
            webhook_secrets,
        )
    )
    return SetupStatusView(
        ready=overall_ready,
        storage_bootstrap=storage_bootstrap,
        auth_bootstrap=auth_bootstrap,
        secret_backend=secret_backend_ready,
        llm_runtime=llm_runtime,
        github_runtime=github_runtime,
        webhook_secrets=webhook_secrets,
    )


async def _build_secret_settings_views(storage: ActivityStorage) -> list[SecretSettingView]:
    """Build non-sensitive secret metadata views for the admin UI."""
    settings = get_settings()
    startup_fields_set = _startup_configured_fields()
    store = build_secret_store(storage)
    views: list[SecretSettingView] = []
    try:
        for spec in SECRET_SETTING_SPECS:
            env_overridden = spec.key in startup_fields_set
            current_value = str(getattr(settings, spec.key, "") or "")
            if env_overridden:
                views.append(
                    SecretSettingView(
                        key=spec.key,
                        configured=bool(current_value.strip()),
                        source="env",
                        backend="env",
                        requires_restart=spec.requires_restart,
                        overridden_by_env=True,
                        safe_hint=(
                            (urlparse(current_value).hostname or "")
                            if spec.value_type == "secret_url" and current_value.strip()
                            else None
                        ),
                        note="This secret is currently overridden by environment configuration.",
                    )
                )
                continue

            metadata = await store.describe(spec.key)
            views.append(
                SecretSettingView(
                    key=spec.key,
                    configured=metadata.configured,
                    source="secret_store" if metadata.configured else "missing",
                    backend=metadata.backend,
                    requires_restart=spec.requires_restart,
                    overridden_by_env=False,
                    last_updated_at=metadata.last_updated_at,
                    safe_hint=metadata.safe_hint,
                    note=(
                        f"Stored in {metadata.backend}."
                        if metadata.configured
                        else "Not configured in the runtime secret store."
                    ),
                )
            )
    finally:
        await store.close()
    return views


def _build_settings_view(storage: ActivityStorage | None = None) -> AppSettingsView:
    """Build the API response for settings from current runtime configuration."""
    settings = get_settings()
    has_pat, has_app, github_auth_mode = _resolve_github_auth_mode()
    handoff_webhook_host = (urlparse(settings.agent_handoff_webhook_url).hostname or "").strip().lower()

    return AppSettingsView(
        environment=settings.environment,
        storage_mode=_get_storage_mode_name(storage, settings.environment),
        storage_backend=_get_storage_backend_name(storage),
        heal_mode=settings.heal_mode,
        auto_apply_remediation=settings.auto_apply_remediation,
        auto_create_pr=settings.auto_create_pr,
        jenkins_bridge_allow_pr=settings.jenkins_bridge_allow_pr,
        auto_create_issue=settings.auto_create_issue,
        auto_retry_workflow=settings.auto_retry_workflow,
        auto_create_tracking_issue_for_prs=settings.auto_create_tracking_issue_for_prs,
        max_remediation_attempts=settings.max_remediation_attempts,
        pipeline_step_timeout_seconds=settings.pipeline_step_timeout_seconds,
        github_api_max_retries=settings.github_api_max_retries,
        github_api_retry_base_seconds=settings.github_api_retry_base_seconds,
        github_api_retry_max_seconds=settings.github_api_retry_max_seconds,
        log_prompt_max_chars=settings.log_prompt_max_chars,
        log_prompt_head_chars=settings.log_prompt_head_chars,
        log_prompt_tail_chars=settings.log_prompt_tail_chars,
        verify_webhook_signature=settings.verify_webhook_signature,
        verify_webhook_signature_in_development=settings.verify_webhook_signature_in_development,
        settings_secret_backend=settings.settings_secret_backend,
        api_auth_enabled=bool(settings.api_auth_key),
        admin_api_auth_enabled=bool(settings.admin_api_key),
        auth_mode=settings.auth_mode,
        entra_auth_enabled=bool(settings.entra_tenant_id and settings.entra_client_id),
        entra_admin_roles=[role for role in settings.entra_admin_roles if role],
        github_app_id=settings.github_app_id,
        github_pat_configured=has_pat,
        github_app_configured=has_app,
        github_auth_mode=github_auth_mode,
        jenkins_bridge_enabled=settings.jenkins_bridge_enabled,
        jenkins_bridge_max_skew_seconds=settings.jenkins_bridge_max_skew_seconds,
        jenkins_bridge_replay_ttl_seconds=settings.jenkins_bridge_replay_ttl_seconds,
        jenkins_bridge_max_body_bytes=settings.jenkins_bridge_max_body_bytes,
        gh_aw_tools_enabled=settings.gh_aw_tools_enabled,
        gh_aw_ingestion_mode=settings.gh_aw_ingestion_mode,
        gh_aw_known_workflows=_normalize_workflow_names(settings.gh_aw_known_workflows),
        external_diagnostics_wait_seconds=settings.external_diagnostics_wait_seconds,
        external_diagnostics_poll_interval_seconds=(
            settings.external_diagnostics_poll_interval_seconds
        ),
        agent_handoff_enabled=settings.agent_handoff_enabled,
        agent_handoff_mode=settings.agent_handoff_mode,
        agent_handoff_webhook_configured=bool(settings.agent_handoff_webhook_url.strip()),
        agent_handoff_webhook_host=handoff_webhook_host,
        agent_handoff_webhook_allowlist=_safe_hostname_allowlist(
            settings.agent_handoff_webhook_allowlist
        ),
        agent_handoff_timeout_seconds=settings.agent_handoff_timeout_seconds,
        agent_handoff_max_retries=settings.agent_handoff_max_retries,
        agent_handoff_default_target=settings.agent_handoff_default_target,
        agent_handoff_enabled_targets=list(settings.agent_handoff_enabled_targets),
        codex_app_server_handoff_configured=bool(settings.codex_app_server_handoff_url.strip()),
        openclaw_handoff_configured=bool(settings.openclaw_handoff_url.strip()),
        hermes_handoff_configured=bool(settings.hermes_handoff_url.strip()),
        ph_allowed_repos=_safe_settings_allowlist(settings.ph_allowed_repos),
        cors_allowed_origins=settings.cors_allowed_origins,
        cors_allow_origin_regex=settings.cors_allow_origin_regex,
        llm_provider=settings.llm_provider,
        openai_compatible_base_url=settings.openai_compatible_base_url,
        openai_compatible_model=settings.openai_compatible_model,
        codex_app_server_transport=settings.codex_app_server_transport,
        codex_app_server_command=settings.codex_app_server_command,
        codex_app_server_model=settings.codex_app_server_model,
        codex_app_server_turn_timeout_ms=settings.codex_app_server_turn_timeout_ms,
        codex_app_server_ws_url=settings.codex_app_server_ws_url,
        codex_app_server_ws_allow_remote=settings.codex_app_server_ws_allow_remote,
        llm_model_analysis=settings.llm_model_analysis,
        llm_model_diagnosis=settings.llm_model_diagnosis,
        llm_model_remediation=settings.llm_model_remediation,
        openai_compatible_api_key_configured=bool(settings.openai_compatible_api_key),
        mcp_enabled=settings.mcp_enabled,
        mcp_provider=settings.mcp_provider,
        mcp_read_only=settings.mcp_read_only,
        mcp_timeout_seconds=settings.mcp_timeout_seconds,
        mcp_max_retries=settings.mcp_max_retries,
        mcp_tool_policies=_normalize_mcp_tool_policies(settings.mcp_tool_policies),
        mcp_repo_allowlist=_safe_settings_allowlist(settings.mcp_repo_allowlist),
        azure_openai_endpoint=settings.azure_openai_endpoint,
        azure_openai_deployment_name=settings.azure_openai_deployment_name,
        azure_openai_api_version=settings.azure_openai_api_version,
        azure_openai_chat_api_version=settings.azure_openai_chat_api_version,
        infisical_project_id=settings.infisical_project_id,
        infisical_environment=settings.infisical_environment,
        infisical_secret_path=settings.infisical_secret_path,
        infisical_cli_path=settings.infisical_cli_path,
        infisical_api_url=settings.infisical_api_url,
        setup_status=_build_setup_status(storage),
        settings_metadata=_build_settings_metadata(),
    )


# Lightweight demo audit buffer (non-durable by design for hackathon runtime).
_admin_settings_audit: list[AdminSettingsAuditEntry] = []
_MAX_ADMIN_SETTINGS_AUDIT_ENTRIES = 200
_MUTABLE_SETTINGS_ENV_KEYS: tuple[tuple[str, str], ...] = RUNTIME_NON_SECRET_ENV_KEYS


def clear_admin_settings_audit() -> None:
    """Clear in-memory admin settings audit log (useful for tests)."""
    _admin_settings_audit.clear()


def clear_settings_runtime_provenance() -> None:
    """Clear in-process runtime provenance markers (useful for tests)."""
    global _startup_configured_fields_cache_signature, _startup_configured_fields_cache_value
    _runtime_override_keys.clear()
    _persisted_runtime_override_keys.clear()
    _startup_configured_fields_cache_signature = None
    _startup_configured_fields_cache_value = frozenset()


def _build_admin_settings_actor_fingerprint(
    *,
    request: Request,
    x_admin_key: str | None,
) -> str | None:
    """Return privacy-safe actor fingerprint for admin settings operations."""
    settings = get_settings()
    principal = get_request_principal(request)
    if principal is not None:
        return f"entra:{principal.subject[:24]}"
    if x_admin_key:
        salted = f"{settings.audit_salt}:{x_admin_key}" if settings.audit_salt else x_admin_key
        return f"admin_key:sha256:{hashlib.sha256(salted.encode('utf-8')).hexdigest()[:12]}"
    return None


async def _append_admin_settings_audit_entry(
    *,
    storage: ActivityStorage,
    entry: AdminSettingsAuditEntry,
) -> None:
    """Append one admin settings audit entry with storage persistence fallback."""
    _admin_settings_audit.append(entry)
    try:
        await storage.append_admin_settings_audit_entry(entry.model_dump(mode="json"))
    except Exception as exc:
        logger.warning("Failed to persist admin settings audit entry: %s", exc)

    # Keep memory bounded for long-running pods.
    if len(_admin_settings_audit) > _MAX_ADMIN_SETTINGS_AUDIT_ENTRIES:
        del _admin_settings_audit[: len(_admin_settings_audit) - _MAX_ADMIN_SETTINGS_AUDIT_ENTRIES]


_LEARNING_QUEUE_ALLOWED_STATUS = {
    LearningQueueStatus.CANDIDATE.value,
    LearningQueueStatus.APPROVED.value,
    LearningQueueStatus.REJECTED.value,
    LearningQueueStatus.ACTIVE.value,
    LearningQueueStatus.RETIRED.value,
}
_LEARNING_QUEUE_ALLOWED_ACTIONS = {
    "approve": LearningQueueStatus.APPROVED.value,
    "reject": LearningQueueStatus.REJECTED.value,
    "activate": LearningQueueStatus.ACTIVE.value,
    "retire": LearningQueueStatus.RETIRED.value,
    "reset_candidate": LearningQueueStatus.CANDIDATE.value,
}
_LEARNING_PROMOTION_MIN_OCCURRENCES = 2
_LEARNING_PROMOTION_MIN_SUCCESS_RATE = 0.8
_LEARNING_PROMOTION_MIN_SAMPLE_SIZE = 2
_LEARNING_PROMOTION_MIN_VERIFICATION_SAMPLE_SIZE = 1
_LEARNING_PROMOTION_MIN_VERIFICATION_PASS_RATE = 0.8


def _normalize_reason_code(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_verification_outcome(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {
        LearningVerificationOutcome.PASS.value,
        LearningVerificationOutcome.PARTIAL.value,
        LearningVerificationOutcome.FAIL.value,
    }:
        return normalized
    return None


def _normalize_guidance_effectiveness(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {
        LearningGuidanceEffectiveness.HELPED.value,
        LearningGuidanceEffectiveness.NEUTRAL.value,
        LearningGuidanceEffectiveness.HURT.value,
    }:
        return normalized
    return None


def _derive_verification_overall(
    *,
    identification: str,
    diagnosis: str,
    remediation: str,
) -> str:
    outcomes = {identification, diagnosis, remediation}
    if LearningVerificationOutcome.FAIL.value in outcomes:
        return LearningVerificationOutcome.FAIL.value
    if outcomes == {LearningVerificationOutcome.PASS.value}:
        return LearningVerificationOutcome.PASS.value
    return LearningVerificationOutcome.PARTIAL.value


def _extract_activity_verification(activity: ActivityRecord) -> dict[str, Any] | None:
    """Extract normalized verification feedback from one activity result."""
    remediation = activity.remediation_result
    if remediation is None or not isinstance(remediation.details, dict):
        return None

    payload = remediation.details.get("verification")
    if not isinstance(payload, dict):
        return None

    identification = _normalize_verification_outcome(payload.get("identification"))
    diagnosis = _normalize_verification_outcome(payload.get("diagnosis"))
    remediation_outcome = _normalize_verification_outcome(payload.get("remediation"))
    if not identification or not diagnosis or not remediation_outcome:
        return None

    overall = _normalize_verification_outcome(payload.get("overall")) or _derive_verification_overall(
        identification=identification,
        diagnosis=diagnosis,
        remediation=remediation_outcome,
    )
    guidance_effectiveness = _normalize_guidance_effectiveness(
        payload.get("guidance_effectiveness")
    )
    return {
        "identification": identification,
        "diagnosis": diagnosis,
        "remediation": remediation_outcome,
        "overall": overall,
        "guidance_effectiveness": guidance_effectiveness,
        "recorded_at": payload.get("recorded_at"),
        "issue_number": payload.get("issue_number"),
    }


def _extract_applied_learning_context(activity: ActivityRecord) -> dict[str, Any] | None:
    """Extract normalized applied learning guidance metadata from one activity result."""
    remediation = activity.remediation_result
    if remediation is None or not isinstance(remediation.details, dict):
        return None
    payload = remediation.details.get("applied_learning_context")
    if not isinstance(payload, dict):
        return None
    candidate_id = str(payload.get("id") or "").strip()
    if not candidate_id:
        return None
    return {
        "id": candidate_id,
        "title": str(payload.get("title") or "").strip(),
        "reason_code": _normalize_reason_code(payload.get("reason_code")),
        "match_rank": payload.get("match_rank"),
        "match_score": payload.get("match_score"),
    }


def _compute_guidance_metrics(
    candidate_id: str,
    activities: list[ActivityRecord],
) -> dict[str, int | float]:
    """Compute bounded applied-guidance metrics for one learning candidate."""
    guidance_application_count = 0
    guidance_feedback_count = 0
    guidance_helped_count = 0
    guidance_neutral_count = 0
    guidance_hurt_count = 0

    for activity in activities:
        applied_learning = _extract_applied_learning_context(activity)
        if applied_learning is None or applied_learning.get("id") != candidate_id:
            continue
        guidance_application_count += 1
        verification = _extract_activity_verification(activity)
        guidance_effectiveness = (
            str(verification.get("guidance_effectiveness") or "") if verification else ""
        )
        if guidance_effectiveness == LearningGuidanceEffectiveness.HELPED.value:
            guidance_feedback_count += 1
            guidance_helped_count += 1
        elif guidance_effectiveness == LearningGuidanceEffectiveness.NEUTRAL.value:
            guidance_feedback_count += 1
            guidance_neutral_count += 1
        elif guidance_effectiveness == LearningGuidanceEffectiveness.HURT.value:
            guidance_feedback_count += 1
            guidance_hurt_count += 1

    guidance_help_rate = (
        round((guidance_helped_count / guidance_feedback_count), 4)
        if guidance_feedback_count > 0
        else 0.0
    )
    return {
        "guidance_application_count": guidance_application_count,
        "guidance_feedback_count": guidance_feedback_count,
        "guidance_helped_count": guidance_helped_count,
        "guidance_neutral_count": guidance_neutral_count,
        "guidance_hurt_count": guidance_hurt_count,
        "guidance_help_rate": guidance_help_rate,
    }


def _extract_activity_reason_code(activity: ActivityRecord) -> str | None:
    """Extract stable reason code from activity diagnosis/remediation context."""
    diagnosis_details = activity.diagnosis.error_details if activity.diagnosis else {}
    if isinstance(diagnosis_details, dict):
        reason_code = _normalize_reason_code(diagnosis_details.get("reason_code"))
        if reason_code:
            return reason_code
        classification_pattern = _normalize_reason_code(
            diagnosis_details.get("classification_pattern")
        )
        if classification_pattern:
            return classification_pattern
        classification_signal = _normalize_reason_code(
            diagnosis_details.get("classification_signal")
        )
        if classification_signal:
            return classification_signal

    remediation_details = activity.remediation_result.details if activity.remediation_result else {}
    if isinstance(remediation_details, dict):
        reason_code = _normalize_reason_code(remediation_details.get("reason_code"))
        if reason_code:
            return reason_code
    if activity.failure_context and activity.failure_context.signal:
        return _normalize_reason_code(activity.failure_context.signal)
    return None


def _evaluate_learning_promotion_readiness(
    candidate: LearningQueueItem,
) -> LearningPromotionReadiness:
    """Evaluate whether a candidate is safe to activate as a promoted playbook."""
    # Gates are intentionally deterministic so operators can reason about
    # activation outcomes before clicking any decision action.
    occurrence_count = max(int(candidate.occurrence_count), 0)
    success_count = max(int(candidate.success_count), 0)
    sample_size = len(candidate.sample_activity_ids)
    success_rate = (success_count / occurrence_count) if occurrence_count > 0 else 0.0

    status_gate_passed = candidate.status in {
        LearningQueueStatus.APPROVED,
        LearningQueueStatus.ACTIVE,
    }
    occurrence_gate_passed = occurrence_count >= _LEARNING_PROMOTION_MIN_OCCURRENCES
    success_rate_gate_passed = success_rate >= _LEARNING_PROMOTION_MIN_SUCCESS_RATE
    sample_gate_passed = sample_size >= _LEARNING_PROMOTION_MIN_SAMPLE_SIZE
    verification_sample_count = max(int(candidate.verification_sample_count), 0)
    verification_pass_rate = (
        max(float(candidate.verification_pass_rate), 0.0) if verification_sample_count > 0 else 0.0
    )
    verification_sample_gate_passed = (
        verification_sample_count >= _LEARNING_PROMOTION_MIN_VERIFICATION_SAMPLE_SIZE
    )
    verification_gate_passed = (
        verification_sample_gate_passed
        and verification_pass_rate >= _LEARNING_PROMOTION_MIN_VERIFICATION_PASS_RATE
    )

    reasons: list[str] = []
    if not status_gate_passed:
        if candidate.status == LearningQueueStatus.CANDIDATE:
            reasons.append("status_candidate_requires_approval")
        elif candidate.status == LearningQueueStatus.REJECTED:
            reasons.append("status_rejected")
        elif candidate.status == LearningQueueStatus.RETIRED:
            reasons.append("status_retired")
        else:
            reasons.append("status_not_approved")
    if not occurrence_gate_passed:
        reasons.append("occurrence_below_threshold")
    if not success_rate_gate_passed:
        reasons.append("success_rate_below_threshold")
    if not sample_gate_passed:
        reasons.append("sample_size_below_threshold")
    if not verification_sample_gate_passed:
        reasons.append("verification_sample_below_threshold")
    elif not verification_gate_passed:
        reasons.append("verification_pass_rate_below_threshold")

    ready = (
        status_gate_passed
        and occurrence_gate_passed
        and success_rate_gate_passed
        and sample_gate_passed
        and verification_gate_passed
    )
    requires_force_activate = not ready and candidate.status != LearningQueueStatus.ACTIVE

    return LearningPromotionReadiness(
        ready=ready,
        status_gate_passed=status_gate_passed,
        occurrence_gate_passed=occurrence_gate_passed,
        success_rate_gate_passed=success_rate_gate_passed,
        sample_gate_passed=sample_gate_passed,
        verification_sample_gate_passed=verification_sample_gate_passed,
        verification_gate_passed=verification_gate_passed,
        requires_force_activate=requires_force_activate,
        reasons=reasons,
        min_occurrences=_LEARNING_PROMOTION_MIN_OCCURRENCES,
        min_success_rate=_LEARNING_PROMOTION_MIN_SUCCESS_RATE,
        min_sample_size=_LEARNING_PROMOTION_MIN_SAMPLE_SIZE,
        min_verification_sample_size=_LEARNING_PROMOTION_MIN_VERIFICATION_SAMPLE_SIZE,
        min_verification_pass_rate=_LEARNING_PROMOTION_MIN_VERIFICATION_PASS_RATE,
        occurrence_count=occurrence_count,
        success_rate=round(success_rate, 4),
        sample_size=sample_size,
        verification_sample_count=verification_sample_count,
        verification_pass_rate=round(verification_pass_rate, 4),
    )


def _build_learning_fingerprint(
    *,
    failure_type: FailureType | None,
    reason_code: str | None,
    proposed_action: str,
    suggested_playbook: str,
) -> str:
    material = "|".join(
        [
            (failure_type.value if failure_type else "unknown"),
            reason_code or "unknown",
            proposed_action.lower(),
            suggested_playbook.strip().lower()[:240],
        ]
    )
    return hashlib.sha1(material.encode("utf-8")).hexdigest()  # noqa: S324


def _summarize_learning_title(
    failure_type: FailureType | None,
    reason_code: str | None,
) -> str:
    failure = failure_type.value if failure_type else "unknown"
    if reason_code:
        return f"{failure}: {reason_code}"
    return f"{failure}: unclassified recurring incident"


async def _collect_bounded_activities(
    storage: ActivityStorage,
    *,
    max_scan: int,
    since: datetime | None = None,
) -> list[ActivityRecord]:
    """Collect activities with bounded pagination for refresh and metrics recomputation."""
    collected: list[ActivityRecord] = []
    offset = 0
    page_size = min(100, max_scan)
    while len(collected) < max_scan:
        remaining = max_scan - len(collected)
        limit = min(page_size, remaining)
        batch = await storage.get_activities(limit=limit, offset=offset, since=since)
        if not batch:
            break
        collected.extend(batch)
        offset += len(batch)
        if len(batch) < limit:
            break
    return collected


async def _collect_recent_activities(
    storage: ActivityStorage,
    *,
    lookback_hours: float,
    max_scan: int,
) -> list[ActivityRecord]:
    """Collect recent activities with bounded pagination for learning refresh."""
    since = utcnow() - timedelta(hours=lookback_hours)
    return await _collect_bounded_activities(storage, max_scan=max_scan, since=since)


def _extract_learning_candidates(
    activities: list[ActivityRecord],
    *,
    min_occurrences: int,
) -> list[LearningQueueItem]:
    """Build candidate groups from successful completed activities."""
    grouped: dict[str, dict[str, Any]] = {}
    for activity in activities:
        if activity.status != RemediationStatus.COMPLETED:
            continue
        remediation = activity.remediation_result
        if remediation is None or not remediation.success:
            continue
        if activity.failure_type is None:
            continue

        reason_code = _extract_activity_reason_code(activity)
        proposed_action = remediation.action_taken.value
        suggested_playbook = (
            (activity.diagnosis.suggested_fix if activity.diagnosis else "")
            or (activity.diagnosis.root_cause if activity.diagnosis else "")
            or "No suggested fix captured."
        ).strip()
        fingerprint = _build_learning_fingerprint(
            failure_type=activity.failure_type,
            reason_code=reason_code,
            proposed_action=proposed_action,
            suggested_playbook=suggested_playbook,
        )
        bucket = grouped.setdefault(
            fingerprint,
            {
                "fingerprint": fingerprint,
                "title": _summarize_learning_title(activity.failure_type, reason_code),
                "failure_type": activity.failure_type,
                "reason_code": reason_code,
                "proposed_action": proposed_action,
                "suggested_playbook": suggested_playbook,
                "repositories": set(),
                "occurrence_count": 0,
                "success_count": 0,
                "sample_activity_ids": [],
                "verification_sample_count": 0,
                "verification_pass_count": 0,
                "verification_partial_count": 0,
                "verification_fail_count": 0,
                "guidance_application_count": 0,
                "guidance_feedback_count": 0,
                "guidance_helped_count": 0,
                "guidance_neutral_count": 0,
                "guidance_hurt_count": 0,
                "latest_activity_at": None,
            },
        )
        bucket["repositories"].add(activity.repository_name)
        bucket["occurrence_count"] += 1
        bucket["success_count"] += 1
        if len(bucket["sample_activity_ids"]) < 5:
            bucket["sample_activity_ids"].append(activity.id)
        verification = _extract_activity_verification(activity)
        if verification:
            bucket["verification_sample_count"] += 1
            overall = str(verification.get("overall") or "")
            if overall == LearningVerificationOutcome.PASS.value:
                bucket["verification_pass_count"] += 1
            elif overall == LearningVerificationOutcome.PARTIAL.value:
                bucket["verification_partial_count"] += 1
            else:
                bucket["verification_fail_count"] += 1
        latest = bucket["latest_activity_at"]
        if latest is None or (activity.updated_at and activity.updated_at > latest):
            bucket["latest_activity_at"] = activity.updated_at

    candidates: list[LearningQueueItem] = []
    for data in grouped.values():
        if int(data["occurrence_count"]) < min_occurrences:
            continue
        fingerprint = str(data["fingerprint"])
        verification_sample_count = int(data["verification_sample_count"])
        verification_pass_count = int(data["verification_pass_count"])
        verification_partial_count = int(data["verification_partial_count"])
        verification_fail_count = int(data["verification_fail_count"])
        verification_pass_rate = (
            verification_pass_count / verification_sample_count
            if verification_sample_count > 0
            else 0.0
        )
        candidate = LearningQueueItem(
            id=f"learning-{fingerprint[:20]}",
            fingerprint=fingerprint,
            title=str(data["title"]),
            failure_type=data["failure_type"],
            reason_code=data["reason_code"],
            proposed_action=str(data["proposed_action"]),
            suggested_playbook=str(data["suggested_playbook"]),
            repositories=sorted(data["repositories"]),
            occurrence_count=int(data["occurrence_count"]),
            success_count=int(data["success_count"]),
            sample_activity_ids=list(data["sample_activity_ids"]),
            verification_sample_count=verification_sample_count,
            verification_pass_count=verification_pass_count,
            verification_partial_count=verification_partial_count,
            verification_fail_count=verification_fail_count,
            verification_pass_rate=round(verification_pass_rate, 4),
            latest_activity_at=data["latest_activity_at"],
            status=LearningQueueStatus.CANDIDATE,
        )
        candidate.promotion_readiness = _evaluate_learning_promotion_readiness(candidate)
        candidates.append(candidate)

    for candidate in candidates:
        guidance_metrics = _compute_guidance_metrics(candidate.id, activities)
        candidate.guidance_application_count = int(guidance_metrics["guidance_application_count"])
        candidate.guidance_feedback_count = int(guidance_metrics["guidance_feedback_count"])
        candidate.guidance_helped_count = int(guidance_metrics["guidance_helped_count"])
        candidate.guidance_neutral_count = int(guidance_metrics["guidance_neutral_count"])
        candidate.guidance_hurt_count = int(guidance_metrics["guidance_hurt_count"])
        candidate.guidance_help_rate = float(guidance_metrics["guidance_help_rate"])
    epoch = datetime.fromtimestamp(0, tz=utcnow().tzinfo)
    candidates.sort(
        key=lambda item: (item.latest_activity_at or epoch).timestamp(),
        reverse=True,
    )
    return candidates


def _backend_root() -> Path:
    """Resolve the backend project root for local and container layouts."""
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").is_dir():
            return candidate
    return current.parents[2]


def _repo_root() -> Path:
    """Resolve repository root for helper command/script execution."""
    override = os.getenv("PIPELINEHEALER_REPO_ROOT", "").strip()
    if override:
        return Path(override).resolve()

    backend_root = _backend_root()
    for candidate in (backend_root, *backend_root.parents):
        if (candidate / "scripts" / "ph.sh").exists():
            return candidate
    return backend_root


def _env_file_path() -> Path:
    """Resolve mutable env file path used by settings persistence."""
    override = os.getenv("PIPELINEHEALER_ENV_FILE_PATH", "").strip()
    if override:
        return Path(override).resolve()
    return _backend_root() / ".env"


def _env_bool(value: bool) -> str:
    return "true" if value else "false"


def _mutable_runtime_settings_snapshot() -> dict[str, Any]:
    """Capture live mutable runtime settings in normalized Python types."""
    settings = get_settings()
    values: dict[str, Any] = {}
    for attr_name, _ in _MUTABLE_SETTINGS_ENV_KEYS:
        raw = getattr(settings, attr_name)
        if attr_name in {
            "ph_allowed_repos",
            "mcp_repo_allowlist",
            "agent_handoff_webhook_allowlist",
        }:
            if attr_name == "agent_handoff_webhook_allowlist":
                values[attr_name] = _safe_hostname_allowlist(raw)
            else:
                values[attr_name] = _safe_settings_allowlist(raw)
        elif attr_name == "mcp_tool_policies":
            values[attr_name] = _normalize_mcp_tool_policies(raw)
        elif attr_name == "gh_aw_known_workflows":
            values[attr_name] = _normalize_workflow_names(raw)
        else:
            values[attr_name] = raw
    return values


def _runtime_settings_to_env_values(runtime_values: dict[str, Any]) -> dict[str, str]:
    """Convert mutable runtime settings snapshot into env var string values."""
    values: dict[str, str] = {}
    for attr_name, env_key in _MUTABLE_SETTINGS_ENV_KEYS:
        raw = runtime_values[attr_name]
        if attr_name in {
            "ph_allowed_repos",
            "gh_aw_known_workflows",
            "mcp_repo_allowlist",
            "agent_handoff_webhook_allowlist",
        }:
            values[env_key] = ",".join(raw)
        elif attr_name == "mcp_tool_policies":
            if not raw:
                values[env_key] = ""
            else:
                pairs = [f"{tool}={mode}" for tool, mode in sorted(raw.items())]
                values[env_key] = ",".join(pairs)
        elif isinstance(raw, bool):
            values[env_key] = _env_bool(raw)
        else:
            values[env_key] = str(raw)
    return values


def _upsert_env_line(env_file: Path, key: str, value: str) -> None:
    """Replace or append KEY=value in env file while preserving ordering."""
    lines = env_file.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(f"{key}="):
            output.append(f"{key}={value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{key}={value}")
    env_file.write_text("\n".join(output) + "\n", encoding="utf-8")


def _persist_mutable_settings_to_env_file(env_values: dict[str, str]) -> str | None:
    """Persist mutable runtime settings to env file when available."""
    env_file = _env_file_path()
    if not env_file.exists():
        return None

    for key, value in env_values.items():
        _upsert_env_line(env_file, key, value)

    return str(env_file)


async def _persist_mutable_settings_to_storage(
    runtime_values: dict[str, Any],
    storage: ActivityStorage,
) -> None:
    """Persist mutable runtime settings to configured durable storage backend."""
    await storage.upsert_runtime_settings(runtime_values)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _normalize_persisted_mutable_value(attr_name: str, value: Any) -> Any:
    if attr_name == "heal_mode":
        normalized = str(value).strip().lower()
        if normalized not in {"safe", "demo", "freestyle", "debug"}:
            raise ValueError("invalid heal_mode")
        return normalized
    if attr_name in {
        "auto_apply_remediation",
        "auto_create_pr",
        "jenkins_bridge_allow_pr",
        "auto_create_issue",
        "auto_retry_workflow",
        "auto_create_tracking_issue_for_prs",
        "verify_webhook_signature",
        "verify_webhook_signature_in_development",
        "gh_aw_tools_enabled",
        "jenkins_bridge_enabled",
        "agent_handoff_enabled",
        "mcp_enabled",
        "mcp_read_only",
    }:
        return _coerce_bool(value)
    if attr_name in {
        "max_remediation_attempts",
        "github_api_max_retries",
        "log_prompt_max_chars",
        "log_prompt_head_chars",
        "log_prompt_tail_chars",
        "jenkins_bridge_max_skew_seconds",
        "jenkins_bridge_replay_ttl_seconds",
        "jenkins_bridge_max_body_bytes",
        "agent_handoff_max_retries",
        "mcp_max_retries",
    }:
        return int(value)
    if attr_name in {
        "pipeline_step_timeout_seconds",
        "github_api_retry_base_seconds",
        "github_api_retry_max_seconds",
        "agent_handoff_timeout_seconds",
        "mcp_timeout_seconds",
    }:
        return float(value)
    if attr_name == "external_diagnostics_wait_seconds":
        wait_seconds = float(value)
        if wait_seconds < 0.0 or wait_seconds > 900.0:
            raise ValueError("invalid external_diagnostics_wait_seconds")
        return wait_seconds
    if attr_name == "external_diagnostics_poll_interval_seconds":
        poll_seconds = float(value)
        if poll_seconds <= 0.0 or poll_seconds > 120.0:
            raise ValueError("invalid external_diagnostics_poll_interval_seconds")
        return poll_seconds
    if attr_name == "gh_aw_ingestion_mode":
        normalized = str(value).strip().lower()
        if normalized not in {"disabled", "passive", "hybrid"}:
            raise ValueError("invalid gh_aw_ingestion_mode")
        return normalized
    if attr_name == "gh_aw_known_workflows":
        if not isinstance(value, list):
            raise ValueError("invalid gh_aw_known_workflows")
        return _normalize_workflow_names(value)
    if attr_name == "agent_handoff_mode":
        normalized = str(value).strip().lower()
        if normalized not in {"copy_only", "webhook"}:
            raise ValueError("invalid agent_handoff_mode")
        return normalized
    if attr_name == "agent_handoff_webhook_allowlist":
        if not isinstance(value, list):
            raise ValueError("invalid agent_handoff_webhook_allowlist")
        return _normalize_hostname_allowlist(value)
    if attr_name == "ph_allowed_repos":
        if not isinstance(value, list):
            raise ValueError("invalid ph_allowed_repos")
        return _normalize_allowed_repo_list(value)
    if attr_name == "mcp_repo_allowlist":
        if not isinstance(value, list):
            raise ValueError("invalid mcp_repo_allowlist")
        return _normalize_allowed_repo_list(value)
    if attr_name == "mcp_tool_policies":
        if not isinstance(value, dict):
            raise ValueError("invalid mcp_tool_policies")
        return _normalize_mcp_tool_policies(value)
    if attr_name == "azure_openai_deployment_name":
        return str(value).strip()
    if attr_name in {
        "azure_openai_endpoint",
        "azure_openai_api_version",
        "azure_openai_chat_api_version",
        "openai_compatible_base_url",
        "openai_compatible_model",
        "github_app_id",
    }:
        return str(value).strip()
    if attr_name in {"llm_model_analysis", "llm_model_diagnosis", "llm_model_remediation"}:
        return str(value).strip()
    if attr_name == "llm_provider":
        try:
            return resolve_llm_provider(str(value)).value
        except ValueError as exc:
            raise ValueError("invalid llm_provider") from exc
    if attr_name == "mcp_provider":
        normalized = str(value).strip().lower()
        if normalized not in {"disabled", "github", "azure_monitor", "custom"}:
            raise ValueError("invalid mcp_provider")
        return normalized
    return value


async def apply_persisted_runtime_settings(
    storage: ActivityStorage,
    workflow: PipelineHealerWorkflow | None = None,
) -> None:
    """Apply persisted mutable runtime settings at startup, if available.

    Called during lifespan init with explicit storage/workflow references.
    """
    settings = get_settings()
    startup_snapshot = load_settings_snapshot()
    startup_fields_set = _startup_configured_fields()
    persisted = await storage.get_runtime_settings() or {}
    changed_keys: list[str] = []
    applied_keys: set[str] = set()
    for attr_name, _ in _MUTABLE_SETTINGS_ENV_KEYS:
        if attr_name in startup_fields_set:
            setattr(settings, attr_name, getattr(startup_snapshot, attr_name))
            continue
        if attr_name not in persisted:
            continue
        try:
            normalized = _normalize_persisted_mutable_value(attr_name, persisted[attr_name])
        except Exception:
            logger.warning(
                "Skipping invalid persisted runtime setting: %s",
                attr_name,
            )
            continue
        setattr(settings, attr_name, normalized)
        changed_keys.append(attr_name)
        applied_keys.add(attr_name)

    secret_store = build_secret_store(storage)
    try:
        for spec in SECRET_SETTING_SPECS:
            if spec.key in startup_fields_set:
                setattr(settings, spec.key, getattr(startup_snapshot, spec.key))
                continue
            try:
                record = await secret_store.get(spec.key)
            except SecretStoreError as exc:
                logger.warning("Runtime secret store unavailable for %s: %s", spec.key, exc)
                continue
            except Exception:
                logger.exception("Failed to load persisted runtime secret: %s", spec.key)
                continue
            if record is None:
                continue
            setattr(settings, spec.key, record.value)
            changed_keys.append(spec.key)
            applied_keys.add(spec.key)
    finally:
        await secret_store.close()

    if (
        settings.external_diagnostics_wait_seconds > 0
        and settings.external_diagnostics_poll_interval_seconds
        > settings.external_diagnostics_wait_seconds
    ):
        logger.warning(
            "Adjusting invalid persisted diagnostics poll interval %.2fs to wait budget %.2fs",
            settings.external_diagnostics_poll_interval_seconds,
            settings.external_diagnostics_wait_seconds,
        )
        settings.external_diagnostics_poll_interval_seconds = (
            settings.external_diagnostics_wait_seconds
        )
        changed_keys.append("external_diagnostics_poll_interval_seconds")

    if changed_keys and workflow is not None:
        workflow.refresh_runtime_settings()
        logger.info(
            "Applied persisted runtime settings from storage",
            extra={"changed_keys": sorted(changed_keys)},
        )
    if applied_keys:
        _runtime_override_keys.difference_update(applied_keys)
        _persisted_runtime_override_keys.update(applied_keys)


def _truncate_output(raw: str, limit: int = 280) -> str:
    text = raw.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _sanitize_handoff_context(input_text: str) -> str:
    """Redact common secret patterns from handoff context payloads."""
    output = input_text
    output = re.sub(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", "[REDACTED_GITHUB_TOKEN]", output)
    output = re.sub(
        r"(authorization\s*:\s*bearer\s+)[^\s\"']+",
        r"\1[REDACTED_TOKEN]",
        output,
        flags=re.IGNORECASE,
    )
    output = re.sub(
        r"\b(api[_-]?key|token|secret|password|client[_-]?secret)\b(\s*[:=]\s*)[^\s\"']{8,}",
        r"\1\2[REDACTED]",
        output,
        flags=re.IGNORECASE,
    )
    return output


def _handoff_context_preview(context: str, max_chars: int = 280) -> str:
    sanitized = re.sub(r"\s+", " ", context).strip()
    if len(sanitized) <= max_chars:
        return sanitized
    return sanitized[: max_chars - 3] + "..."


def _handoff_activity_url(request: Request, activity_id: str) -> str | None:
    origin = str(request.headers.get("origin", "") or "").strip().rstrip("/")
    if not origin.startswith(("http://", "https://")):
        return None
    return f"{origin}/app/activities/{activity_id}"


def _handoff_summary(activity: ActivityRecord, request: Request) -> dict[str, Any]:
    diagnosis = activity.diagnosis
    remediation = activity.remediation_result
    return {
        "activity_url": _handoff_activity_url(request, activity.id),
        "root_cause": (diagnosis.root_cause if diagnosis else "").strip(),
        "suggested_fix": (diagnosis.suggested_fix if diagnosis else "").strip(),
        "diagnosis_confidence": float(diagnosis.confidence) if diagnosis else None,
        "remediation_action": remediation.action_taken.value if remediation else "",
        "remediation_success": remediation.success if remediation else None,
        "issue_url": (remediation.issue_url if remediation else "") or "",
        "pr_url": (remediation.pr_url if remediation else "") or "",
        "error_message": (remediation.error_message if remediation else "") or "",
    }


def _handoff_actor(request: Request) -> str | None:
    principal = get_request_principal(request)
    if principal is not None:
        return f"entra:{principal.subject[:24]}"
    return "api_client"


def _agent_handoff_config_view() -> AgentHandoffConfigView:
    settings = get_settings()
    mode = AgentHandoffMode(settings.agent_handoff_mode)
    webhook_configured = bool(settings.agent_handoff_webhook_url.strip())
    enabled_targets = [ExternalAgentTarget(value) for value in settings.agent_handoff_enabled_targets]
    target_configured = {
        ExternalAgentTarget.CODEX_APP_SERVER: bool(settings.codex_app_server_handoff_url.strip()),
        ExternalAgentTarget.OPENCLAW: bool(settings.openclaw_handoff_url.strip()),
        ExternalAgentTarget.HERMES: bool(settings.hermes_handoff_url.strip()),
        ExternalAgentTarget.CUSTOM: webhook_configured,
    }
    if not settings.agent_handoff_enabled:
        return AgentHandoffConfigView(
            enabled=False,
            mode=mode,
            webhook_configured=webhook_configured,
            timeout_seconds=settings.agent_handoff_timeout_seconds,
            max_retries=settings.agent_handoff_max_retries,
            default_target=ExternalAgentTarget(settings.agent_handoff_default_target),
            enabled_targets=enabled_targets,
            target_configured=target_configured,
            reason="disabled_by_runtime",
        )
    if mode == AgentHandoffMode.WEBHOOK and not webhook_configured:
        return AgentHandoffConfigView(
            enabled=True,
            mode=mode,
            webhook_configured=False,
            timeout_seconds=settings.agent_handoff_timeout_seconds,
            max_retries=settings.agent_handoff_max_retries,
            default_target=ExternalAgentTarget(settings.agent_handoff_default_target),
            enabled_targets=enabled_targets,
            target_configured=target_configured,
            reason="missing_webhook_url",
        )
    return AgentHandoffConfigView(
        enabled=True,
        mode=mode,
        webhook_configured=webhook_configured,
        timeout_seconds=settings.agent_handoff_timeout_seconds,
        max_retries=settings.agent_handoff_max_retries,
        default_target=ExternalAgentTarget(settings.agent_handoff_default_target),
        enabled_targets=enabled_targets,
        target_configured=target_configured,
        reason="ok",
    )


def _agent_handoff_receiver_health_url(webhook_url: str) -> str | None:
    parsed = urlparse(webhook_url.strip())
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return None
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, "/api/healthz", "", "", ""))


async def _probe_agent_handoff_receiver_health(
    health_url: str,
) -> NotificationTargetHealthView | None:
    timeout = httpx.Timeout(2.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(health_url)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        return None

    notifications_raw = payload.get("notifications")
    if not isinstance(notifications_raw, dict):
        return None

    supported_target_types_raw = notifications_raw.get("supported_target_types", [])
    if not isinstance(supported_target_types_raw, list):
        raise ValueError("receiver notifications.supported_target_types must be a list")

    errors_raw = notifications_raw.get("errors", [])
    if not isinstance(errors_raw, list):
        raise ValueError("receiver notifications.errors must be a list")

    return NotificationTargetHealthView(
        configured_targets=int(notifications_raw.get("configured_targets", 0) or 0),
        enabled_targets=int(notifications_raw.get("enabled_targets", 0) or 0),
        invalid_targets=int(notifications_raw.get("invalid_targets", 0) or 0),
        supported_target_types=[
            str(item).strip()
            for item in supported_target_types_raw
            if str(item).strip()
        ],
        errors=[str(item).strip() for item in errors_raw if str(item).strip()],
    )


async def _agent_handoff_integration_status_view() -> AgentHandoffIntegrationStatusView:
    settings = get_settings()
    mode = AgentHandoffMode(settings.agent_handoff_mode)
    webhook_url = settings.agent_handoff_webhook_url.strip()
    webhook_configured = bool(webhook_url)
    webhook_host = (urlparse(webhook_url).hostname or "").strip().lower() if webhook_url else ""
    checked_at = utcnow().isoformat()

    if not settings.agent_handoff_enabled:
        return AgentHandoffIntegrationStatusView(
            enabled=False,
            mode=mode,
            webhook_configured=webhook_configured,
            webhook_host=webhook_host,
            receiver_status="not_required",
            reason="disabled_by_runtime",
            checked_at=checked_at,
        )

    if mode == AgentHandoffMode.COPY_ONLY:
        return AgentHandoffIntegrationStatusView(
            enabled=True,
            mode=mode,
            webhook_configured=webhook_configured,
            webhook_host=webhook_host,
            receiver_status="not_required",
            reason="copy_only_mode",
            checked_at=checked_at,
        )

    if not webhook_configured:
        return AgentHandoffIntegrationStatusView(
            enabled=True,
            mode=mode,
            webhook_configured=False,
            receiver_status="missing_configuration",
            reason="missing_webhook_url",
            checked_at=checked_at,
        )

    health_url = _agent_handoff_receiver_health_url(webhook_url)
    if not health_url:
        return AgentHandoffIntegrationStatusView(
            enabled=True,
            mode=mode,
            webhook_configured=True,
            webhook_host=webhook_host,
            receiver_status="invalid_configuration",
            reason="invalid_webhook_url",
            checked_at=checked_at,
        )

    if not _is_allowed_handoff_host(webhook_host, settings.agent_handoff_webhook_allowlist):
        return AgentHandoffIntegrationStatusView(
            enabled=True,
            mode=mode,
            webhook_configured=True,
            webhook_host=webhook_host,
            receiver_health_url=health_url,
            receiver_status="invalid_configuration",
            reason="destination_not_allowlisted",
            checked_at=checked_at,
        )

    try:
        notifications = await _probe_agent_handoff_receiver_health(health_url)
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        logger.warning("agent_handoff_receiver_probe_failed url=%s error=%s", health_url, exc)
        return AgentHandoffIntegrationStatusView(
            enabled=True,
            mode=mode,
            webhook_configured=True,
            webhook_host=webhook_host,
            receiver_health_url=health_url,
            receiver_status="unreachable",
            reason="receiver_probe_failed",
            checked_at=checked_at,
        )

    if notifications is None:
        return AgentHandoffIntegrationStatusView(
            enabled=True,
            mode=mode,
            webhook_configured=True,
            webhook_host=webhook_host,
            receiver_health_url=health_url,
            receiver_status="invalid_response",
            reason="missing_notifications_summary",
            checked_at=checked_at,
        )

    receiver_status = "available"
    reason = "ok"
    if notifications.invalid_targets > 0:
        receiver_status = "degraded"
        reason = "invalid_notification_targets"
    elif notifications.configured_targets == 0:
        reason = "no_notification_targets"

    return AgentHandoffIntegrationStatusView(
        enabled=True,
        mode=mode,
        webhook_configured=True,
        webhook_host=webhook_host,
        receiver_health_url=health_url,
        receiver_status=receiver_status,
        reason=reason,
        checked_at=checked_at,
        notifications=notifications,
    )


def _is_allowed_handoff_host(hostname: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    normalized_host = hostname.strip().lower()
    return normalized_host in {item.strip().lower() for item in allowlist if item.strip()}


async def _deliver_handoff_webhook(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    max_retries: int,
) -> tuple[bool, str | None]:
    """Deliver handoff payload with bounded retry for transient failures."""
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries + 1):
            try:
                response = await client.post(url, json=payload)
            except httpx.RequestError as exc:
                if attempt >= max_retries:
                    return False, f"{type(exc).__name__}"
                await asyncio.sleep(0.2 * (attempt + 1))
                continue

            if response.status_code >= 500 and attempt < max_retries:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue

            if response.status_code >= 400:
                return False, f"http_{response.status_code}"
            return True, None
    return False, "delivery_failed"


_HANDOFF_BASE_LABELS = (
    "pipelinehealer:detected",
    "pipelinehealer:delegated",
    "pipelinehealer:external-agent",
)
_HANDOFF_TARGET_LABELS = {
    ExternalAgentTarget.CODEX_APP_SERVER: "agent:codex",
    ExternalAgentTarget.OPENCLAW: "agent:openclaw",
    ExternalAgentTarget.HERMES: "agent:hermes",
    ExternalAgentTarget.CUSTOM: "agent:custom",
}
_HANDOFF_EVENT_STATUS = {
    HandoffEventType.ACKNOWLEDGED: HandoffSessionStatus.ACKNOWLEDGED,
    HandoffEventType.STARTED_WORK: HandoffSessionStatus.IN_PROGRESS,
    HandoffEventType.NEEDS_MORE_INFO: HandoffSessionStatus.WAITING_ON_PIPELINEHEALER,
    HandoffEventType.PR_OPENED: HandoffSessionStatus.PR_OPENED,
    HandoffEventType.ISSUE_COMMENTED: HandoffSessionStatus.IN_PROGRESS,
    HandoffEventType.LABEL_APPLIED: HandoffSessionStatus.IN_PROGRESS,
    HandoffEventType.WORKFLOW_RERUN: HandoffSessionStatus.IN_PROGRESS,
    HandoffEventType.COMPLETED: HandoffSessionStatus.COMPLETED,
    HandoffEventType.FAILED: HandoffSessionStatus.FAILED,
}


def _handoff_labels(target: ExternalAgentTarget, extra: list[str]) -> list[str]:
    labels = [*_HANDOFF_BASE_LABELS, _HANDOFF_TARGET_LABELS[target], *extra]
    normalized: list[str] = []
    seen: set[str] = set()
    for label in labels:
        value = str(label).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _target_handoff_url(target: ExternalAgentTarget) -> str:
    settings = get_settings()
    legacy_url = settings.agent_handoff_webhook_url.strip()
    if target == ExternalAgentTarget.CODEX_APP_SERVER:
        return settings.codex_app_server_handoff_url.strip() or legacy_url
    if target == ExternalAgentTarget.OPENCLAW:
        return settings.openclaw_handoff_url.strip() or legacy_url
    if target == ExternalAgentTarget.HERMES:
        return settings.hermes_handoff_url.strip() or legacy_url
    return legacy_url


def _target_enabled(target: ExternalAgentTarget) -> bool:
    settings = get_settings()
    return target.value in {item.strip().lower() for item in settings.agent_handoff_enabled_targets}


def _session_callback_url(request: Request, session_id: str) -> str | None:
    origin = str(request.headers.get("origin", "") or "").strip().rstrip("/")
    if not origin.startswith(("http://", "https://")):
        return None
    return f"{origin}/api/handoff-sessions/{session_id}/events"


def _message_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, default=str)
    redacted = _sanitize_handoff_context(text)
    try:
        parsed = json.loads(redacted)
    except json.JSONDecodeError:
        return {"redacted": redacted}
    return parsed if isinstance(parsed, dict) else {"redacted": redacted}


async def _verify_handoff_callback_signature(request: Request) -> tuple[bool, bytes]:
    body = await request.body()
    secret = get_settings().agent_handoff_callback_secret.strip()
    if not secret:
        return False, body
    signature = str(request.headers.get("X-PipelineHealer-Signature", "") or "").strip()
    if not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing handoff callback signature")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, f"sha256={expected}"):
        raise HTTPException(status_code=401, detail="Invalid handoff callback signature")
    return True, body


def _github_refs_for_activity(activity: ActivityRecord) -> HandoffGitHubRefs:
    return HandoffGitHubRefs(
        repository=activity.repository_name,
        run_id=activity.workflow_run_id,
        issue_url=(activity.remediation_result.issue_url if activity.remediation_result else None),
        pr_url=(activity.remediation_result.pr_url if activity.remediation_result else None),
    )


async def _record_handoff_activity_audit(
    *,
    storage: ActivityStorage,
    activity: ActivityRecord,
    session: HandoffSession,
    status: AgentHandoffStatus,
    mode: AgentHandoffMode,
    error: str | None = None,
) -> None:
    audit = AgentHandoffAuditEntry(
        status=status,
        mode=mode,
        actor=session.created_by,
        request_id=session.request_id,
        context_chars=len(session.context_preview),
        context_sha256=session.context_sha256,
        context_preview=session.context_preview,
        delivery_id=session.delivery_id,
        destination_host=urlparse(_target_handoff_url(session.target)).hostname,
        error=error,
    )
    activity.agent_handoff_audit.append(audit)
    activity.agent_handoff_audit = activity.agent_handoff_audit[-_AGENT_HANDOFF_MAX_AUDIT_ENTRIES:]
    await storage.update_activity(activity)


async def _start_env_only_redeploy_background() -> tuple[bool, str]:
    """Start env-only redeploy in background via scripts/ph.sh deploy:bg --env-only."""
    repo_root = _repo_root()
    script = repo_root / "scripts" / "ph.sh"
    if not script.exists():
        return False, f"Missing helper script: {script}"

    try:
        process = await asyncio.create_subprocess_exec(
            "bash",
            str(script),
            "deploy:bg",
            "--env-only",
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"Failed to start env redeploy: {exc}"

    output = stdout.decode("utf-8", errors="replace")
    if process.returncode != 0:
        return False, _truncate_output(output) or "deploy:bg returned non-zero exit code"
    return True, _truncate_output(output) or "Started env-only redeploy in background"


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(storage: ActivityStorage = Depends(get_storage)) -> DashboardStats:
    """Get overall statistics for the dashboard."""
    try:
        stats = await storage.get_stats()
        return stats
    except Exception as e:
        logger.exception(f"Failed to get dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/settings",
    response_model=AppSettingsView,
    dependencies=[Depends(require_admin_key)],
)
async def get_app_settings(storage: ActivityStorage = Depends(get_storage)) -> AppSettingsView:
    """Get non-secret runtime settings for admin users."""
    return _build_settings_view(storage)


@router.patch(
    "/settings",
    response_model=AppSettingsView,
    dependencies=[Depends(require_admin_key)],
)
async def update_app_settings(
    update: AdminSettingsUpdateRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
    workflow: PipelineHealerWorkflow = Depends(get_workflow),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> AppSettingsView:
    """Apply and durably persist admin runtime configuration updates."""
    settings = get_settings()
    changes = update.model_dump(exclude_none=True)

    if not changes:
        return _build_settings_view(storage)

    if "heal_mode" in changes:
        heal_mode = str(changes["heal_mode"]).strip().lower()
        if heal_mode not in {"safe", "demo", "freestyle", "debug"}:
            raise HTTPException(
                status_code=422,
                detail="heal_mode must be one of: safe, demo, freestyle, debug",
            )
        changes["heal_mode"] = heal_mode

    if "ph_allowed_repos" in changes:
        repos = changes["ph_allowed_repos"]
        if not isinstance(repos, list):
            raise HTTPException(status_code=422, detail="ph_allowed_repos must be a list")
        try:
            changes["ph_allowed_repos"] = _normalize_allowed_repo_list(repos)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if "gh_aw_ingestion_mode" in changes:
        mode = str(changes["gh_aw_ingestion_mode"]).strip().lower()
        if mode not in {"disabled", "passive", "hybrid"}:
            raise HTTPException(
                status_code=422,
                detail="gh_aw_ingestion_mode must be one of: disabled, passive, hybrid",
            )
        changes["gh_aw_ingestion_mode"] = mode

    if "gh_aw_known_workflows" in changes:
        workflows = changes["gh_aw_known_workflows"]
        if not isinstance(workflows, list):
            raise HTTPException(status_code=422, detail="gh_aw_known_workflows must be a list")
        changes["gh_aw_known_workflows"] = _normalize_workflow_names(workflows)

    if "agent_handoff_mode" in changes:
        handoff_mode = str(changes["agent_handoff_mode"]).strip().lower()
        if handoff_mode not in {"copy_only", "webhook"}:
            raise HTTPException(
                status_code=422,
                detail="agent_handoff_mode must be one of: copy_only, webhook",
            )
        changes["agent_handoff_mode"] = handoff_mode

    if "agent_handoff_webhook_allowlist" in changes:
        allowlist = changes["agent_handoff_webhook_allowlist"]
        if not isinstance(allowlist, list):
            raise HTTPException(
                status_code=422,
                detail="agent_handoff_webhook_allowlist must be a list",
            )
        try:
            changes["agent_handoff_webhook_allowlist"] = _normalize_hostname_allowlist(allowlist)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if "agent_handoff_default_target" in changes:
        target = str(changes["agent_handoff_default_target"]).strip().lower()
        if target not in {"codex_app_server", "openclaw", "hermes", "custom"}:
            raise HTTPException(
                status_code=422,
                detail=(
                    "agent_handoff_default_target must be one of: "
                    "codex_app_server, openclaw, hermes, custom"
                ),
            )
        changes["agent_handoff_default_target"] = target

    if "agent_handoff_enabled_targets" in changes:
        targets = changes["agent_handoff_enabled_targets"]
        if not isinstance(targets, list):
            raise HTTPException(
                status_code=422,
                detail="agent_handoff_enabled_targets must be a list",
            )
        allowed_targets = {"codex_app_server", "openclaw", "hermes", "custom"}
        normalized_targets = [str(item).strip().lower() for item in targets if str(item).strip()]
        invalid_targets = [target for target in normalized_targets if target not in allowed_targets]
        if invalid_targets:
            raise HTTPException(
                status_code=422,
                detail=(
                    "agent_handoff_enabled_targets values must be one of: "
                    "codex_app_server, openclaw, hermes, custom"
                ),
            )
        changes["agent_handoff_enabled_targets"] = normalized_targets

    if "agent_handoff_default_target" in changes or "agent_handoff_enabled_targets" in changes:
        effective_default_target = str(
            changes.get("agent_handoff_default_target", settings.agent_handoff_default_target)
        ).strip().lower()
        effective_enabled_targets = {
            str(target).strip().lower()
            for target in changes.get(
                "agent_handoff_enabled_targets",
                settings.agent_handoff_enabled_targets,
            )
            if str(target).strip()
        }
        if effective_default_target not in effective_enabled_targets:
            raise HTTPException(
                status_code=422,
                detail="agent_handoff_default_target must be included in agent_handoff_enabled_targets",
            )

    try:
        effective_handoff_webhook_url = _validate_handoff_webhook_url(
            settings.agent_handoff_webhook_url
        )
    except ValueError as exc:
        logger.warning("Invalid AGENT_HANDOFF_WEBHOOK_URL in settings: %s", exc)
        effective_handoff_webhook_url = ""
    effective_handoff_allowlist = changes.get(
        "agent_handoff_webhook_allowlist",
        _safe_hostname_allowlist(settings.agent_handoff_webhook_allowlist),
    )
    if effective_handoff_webhook_url and effective_handoff_allowlist:
        effective_host = (urlparse(effective_handoff_webhook_url).hostname or "").strip().lower()
        if not _is_allowed_handoff_host(effective_host, effective_handoff_allowlist):
            raise HTTPException(
                status_code=422,
                detail=(
                    "agent_handoff_webhook_allowlist must include the configured "
                    "AGENT_HANDOFF_WEBHOOK_URL host"
                ),
            )

    # External diagnostics fast-path settings:
    # keep waits bounded and ensure poll interval does not exceed wait budget
    # unless wait is explicitly 0 (fully async mode).
    wait_budget = float(
        changes.get(
            "external_diagnostics_wait_seconds",
            settings.external_diagnostics_wait_seconds,
        )
    )
    poll_interval = float(
        changes.get(
            "external_diagnostics_poll_interval_seconds",
            settings.external_diagnostics_poll_interval_seconds,
        )
    )
    if wait_budget > 0 and poll_interval > wait_budget:
        raise HTTPException(
            status_code=422,
            detail=(
                "external_diagnostics_poll_interval_seconds must be <= "
                "external_diagnostics_wait_seconds when wait budget is enabled"
            ),
        )

    if "azure_openai_deployment_name" in changes:
        changes["azure_openai_deployment_name"] = str(changes["azure_openai_deployment_name"]).strip()

    if "azure_openai_endpoint" in changes:
        changes["azure_openai_endpoint"] = str(changes["azure_openai_endpoint"]).strip()

    if "azure_openai_api_version" in changes:
        changes["azure_openai_api_version"] = str(changes["azure_openai_api_version"]).strip()

    if "azure_openai_chat_api_version" in changes:
        changes["azure_openai_chat_api_version"] = str(changes["azure_openai_chat_api_version"]).strip()

    if "llm_provider" in changes:
        llm_provider = str(changes["llm_provider"]).strip().lower()
        if llm_provider not in {"azure_openai", "openai_compatible", "codex_app_server", "custom"}:
            raise HTTPException(
                status_code=422,
                detail=(
                    "llm_provider must be one of: "
                    "azure_openai, openai_compatible, codex_app_server, custom"
                ),
            )
        changes["llm_provider"] = llm_provider

    if "openai_compatible_base_url" in changes:
        changes["openai_compatible_base_url"] = str(changes["openai_compatible_base_url"]).strip()

    if "openai_compatible_model" in changes:
        changes["openai_compatible_model"] = str(changes["openai_compatible_model"]).strip()
    if "codex_app_server_transport" in changes:
        transport = str(changes["codex_app_server_transport"]).strip().lower() or "stdio"
        if transport not in {"stdio", "websocket"}:
            raise HTTPException(
                status_code=422,
                detail="codex_app_server_transport must be one of: stdio, websocket",
            )
        changes["codex_app_server_transport"] = transport
    if "codex_app_server_command" in changes:
        changes["codex_app_server_command"] = str(changes["codex_app_server_command"]).strip()
    if "codex_app_server_model" in changes:
        changes["codex_app_server_model"] = str(changes["codex_app_server_model"]).strip()
    if "codex_app_server_ws_url" in changes:
        changes["codex_app_server_ws_url"] = str(changes["codex_app_server_ws_url"]).strip()
    if "llm_model_analysis" in changes:
        changes["llm_model_analysis"] = str(changes["llm_model_analysis"]).strip()
    if "llm_model_diagnosis" in changes:
        changes["llm_model_diagnosis"] = str(changes["llm_model_diagnosis"]).strip()
    if "llm_model_remediation" in changes:
        changes["llm_model_remediation"] = str(changes["llm_model_remediation"]).strip()
    if "github_app_id" in changes:
        changes["github_app_id"] = str(changes["github_app_id"]).strip()
    if "infisical_project_id" in changes:
        changes["infisical_project_id"] = str(changes["infisical_project_id"]).strip()
    if "infisical_environment" in changes:
        changes["infisical_environment"] = str(changes["infisical_environment"]).strip() or "dev"
    if "infisical_secret_path" in changes:
        path = str(changes["infisical_secret_path"]).strip() or "/"
        changes["infisical_secret_path"] = path if path.startswith("/") else f"/{path}"
    if "infisical_cli_path" in changes:
        changes["infisical_cli_path"] = str(changes["infisical_cli_path"]).strip() or "infisical"
    if "infisical_api_url" in changes:
        changes["infisical_api_url"] = str(changes["infisical_api_url"]).strip()

    if "mcp_provider" in changes:
        mcp_provider = str(changes["mcp_provider"]).strip().lower()
        if mcp_provider not in {"disabled", "github", "azure_monitor", "custom"}:
            raise HTTPException(
                status_code=422,
                detail="mcp_provider must be one of: disabled, github, azure_monitor, custom",
            )
        changes["mcp_provider"] = mcp_provider

    if "mcp_repo_allowlist" in changes:
        repos = changes["mcp_repo_allowlist"]
        if not isinstance(repos, list):
            raise HTTPException(status_code=422, detail="mcp_repo_allowlist must be a list")
        try:
            changes["mcp_repo_allowlist"] = _normalize_allowed_repo_list(repos)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if "mcp_tool_policies" in changes:
        policies = changes["mcp_tool_policies"]
        if not isinstance(policies, dict):
            raise HTTPException(status_code=422, detail="mcp_tool_policies must be an object")
        try:
            changes["mcp_tool_policies"] = _normalize_mcp_tool_policies(policies)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    max_chars = int(changes.get("log_prompt_max_chars", settings.log_prompt_max_chars))
    head_chars = int(changes.get("log_prompt_head_chars", settings.log_prompt_head_chars))
    tail_chars = int(changes.get("log_prompt_tail_chars", settings.log_prompt_tail_chars))
    if head_chars + tail_chars > max_chars:
        raise HTTPException(
            status_code=422,
            detail="log_prompt_head_chars + log_prompt_tail_chars must be <= log_prompt_max_chars",
        )

    previous_values = {key: getattr(settings, key, None) for key in changes}
    persisted_values = await storage.get_runtime_settings() or {}
    persisted_values.update(changes)
    await _persist_mutable_settings_to_storage(persisted_values, storage)
    await apply_persisted_runtime_settings(storage, workflow)

    audit_entry = AdminSettingsAuditEntry(
        changed_keys=sorted(changes.keys()),
        changes={
            key: {"old": previous_values[key], "new": changes[key]}
            for key in sorted(changes.keys())
        },
        actor=_build_admin_settings_actor_fingerprint(
            request=request,
            x_admin_key=x_admin_key,
        ),
        # request_id is injected by middleware to correlate audit entries with API logs.
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    await _append_admin_settings_audit_entry(
        storage=storage,
        entry=audit_entry,
    )

    logger.info("Admin runtime settings updated; changed_keys=%s", sorted(changes.keys()))

    return _build_settings_view(storage)


@router.get(
    "/settings/secrets",
    response_model=list[SecretSettingView],
    dependencies=[Depends(require_admin_key)],
)
async def get_secret_settings(
    storage: ActivityStorage = Depends(get_storage),
) -> list[SecretSettingView]:
    """Return non-sensitive metadata for runtime-managed secrets."""
    return await _build_secret_settings_views(storage)


@router.patch(
    "/settings/secrets",
    response_model=list[SecretSettingView],
    dependencies=[Depends(require_admin_key)],
)
async def update_secret_settings(
    payload: AdminSecretsUpdateRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
    workflow: PipelineHealerWorkflow = Depends(get_workflow),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> list[SecretSettingView]:
    """Write, rotate, or clear runtime-managed secrets without returning plaintext."""
    if not payload.secrets:
        return await _build_secret_settings_views(storage)

    invalid_keys = sorted(set(payload.secrets) - set(SECRET_SETTING_SPECS_BY_KEY))
    if invalid_keys:
        raise HTTPException(status_code=422, detail=f"Unknown secret keys: {', '.join(invalid_keys)}")

    store = build_secret_store(storage)
    settings = get_settings()
    startup_fields_set = _startup_configured_fields()
    audit_changes: dict[str, dict[str, Any]] = {}
    try:
        for key, write in payload.secrets.items():
            if write.clear:
                await store.delete(key)
                if key not in startup_fields_set:
                    setattr(settings, key, "")
                    _persisted_runtime_override_keys.discard(key)
                audit_changes[key] = {"old": "configured", "new": {"action": "cleared", "backend": store.backend_name}}
                continue

            value = str(write.value or "").strip()
            if not value:
                raise HTTPException(status_code=422, detail=f"{key} requires a non-empty value or clear=true")
            previous = getattr(settings, key, "")
            await store.set(key, value, metadata={"request_id": getattr(request.state, "request_id", None)})
            if key not in startup_fields_set:
                setattr(settings, key, value)
                _persisted_runtime_override_keys.add(key)
            audit_changes[key] = {
                "old": "configured" if previous else None,
                "new": {
                    "action": "rotated" if previous else "set",
                    "backend": store.backend_name,
                },
            }
    except SecretStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await store.close()

    workflow.refresh_runtime_settings()
    audit_entry = AdminSettingsAuditEntry(
        changed_keys=sorted(audit_changes.keys()),
        changes=audit_changes,
        actor=_build_admin_settings_actor_fingerprint(request=request, x_admin_key=x_admin_key),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    await _append_admin_settings_audit_entry(storage=storage, entry=audit_entry)
    return await _build_secret_settings_views(storage)


@router.get(
    "/settings/llm/provider-health",
    response_model=LLMProviderHealthView,
    dependencies=[Depends(require_admin_key)],
)
async def get_llm_provider_health(
    storage: ActivityStorage = Depends(get_storage),
) -> LLMProviderHealthView:
    """Get health/status for the configured LLM provider adapter."""
    settings = get_settings()
    adapter = get_llm_provider_adapter(settings)
    base_health = adapter.health(settings)
    capability = await build_llm_capability_snapshot(
        settings=settings,
        storage=storage,
        provider_health=base_health,
    )
    return LLMProviderHealthView(**base_health, **capability)


@router.get(
    "/settings/mcp/provider-health",
    response_model=MCPProviderHealthView,
    dependencies=[Depends(require_admin_key)],
)
async def get_mcp_provider_health() -> MCPProviderHealthView:
    """Get health/status for the configured MCP provider adapter."""
    settings = get_settings()
    provider = get_mcp_provider(settings)
    return MCPProviderHealthView(**asdict(provider.health(settings)))


@router.get(
    "/settings/audit",
    response_model=list[AdminSettingsAuditEntry],
    dependencies=[Depends(require_admin_key)],
)
async def get_settings_audit(
    limit: int = Query(
        50,
        ge=1,
        le=_MAX_ADMIN_SETTINGS_AUDIT_ENTRIES,
        description="Maximum number of admin settings audit records",
    ),
    storage: ActivityStorage = Depends(get_storage),
) -> list[AdminSettingsAuditEntry]:
    """Get recent admin settings change records (latest first)."""
    try:
        persisted = await storage.list_admin_settings_audit_entries(limit=limit)
    except Exception as exc:
        logger.warning("Failed to load persisted admin settings audit entries: %s", exc)
        persisted = []

    if persisted:
        return [AdminSettingsAuditEntry(**item) for item in persisted]
    return list(reversed(_admin_settings_audit))[:limit]


@router.post(
    "/settings/persist",
    response_model=AdminSettingsPersistResponse,
    dependencies=[Depends(require_admin_key)],
)
async def persist_app_settings(
    payload: AdminSettingsPersistRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> AdminSettingsPersistResponse:
    """Compatibility endpoint retained after the UI-first durable-save refactor."""
    _ = payload
    persisted_keys = sorted((await storage.get_runtime_settings() or {}).keys())
    response = AdminSettingsPersistResponse(
        env_file="",
        persisted_keys=persisted_keys,
        redeploy_attempted=False,
        redeploy_started=False,
        redeploy_message=(
            "Deprecated: PATCH /api/settings and PATCH /api/settings/secrets already persist changes durably. "
            "Use environment variables only for bootstrap overrides."
        ),
        deprecated=True,
    )

    persist_audit_entry = AdminSettingsAuditEntry(
        changed_keys=["persist_settings"],
        changes={
            "persist_settings": {
                "old": None,
                "new": {
                    "skip_redeploy": payload.skip_redeploy,
                    "persisted_keys": persisted_keys,
                    "deprecated": True,
                },
            }
        },
        actor=_build_admin_settings_actor_fingerprint(
            request=request,
            x_admin_key=x_admin_key,
        ),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    await _append_admin_settings_audit_entry(
        storage=storage,
        entry=persist_audit_entry,
    )

    return response


@router.get(
    "/settings/learning/queue",
    response_model=list[LearningQueueItem],
    dependencies=[Depends(require_admin_key)],
)
async def list_learning_queue(
    status: str | None = Query(
        default=None,
        description=(
            "Optional queue status filter: "
            "candidate|approved|rejected|active|retired"
        ),
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of learning queue records to return",
    ),
    storage: ActivityStorage = Depends(get_storage),
) -> list[LearningQueueItem]:
    """List remediation learning queue candidates."""
    normalized_status = status.strip().lower() if status else None
    if normalized_status and normalized_status not in _LEARNING_QUEUE_ALLOWED_STATUS:
        raise HTTPException(
            status_code=422,
            detail=(
                "status must be one of: "
                "candidate, approved, rejected, active, retired"
            ),
        )

    items = await storage.list_learning_queue_items(status=normalized_status, limit=limit)
    output: list[LearningQueueItem] = []
    for item in items:
        try:
            parsed = LearningQueueItem(**item)
            parsed.promotion_readiness = _evaluate_learning_promotion_readiness(parsed)
            output.append(parsed)
        except Exception as exc:
            logger.warning("Skipping invalid learning queue item: %s", exc)
    return output


@router.post(
    "/settings/learning/queue/refresh",
    response_model=LearningQueueRefreshResponse,
    dependencies=[Depends(require_admin_key)],
)
async def refresh_learning_queue(
    request: Request,
    lookback_hours: float = Query(
        default=168.0,
        ge=1.0,
        le=24.0 * 90.0,
        description="How far back to scan completed successful activities for candidates",
    ),
    min_occurrences: int = Query(
        default=2,
        ge=2,
        le=20,
        description="Minimum recurring occurrences required to create a candidate",
    ),
    max_scan: int = Query(
        default=500,
        ge=20,
        le=5000,
        description="Maximum activities to scan per refresh operation",
    ),
    max_candidates: int = Query(
        default=100,
        ge=1,
        le=300,
        description="Maximum generated candidates to upsert in one refresh",
    ),
    storage: ActivityStorage = Depends(get_storage),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> LearningQueueRefreshResponse:
    """Build/refresh learning candidates from recent successful remediations."""
    activities = await _collect_recent_activities(
        storage,
        lookback_hours=lookback_hours,
        max_scan=max_scan,
    )
    generated = _extract_learning_candidates(
        activities,
        min_occurrences=min_occurrences,
    )[:max_candidates]

    existing_items = await storage.list_learning_queue_items(limit=300)
    existing_by_fingerprint: dict[str, LearningQueueItem] = {}
    for row in existing_items:
        try:
            parsed = LearningQueueItem(**row)
        except Exception:
            continue
        existing_by_fingerprint[parsed.fingerprint] = parsed

    upserted = 0
    now = utcnow()
    for candidate in generated:
        existing = existing_by_fingerprint.get(candidate.fingerprint)
        if existing is not None:
            candidate.id = existing.id
            candidate.created_at = existing.created_at
            candidate.status = existing.status
            candidate.decision_reason = existing.decision_reason
            candidate.decision_actor = existing.decision_actor
            candidate.metadata = dict(existing.metadata or {})
        candidate.promotion_readiness = _evaluate_learning_promotion_readiness(candidate)
        candidate.updated_at = now
        await storage.upsert_learning_queue_item(candidate.model_dump(mode="json"))
        upserted += 1

    refresh_audit_entry = AdminSettingsAuditEntry(
        changed_keys=["learning_queue_refresh"],
        changes={
            "learning_queue_refresh": {
                "old": None,
                "new": {
                    "lookback_hours": lookback_hours,
                    "min_occurrences": min_occurrences,
                    "max_scan": max_scan,
                    "considered_activities": len(activities),
                    "generated_candidates": len(generated),
                    "upserted_candidates": upserted,
                },
            }
        },
        actor=_build_admin_settings_actor_fingerprint(
            request=request,
            x_admin_key=x_admin_key,
        ),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    await _append_admin_settings_audit_entry(storage=storage, entry=refresh_audit_entry)

    return LearningQueueRefreshResponse(
        considered_activities=len(activities),
        generated_candidates=len(generated),
        upserted_candidates=upserted,
    )


@router.post(
    "/settings/learning/queue/{candidate_id}/decision",
    response_model=LearningQueueItem,
    dependencies=[Depends(require_admin_key)],
)
async def decide_learning_queue_item(
    candidate_id: str,
    payload: LearningQueueDecisionRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> LearningQueueItem:
    """Approve/reject/activate/retire one learning queue candidate."""
    item = await storage.get_learning_queue_item(candidate_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Learning queue item not found")

    candidate = LearningQueueItem(**item)
    action = str(payload.action).strip().lower()
    next_status = _LEARNING_QUEUE_ALLOWED_ACTIONS.get(action)
    if next_status is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "action must be one of: approve, reject, activate, retire, reset_candidate"
            ),
        )
    if payload.force_activate and action != "activate":
        raise HTTPException(
            status_code=422,
            detail="force_activate is supported only when action=activate",
        )

    readiness_before = _evaluate_learning_promotion_readiness(candidate)
    forced_activation = bool(payload.force_activate and action == "activate")
    # Block activation by default when gates do not pass; force activation is
    # an explicit override path and must leave a durable audit trail.
    if action == "activate" and not readiness_before.ready and not forced_activation:
        raise HTTPException(
            status_code=409,
            detail=(
                "Candidate is not promotion-ready for activation. "
                "Approve first and satisfy readiness thresholds, or retry with force_activate=true."
            ),
        )

    previous_status = candidate.status.value
    candidate.status = LearningQueueStatus(next_status)
    candidate.updated_at = utcnow()
    candidate.decision_reason = str(payload.reason or "").strip()
    candidate.decision_actor = _build_admin_settings_actor_fingerprint(
        request=request,
        x_admin_key=x_admin_key,
    )
    if forced_activation:
        # Keep operator intent visible for post-incident traceability.
        candidate.metadata["forced_activation"] = {
            "at": candidate.updated_at.isoformat(),
            "actor": candidate.decision_actor,
            "reasons": readiness_before.reasons,
            "request_id": getattr(request.state, "request_id", None),
        }
    candidate.promotion_readiness = _evaluate_learning_promotion_readiness(candidate)
    await storage.upsert_learning_queue_item(candidate.model_dump(mode="json"))

    decision_audit_entry = AdminSettingsAuditEntry(
        changed_keys=["learning_queue_decision"],
        changes={
            "learning_queue_decision": {
                "old": {"status": previous_status},
                "new": {
                    "candidate_id": candidate.id,
                    "fingerprint": candidate.fingerprint,
                    "action": action,
                    "force_activate": forced_activation,
                    "promotion_readiness_before": readiness_before.model_dump(mode="json"),
                    "promotion_readiness_after": (
                        candidate.promotion_readiness.model_dump(mode="json")
                        if candidate.promotion_readiness
                        else None
                    ),
                    "status": candidate.status.value,
                    "reason": candidate.decision_reason,
                },
            }
        },
        actor=candidate.decision_actor,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    await _append_admin_settings_audit_entry(
        storage=storage,
        entry=decision_audit_entry,
    )

    return candidate


@router.post(
    "/settings/learning/feedback",
    response_model=LearningVerificationFeedbackResponse,
    dependencies=[Depends(require_admin_key)],
)
async def record_learning_feedback(
    payload: LearningVerificationFeedbackRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> LearningVerificationFeedbackResponse:
    """Capture operator verification outcomes for one remediation activity."""
    activity = await storage.get_activity(payload.activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    if activity.remediation_result is None:
        raise HTTPException(
            status_code=409,
            detail="Activity has no remediation result to verify",
        )

    details = (
        dict(activity.remediation_result.details)
        if isinstance(activity.remediation_result.details, dict)
        else {}
    )
    applied_learning_context = _extract_applied_learning_context(activity)
    if payload.guidance_effectiveness is not None and applied_learning_context is None:
        raise HTTPException(
            status_code=409,
            detail="Activity has no applied learning guidance to rate",
        )
    actor = _build_admin_settings_actor_fingerprint(
        request=request,
        x_admin_key=x_admin_key,
    )
    recorded_at = utcnow()
    verification_overall = _derive_verification_overall(
        identification=payload.identification.value,
        diagnosis=payload.diagnosis.value,
        remediation=payload.remediation.value,
    )
    verification_payload = {
        "identification": payload.identification.value,
        "diagnosis": payload.diagnosis.value,
        "remediation": payload.remediation.value,
        "overall": verification_overall,
        "guidance_effectiveness": (
            payload.guidance_effectiveness.value if payload.guidance_effectiveness is not None else None
        ),
        "notes": payload.notes.strip(),
        "issue_number": payload.issue_number,
        "issue_url": (payload.issue_url or "").strip() or None,
        "target_version": (payload.target_version or "").strip() or None,
        "recorded_at": recorded_at.isoformat(),
        "actor": actor,
        "request_id": getattr(request.state, "request_id", None),
    }
    history_raw = details.get("verification_history")
    history = history_raw if isinstance(history_raw, list) else []
    history.append(verification_payload)
    details["verification"] = verification_payload
    details["verification_history"] = history[-20:]
    activity.remediation_result.details = details
    await storage.update_activity(activity)

    updated_candidate_ids: list[str] = []
    activity_window: list[ActivityRecord] = []
    existing_items = await storage.list_learning_queue_items(limit=300)
    for row in existing_items:
        try:
            candidate = LearningQueueItem(**row)
        except Exception:
            continue
        candidate_was_sampled = activity.id in candidate.sample_activity_ids
        candidate_received_guidance = (
            applied_learning_context is not None and applied_learning_context.get("id") == candidate.id
        )
        if not candidate_was_sampled and not candidate_received_guidance:
            continue
        pass_count = 0
        partial_count = 0
        fail_count = 0
        sample_count = 0
        for sample_id in candidate.sample_activity_ids:
            sample_activity = await storage.get_activity(sample_id)
            if sample_activity is None:
                continue
            verification = _extract_activity_verification(sample_activity)
            if verification is None:
                continue
            sample_count += 1
            overall = str(verification.get("overall") or "")
            if overall == LearningVerificationOutcome.PASS.value:
                pass_count += 1
            elif overall == LearningVerificationOutcome.PARTIAL.value:
                partial_count += 1
            else:
                fail_count += 1
        candidate.verification_sample_count = sample_count
        candidate.verification_pass_count = pass_count
        candidate.verification_partial_count = partial_count
        candidate.verification_fail_count = fail_count
        candidate.verification_pass_rate = round((pass_count / sample_count), 4) if sample_count > 0 else 0.0
        if candidate_received_guidance:
            if not activity_window:
                activity_window = await _collect_bounded_activities(storage, max_scan=2000)
            guidance_metrics = _compute_guidance_metrics(candidate.id, activity_window)
            candidate.guidance_application_count = int(guidance_metrics["guidance_application_count"])
            candidate.guidance_feedback_count = int(guidance_metrics["guidance_feedback_count"])
            candidate.guidance_helped_count = int(guidance_metrics["guidance_helped_count"])
            candidate.guidance_neutral_count = int(guidance_metrics["guidance_neutral_count"])
            candidate.guidance_hurt_count = int(guidance_metrics["guidance_hurt_count"])
            candidate.guidance_help_rate = float(guidance_metrics["guidance_help_rate"])
        candidate.updated_at = recorded_at
        candidate.promotion_readiness = _evaluate_learning_promotion_readiness(candidate)
        await storage.upsert_learning_queue_item(candidate.model_dump(mode="json"))
        updated_candidate_ids.append(candidate.id)

    feedback_audit_entry = AdminSettingsAuditEntry(
        changed_keys=["learning_verification_feedback"],
        changes={
            "learning_verification_feedback": {
                "old": None,
                "new": {
                    "activity_id": activity.id,
                    "verification": verification_payload,
                    "updated_candidate_ids": updated_candidate_ids,
                },
            }
        },
        actor=actor,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    await _append_admin_settings_audit_entry(
        storage=storage,
        entry=feedback_audit_entry,
    )

    return LearningVerificationFeedbackResponse(
        activity_id=activity.id,
        verification_overall=LearningVerificationOutcome(verification_overall),
        updated_candidate_ids=updated_candidate_ids,
    )


@router.get("/activities", response_model=list[ActivityRecord])
async def get_activities(
    repository: str | None = Query(None, description="Filter by repository name"),
    status: RemediationStatus | None = Query(None, description="Filter by status"),
    failure_type: FailureType | None = Query(None, description="Filter by failure type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    since: datetime | None = Query(None, description="Filter activities since this time"),
    storage: ActivityStorage = Depends(get_storage),
) -> list[ActivityRecord]:
    """Get activity records with optional filtering."""

    try:
        activities = await storage.get_activities(
            repository=repository,
            status=status,
            failure_type=failure_type,
            limit=limit,
            offset=offset,
            since=since,
        )
        return activities
    except Exception as e:
        logger.exception(f"Failed to get activities: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/activities/{activity_id}", response_model=ActivityRecord)
async def get_activity(activity_id: str, storage: ActivityStorage = Depends(get_storage)) -> ActivityRecord:
    """Get a specific activity record by ID."""

    try:
        activity = await storage.get_activity(activity_id)
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")
        return activity
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get activity {activity_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agent-handoff/config", response_model=AgentHandoffConfigView)
async def get_agent_handoff_config() -> AgentHandoffConfigView:
    """Return runtime-safe Assign-to-Agent integration configuration."""
    return _agent_handoff_config_view()


@router.get("/agent-handoff/integration-status", response_model=AgentHandoffIntegrationStatusView)
async def get_agent_handoff_integration_status() -> AgentHandoffIntegrationStatusView:
    """Return live receiver and notification dependency status for operator surfaces."""
    return await _agent_handoff_integration_status_view()


@router.post(
    "/activities/{activity_id}/handoff-sessions",
    response_model=HandoffSessionCreateResponse,
)
async def create_handoff_session(
    activity_id: str,
    payload: HandoffSessionCreateRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
) -> HandoffSessionCreateResponse:
    """Create a durable external-agent handoff session for one activity."""
    activity = await storage.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    settings = get_settings()
    if not settings.agent_handoff_enabled:
        raise HTTPException(status_code=409, detail="External agent handoff is disabled")
    if not _target_enabled(payload.target):
        raise HTTPException(status_code=422, detail=f"Target '{payload.target.value}' is not enabled")

    sanitized_context = _sanitize_handoff_context(payload.context)
    context_hash = hashlib.sha256(sanitized_context.encode("utf-8")).hexdigest()
    session_id = str(uuid4())
    target_url = _target_handoff_url(payload.target)
    parsed = urlparse(target_url) if target_url else None
    destination_host = (parsed.hostname or "").strip().lower() if parsed else ""
    delivery_requested = payload.send and settings.agent_handoff_mode == AgentHandoffMode.WEBHOOK.value
    if delivery_requested and target_url and (
        parsed is None
        or parsed.scheme not in {"http", "https"}
        or not destination_host
        or not _is_allowed_handoff_host(destination_host, settings.agent_handoff_webhook_allowlist)
    ):
        raise HTTPException(
            status_code=422,
            detail="Configured target handoff URL is invalid or not allowlisted",
        )

    labels = _handoff_labels(payload.target, payload.labels)
    session = HandoffSession(
        id=session_id,
        activity_id=activity.id,
        target=payload.target,
        status=HandoffSessionStatus.CREATED,
        goal=payload.goal.strip(),
        created_by=_handoff_actor(request),
        request_id=getattr(request.state, "request_id", None),
        delivery_id=f"handoff-session:{activity.id}:{session_id}",
        github=_github_refs_for_activity(activity),
        labels=labels,
        policy_decision=payload.policy_decision.strip() or "operator_requested",
        callback_url=_session_callback_url(request, session_id),
        context_sha256=context_hash,
        context_preview=_handoff_context_preview(sanitized_context),
        metadata={
            "context_format": payload.context_format,
            "target_url_configured": bool(target_url),
            **payload.metadata,
        },
    )
    initial_payload = {
        "session_id": session.id,
        "activity_id": activity.id,
        "target": payload.target.value,
        "goal": session.goal,
        "context_format": payload.context_format,
        "context": sanitized_context,
        "labels": labels,
        "github": session.github.model_dump(mode="json"),
    }
    initial_message = HandoffMessage(
        session_id=session.id,
        event_type=HandoffEventType.DELEGATED,
        direction=HandoffMessageDirection.OUTBOUND,
        actor=session.created_by or "api_client",
        body=session.goal,
        payload_sha256=_message_payload_hash(initial_payload),
        payload_redacted=_redact_payload(initial_payload),
        github=session.github,
        labels=labels,
        request_id=session.request_id,
    )

    delivery_status = AgentHandoffStatus.COPIED
    response_message = "Handoff session recorded"
    error_code: str | None = None
    mode = AgentHandoffMode.COPY_ONLY
    if delivery_requested and target_url:
        mode = AgentHandoffMode.WEBHOOK
        outbound_payload = {
            "delivery_id": session.delivery_id,
            "session_id": session.id,
            "callback_url": session.callback_url,
            "target": payload.target.value,
            "activity": {
                "id": activity.id,
                "repository": activity.repository_name,
                "workflow_name": activity.workflow_name,
                "workflow_run_id": activity.workflow_run_id,
                "status": activity.status.value,
                "failure_type": activity.failure_type.value if activity.failure_type else None,
            },
            "goal": session.goal,
            "summary": _handoff_summary(activity, request),
            "github": session.github.model_dump(mode="json"),
            "labels": labels,
            "context_format": payload.context_format,
            "context": sanitized_context,
            "sent_at": utcnow().isoformat(),
        }
        delivered, error_code = await _deliver_handoff_webhook(
            url=target_url,
            payload=outbound_payload,
            timeout_seconds=settings.agent_handoff_timeout_seconds,
            max_retries=settings.agent_handoff_max_retries,
        )
        delivery_status = AgentHandoffStatus.QUEUED if delivered else AgentHandoffStatus.FAILED
        session.status = HandoffSessionStatus.QUEUED if delivered else HandoffSessionStatus.FAILED
        response_message = (
            "Handoff session delivered to target"
            if delivered
            else f"Handoff session delivery failed ({error_code or 'unknown_error'})"
        )
    elif payload.send and settings.agent_handoff_mode != AgentHandoffMode.WEBHOOK.value:
        response_message = "Handoff session recorded; copy-only mode is active"
    elif payload.send:
        response_message = "Handoff session recorded; target URL is not configured"

    await storage.upsert_handoff_session(session)
    await storage.append_handoff_message(initial_message)
    await _record_handoff_activity_audit(
        storage=storage,
        activity=activity,
        session=session,
        status=delivery_status,
        mode=mode,
        error=error_code,
    )
    return HandoffSessionCreateResponse(
        session=session,
        initial_message=initial_message,
        delivery_status=delivery_status,
        message=response_message,
    )


@router.get(
    "/activities/{activity_id}/handoff-sessions",
    response_model=list[HandoffSessionView],
)
async def list_activity_handoff_sessions(
    activity_id: str,
    storage: ActivityStorage = Depends(get_storage),
) -> list[HandoffSessionView]:
    """List durable handoff sessions for an activity."""
    activity = await storage.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    sessions = await storage.list_handoff_sessions_for_activity(activity_id)
    return [
        HandoffSessionView(
            session=session,
            messages=await storage.list_handoff_messages(session.id),
        )
        for session in sessions
    ]


@router.get("/handoff-sessions/{session_id}", response_model=HandoffSessionView)
async def get_handoff_session(
    session_id: str,
    storage: ActivityStorage = Depends(get_storage),
) -> HandoffSessionView:
    """Return one durable handoff session with its messages."""
    session = await storage.get_handoff_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Handoff session not found")
    return HandoffSessionView(
        session=session,
        messages=await storage.list_handoff_messages(session.id),
    )


@router.post("/handoff-sessions/{session_id}/events", response_model=HandoffSessionView)
async def record_handoff_session_event(
    session_id: str,
    payload: HandoffSessionEventRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
) -> HandoffSessionView:
    """Record an external-agent callback event on a handoff session."""
    signature_verified, raw_body = await _verify_handoff_callback_signature(request)
    session = await storage.get_handoff_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Handoff session not found")

    next_status = _HANDOFF_EVENT_STATUS.get(payload.event_type)
    if next_status is not None:
        session.status = next_status
    if payload.external_thread_id:
        session.external_thread_id = payload.external_thread_id
    merged_labels = _handoff_labels(session.target, [*session.labels, *payload.labels])
    session.labels = merged_labels
    if payload.github.repository:
        session.github.repository = payload.github.repository
    for attr in ("run_id", "issue_url", "pr_url", "comment_url", "workflow_rerun_url"):
        value = getattr(payload.github, attr)
        if value:
            setattr(session.github, attr, value)
    if payload.github.labels:
        session.github.labels = _handoff_labels(session.target, payload.github.labels)
    session.updated_at = utcnow()

    raw_payload = json.loads(raw_body.decode("utf-8")) if raw_body else payload.model_dump(mode="json")
    message = HandoffMessage(
        session_id=session.id,
        event_type=payload.event_type,
        direction=HandoffMessageDirection.INBOUND,
        actor=payload.actor.strip() or session.target.value,
        body=_sanitize_handoff_context(payload.message),
        payload_sha256=hashlib.sha256(raw_body).hexdigest() if raw_body else "",
        payload_redacted=_redact_payload(raw_payload if isinstance(raw_payload, dict) else {}),
        github=payload.github,
        labels=payload.labels,
        signature_verified=signature_verified,
        request_id=getattr(request.state, "request_id", None),
    )
    await storage.upsert_handoff_session(session)
    await storage.append_handoff_message(message)

    activity = await storage.get_activity(session.activity_id)
    if activity is not None:
        status = AgentHandoffStatus.QUEUED
        if session.status == HandoffSessionStatus.FAILED:
            status = AgentHandoffStatus.FAILED
        await _record_handoff_activity_audit(
            storage=storage,
            activity=activity,
            session=session,
            status=status,
            mode=AgentHandoffMode.WEBHOOK,
            error=session.status.value if session.status == HandoffSessionStatus.FAILED else None,
        )

    return HandoffSessionView(
        session=session,
        messages=await storage.list_handoff_messages(session.id),
    )


@router.post(
    "/activities/{activity_id}/agent-handoff",
    response_model=AgentHandoffResponse,
)
async def assign_activity_to_agent(
    activity_id: str,
    payload: AgentHandoffRequest,
    request: Request,
    storage: ActivityStorage = Depends(get_storage),
) -> AgentHandoffResponse:
    """Submit one activity handoff request in copy-only or webhook mode.

    This endpoint is intentionally non-blocking for activity page operations:
    it records failed attempts in activity audit metadata and returns a
    structured response instead of raising server errors for delivery failures.
    """
    activity = await storage.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    settings = get_settings()
    effective_mode = payload.mode or AgentHandoffMode(settings.agent_handoff_mode)
    request_id = getattr(request.state, "request_id", None)
    actor = _handoff_actor(request)
    sanitized_context = _sanitize_handoff_context(payload.context)
    context_hash = hashlib.sha256(sanitized_context.encode("utf-8")).hexdigest()

    if not settings.agent_handoff_enabled:
        audit = AgentHandoffAuditEntry(
            status=AgentHandoffStatus.DISABLED,
            mode=effective_mode,
            actor=actor,
            request_id=request_id,
            context_chars=len(sanitized_context),
            context_sha256=context_hash,
            context_preview=_handoff_context_preview(sanitized_context),
            error="disabled_by_runtime",
        )
        activity.agent_handoff_audit.append(audit)
        activity.agent_handoff_audit = activity.agent_handoff_audit[-_AGENT_HANDOFF_MAX_AUDIT_ENTRIES:]
        await storage.update_activity(activity)
        return AgentHandoffResponse(
            status=AgentHandoffStatus.DISABLED,
            mode=effective_mode,
            activity_id=activity.id,
            message="Assign-to-Agent is disabled by runtime configuration",
            request_id=request_id,
        )

    if effective_mode == AgentHandoffMode.COPY_ONLY:
        audit = AgentHandoffAuditEntry(
            status=AgentHandoffStatus.COPIED,
            mode=effective_mode,
            actor=actor,
            request_id=request_id,
            context_chars=len(sanitized_context),
            context_sha256=context_hash,
            context_preview=_handoff_context_preview(sanitized_context),
        )
        activity.agent_handoff_audit.append(audit)
        activity.agent_handoff_audit = activity.agent_handoff_audit[-_AGENT_HANDOFF_MAX_AUDIT_ENTRIES:]
        await storage.update_activity(activity)
        return AgentHandoffResponse(
            status=AgentHandoffStatus.COPIED,
            mode=effective_mode,
            activity_id=activity.id,
            message="Context copied-only handoff recorded",
            request_id=request_id,
        )

    webhook_url = settings.agent_handoff_webhook_url.strip()
    if not webhook_url:
        audit = AgentHandoffAuditEntry(
            status=AgentHandoffStatus.FAILED,
            mode=effective_mode,
            actor=actor,
            request_id=request_id,
            context_chars=len(sanitized_context),
            context_sha256=context_hash,
            context_preview=_handoff_context_preview(sanitized_context),
            error="missing_webhook_url",
        )
        activity.agent_handoff_audit.append(audit)
        activity.agent_handoff_audit = activity.agent_handoff_audit[-_AGENT_HANDOFF_MAX_AUDIT_ENTRIES:]
        await storage.update_activity(activity)
        return AgentHandoffResponse(
            status=AgentHandoffStatus.FAILED,
            mode=effective_mode,
            activity_id=activity.id,
            message="Webhook mode configured without AGENT_HANDOFF_WEBHOOK_URL",
            request_id=request_id,
        )

    parsed = urlparse(webhook_url)
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise HTTPException(status_code=422, detail="Invalid AGENT_HANDOFF_WEBHOOK_URL")
    if not _is_allowed_handoff_host(host, settings.agent_handoff_webhook_allowlist):
        audit = AgentHandoffAuditEntry(
            status=AgentHandoffStatus.FAILED,
            mode=effective_mode,
            actor=actor,
            request_id=request_id,
            context_chars=len(sanitized_context),
            context_sha256=context_hash,
            context_preview=_handoff_context_preview(sanitized_context),
            destination_host=host,
            error="destination_not_allowlisted",
        )
        activity.agent_handoff_audit.append(audit)
        activity.agent_handoff_audit = activity.agent_handoff_audit[-_AGENT_HANDOFF_MAX_AUDIT_ENTRIES:]
        await storage.update_activity(activity)
        return AgentHandoffResponse(
            status=AgentHandoffStatus.FAILED,
            mode=effective_mode,
            activity_id=activity.id,
            message=f"Webhook destination host '{host}' is not allowlisted",
            request_id=request_id,
        )

    delivery_id = f"handoff:{activity.id}:{uuid4()}"
    outbound_payload = {
        "delivery_id": delivery_id,
        "request_id": request_id,
        "activity": {
            "id": activity.id,
            "repository": activity.repository_name,
            "workflow_name": activity.workflow_name,
            "workflow_run_id": activity.workflow_run_id,
            "status": activity.status.value,
            "failure_type": activity.failure_type.value if activity.failure_type else None,
        },
        "summary": _handoff_summary(activity, request),
        "context_format": payload.context_format,
        "context": sanitized_context,
        "sent_at": utcnow().isoformat(),
    }
    delivered, error_code = await _deliver_handoff_webhook(
        url=webhook_url,
        payload=outbound_payload,
        timeout_seconds=settings.agent_handoff_timeout_seconds,
        max_retries=settings.agent_handoff_max_retries,
    )
    status_value = AgentHandoffStatus.QUEUED if delivered else AgentHandoffStatus.FAILED
    audit = AgentHandoffAuditEntry(
        status=status_value,
        mode=effective_mode,
        actor=actor,
        request_id=request_id,
        context_chars=len(sanitized_context),
        context_sha256=context_hash,
        context_preview=_handoff_context_preview(sanitized_context),
        delivery_id=delivery_id,
        destination_host=host,
        error=error_code,
    )
    activity.agent_handoff_audit.append(audit)
    activity.agent_handoff_audit = activity.agent_handoff_audit[-_AGENT_HANDOFF_MAX_AUDIT_ENTRIES:]
    await storage.update_activity(activity)
    if delivered:
        return AgentHandoffResponse(
            status=AgentHandoffStatus.QUEUED,
            mode=effective_mode,
            activity_id=activity.id,
            delivery_id=delivery_id,
            message="Handoff delivered to configured webhook",
            request_id=request_id,
        )
    return AgentHandoffResponse(
        status=AgentHandoffStatus.FAILED,
        mode=effective_mode,
        activity_id=activity.id,
        delivery_id=delivery_id,
        message=f"Handoff delivery failed ({error_code or 'unknown_error'})",
        request_id=request_id,
    )


@router.get("/repositories", response_model=list[dict[str, Any]])
async def get_repositories(storage: ActivityStorage = Depends(get_storage)) -> list[dict[str, Any]]:
    """Get list of repositories with activity counts."""

    try:
        repos = await storage.get_repositories()
        return repos
    except Exception as e:
        logger.exception(f"Failed to get repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/timeline")
async def get_timeline(
    days: int = Query(7, ge=1, le=30, description="Number of days to include"),
    storage: ActivityStorage = Depends(get_storage),
) -> dict[str, Any]:
    """Get activity timeline data for charts."""

    try:
        since = utcnow() - timedelta(days=days)
        timeline = await storage.get_timeline(since=since)
        return timeline
    except Exception as e:
        logger.exception(f"Failed to get timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/failure-breakdown")
async def get_failure_breakdown(
    days: int = Query(30, ge=1, le=90, description="Number of days to include"),
    storage: ActivityStorage = Depends(get_storage),
) -> dict[str, int]:
    """Get breakdown of failures by type."""

    try:
        since = utcnow() - timedelta(days=days)
        breakdown = await storage.get_failure_breakdown(since=since)
        return breakdown
    except Exception as e:
        logger.exception(f"Failed to get failure breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/activities/{activity_id}/retry")
async def retry_activity(
    activity_id: str,
    storage: ActivityStorage = Depends(get_storage),
    workflow: PipelineHealerWorkflow = Depends(get_workflow),
) -> dict[str, Any]:
    """Manually retry a failed remediation."""

    try:
        activity = await storage.get_activity(activity_id)
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")

        if activity.status not in (RemediationStatus.FAILED, RemediationStatus.SKIPPED):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot retry activity with status: {activity.status}",
            )

        # Minimum viable retry: ask GitHub Actions to re-run failed jobs for the run.
        # A new webhook event will arrive if the re-run fails again.
        if "/" not in activity.repository_name:
            raise HTTPException(status_code=500, detail="Invalid repository name format")
        owner, repo = activity.repository_name.split("/", 1)
        await workflow.github_tools.rerun_failed_jobs(
            owner=owner, repo=repo, run_id=activity.workflow_run_id
        )

        return {
            "status": "queued",
            "activity_id": activity_id,
            "message": "GitHub rerun-failed-jobs requested",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to retry activity {activity_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/backfill-diagnostics")
async def backfill_diagnostics(
    max_age_hours: float = Query(default=24.0, ge=1.0, le=168.0),
    workflow: PipelineHealerWorkflow = Depends(get_workflow),
) -> dict[str, Any]:
    """Manually trigger a backfill sweep for external diagnostics.

    Finds completed activities whose ci-doctor poll window was exhausted
    and attempts to attach findings that have been published since.
    """
    try:
        count = await workflow.run_backfill_sweep(max_age_hours=max_age_hours)
        return {
            "status": "completed",
            "backfilled": count,
            "max_age_hours": max_age_hours,
        }
    except Exception as e:
        logger.exception(f"Backfill sweep failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
