"""Shared FastAPI dependency functions for PipelineHealer API routes.

All route handlers should obtain ``storage`` and ``workflow`` instances via
these dependencies, which read from ``request.app.state`` (set during the
application lifespan in ``main.py``).
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..storage import ActivityStorage
from ..workflows.pipeline_healer import PipelineHealerWorkflow


def get_storage(request: Request) -> ActivityStorage:
    """FastAPI dependency: return the ``ActivityStorage`` from app state."""
    storage: ActivityStorage | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    return storage


def get_workflow(request: Request) -> PipelineHealerWorkflow:
    """FastAPI dependency: return the ``PipelineHealerWorkflow`` from app state."""
    workflow: PipelineHealerWorkflow | None = getattr(request.app.state, "workflow", None)
    if workflow is None:
        raise HTTPException(status_code=500, detail="Workflow not initialized")
    return workflow
