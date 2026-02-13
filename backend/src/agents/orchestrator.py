"""Orchestrator Agent for coordinating the healing pipeline."""

import asyncio
import logging
import time
from collections.abc import Awaitable
from typing import Any, TypeVar

from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import (
    ActivityRecord,
    RemediationStatus,
    WorkflowRunEvent,
)
from ..storage import ActivityStorage
from ..tools.github_tools import GitHubTools
from .base import create_cloud_agent, get_agent_prompt
from .diagnosis import DiagnosisAgent
from .log_analyzer import LogAnalyzerAgent
from .remediation import RemediationAgent

logger = logging.getLogger(__name__)
T = TypeVar("T")


class OrchestratorAgent:
    """Agent for orchestrating the CI/CD healing pipeline.

    This agent coordinates the Log Analyzer, Diagnosis, and Remediation
    agents to process failed workflow runs and generate fixes.
    """

    def __init__(
        self,
        github_tools: GitHubTools,
        storage: ActivityStorage,
        azure_credential: DefaultAzureCredential | None = None,
    ):
        """Initialize the Orchestrator Agent.

        Args:
            github_tools: GitHub tools for API access
            storage: Storage for activity records
            azure_credential: Azure credential for OpenAI
        """
        self._github_tools = github_tools
        self._storage = storage
        self._credential = azure_credential or DefaultAzureCredential()
        self._settings = get_settings()

        # Initialize sub-agents
        self._log_analyzer = LogAnalyzerAgent(github_tools, azure_credential)
        self._diagnosis_agent = DiagnosisAgent(azure_credential)
        self._remediation_agent = RemediationAgent(github_tools, azure_credential=azure_credential)

        self._agent: Any | None = None

    async def _get_agent(self) -> Any:
        """Get or create the orchestrator agent instance."""
        if self._agent is None:
            self._agent = create_cloud_agent(
                name="Orchestrator",
                instructions=get_agent_prompt("orchestrator"),
                credential=self._credential,
                settings=self._settings,
            )

        return self._agent

    def refresh_runtime_settings(self) -> None:
        """Refresh mutable runtime settings for orchestrator and child agents."""
        self._settings = get_settings()
        self._remediation_agent.refresh_runtime_settings()

    async def _run_with_timeout(self, *, step_name: str, coro: Awaitable[T]) -> T:
        """Run a pipeline step with optional timeout protection."""
        timeout_seconds = self._settings.pipeline_step_timeout_seconds
        if timeout_seconds <= 0:
            return await coro

        try:
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(
                f"{step_name} step timed out after {timeout_seconds:.1f}s"
            ) from exc

    async def process_workflow_failure(
        self,
        event: WorkflowRunEvent,
        activity_id: str | None = None,
    ) -> ActivityRecord:
        """Process a workflow failure event.

        This is the main entry point for the healing pipeline.

        Args:
            event: The workflow run event from GitHub

        Returns:
            Activity record with the results
        """
        owner = event.repository.owner.get("login", "")
        repo = event.repository.name
        run_id = event.workflow_run.id

        logger.info(f"Processing workflow failure: {owner}/{repo} run {run_id}")

        is_debug = self._settings.heal_mode == "debug"
        src_logger = logging.getLogger("src")
        prev_level = src_logger.level
        prev_handler_levels: list[tuple[logging.Handler, int]] = []
        if is_debug:
            src_logger.setLevel(logging.DEBUG)
            # Also lower the root handler levels so DEBUG messages aren't
            # suppressed by basicConfig's handler-level filter.
            for handler in logging.getLogger().handlers:
                prev_handler_levels.append((handler, handler.level))
                if handler.level > logging.DEBUG:
                    handler.setLevel(logging.DEBUG)
            logger.debug("[debug-mode] Verbose pipeline logging enabled for this run")

        # Use the pre-created activity record when provided (webhook/start() returns this ID).
        activity: ActivityRecord | None = None
        if activity_id:
            activity = await self._storage.get_activity(activity_id)

        if activity is None:
            activity = ActivityRecord(
                id=activity_id or "",
                repositoryId=str(event.repository.id),
                repository_name=event.repository.full_name,
                workflow_run_id=run_id,
                workflow_name=event.workflow_run.name or "Unknown",
                status=RemediationStatus.PENDING,
            )
            created_id = await self._storage.create_activity(activity)
            activity.id = created_id

        try:
            # Step 1: Analyze logs
            logger.info("Step 1: Analyzing logs...")
            activity.status = RemediationStatus.ANALYZING
            await self._storage.update_activity(activity)

            t0 = time.monotonic()
            log_analyses = await self._run_with_timeout(
                step_name="Analyze",
                coro=self._log_analyzer.analyze(owner, repo, run_id),
            )
            if is_debug:
                logger.debug(
                    "[debug-mode] Step 1 completed in %.2fs — %d job(s) analyzed",
                    time.monotonic() - t0,
                    len(log_analyses),
                )

            if not log_analyses:
                logger.warning("No log analyses produced")
                activity.status = RemediationStatus.FAILED
                activity.error = "No logs available for analysis"
                await self._storage.update_activity(activity)
                return activity

            # Step 2: Diagnose the failure
            logger.info("Step 2: Diagnosing failure...")
            activity.status = RemediationStatus.DIAGNOSING
            await self._storage.update_activity(activity)

            workflow_info = {
                "run_id": run_id,
                "name": event.workflow_run.name,
                "branch": event.workflow_run.head_branch,
                "conclusion": event.workflow_run.conclusion,
            }

            t1 = time.monotonic()
            diagnosis = await self._run_with_timeout(
                step_name="Diagnose",
                coro=self._diagnosis_agent.diagnose(log_analyses, workflow_info),
            )
            activity.failure_type = diagnosis.failure_type
            activity.diagnosis = diagnosis

            logger.info(
                f"Diagnosis: {diagnosis.failure_type.value} "
                f"(confidence: {diagnosis.confidence:.0%})"
            )
            if is_debug:
                logger.debug(
                    "[debug-mode] Step 2 completed in %.2fs — type=%s confidence=%.2f root_cause=%s",
                    time.monotonic() - t1,
                    diagnosis.failure_type.value,
                    diagnosis.confidence,
                    diagnosis.root_cause[:200] if diagnosis.root_cause else "N/A",
                )

            # Step 3: Remediate
            logger.info("Step 3: Generating remediation...")
            activity.status = RemediationStatus.REMEDIATING
            await self._storage.update_activity(activity)

            repository_info = {
                "id": event.repository.id,
                "name": event.repository.name,
                "full_name": event.repository.full_name,
                "owner": event.repository.owner,
                "default_branch": event.repository.default_branch,
            }

            # Check if auto-creation is enabled
            dry_run = not self._settings.auto_create_pr

            t2 = time.monotonic()
            result = await self._run_with_timeout(
                step_name="Remediate",
                coro=self._remediation_agent.remediate(
                    diagnosis=diagnosis,
                    repository_info=repository_info,
                    workflow_run_id=run_id,
                    dry_run=dry_run,
                ),
            )

            activity.remediation_result = result

            if is_debug:
                logger.debug(
                    "[debug-mode] Step 3 completed in %.2fs — action=%s success=%s",
                    time.monotonic() - t2,
                    result.action_taken.value if result.action_taken else "none",
                    result.success,
                )

            # Update final status
            if result.success:
                activity.status = RemediationStatus.COMPLETED
                logger.info(f"Remediation completed: {result.action_taken.value}")
                if result.pr_url:
                    logger.info(f"PR created: {result.pr_url}")
                if result.issue_url:
                    logger.info(f"Issue created: {result.issue_url}")
            else:
                activity.status = RemediationStatus.FAILED
                activity.error = result.error_message
                logger.warning(f"Remediation failed: {result.error_message}")

            await self._storage.update_activity(activity)
            return activity

        except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            activity.status = RemediationStatus.FAILED
            activity.error = str(e)
            await self._storage.update_activity(activity)
            return activity
        finally:
            if is_debug:
                src_logger.setLevel(prev_level)
                for handler, level in prev_handler_levels:
                    handler.setLevel(level)

    async def get_status(self, activity_id: str) -> ActivityRecord | None:
        """Get the status of a healing activity.

        Args:
            activity_id: The activity ID

        Returns:
            Activity record or None if not found
        """
        return await self._storage.get_activity(activity_id)

    async def should_process(self, event: WorkflowRunEvent) -> tuple[bool, str]:
        """Determine if a workflow failure should be processed.

        Args:
            event: The workflow run event

        Returns:
            Tuple of (should_process, reason)
        """
        # Check if this is a failure
        if event.workflow_run.conclusion not in ("failure", "timed_out"):
            return False, f"Not a failure: {event.workflow_run.conclusion}"

        # Check if we've already processed this run
        existing = await self._storage.get_activities(
            repository=event.repository.full_name,
            limit=10,
        )

        for activity in existing:
            if activity.workflow_run_id == event.workflow_run.id:
                # Check if this is a retry
                if event.workflow_run.run_attempt > 1:
                    return True, "Retry attempt"
                return False, "Already processed"

        # Check if we've hit the max attempts for this repo recently
        # This prevents infinite loops
        recent_failures = [a for a in existing if a.status == RemediationStatus.FAILED]

        if len(recent_failures) >= self._settings.max_remediation_attempts:
            return False, "Max remediation attempts reached for this repository"

        return True, "New failure to process"
