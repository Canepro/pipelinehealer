"""PipelineHealer Workflow using Microsoft Agent Framework workflows."""

import asyncio
import logging
from typing import Any
from uuid import uuid4

from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import (
    ActivityRecord,
    RemediationStatus,
    WorkflowRunEvent,
)
from ..storage import ActivityStorage, InMemoryStorage
from ..tools.github_tools import GitHubTools
from ..agents.orchestrator import OrchestratorAgent

logger = logging.getLogger(__name__)


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
        for task_id, task in self._running_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
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
                repository_id=str(event.repository.id),
                repository_name=event.repository.full_name,
                workflow_run_id=event.workflow_run.id,
                workflow_name=event.workflow_run.name or "Unknown",
                status=RemediationStatus.SKIPPED,
                error=reason,
            )
            await self._storage.create_activity(activity)
            return activity.id
        
        # Generate activity ID
        activity_id = str(uuid4())
        
        # Start processing in background
        task = asyncio.create_task(
            self._process_event(event, activity_id),
            name=f"heal-{activity_id}",
        )
        self._running_tasks[activity_id] = task
        
        # Clean up completed task reference when done
        task.add_done_callback(
            lambda t: self._running_tasks.pop(activity_id, None)
        )
        
        logger.info(f"Started healing workflow: {activity_id}")
        return activity_id

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
            result = await self._orchestrator.process_workflow_failure(event)
            return result
        except Exception as e:
            logger.exception(f"Workflow processing failed: {e}")
            # Create a failed activity record
            activity = ActivityRecord(
                id=activity_id,
                repository_id=str(event.repository.id),
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

    @property
    def storage(self) -> ActivityStorage:
        """Get the storage instance."""
        return self._storage


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
    
    # Create storage
    if use_in_memory or settings.environment == "development":
        storage: ActivityStorage = InMemoryStorage()
    else:
        storage = ActivityStorage()
    
    # Create credential
    credential = DefaultAzureCredential()
    
    return PipelineHealerWorkflow(
        github_tools=github_tools,
        storage=storage,
        azure_credential=credential,
    )
