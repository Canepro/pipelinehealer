"""Dashboard API endpoints for PipelineHealer."""

import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..config import get_settings
from ..models import (
    ActivityRecord,
    AdminSettingsAuditEntry,
    AdminSettingsPersistRequest,
    AdminSettingsPersistResponse,
    AdminSettingsUpdateRequest,
    AppSettingsView,
    DashboardStats,
    FailureType,
    RemediationStatus,
    utcnow,
)
from ..storage import ActivityStorage
from ..workflows.pipeline_healer import PipelineHealerWorkflow
from .deps import get_storage, get_workflow
from .security import require_admin_key, require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"], dependencies=[Depends(require_api_key)])
_REPO_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


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


def _get_storage_backend_name(storage: ActivityStorage | None) -> str:
    """Return a user-friendly name for the currently configured storage backend."""
    if storage is None:
        return "unknown"
    storage_class = type(storage).__name__
    if storage_class == "InMemoryStorage":
        return "in_memory"
    if storage_class == "ActivityStorage":
        return "cosmos_db"
    return storage_class.lower()


def _safe_settings_allowlist(raw_repos: list[str]) -> list[str]:
    """Best-effort normalization for settings view without crashing on bad env values."""
    try:
        return _normalize_allowed_repo_list(raw_repos)
    except ValueError:
        logger.warning("Invalid PH_ALLOWED_REPOS entry detected; exposing raw values in settings view")
        return [str(repo).strip() for repo in raw_repos if str(repo).strip()]


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


def _resolve_github_auth_mode() -> tuple[bool, bool, str]:
    """Return GitHub auth capabilities and active mode description."""
    settings = get_settings()
    has_pat = bool(settings.github_personal_access_token)
    has_app = bool(settings.github_app_id and settings.key_vault_url)

    if has_pat and has_app:
        mode = "pat+github_app"
    elif has_app:
        mode = "github_app"
    elif has_pat:
        mode = "pat"
    else:
        mode = "none"

    return has_pat, has_app, mode


def _build_settings_view(storage: ActivityStorage | None = None) -> AppSettingsView:
    """Build the API response for settings from current runtime configuration."""
    settings = get_settings()
    has_pat, has_app, github_auth_mode = _resolve_github_auth_mode()

    return AppSettingsView(
        environment=settings.environment,
        storage_backend=_get_storage_backend_name(storage),
        heal_mode=settings.heal_mode,
        auto_create_pr=settings.auto_create_pr,
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
        api_auth_enabled=bool(settings.api_auth_key),
        admin_api_auth_enabled=bool(settings.admin_api_key),
        github_pat_configured=has_pat,
        github_app_configured=has_app,
        github_auth_mode=github_auth_mode,
        gh_aw_tools_enabled=settings.gh_aw_tools_enabled,
        gh_aw_ingestion_mode=settings.gh_aw_ingestion_mode,
        gh_aw_known_workflows=_normalize_workflow_names(settings.gh_aw_known_workflows),
        ph_allowed_repos=_safe_settings_allowlist(settings.ph_allowed_repos),
        cors_allowed_origins=settings.cors_allowed_origins,
        cors_allow_origin_regex=settings.cors_allow_origin_regex,
        azure_openai_endpoint=settings.azure_openai_endpoint,
        azure_openai_deployment_name=settings.azure_openai_deployment_name,
        azure_openai_api_version=settings.azure_openai_api_version,
        azure_openai_chat_api_version=settings.azure_openai_chat_api_version,
    )


# Lightweight demo audit buffer (non-durable by design for hackathon runtime).
_admin_settings_audit: list[AdminSettingsAuditEntry] = []
_MAX_ADMIN_SETTINGS_AUDIT_ENTRIES = 200
_MUTABLE_SETTINGS_ENV_KEYS: tuple[tuple[str, str], ...] = (
    ("heal_mode", "HEAL_MODE"),
    ("auto_create_pr", "AUTO_CREATE_PR"),
    ("auto_create_tracking_issue_for_prs", "AUTO_CREATE_TRACKING_ISSUE_FOR_PRS"),
    ("max_remediation_attempts", "MAX_REMEDIATION_ATTEMPTS"),
    (
        "verify_webhook_signature_in_development",
        "VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT",
    ),
    ("pipeline_step_timeout_seconds", "PIPELINE_STEP_TIMEOUT_SECONDS"),
    ("github_api_max_retries", "GITHUB_API_MAX_RETRIES"),
    ("github_api_retry_base_seconds", "GITHUB_API_RETRY_BASE_SECONDS"),
    ("github_api_retry_max_seconds", "GITHUB_API_RETRY_MAX_SECONDS"),
    ("log_prompt_max_chars", "LOG_PROMPT_MAX_CHARS"),
    ("log_prompt_head_chars", "LOG_PROMPT_HEAD_CHARS"),
    ("log_prompt_tail_chars", "LOG_PROMPT_TAIL_CHARS"),
    ("gh_aw_tools_enabled", "GH_AW_TOOLS_ENABLED"),
    ("gh_aw_ingestion_mode", "GH_AW_INGESTION_MODE"),
    ("gh_aw_known_workflows", "GH_AW_KNOWN_WORKFLOWS"),
    ("ph_allowed_repos", "PH_ALLOWED_REPOS"),
    ("azure_openai_deployment_name", "AZURE_OPENAI_DEPLOYMENT_NAME"),
)


def clear_admin_settings_audit() -> None:
    """Clear in-memory admin settings audit log (useful for tests)."""
    _admin_settings_audit.clear()


def _repo_root() -> Path:
    """Resolve repository root for helper command/script execution."""
    override = os.getenv("PIPELINEHEALER_REPO_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    # backend/src/api/dashboard.py -> repo root is 2 levels up (/app in container).
    return Path(__file__).resolve().parents[2]


def _env_file_path() -> Path:
    """Resolve mutable env file path used by settings persistence."""
    override = os.getenv("PIPELINEHEALER_ENV_FILE_PATH", "").strip()
    if override:
        return Path(override).resolve()
    return _repo_root() / "backend" / ".env"


def _env_bool(value: bool) -> str:
    return "true" if value else "false"


def _mutable_runtime_settings_snapshot() -> dict[str, Any]:
    """Capture live mutable runtime settings in normalized Python types."""
    settings = get_settings()
    values: dict[str, Any] = {}
    for attr_name, _ in _MUTABLE_SETTINGS_ENV_KEYS:
        raw = getattr(settings, attr_name)
        if attr_name == "ph_allowed_repos":
            values[attr_name] = _safe_settings_allowlist(raw)
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
        if attr_name in {"ph_allowed_repos", "gh_aw_known_workflows"}:
            values[env_key] = ",".join(raw)
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
        if normalized not in {"safe", "demo", "debug"}:
            raise ValueError("invalid heal_mode")
        return normalized
    if attr_name in {
        "auto_create_pr",
        "auto_create_tracking_issue_for_prs",
        "verify_webhook_signature_in_development",
        "gh_aw_tools_enabled",
    }:
        return _coerce_bool(value)
    if attr_name in {"max_remediation_attempts", "github_api_max_retries", "log_prompt_max_chars", "log_prompt_head_chars", "log_prompt_tail_chars"}:
        return int(value)
    if attr_name in {"pipeline_step_timeout_seconds", "github_api_retry_base_seconds", "github_api_retry_max_seconds"}:
        return float(value)
    if attr_name == "gh_aw_ingestion_mode":
        normalized = str(value).strip().lower()
        if normalized not in {"disabled", "passive"}:
            raise ValueError("invalid gh_aw_ingestion_mode")
        return normalized
    if attr_name == "gh_aw_known_workflows":
        if not isinstance(value, list):
            raise ValueError("invalid gh_aw_known_workflows")
        return _normalize_workflow_names(value)
    if attr_name == "ph_allowed_repos":
        if not isinstance(value, list):
            raise ValueError("invalid ph_allowed_repos")
        return _normalize_allowed_repo_list(value)
    if attr_name == "azure_openai_deployment_name":
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("invalid azure_openai_deployment_name")
        return normalized
    return value


async def apply_persisted_runtime_settings(
    storage: ActivityStorage,
    workflow: PipelineHealerWorkflow | None = None,
) -> None:
    """Apply persisted mutable runtime settings at startup, if available.

    Called during lifespan init with explicit storage/workflow references.
    """
    persisted = await storage.get_runtime_settings()
    if not persisted:
        return

    settings = get_settings()
    changed_keys: list[str] = []
    for attr_name, _ in _MUTABLE_SETTINGS_ENV_KEYS:
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

    if changed_keys and workflow is not None:
        workflow.refresh_runtime_settings()
        logger.info(
            "Applied persisted runtime settings from storage",
            extra={"changed_keys": sorted(changed_keys)},
        )


def _truncate_output(raw: str, limit: int = 280) -> str:
    text = raw.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


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
    """Apply admin runtime overrides (in-memory until backend restart)."""
    settings = get_settings()
    changes = update.model_dump(exclude_none=True)

    if not changes:
        return _build_settings_view(storage)

    if "heal_mode" in changes:
        heal_mode = str(changes["heal_mode"]).strip().lower()
        if heal_mode not in {"safe", "demo", "debug"}:
            raise HTTPException(
                status_code=422,
                detail="heal_mode must be one of: safe, demo, debug",
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
        if mode not in {"disabled", "passive"}:
            raise HTTPException(
                status_code=422,
                detail="gh_aw_ingestion_mode must be one of: disabled, passive",
            )
        changes["gh_aw_ingestion_mode"] = mode

    if "gh_aw_known_workflows" in changes:
        workflows = changes["gh_aw_known_workflows"]
        if not isinstance(workflows, list):
            raise HTTPException(status_code=422, detail="gh_aw_known_workflows must be a list")
        changes["gh_aw_known_workflows"] = _normalize_workflow_names(workflows)

    if "azure_openai_deployment_name" in changes:
        deployment_name = str(changes["azure_openai_deployment_name"]).strip()
        if not deployment_name:
            raise HTTPException(
                status_code=422,
                detail="azure_openai_deployment_name must be a non-empty string",
            )
        changes["azure_openai_deployment_name"] = deployment_name

    max_chars = int(changes.get("log_prompt_max_chars", settings.log_prompt_max_chars))
    head_chars = int(changes.get("log_prompt_head_chars", settings.log_prompt_head_chars))
    tail_chars = int(changes.get("log_prompt_tail_chars", settings.log_prompt_tail_chars))
    if head_chars + tail_chars > max_chars:
        raise HTTPException(
            status_code=422,
            detail="log_prompt_head_chars + log_prompt_tail_chars must be <= log_prompt_max_chars",
        )

    # Capture the pre-change snapshot so audit entries can store old -> new values.
    previous_values = {key: getattr(settings, key, None) for key in changes}
    for key, value in changes.items():
        setattr(settings, key, value)

    workflow.refresh_runtime_settings()

    # Never store raw admin credentials. Keep a short salted fingerprint for traceability.
    actor_fingerprint: str | None = None
    if x_admin_key:
        salted = f"{settings.audit_salt}:{x_admin_key}" if settings.audit_salt else x_admin_key
        actor_fingerprint = f"admin_key:sha256:{hashlib.sha256(salted.encode('utf-8')).hexdigest()[:12]}"

    audit_entry = AdminSettingsAuditEntry(
        changed_keys=sorted(changes.keys()),
        changes={
            key: {"old": previous_values[key], "new": changes[key]}
            for key in sorted(changes.keys())
        },
        actor=actor_fingerprint,
        # request_id is injected by middleware to correlate audit entries with API logs.
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    _admin_settings_audit.append(audit_entry)
    try:
        await storage.append_admin_settings_audit_entry(
            audit_entry.model_dump(mode="json")
        )
    except Exception as exc:
        logger.warning("Failed to persist admin settings audit entry: %s", exc)

    # Keep memory bounded for long-running pods.
    if len(_admin_settings_audit) > _MAX_ADMIN_SETTINGS_AUDIT_ENTRIES:
        del _admin_settings_audit[: len(_admin_settings_audit) - _MAX_ADMIN_SETTINGS_AUDIT_ENTRIES]

    logger.info("Admin runtime settings updated; changed_keys=%s", sorted(changes.keys()))

    return _build_settings_view(storage)


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
    request: AdminSettingsPersistRequest,
    storage: ActivityStorage = Depends(get_storage),
) -> AdminSettingsPersistResponse:
    """Persist effective mutable runtime settings to durable storage and optionally redeploy."""
    runtime_values = _mutable_runtime_settings_snapshot()
    env_values = _runtime_settings_to_env_values(runtime_values)
    persisted_keys = list(env_values.keys())

    try:
        await _persist_mutable_settings_to_storage(runtime_values, storage)
    except Exception as exc:
        logger.exception("Failed to persist mutable runtime settings to storage: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to persist settings to durable storage",
        ) from exc

    env_file = _persist_mutable_settings_to_env_file(env_values)
    if request.skip_redeploy:
        return AdminSettingsPersistResponse(
            env_file=env_file or "",
            persisted_keys=persisted_keys,
            redeploy_attempted=False,
            redeploy_started=False,
            redeploy_message=(
                "Persisted settings to durable storage"
                + (f" and {env_file}" if env_file else "")
                + " (redeploy skipped by request)"
            ),
        )

    if env_file is None:
        return AdminSettingsPersistResponse(
            env_file="",
            persisted_keys=persisted_keys,
            redeploy_attempted=False,
            redeploy_started=False,
            redeploy_message=(
                "Persisted settings to durable storage. "
                "Local backend/.env not available in this runtime, so env-only redeploy was skipped."
            ),
        )

    redeploy_started, redeploy_message = await _start_env_only_redeploy_background()
    if not redeploy_started:
        logger.warning("Admin settings persisted but env-only redeploy did not start: %s", redeploy_message)
    else:
        logger.info("Admin settings persisted and env-only redeploy started")

    return AdminSettingsPersistResponse(
        env_file=env_file,
        persisted_keys=persisted_keys,
        redeploy_attempted=True,
        redeploy_started=redeploy_started,
        redeploy_message=redeploy_message,
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

        activity.status = RemediationStatus.PENDING
        activity.error = None
        activity.updated_at = utcnow()
        await storage.update_activity(activity)

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
