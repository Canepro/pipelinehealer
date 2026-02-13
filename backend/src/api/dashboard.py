"""Dashboard API endpoints for PipelineHealer."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..config import get_settings
from ..models import (
    ActivityRecord,
    AdminSettingsAuditEntry,
    AdminSettingsUpdateRequest,
    AppSettingsView,
    DashboardStats,
    FailureType,
    RemediationStatus,
)
from ..storage import ActivityStorage
from ..workflows.pipeline_healer import PipelineHealerWorkflow
from .security import require_admin_key, require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"], dependencies=[Depends(require_api_key)])


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _get_storage_backend_name() -> str:
    """Return a user-friendly name for the currently configured storage backend."""
    if _storage is None:
        return "unknown"
    storage_class = type(_storage).__name__
    if storage_class == "InMemoryStorage":
        return "in_memory"
    if storage_class == "ActivityStorage":
        return "cosmos_db"
    return storage_class.lower()


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


def _build_settings_view() -> AppSettingsView:
    """Build the API response for settings from current runtime configuration."""
    settings = get_settings()
    has_pat, has_app, github_auth_mode = _resolve_github_auth_mode()

    return AppSettingsView(
        environment=settings.environment,
        storage_backend=_get_storage_backend_name(),
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
        ph_allowed_repos=settings.ph_allowed_repos,
        cors_allowed_origins=settings.cors_allowed_origins,
        cors_allow_origin_regex=settings.cors_allow_origin_regex,
        azure_openai_endpoint=settings.azure_openai_endpoint,
        azure_openai_deployment_name=settings.azure_openai_deployment_name,
        azure_openai_api_version=settings.azure_openai_api_version,
    )


# Storage instance (will be properly initialized)
_storage: ActivityStorage | None = None
_workflow: PipelineHealerWorkflow | None = None
_admin_settings_audit: list[AdminSettingsAuditEntry] = []
_MAX_ADMIN_SETTINGS_AUDIT_ENTRIES = 200


def set_storage(storage: ActivityStorage) -> None:
    """Set the storage instance for the dashboard."""
    global _storage
    _storage = storage


def set_workflow(workflow: PipelineHealerWorkflow) -> None:
    """Set the workflow instance for retry operations."""
    global _workflow
    _workflow = workflow


def clear_admin_settings_audit() -> None:
    """Clear in-memory admin settings audit log (useful for tests)."""
    _admin_settings_audit.clear()


def get_storage() -> ActivityStorage:
    """Get the storage instance."""
    if _storage is None:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    return _storage


def get_workflow() -> PipelineHealerWorkflow:
    """Get the workflow instance."""
    if _workflow is None:
        raise HTTPException(status_code=500, detail="Workflow not initialized")
    return _workflow


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats() -> DashboardStats:
    """Get overall statistics for the dashboard."""
    storage = get_storage()

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
async def get_app_settings() -> AppSettingsView:
    """Get non-secret runtime settings for admin users."""
    return _build_settings_view()


@router.patch(
    "/settings",
    response_model=AppSettingsView,
    dependencies=[Depends(require_admin_key)],
)
async def update_app_settings(
    update: AdminSettingsUpdateRequest,
    request: Request,
    user_agent: str | None = Header(default=None, alias="User-Agent"),
) -> AppSettingsView:
    """Apply admin runtime overrides (in-memory until backend restart)."""
    settings = get_settings()
    changes = update.model_dump(exclude_none=True)

    if not changes:
        return _build_settings_view()

    if "heal_mode" in changes:
        heal_mode = str(changes["heal_mode"]).strip().lower()
        if heal_mode not in {"safe", "demo"}:
            raise HTTPException(
                status_code=422,
                detail="heal_mode must be one of: safe, demo",
            )
        changes["heal_mode"] = heal_mode

    max_chars = int(changes.get("log_prompt_max_chars", settings.log_prompt_max_chars))
    head_chars = int(changes.get("log_prompt_head_chars", settings.log_prompt_head_chars))
    tail_chars = int(changes.get("log_prompt_tail_chars", settings.log_prompt_tail_chars))
    if head_chars + tail_chars > max_chars:
        raise HTTPException(
            status_code=422,
            detail="log_prompt_head_chars + log_prompt_tail_chars must be <= log_prompt_max_chars",
        )

    previous_values = {key: getattr(settings, key, None) for key in changes}
    for key, value in changes.items():
        setattr(settings, key, value)

    workflow = get_workflow()
    workflow.refresh_runtime_settings()

    audit_entry = AdminSettingsAuditEntry(
        changed_keys=sorted(changes.keys()),
        changes={
            key: {"old": previous_values[key], "new": changes[key]}
            for key in sorted(changes.keys())
        },
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
    )
    _admin_settings_audit.append(audit_entry)
    if len(_admin_settings_audit) > _MAX_ADMIN_SETTINGS_AUDIT_ENTRIES:
        del _admin_settings_audit[: len(_admin_settings_audit) - _MAX_ADMIN_SETTINGS_AUDIT_ENTRIES]

    logger.info("Admin runtime settings updated; changed_keys=%s", sorted(changes.keys()))

    return _build_settings_view()


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
) -> list[AdminSettingsAuditEntry]:
    """Get recent admin settings change records (latest first)."""
    return list(reversed(_admin_settings_audit))[:limit]


@router.get("/activities", response_model=list[ActivityRecord])
async def get_activities(
    repository: str | None = Query(None, description="Filter by repository name"),
    status: RemediationStatus | None = Query(None, description="Filter by status"),
    failure_type: FailureType | None = Query(None, description="Filter by failure type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    since: datetime | None = Query(None, description="Filter activities since this time"),
) -> list[ActivityRecord]:
    """Get activity records with optional filtering."""
    storage = get_storage()

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
async def get_activity(activity_id: str) -> ActivityRecord:
    """Get a specific activity record by ID."""
    storage = get_storage()

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
async def get_repositories() -> list[dict[str, Any]]:
    """Get list of repositories with activity counts."""
    storage = get_storage()

    try:
        repos = await storage.get_repositories()
        return repos
    except Exception as e:
        logger.exception(f"Failed to get repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/timeline")
async def get_timeline(
    days: int = Query(7, ge=1, le=30, description="Number of days to include"),
) -> dict[str, Any]:
    """Get activity timeline data for charts."""
    storage = get_storage()

    try:
        since = _utcnow() - timedelta(days=days)
        timeline = await storage.get_timeline(since=since)
        return timeline
    except Exception as e:
        logger.exception(f"Failed to get timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/failure-breakdown")
async def get_failure_breakdown(
    days: int = Query(30, ge=1, le=90, description="Number of days to include"),
) -> dict[str, int]:
    """Get breakdown of failures by type."""
    storage = get_storage()

    try:
        since = _utcnow() - timedelta(days=days)
        breakdown = await storage.get_failure_breakdown(since=since)
        return breakdown
    except Exception as e:
        logger.exception(f"Failed to get failure breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/activities/{activity_id}/retry")
async def retry_activity(activity_id: str) -> dict[str, Any]:
    """Manually retry a failed remediation."""
    storage = get_storage()
    workflow = get_workflow()

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
        activity.updated_at = _utcnow()
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
