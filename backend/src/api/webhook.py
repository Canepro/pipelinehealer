"""GitHub Webhook Handler for PipelineHealer."""

import hashlib
import hmac
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..config import get_settings
from ..models import JenkinsBridgePayload, WorkflowRunEvent
from ..workflows.pipeline_healer import PipelineHealerWorkflow
from .deps import get_workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])
_jenkins_nonce_replay: dict[str, float] = {}
_jenkins_delivery_replay: dict[str, float] = {}


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
    # Empty allowlist means "no repo restriction" for local/demo convenience.
    if not allowed_repos:
        return True
    normalized = repo_full_name.strip().lower()
    return normalized in {repo.strip().lower() for repo in allowed_repos if repo.strip()}


def _cleanup_replay_store(now_epoch: float, ttl_seconds: int) -> None:
    cutoff = now_epoch - float(ttl_seconds)
    for key, seen_at in list(_jenkins_nonce_replay.items()):
        if seen_at < cutoff:
            _jenkins_nonce_replay.pop(key, None)
    for key, seen_at in list(_jenkins_delivery_replay.items()):
        if seen_at < cutoff:
            _jenkins_delivery_replay.pop(key, None)


def _build_jenkins_canonical_string(
    *,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    body_sha = hashlib.sha256(body).hexdigest()
    return "\n".join([method.upper(), path, timestamp, nonce, body_sha])


def _verify_jenkins_bridge_signature(
    *,
    body: bytes,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    signature: str,
    secret: str,
) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    canonical = _build_jenkins_canonical_string(
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")


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
        workflow = await get_workflow(request)
        return await _handle_workflow_run_event(payload, x_github_delivery, workflow)
    elif x_github_event == "ping":
        return {"status": "pong", "delivery_id": x_github_delivery}
    else:
        logger.debug(f"Ignoring event type: {x_github_event}")
        return {
            "status": "ignored",
            "event": x_github_event,
            "delivery_id": x_github_delivery,
        }


async def _handle_workflow_run_event(
    payload: dict[str, Any],
    delivery_id: str,
    workflow: PipelineHealerWorkflow,
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
    # Server-side repository scope guard. This protects PAT-based deployments from acting org-wide.
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

    try:
        # Start the workflow asynchronously
        activity_id = await workflow.start(event)

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


@router.post("/jenkins")
async def handle_jenkins_bridge_webhook(
    request: Request,
    workflow: PipelineHealerWorkflow = Depends(get_workflow),
    x_ph_bridge_provider: str = Header(..., alias="X-PH-Bridge-Provider"),
    x_ph_bridge_timestamp: str = Header(..., alias="X-PH-Bridge-Timestamp"),
    x_ph_bridge_nonce: str = Header(..., alias="X-PH-Bridge-Nonce"),
    x_ph_bridge_signature: str = Header(..., alias="X-PH-Bridge-Signature"),
) -> dict[str, Any]:
    """Handle signed Jenkins bridge ingestion payloads."""
    settings = get_settings()
    if not settings.jenkins_bridge_enabled:
        raise HTTPException(status_code=404, detail="Jenkins bridge webhook is disabled")

    body = await request.body()
    if len(body) > settings.jenkins_bridge_max_body_bytes:
        raise HTTPException(status_code=413, detail="Bridge payload exceeds maximum body size")
    if x_ph_bridge_provider.strip().lower() != "jenkins":
        raise HTTPException(status_code=422, detail="Unsupported bridge provider")
    if not settings.jenkins_bridge_shared_secret:
        raise HTTPException(status_code=500, detail="Jenkins bridge shared secret not configured")

    try:
        timestamp_value = int(x_ph_bridge_timestamp.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid bridge timestamp header") from exc

    now_epoch = time.time()
    skew = abs(now_epoch - float(timestamp_value))
    if skew > settings.jenkins_bridge_max_skew_seconds:
        raise HTTPException(status_code=429, detail="Bridge timestamp outside allowed skew window")

    _cleanup_replay_store(now_epoch, settings.jenkins_bridge_replay_ttl_seconds)
    nonce_key = f"jenkins:{x_ph_bridge_nonce.strip()}"
    if nonce_key in _jenkins_nonce_replay:
        return {"status": "ignored", "reason": "duplicate_delivery", "delivery_id": None}

    if not _verify_jenkins_bridge_signature(
        body=body,
        method=request.method,
        path=request.url.path,
        timestamp=x_ph_bridge_timestamp.strip(),
        nonce=x_ph_bridge_nonce.strip(),
        signature=x_ph_bridge_signature.strip(),
        secret=settings.jenkins_bridge_shared_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid bridge signature")

    try:
        payload_json = await request.json()
        payload = JenkinsBridgePayload(**payload_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Jenkins bridge payload: {exc}") from exc

    if payload.provider.strip().lower() != "jenkins":
        raise HTTPException(status_code=422, detail="Invalid payload provider")
    if not _is_allowed_repo(payload.repository, settings.ph_allowed_repos):
        raise HTTPException(status_code=403, detail="Repository is outside PH_ALLOWED_REPOS")

    delivery_key = f"jenkins:{payload.delivery_id.strip()}"
    if delivery_key in _jenkins_delivery_replay:
        return {
            "status": "ignored",
            "reason": "duplicate_delivery",
            "delivery_id": payload.delivery_id,
        }

    _jenkins_nonce_replay[nonce_key] = now_epoch
    _jenkins_delivery_replay[delivery_key] = now_epoch

    activity_id = await workflow.start_bridge_failure(
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return {
        "status": "processing",
        "activity_id": activity_id,
        "source": "jenkins_bridge",
        "repository": payload.repository,
        "delivery_id": payload.delivery_id,
    }


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "pipelinehealer-webhook"}
