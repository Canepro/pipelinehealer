"""Dashboard API endpoints for PipelineHealer."""

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..models import (
    ActivityRecord,
    DashboardStats,
    FailureType,
    RemediationStatus,
)
from ..storage import ActivityStorage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"])

# Storage instance (will be properly initialized)
_storage: ActivityStorage | None = None


def set_storage(storage: ActivityStorage) -> None:
    """Set the storage instance for the dashboard."""
    global _storage
    _storage = storage


def get_storage() -> ActivityStorage:
    """Get the storage instance."""
    if _storage is None:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    return _storage


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats() -> DashboardStats:
    """Get overall statistics for the dashboard."""
    storage = get_storage()
    
    try:
        stats = await storage.get_stats()
        return stats
    except Exception as e:
        logger.exception(f"Failed to get dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/repositories", response_model=list[dict[str, Any]])
async def get_repositories() -> list[dict[str, Any]]:
    """Get list of repositories with activity counts."""
    storage = get_storage()
    
    try:
        repos = await storage.get_repositories()
        return repos
    except Exception as e:
        logger.exception(f"Failed to get repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline")
async def get_timeline(
    days: int = Query(7, ge=1, le=30, description="Number of days to include"),
) -> dict[str, Any]:
    """Get activity timeline data for charts."""
    storage = get_storage()
    
    try:
        since = datetime.utcnow() - timedelta(days=days)
        timeline = await storage.get_timeline(since=since)
        return timeline
    except Exception as e:
        logger.exception(f"Failed to get timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/failure-breakdown")
async def get_failure_breakdown(
    days: int = Query(30, ge=1, le=90, description="Number of days to include"),
) -> dict[str, int]:
    """Get breakdown of failures by type."""
    storage = get_storage()
    
    try:
        since = datetime.utcnow() - timedelta(days=days)
        breakdown = await storage.get_failure_breakdown(since=since)
        return breakdown
    except Exception as e:
        logger.exception(f"Failed to get failure breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/activities/{activity_id}/retry")
async def retry_activity(activity_id: str) -> dict[str, Any]:
    """Manually retry a failed remediation."""
    storage = get_storage()
    
    try:
        activity = await storage.get_activity(activity_id)
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")
        
        if activity.status not in (RemediationStatus.FAILED, RemediationStatus.SKIPPED):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot retry activity with status: {activity.status}",
            )
        
        # TODO: Implement retry logic through workflow
        # For now, just mark it as pending
        activity.status = RemediationStatus.PENDING
        activity.updated_at = datetime.utcnow()
        await storage.update_activity(activity)
        
        return {
            "status": "queued",
            "activity_id": activity_id,
            "message": "Remediation retry queued",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to retry activity {activity_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
