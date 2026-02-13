"""GitHub Webhook Handler for PipelineHealer."""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from ..config import get_settings
from ..models import WorkflowRunEvent
from ..workflows import PipelineHealerWorkflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

# Workflow instance (will be properly initialized with dependencies)
_workflow: PipelineHealerWorkflow | None = None


def set_workflow(workflow: PipelineHealerWorkflow) -> None:
    """Set the workflow instance for handling events."""
    global _workflow
    _workflow = workflow


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the GitHub webhook signature.

    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header value
        secret: Webhook secret

    Returns:
        True if signature is valid
    """
    if not signature or not signature.startswith("sha256="):
        return False

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected_signature}", signature)


def _is_allowed_repo(repo_full_name: str, allowed_repos: list[str]) -> bool:
    """Return True when repo is in allowlist (or allowlist is empty)."""
    if not allowed_repos:
        return True
    normalized = repo_full_name.strip().lower()
    return normalized in {repo.strip().lower() for repo in allowed_repos if repo.strip()}


@router.post("/github")
async def handle_github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: str = Header(..., alias="X-GitHub-Delivery"),
) -> dict[str, Any]:
    """Handle incoming GitHub webhook events.

    This endpoint receives workflow_run events from GitHub and triggers
    the PipelineHealer workflow for failed runs.
    """
    settings = get_settings()

    # Get raw body for signature verification
    body = await request.body()

    should_verify_signature = settings.verify_webhook_signature and (
        settings.environment != "development"
        or settings.verify_webhook_signature_in_development
    )

    if should_verify_signature:
        if not settings.github_webhook_secret:
            logger.error("GitHub webhook secret not configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook secret not configured",
            )

        if not verify_github_signature(
            body, x_hub_signature_256 or "", settings.github_webhook_secret
        ):
            logger.warning(f"Invalid webhook signature for delivery {x_github_delivery}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
    elif settings.environment != "development" and not settings.verify_webhook_signature:
        # Explicitly log insecure non-dev mode to make the policy obvious.
        logger.warning("Webhook signature verification is disabled in a non-development environment")

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from e

    logger.info(
        f"Received GitHub webhook: event={x_github_event}, "
        f"delivery={x_github_delivery}, action={payload.get('action', 'N/A')}"
    )

    # Handle different event types
    if x_github_event == "workflow_run":
        return await handle_workflow_run_event(payload, x_github_delivery)
    elif x_github_event == "ping":
        return {"status": "pong", "delivery_id": x_github_delivery}
    else:
        logger.debug(f"Ignoring event type: {x_github_event}")
        return {
            "status": "ignored",
            "event": x_github_event,
            "delivery_id": x_github_delivery,
        }


async def handle_workflow_run_event(
    payload: dict[str, Any],
    delivery_id: str,
) -> dict[str, Any]:
    """Handle a workflow_run event from GitHub.

    We're interested in completed workflow runs that have failed.
    """
    action = payload.get("action")
    workflow_run = payload.get("workflow_run", {})
    conclusion = workflow_run.get("conclusion")

    # Only process completed runs that failed
    if action != "completed":
        logger.debug(f"Ignoring workflow_run action: {action}")
        return {
            "status": "ignored",
            "reason": f"action is '{action}', not 'completed'",
            "delivery_id": delivery_id,
        }

    if conclusion not in ("failure", "timed_out"):
        logger.debug(f"Ignoring workflow_run conclusion: {conclusion}")
        return {
            "status": "ignored",
            "reason": f"conclusion is '{conclusion}', not a failure",
            "delivery_id": delivery_id,
        }

    # Parse the event
    try:
        event = WorkflowRunEvent(**payload)
    except Exception as e:
        logger.error(f"Failed to parse workflow_run event: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid workflow_run event format: {e}",
        ) from e

    settings = get_settings()
    repo_full_name = event.repository.full_name
    if not _is_allowed_repo(repo_full_name, settings.ph_allowed_repos):
        logger.info(
            "webhook ignored: repo %s not in PH_ALLOWED_REPOS (delivery=%s)",
            repo_full_name,
            delivery_id,
        )
        return {
            "status": "ignored",
            "reason": f"repository '{repo_full_name}' is outside PH_ALLOWED_REPOS",
            "delivery_id": delivery_id,
        }

    logger.info(
        f"Processing failed workflow run: "
        f"repo={repo_full_name}, "
        f"workflow={event.workflow_run.name}, "
        f"run_id={event.workflow_run.id}, "
        f"conclusion={conclusion}"
    )

    # Trigger the healing workflow
    if _workflow is None:
        logger.error("Workflow not initialized")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workflow not initialized",
        )

    try:
        # Start the workflow asynchronously
        activity_id = await _workflow.start(event)

        return {
            "status": "processing",
            "activity_id": activity_id,
            "repository": event.repository.full_name,
            "workflow_run_id": event.workflow_run.id,
            "delivery_id": delivery_id,
        }
    except Exception as e:
        logger.exception(f"Failed to start healing workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start healing workflow: {e}",
        ) from e


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "pipelinehealer-webhook"}
