"""PipelineHealer Workflow using Microsoft Agent Framework workflows."""

import asyncio
import logging
from contextlib import suppress
from typing import Any
from uuid import uuid4

from azure.identity import DefaultAzureCredential

from ..agents.orchestrator import OrchestratorAgent
from ..config import get_settings
from ..models import (
    ActivityRecord,
    JenkinsBridgePayload,
    RemediationStatus,
    WorkflowRunEvent,
)
from ..storage import ActivityStorage, InMemoryStorage, PostgresStorage
from ..tools.github_tools import GitHubTools

logger = logging.getLogger(__name__)

_STORAGE_MODE_MEMORY = "memory"
_STORAGE_MODE_COSMOS = "cosmos"
_STORAGE_MODE_POSTGRES = "postgres"


class PipelineHealerWorkflow:
    """Main workflow for the PipelineHealer system.

    This workflow coordinates the entire healing pipeline:
    1. Receives workflow failure events
    2. Orchestrates agents to analyze and diagnose
    3. Generates and applies remediations
    4. Tracks all activity for the dashboard
    """

    def __init__(
        self,
        github_tools: GitHubTools | None = None,
        storage: ActivityStorage | None = None,
        azure_credential: DefaultAzureCredential | None = None,
    ):
        """Initialize the PipelineHealer workflow.

        Args:
            github_tools: GitHub tools instance (created if not provided)
            storage: Activity storage (uses in-memory if not provided)
            azure_credential: Azure credential for services
        """
        self._settings = get_settings()
        self._credential = azure_credential or DefaultAzureCredential()

        # Initialize GitHub tools
        self._github_tools = github_tools or GitHubTools()

        # Initialize storage
        self._storage = storage or InMemoryStorage()

        # Initialize the orchestrator
        self._orchestrator = OrchestratorAgent(
            github_tools=self._github_tools,
            storage=self._storage,
            azure_credential=self._credential,
        )

        # Background task tracking
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}

    async def initialize(self) -> None:
        """Initialize the workflow and its dependencies."""
        await self._storage.initialize()
        logger.info("PipelineHealer workflow initialized")

    async def close(self) -> None:
        """Clean up resources."""
        # Cancel any running tasks
        # Iterate over a snapshot because task done-callbacks mutate
        # ``self._running_tasks`` by popping completed task IDs.
        for task_id, task in list(self._running_tasks.items()):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            self._running_tasks.pop(task_id, None)

        await self._github_tools.close()
        await self._storage.close()
        logger.info("PipelineHealer workflow closed")

    async def start(self, event: WorkflowRunEvent) -> str:
        """Start processing a workflow failure event.

        This method starts the healing pipeline asynchronously and returns
        an activity ID that can be used to track progress.

        Args:
            event: The workflow run event from GitHub

        Returns:
            Activity ID for tracking
        """
        # Check if we should process this event
        should_process, reason = await self._orchestrator.should_process(event)

        if not should_process:
            logger.info(f"Skipping event: {reason}")
            # Create a skipped activity record
            activity = ActivityRecord(
                id=str(uuid4()),
                repositoryId=str(event.repository.id),
                repository_name=event.repository.full_name,
                workflow_run_id=event.workflow_run.id,
                workflow_name=event.workflow_run.name or "Unknown",
                status=RemediationStatus.SKIPPED,
                error=reason,
            )
            await self._storage.create_activity(activity)
            return activity.id

        # Create the persisted activity record up-front so the returned ID is queryable immediately.
        activity = ActivityRecord(
            repositoryId=str(event.repository.id),
            repository_name=event.repository.full_name,
            workflow_run_id=event.workflow_run.id,
            workflow_name=event.workflow_run.name or "Unknown",
            status=RemediationStatus.PENDING,
        )
        activity_id = await self._storage.create_activity(activity)

        # Start processing in background
        task = asyncio.create_task(
            self._process_event(event, activity_id),
            name=f"heal-{activity_id}",
        )
        self._running_tasks[activity_id] = task

        # Clean up completed task reference when done
        task.add_done_callback(lambda t: self._running_tasks.pop(activity_id, None))

        logger.info(f"Started healing workflow: {activity_id}")
        return activity_id

    async def handle_successful_run(self, event: WorkflowRunEvent) -> dict[str, Any]:
        """Process a successful workflow run for artifact lifecycle hygiene."""
        task = asyncio.create_task(
            self._orchestrator.handle_successful_run(event),
            name=f"heal-success-{event.workflow_run.id}",
        )
        self._running_tasks[f"success-{event.workflow_run.id}"] = task
        task.add_done_callback(
            lambda t: self._running_tasks.pop(f"success-{event.workflow_run.id}", None)
        )
        return {"status": "processing", "workflow_run_id": event.workflow_run.id}

    async def _process_event(
        self,
        event: WorkflowRunEvent,
        activity_id: str,
    ) -> ActivityRecord:
        """Process a workflow failure event.

        Args:
            event: The workflow run event
            activity_id: Pre-generated activity ID

        Returns:
            The activity record with results
        """
        try:
            result = await self._orchestrator.process_workflow_failure(
                event,
                activity_id=activity_id,
            )
            return result
        except Exception as e:
            logger.exception(f"Workflow processing failed: {e}")
            # Create a failed activity record
            activity = ActivityRecord(
                id=activity_id,
                repositoryId=str(event.repository.id),
                repository_name=event.repository.full_name,
                workflow_run_id=event.workflow_run.id,
                workflow_name=event.workflow_run.name or "Unknown",
                status=RemediationStatus.FAILED,
                error=str(e),
            )
            await self._storage.update_activity(activity)
            return activity

    async def get_activity(self, activity_id: str) -> ActivityRecord | None:
        """Get an activity record by ID.

        Args:
            activity_id: The activity ID

        Returns:
            Activity record or None if not found
        """
        return await self._storage.get_activity(activity_id)

    async def get_task_status(self, activity_id: str) -> str:
        """Get the status of a running task.

        Args:
            activity_id: The activity ID

        Returns:
            Task status string
        """
        task = self._running_tasks.get(activity_id)

        if task is None:
            return "not_found"
        elif task.done():
            if task.cancelled():
                return "cancelled"
            elif task.exception():
                return "error"
            else:
                return "completed"
        else:
            return "running"

    async def start_bridge_failure(
        self,
        payload: JenkinsBridgePayload,
        *,
        request_id: str | None = None,
    ) -> str:
        """Start processing a signed Jenkins bridge payload asynchronously."""
        synthetic_activity = ActivityRecord(
            repositoryId=f"jenkins:{payload.repository.lower()}",
            repository_name=payload.repository,
            workflow_run_id=int(payload.job.build_number),
            workflow_name=payload.job.name or "Jenkins Job",
            status=RemediationStatus.PENDING,
            source_selection_path="jenkins_bridge",
            source_delivery_id=payload.delivery_id,
            source_metadata={
                "provider": "jenkins",
                "job_url": payload.job.url,
                "build_number": payload.job.build_number,
                "branch": payload.branch,
                "commit_sha": payload.commit_sha,
                "request_id": request_id,
            },
        )
        activity_id = await self._storage.create_activity(synthetic_activity)

        task = asyncio.create_task(
            self._process_bridge_payload(payload, activity_id),
            name=f"heal-jenkins-{activity_id}",
        )
        self._running_tasks[activity_id] = task
        task.add_done_callback(lambda t: self._running_tasks.pop(activity_id, None))
        logger.info("Started Jenkins bridge workflow: %s (delivery=%s)", activity_id, payload.delivery_id)
        return activity_id

    async def _process_bridge_payload(
        self,
        payload: JenkinsBridgePayload,
        activity_id: str,
    ) -> ActivityRecord:
        """Process Jenkins bridge payload using orchestrator diagnosis/remediation flow."""
        try:
            return await self._orchestrator.process_bridge_failure(
                payload,
                activity_id=activity_id,
            )
        except Exception as exc:
            logger.exception("Bridge workflow processing failed: %s", exc)
            activity = await self._storage.get_activity(activity_id)
            if activity is None:
                activity = ActivityRecord(
                    id=activity_id,
                    repositoryId=f"jenkins:{payload.repository.lower()}",
                    repository_name=payload.repository,
                    workflow_run_id=int(payload.job.build_number),
                    workflow_name=payload.job.name or "Jenkins Job",
                    status=RemediationStatus.FAILED,
                    error=str(exc),
                    source_selection_path="jenkins_bridge",
                    source_delivery_id=payload.delivery_id,
                )
            else:
                activity.status = RemediationStatus.FAILED
                activity.error = str(exc)
            await self._storage.update_activity(activity)
            return activity

    @property
    def storage(self) -> ActivityStorage:
        """Get the storage instance."""
        return self._storage

    @property
    def github_tools(self) -> GitHubTools:
        """Get the GitHub tools instance."""
        return self._github_tools

    async def recover_stale_activities(self) -> int:
        """Mark in-flight activities as failed on startup.

        Activities in transient states (pending, analyzing, diagnosing,
        remediating) cannot survive a container restart.  They represent
        runs that were interrupted when the previous process was killed
        (e.g. scale-to-zero, redeploy).  This sweep marks them as failed
        with an explanatory error so they don't stay stuck forever.

        Returns:
            Number of activities recovered.
        """
        transient_statuses = [
            RemediationStatus.PENDING,
            RemediationStatus.ANALYZING,
            RemediationStatus.DIAGNOSING,
            RemediationStatus.REMEDIATING,
        ]
        recovered = 0
        for status in transient_statuses:
            activities = await self._storage.get_activities(status=status, limit=100)
            for activity in activities:
                activity.status = RemediationStatus.FAILED
                activity.error = (
                    f"Interrupted: activity was in '{status}' state when the "
                    f"backend restarted (likely scale-to-zero or redeploy)."
                )
                await self._storage.update_activity(activity)
                recovered += 1
                logger.warning(
                    "Recovered stale activity %s (was %s, run %s)",
                    activity.id,
                    status,
                    activity.workflow_run_id,
                )
        return recovered

    async def run_backfill_sweep(self, *, max_age_hours: float = 24.0) -> int:
        """Sweep completed activities and backfill missing external diagnostics.

        Finds activities whose ci-doctor poll window was exhausted during the
        original pipeline run and tries to attach findings that may have been
        published since then.

        Args:
            max_age_hours: Only consider activities created within this window.

        Returns:
            Number of activities that were successfully backfilled.
        """
        candidates = await self._storage.get_backfill_candidates(
            limit=20,
            max_age_hours=max_age_hours,
        )
        if not candidates:
            return 0

        logger.info("Backfill sweep: found %d candidate(s)", len(candidates))
        backfilled = 0
        for activity in candidates:
            try:
                if await self._orchestrator.backfill_activity_diagnostics(activity):
                    backfilled += 1
            except Exception:
                logger.debug(
                    "Backfill sweep: error processing activity %s", activity.id, exc_info=True,
                )
        if backfilled:
            logger.info("Backfill sweep: enriched %d / %d activities", backfilled, len(candidates))
        return backfilled

    def refresh_runtime_settings(self) -> None:
        """Refresh mutable settings across workflow components."""
        self._settings = get_settings()
        self._github_tools.refresh_runtime_settings()
        self._orchestrator.refresh_runtime_settings()


def create_workflow(
    use_in_memory: bool = False,
) -> PipelineHealerWorkflow:
    """Create a PipelineHealer workflow instance.

    Args:
        use_in_memory: Use in-memory storage (for development)

    Returns:
        Configured workflow instance
    """
    settings = get_settings()

    # Create GitHub tools
    github_tools = GitHubTools()

    # Create storage using explicit mode selection with non-development durability guardrails.
    storage = create_storage(settings=settings, use_in_memory=use_in_memory)

    # Create credential
    credential = DefaultAzureCredential()

    return PipelineHealerWorkflow(
        github_tools=github_tools,
        storage=storage,
        azure_credential=credential,
    )


def resolve_storage_mode(settings: Any, *, use_in_memory: bool = False) -> str:
    """Resolve effective storage mode from settings and startup override.

    Rules:
    - ``use_in_memory=True`` always selects memory (used by tests/local dev startup path).
    - explicit ``STORAGE_MODE`` wins when provided.
    - default is ``memory`` for development and ``cosmos`` otherwise.
    - non-development ``memory`` requires explicit opt-in.
    - ``cosmos`` requires ``COSMOS_DB_ENDPOINT``.
    - ``postgres`` requires ``POSTGRES_DSN``.
    """
    environment = str(getattr(settings, "environment", "development")).strip().lower()
    configured_mode = str(getattr(settings, "storage_mode", "")).strip().lower()

    if use_in_memory:
        return _STORAGE_MODE_MEMORY

    mode = configured_mode or (
        _STORAGE_MODE_MEMORY if environment == "development" else _STORAGE_MODE_COSMOS
    )

    if mode == _STORAGE_MODE_MEMORY:
        allow_non_dev_memory = bool(
            getattr(settings, "allow_in_memory_storage_in_non_development", False)
        )
        if environment != "development" and not allow_non_dev_memory:
            raise RuntimeError(
                "Refusing to start with in-memory storage in non-development. "
                "Set STORAGE_MODE=cosmos for durable storage, or set "
                "ALLOW_IN_MEMORY_STORAGE_IN_NON_DEVELOPMENT=true for explicit demo/local opt-in."
            )
        return mode

    if mode == _STORAGE_MODE_COSMOS:
        cosmos_endpoint = str(getattr(settings, "cosmos_db_endpoint", "")).strip()
        if not cosmos_endpoint:
            raise RuntimeError(
                "STORAGE_MODE=cosmos requires COSMOS_DB_ENDPOINT. "
                "Configure Cosmos DB for durable storage before starting in non-development."
            )
        return mode

    if mode == _STORAGE_MODE_POSTGRES:
        postgres_dsn = str(getattr(settings, "postgres_dsn", "")).strip()
        if not postgres_dsn:
            raise RuntimeError(
                "STORAGE_MODE=postgres requires POSTGRES_DSN. "
                "Configure PostgreSQL for durable storage before starting."
            )
        return mode

    # Defensive fallback; validator should prevent unknown values.
    raise RuntimeError(f"Unsupported STORAGE_MODE '{mode}'")


def create_storage(settings: Any, *, use_in_memory: bool = False) -> ActivityStorage:
    """Build the storage implementation for the resolved storage mode."""
    mode = resolve_storage_mode(settings, use_in_memory=use_in_memory)
    if mode == _STORAGE_MODE_MEMORY:
        return InMemoryStorage()
    if mode == _STORAGE_MODE_POSTGRES:
        return PostgresStorage(postgres_dsn=str(getattr(settings, "postgres_dsn", "")))
    return ActivityStorage()
