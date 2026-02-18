"""Orchestrator Agent for coordinating the healing pipeline."""

import asyncio
import logging
import re
import time
from collections import Counter
from collections.abc import Awaitable
from datetime import timedelta
from typing import Any, TypeVar

from azure.identity import DefaultAzureCredential
from opentelemetry import trace

from ..config import get_settings
from ..llm.telemetry import (
    LLMTelemetryCollector,
    reset_llm_telemetry_collector,
    set_llm_telemetry_collector,
)
from ..models import (
    ActivityRecord,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    MCPModelPath,
    RemediationStatus,
    WorkflowRunEvent,
)
from ..storage import ActivityStorage
from ..tools.gh_aw_adapter import DiagnosticSourceConfig, GHAWAdapter, create_gh_aw_adapter
from ..tools.github_tools import GitHubTools
from ..tools.mcp_provider import get_mcp_provider
from .base import create_cloud_agent, get_agent_prompt
from .diagnosis import DiagnosisAgent
from .log_analyzer import LogAnalyzerAgent
from .remediation import RemediationAgent

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("pipelinehealer.orchestrator")
T = TypeVar("T")


def _build_external_diagnostics_poll_delays(
    wait_budget_seconds: float,
    poll_interval_seconds: float,
) -> tuple[float, ...]:
    """Build bounded polling delays from wait budget + poll interval settings."""
    if wait_budget_seconds <= 0 or poll_interval_seconds <= 0:
        return ()
    remaining = wait_budget_seconds
    delays: list[float] = []
    while remaining > 0:
        step = min(poll_interval_seconds, remaining)
        delays.append(step)
        remaining -= step
    return tuple(delays)


def _normalize_workflow_identifier(name: str) -> str:
    """Normalize workflow names/identifiers for robust comparisons."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _build_source_attribution(
    diagnostics: list[ExternalDiagnostic],
) -> dict[str, int]:
    """Summarize diagnostic source usage counts for activity observability."""
    if not diagnostics:
        return {}
    counts: Counter[str] = Counter()
    for diagnostic in diagnostics:
        source = (diagnostic.source or "unknown").strip().lower() or "unknown"
        counts[source] += 1
    return dict(counts)


def _count_error_diagnostics(diagnostics: list[ExternalDiagnostic]) -> int:
    """Count external diagnostic entries that represent collection errors."""
    return sum(1 for diagnostic in diagnostics if diagnostic.status == ExternalDiagnosticStatus.ERROR)


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
        self._gh_aw_adapter: GHAWAdapter = create_gh_aw_adapter(github_tools=github_tools)

        # Initialize sub-agents
        self._log_analyzer = LogAnalyzerAgent(github_tools, azure_credential)
        self._diagnosis_agent = DiagnosisAgent(
            github_tools=github_tools,
            azure_credential=azure_credential,
        )
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
        self._gh_aw_adapter = create_gh_aw_adapter(github_tools=self._github_tools)
        self._log_analyzer.refresh_runtime_settings()
        self._diagnosis_agent.refresh_runtime_settings()
        self._remediation_agent.refresh_runtime_settings()
        self._agent = None

    @staticmethod
    def _increment_mcp_tool_invocation(
        activity: ActivityRecord,
        *,
        tool_name: str,
        increment: int = 1,
    ) -> None:
        """Increment MCP tool usage counters for one activity."""
        if increment <= 0 or activity.mcp_model_path is None:
            return
        current = activity.mcp_model_path.tool_invocations.get(tool_name, 0)
        activity.mcp_model_path.tool_invocations[tool_name] = current + increment

    def _gh_aw_passive_enabled(self) -> bool:
        """Return whether gh-aw passive diagnostics collection is enabled."""
        return (
            self._settings.gh_aw_tools_enabled
            and self._settings.gh_aw_ingestion_mode == "passive"
        )

    def _github_mcp_collection_enabled(self) -> bool:
        """Return whether direct GitHub MCP context collection can run."""
        provider = (self._settings.mcp_provider or "").strip().lower()
        if not self._settings.mcp_enabled or provider != "github":
            return False
        try:
            health = get_mcp_provider(self._settings).health(self._settings)
        except Exception:
            return False
        return health.enabled and health.available

    @staticmethod
    def _has_github_mcp_diagnostic(
        diagnostics: list[ExternalDiagnostic],
    ) -> bool:
        """Check if diagnostics contain entries from the direct GitHub MCP path."""
        return any(
            (diagnostic.source or "").strip().lower() == "github-mcp"
            for diagnostic in diagnostics
        )

    def _should_count_fetch_failure_context(
        self,
        activity: ActivityRecord,
        diagnostics: list[ExternalDiagnostic],
    ) -> bool:
        """Decide whether fetch_failure_context should be counted for this run."""
        model_path = activity.mcp_model_path
        if model_path is None:
            return False
        if not model_path.enabled or model_path.provider != "github":
            return False
        if self._has_github_mcp_diagnostic(diagnostics):
            return True
        # gh-aw passive diagnostics are also a GitHub context fetch path.
        return self._gh_aw_passive_enabled() and bool(diagnostics)

    async def _collect_external_diagnostics_from_github_mcp(
        self,
        owner: str,
        repo: str,
        event: WorkflowRunEvent,
    ) -> list[ExternalDiagnostic]:
        """Collect baseline run context from GitHub when MCP github provider is enabled."""
        run_id = event.workflow_run.id
        try:
            run_details = await self._github_tools.get_workflow_run(owner, repo, run_id)
            jobs = await self._github_tools.get_workflow_jobs(owner, repo, run_id)
        except Exception as exc:
            return [
                ExternalDiagnostic(
                    source="github-mcp",
                    status=ExternalDiagnosticStatus.ERROR,
                    summary="Failed to collect GitHub MCP context",
                    matched_run_id=run_id,
                    metadata={
                        "reason_code": "github_mcp_fetch_failed",
                        "error_type": type(exc).__name__,
                    },
                )
            ]

        failed_jobs = []
        timed_out_jobs = 0
        failed_job_lines: list[str] = []
        for job in jobs:
            conclusion = str(job.get("conclusion", "")).strip().lower()
            if conclusion not in {"failure", "timed_out"}:
                continue
            failed_jobs.append(job)
            if conclusion == "timed_out":
                timed_out_jobs += 1
            job_name = str(job.get("name", "unknown")).strip() or "unknown"
            failed_job_lines.append(f"- {job_name} ({conclusion})")
            if len(failed_job_lines) >= 12:
                break

        pull_request_numbers: list[int] = []
        for pull_request in run_details.get("pull_requests", []):
            if not isinstance(pull_request, dict):
                continue
            number = pull_request.get("number")
            if isinstance(number, int):
                pull_request_numbers.append(number)

        changed_files: list[str] = []
        for pr_number in pull_request_numbers[:3]:
            try:
                files = await self._github_tools.get_pull_request_files(owner, repo, pr_number, per_page=100)
            except Exception:
                logger.debug(
                    "GitHub MCP context: unable to read files for %s/%s PR #%s",
                    owner,
                    repo,
                    pr_number,
                    exc_info=True,
                )
                continue
            for file_item in files:
                filename = file_item.get("filename")
                if isinstance(filename, str) and filename.strip():
                    changed_files.append(filename.strip())
                if len(changed_files) >= 30:
                    break
            if len(changed_files) >= 30:
                break

        unique_changed_files = sorted(set(changed_files))
        confidence_components: list[tuple[str, float]] = []
        if failed_jobs:
            confidence_components.append(("failed_jobs_detected", 0.04))
        if timed_out_jobs:
            confidence_components.append(("timed_out_jobs_detected", 0.02))
        if pull_request_numbers:
            confidence_components.append(("related_pull_requests", 0.02))
        if unique_changed_files:
            confidence_components.append(("changed_files_correlated", 0.03))

        confidence_delta = min(0.12, sum(delta for _, delta in confidence_components))
        confidence_reason = (
            "GitHub MCP run context aligned with failing run evidence."
            if confidence_delta > 0
            else "GitHub MCP context collected; no additional confidence signal."
        )

        details: dict[str, str] = {
            "summary": (
                f"Collected GitHub MCP run context for run #{run_id}: "
                f"{len(jobs)} job(s), {len(failed_jobs)} failing/timed-out, "
                f"{len(pull_request_numbers)} related PR(s)."
            ),
            "root_cause": (
                "This is contextual evidence from GitHub metadata. "
                "It does not replace root-cause diagnosis from logs."
            ),
            "investigation_findings": (
                f"Head branch: {event.workflow_run.head_branch or 'unknown'}\n"
                f"Run attempt: {run_details.get('run_attempt', event.workflow_run.run_attempt)}\n"
                f"Timed-out jobs: {timed_out_jobs}"
            ),
            "recommended_actions": (
                "- Inspect failing jobs first.\n"
                "- Compare changed files against stack traces.\n"
                "- Re-run only failed jobs after applying a fix."
            ),
        }
        if failed_job_lines:
            details["failed_jobs"] = "\n".join(failed_job_lines)
        if unique_changed_files:
            details["historical_context"] = (
                "Changed files linked to this run:\n"
                + "\n".join(f"- {path}" for path in unique_changed_files[:12])
            )

        return [
            ExternalDiagnostic(
                source="github-mcp",
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary=(
                    "GitHub MCP context captured: "
                    f"{len(jobs)} job(s), {len(failed_jobs)} failing/timed-out, "
                    f"{len(pull_request_numbers)} related PR(s)."
                ),
                url=(
                    str(run_details.get("html_url"))
                    if run_details.get("html_url")
                    else event.workflow_run.html_url
                ),
                matched_run_id=run_id,
                confidence_delta=confidence_delta,
                metadata={
                    "reason_code": "github_mcp_context",
                    "confidence_reason": confidence_reason,
                    "confidence_components": [
                        {"name": name, "delta": delta} for name, delta in confidence_components
                    ],
                    "jobs_total": len(jobs),
                    "failed_jobs_count": len(failed_jobs),
                    "timed_out_jobs_count": timed_out_jobs,
                    "failed_jobs": failed_job_lines,
                    "pull_request_numbers": pull_request_numbers,
                    "changed_files": unique_changed_files,
                    "run_attempt": run_details.get("run_attempt", event.workflow_run.run_attempt),
                    "details": details,
                },
            )
        ]

    async def _collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        event: WorkflowRunEvent,
    ) -> list[ExternalDiagnostic]:
        """Collect external diagnostics from all available gh-aw sources.

        Ambient sources (breaking-change-checker, etc.) are collected
        immediately in a single pass.  ci-doctor is polled with bounded
        backoff because it triggers asynchronously after a CI failure and
        needs time to publish its issue.
        """
        if not self._gh_aw_passive_enabled():
            if self._github_mcp_collection_enabled():
                return await self._collect_external_diagnostics_from_github_mcp(
                    owner,
                    repo,
                    event,
                )
            return []

        # --- Discover available diagnostic sources ---
        try:
            capability = await self._gh_aw_adapter.discover_capability(owner, repo)
        except Exception as exc:
            return [
                ExternalDiagnostic(
                    source="external-diagnostics",
                    status=ExternalDiagnosticStatus.ERROR,
                    summary="Failed to evaluate external diagnostics capability",
                    matched_run_id=event.workflow_run.id,
                    metadata={
                        "reason_code": "capability_discovery_failed",
                        "error_type": type(exc).__name__,
                    },
                )
            ]
        if not capability.is_available:
            logger.info(
                "External diagnostics unavailable for %s/%s: %s",
                owner,
                repo,
                capability.reason or "unknown",
            )
            return [
                ExternalDiagnostic(
                    source="external-diagnostics",
                    status=ExternalDiagnosticStatus.UNAVAILABLE,
                    summary="No gh-aw diagnostic sources found for this repository",
                    matched_run_id=event.workflow_run.id,
                    metadata={
                        "reason_code": "capability_unavailable",
                        "capability_reason": capability.reason,
                        "available_workflows": capability.available_workflows,
                    },
                )
            ]

        # --- Determine skip list (only affects ci-doctor self-diagnosis) ---
        workflow_name = event.workflow_run.name or ""
        workflow_identifier = _normalize_workflow_identifier(workflow_name)
        skip_identifiers = {
            _normalize_workflow_identifier(name)
            for name in self._settings.gh_aw_known_workflows
            if name
        }
        skip_ci_doctor = (
            workflow_identifier != ""
            and workflow_identifier in skip_identifiers
        )

        # Separate ci-doctor from ambient sources.
        ci_doctor_source = None
        ambient_sources = []
        for src in capability.available_sources:
            if src.name == "ci-doctor":
                ci_doctor_source = src
            else:
                ambient_sources.append(src)

        all_diagnostics: list[ExternalDiagnostic] = []
        run_id = event.workflow_run.id
        head_sha = event.workflow_run.head_sha
        run_number = event.workflow_run.run_number

        # --- Phase 1: Immediate collection from ambient sources ---
        if ambient_sources:
            try:
                ambient_findings = await self._gh_aw_adapter.collect_external_diagnostics(
                    owner=owner,
                    repo=repo,
                    run_id=run_id,
                    head_sha=head_sha,
                    run_number=run_number,
                    sources=ambient_sources,
                )
                all_diagnostics.extend(ambient_findings)
                if ambient_findings:
                    logger.info(
                        "Collected %d ambient diagnostic(s) from %s for %s/%s run %s",
                        len(ambient_findings),
                        [s.name for s in ambient_sources],
                        owner,
                        repo,
                        run_id,
                    )
            except Exception as exc:
                logger.warning(
                    "Ambient diagnostics collection failed for %s/%s run %s: %s",
                    owner, repo, run_id, exc,
                )

        # --- Phase 2: ci-doctor (skipped or polled with backoff) ---
        if ci_doctor_source is None:
            # ci-doctor not present in repo; nothing to poll.
            pass
        elif skip_ci_doctor:
            logger.info(
                "Skipping ci-doctor polling: failed workflow '%s' is in the skip list (run %s)",
                workflow_name,
                run_id,
            )
            all_diagnostics.append(
                ExternalDiagnostic(
                    source="ci-doctor",
                    status=ExternalDiagnosticStatus.UNAVAILABLE,
                    summary=(
                        f"Skipped ci-doctor polling because failed workflow "
                        f"'{workflow_name}' is in the skip list."
                    ),
                    matched_run_id=run_id,
                    metadata={
                        "reason_code": "skip_known_gh_aw_workflow",
                        "skip_reason": "failed_workflow_is_gh_aw_workflow",
                        "workflow_name": workflow_name,
                        "workflow_identifier": workflow_identifier,
                    },
                )
            )
        else:
            # Poll with bounded backoff for ci-doctor issue findings.
            ci_doctor_findings = await self._poll_ci_doctor(
                ci_doctor_source, owner, repo, run_id, head_sha, run_number,
            )
            all_diagnostics.extend(ci_doctor_findings)

        # --- Phase 3: Noop signals (informational context) ---
        # Collect recent noop signals from gh-aw workflows that ran but
        # found nothing actionable.  Skip sources that already produced
        # actual findings to avoid noise.
        sources_with_findings = {
            d.source
            for d in all_diagnostics
            if d.status == ExternalDiagnosticStatus.AVAILABLE
        }
        try:
            noop_signals = await self._gh_aw_adapter.collect_noop_signals(
                owner, repo, exclude_sources=sources_with_findings,
            )
            all_diagnostics.extend(noop_signals)
        except Exception as exc:
            logger.warning(
                "Noop signal collection failed for %s/%s: %s",
                owner, repo, exc,
            )

        return all_diagnostics

    async def _poll_ci_doctor(
        self,
        source: DiagnosticSourceConfig,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None,
    ) -> list[ExternalDiagnostic]:
        """Poll for ci-doctor findings with bounded backoff."""
        poll_delays_seconds = _build_external_diagnostics_poll_delays(
            wait_budget_seconds=self._settings.external_diagnostics_wait_seconds,
            poll_interval_seconds=self._settings.external_diagnostics_poll_interval_seconds,
        )
        last_collection_error_type: str | None = None
        for attempt, delay in enumerate((0.0, *poll_delays_seconds)):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                findings = await self._gh_aw_adapter.collect_external_diagnostics(
                    owner=owner,
                    repo=repo,
                    run_id=run_id,
                    head_sha=head_sha,
                    run_number=run_number,
                    sources=[source],
                )
            except Exception as exc:
                last_collection_error_type = type(exc).__name__
                logger.warning(
                    "Transient ci-doctor collection failure for %s/%s run %s on attempt %s: %s",
                    owner, repo, run_id, attempt, last_collection_error_type,
                )
                continue
            if findings:
                return findings

        # Final immediate read to reduce edge misses.
        try:
            final_findings = await self._gh_aw_adapter.collect_external_diagnostics(
                owner=owner,
                repo=repo,
                run_id=run_id,
                head_sha=head_sha,
                run_number=run_number,
                sources=[source],
            )
        except Exception as exc:
            last_collection_error_type = type(exc).__name__
            final_findings = []
        if final_findings:
            return final_findings

        if last_collection_error_type is not None:
            return [
                ExternalDiagnostic(
                    source="ci-doctor",
                    status=ExternalDiagnosticStatus.ERROR,
                    summary="Failed to collect ci-doctor findings after retries",
                    matched_run_id=run_id,
                    metadata={
                        "reason_code": "collection_failed",
                        "error_type": last_collection_error_type,
                        "attempts": len((0.0, *poll_delays_seconds)) + 1,
                        "wait_budget_seconds": self._settings.external_diagnostics_wait_seconds,
                        "poll_interval_seconds": (
                            self._settings.external_diagnostics_poll_interval_seconds
                        ),
                    },
                )
            ]

        return [
            ExternalDiagnostic(
                source="ci-doctor",
                status=ExternalDiagnosticStatus.UNAVAILABLE,
                summary="No ci-doctor findings published within bounded polling window",
                matched_run_id=run_id,
                metadata={
                    "reason_code": "poll_window_exhausted",
                    "poll_delays_seconds": list(poll_delays_seconds),
                    "wait_budget_seconds": self._settings.external_diagnostics_wait_seconds,
                    "poll_interval_seconds": self._settings.external_diagnostics_poll_interval_seconds,
                },
            )
        ]

    async def _build_workflow_context(
        self,
        event: WorkflowRunEvent,
    ) -> dict[str, Any]:
        """Build repository/run context used by diagnosis for deterministic correlation."""
        owner = event.repository.owner.get("login", "")
        repo = event.repository.name
        run_id = event.workflow_run.id

        context: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "run_id": run_id,
            "name": event.workflow_run.name,
            "branch": event.workflow_run.head_branch,
            "head_sha": event.workflow_run.head_sha,
            "conclusion": event.workflow_run.conclusion,
        }

        changed_files: list[str] = []
        pull_request_numbers: list[int] = []

        try:
            run_details = await self._github_tools.get_workflow_run(owner, repo, run_id)
            pull_requests = run_details.get("pull_requests", [])
            if isinstance(pull_requests, list):
                for pr_ref in pull_requests:
                    if not isinstance(pr_ref, dict):
                        continue
                    number = pr_ref.get("number")
                    if isinstance(number, int):
                        pull_request_numbers.append(number)

            for pr_number in pull_request_numbers[:3]:
                files = await self._github_tools.get_pull_request_files(owner, repo, pr_number)
                for item in files:
                    filename = item.get("filename")
                    if isinstance(filename, str) and filename.strip():
                        changed_files.append(filename.strip())
        except Exception as exc:
            logger.debug(
                "Unable to enrich workflow context with PR file details for %s/%s run %s: %s",
                owner,
                repo,
                run_id,
                exc,
            )

        if pull_request_numbers:
            context["pull_request_numbers"] = pull_request_numbers
        if changed_files:
            deduped = sorted(set(changed_files))
            context["changed_files"] = deduped

        # Keep a small recent commit window to help correlate breakage timing.
        try:
            since = (event.workflow_run.created_at - timedelta(days=2)).isoformat()
            commits = await self._github_tools.get_recent_commits(
                owner,
                repo,
                since=since,
                per_page=10,
            )
            context["recent_commits"] = [
                {
                    "sha": item.get("sha"),
                    "message": ((item.get("commit") or {}).get("message", "")[:200]),
                }
                for item in commits
                if isinstance(item, dict)
            ]
        except Exception as exc:
            logger.debug(
                "Unable to load recent commit context for %s/%s run %s: %s",
                owner,
                repo,
                run_id,
                exc,
            )

        return context

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
        telemetry_collector = LLMTelemetryCollector()
        telemetry_token = set_llm_telemetry_collector(telemetry_collector)

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

        # Capture MCP runtime path for per-activity observability, even when disabled.
        try:
            mcp_health = get_mcp_provider(self._settings).health(self._settings)
            activity.mcp_model_path = MCPModelPath(
                provider=mcp_health.provider,
                enabled=mcp_health.enabled,
                available=mcp_health.available,
                read_only=mcp_health.read_only,
                reason=mcp_health.reason,
                configured_tools=list(mcp_health.configured_tools),
            )
        except Exception:
            logger.debug(
                "Failed to resolve MCP provider health for activity %s",
                activity.id,
                exc_info=True,
            )

        with tracer.start_as_current_span(
            "pipeline.process",
            attributes={
                "pipeline.repository": f"{owner}/{repo}",
                "pipeline.run_id": run_id,
                "pipeline.activity_id": activity.id,
            },
        ) as pipeline_span:
          try:
            # Step 1: Analyze logs
            logger.info("Step 1: Analyzing logs...")
            activity.status = RemediationStatus.ANALYZING
            await self._storage.update_activity(activity)

            with tracer.start_as_current_span("pipeline.step.analyze") as span:
                t0 = time.monotonic()
                log_analyses = await self._run_with_timeout(
                    step_name="Analyze",
                    coro=self._log_analyzer.analyze(owner, repo, run_id),
                )
                elapsed = time.monotonic() - t0
                span.set_attribute("step.duration_seconds", round(elapsed, 2))
                span.set_attribute("step.jobs_analyzed", len(log_analyses))
                if is_debug:
                    logger.debug(
                        "[debug-mode] Step 1 completed in %.2fs — %d job(s) analyzed",
                        elapsed,
                        len(log_analyses),
                    )

            if not log_analyses:
                logger.warning("No log analyses produced")
                activity.status = RemediationStatus.FAILED
                activity.error = "No logs available for analysis"
                pipeline_span.set_attribute("pipeline.outcome", "no_logs")
                await self._storage.update_activity(activity)
                return activity

            # Step 2: Diagnose the failure
            logger.info("Step 2: Diagnosing failure...")
            activity.status = RemediationStatus.DIAGNOSING
            await self._storage.update_activity(activity)

            workflow_info = await self._build_workflow_context(event)
            external_diagnostics = await self._collect_external_diagnostics(owner, repo, event)
            if external_diagnostics:
                activity.external_diagnostics = external_diagnostics
            if activity.mcp_model_path is not None:
                if self._should_count_fetch_failure_context(activity, external_diagnostics):
                    self._increment_mcp_tool_invocation(
                        activity,
                        tool_name="fetch_failure_context",
                    )
                activity.mcp_model_path.source_attribution = _build_source_attribution(
                    external_diagnostics
                )
                activity.mcp_model_path.error_count = _count_error_diagnostics(
                    external_diagnostics
                )

            with tracer.start_as_current_span("pipeline.step.diagnose") as span:
                t1 = time.monotonic()
                diagnosis = await self._run_with_timeout(
                    step_name="Diagnose",
                    coro=self._diagnosis_agent.diagnose(
                        log_analyses,
                        workflow_info,
                        external_diagnostics=external_diagnostics,
                    ),
                )
                elapsed = time.monotonic() - t1
                span.set_attribute("step.duration_seconds", round(elapsed, 2))
                span.set_attribute("diagnosis.failure_type", diagnosis.failure_type.value)
                span.set_attribute("diagnosis.confidence", diagnosis.confidence)
                span.set_attribute("diagnosis.is_auto_fixable", diagnosis.is_auto_fixable)

            activity.failure_type = diagnosis.failure_type
            activity.diagnosis = diagnosis

            logger.info(
                f"Diagnosis: {diagnosis.failure_type.value} "
                f"(confidence: {diagnosis.confidence:.0%})"
            )
            if is_debug:
                logger.debug(
                    "[debug-mode] Step 2 completed in %.2fs — type=%s confidence=%.2f root_cause=%s",
                    elapsed,
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

            with tracer.start_as_current_span("pipeline.step.remediate") as span:
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
                elapsed = time.monotonic() - t2
                span.set_attribute("step.duration_seconds", round(elapsed, 2))
                span.set_attribute(
                    "remediation.action",
                    result.action_taken.value if result.action_taken else "none",
                )
                span.set_attribute("remediation.success", result.success)

            activity.remediation_result = result

            if is_debug:
                logger.debug(
                    "[debug-mode] Step 3 completed in %.2fs — action=%s success=%s",
                    elapsed,
                    result.action_taken.value if result.action_taken else "none",
                    result.success,
                )

            # Update final status
            if result.success:
                activity.status = RemediationStatus.COMPLETED
                pipeline_span.set_attribute("pipeline.outcome", "completed")
                logger.info(f"Remediation completed: {result.action_taken.value}")
                if result.pr_url:
                    logger.info(f"PR created: {result.pr_url}")
                if result.issue_url:
                    logger.info(f"Issue created: {result.issue_url}")
            else:
                activity.status = RemediationStatus.FAILED
                activity.error = result.error_message
                pipeline_span.set_attribute("pipeline.outcome", "failed")
                logger.warning(f"Remediation failed: {result.error_message}")

            await self._storage.update_activity(activity)
            return activity

          except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            activity.status = RemediationStatus.FAILED
            activity.error = str(e)
            pipeline_span.set_attribute("pipeline.outcome", "exception")
            pipeline_span.record_exception(e)
            await self._storage.update_activity(activity)
            return activity
          finally:
            try:
                model_path = telemetry_collector.to_model_path()
                if model_path is not None:
                    activity.llm_model_path = model_path
                    await self._storage.update_activity(activity)
            except Exception:
                logger.debug(
                    "Failed to persist LLM model-path telemetry for activity %s",
                    activity.id,
                    exc_info=True,
                )
            reset_llm_telemetry_collector(telemetry_token)
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

        # Fetch enough recent activities to reliably detect duplicates.
        # The previous limit of 10 could miss a matching run_id in busy repos.
        existing = await self._storage.get_activities(
            repository=event.repository.full_name,
            limit=100,
        )

        for activity in existing:
            if activity.workflow_run_id == event.workflow_run.id:
                # Check if this is a retry
                if event.workflow_run.run_attempt > 1:
                    return True, "Retry attempt"
                return False, "Already processed"

        # Check if we've hit the max remediation attempts for this *workflow*
        # (not the entire repo) to avoid blocking unrelated workflows.
        workflow_name = event.workflow_run.name or ""
        recent_workflow_failures = [
            a
            for a in existing
            if a.status == RemediationStatus.FAILED and a.workflow_name == workflow_name
        ]

        if len(recent_workflow_failures) >= self._settings.max_remediation_attempts:
            return False, f"Max remediation attempts reached for workflow '{workflow_name}'"

        return True, "New failure to process"

    # ------------------------------------------------------------------
    # External-diagnostics backfill
    # ------------------------------------------------------------------

    async def backfill_activity_diagnostics(
        self,
        activity: ActivityRecord,
    ) -> bool:
        """Attempt to backfill external diagnostics for a single activity.

        Called after the pipeline has completed when the original poll window
        was exhausted.  If ci-doctor findings are now available, the activity's
        ``external_diagnostics`` list is replaced with the real findings and
        persisted.

        Returns:
            ``True`` if new findings were attached, ``False`` otherwise.
        """
        if "/" not in activity.repository_name:
            return False
        owner, repo = activity.repository_name.split("/", 1)

        if not self._gh_aw_passive_enabled():
            return False

        # Determine head_sha and run_number from stored diagnosis context.
        head_sha = ""
        run_number: int | None = None
        for diag in activity.external_diagnostics:
            if diag.matched_run_id == activity.workflow_run_id:
                # The original poll_window_exhausted entry won't have these,
                # but a partially-collected one might.
                break

        # We need head_sha for the adapter; fall back to a lightweight GitHub API call.
        if not head_sha:
            try:
                run_details = await self._github_tools.get_workflow_run(
                    owner, repo, activity.workflow_run_id,
                )
                head_sha = run_details.get("head_sha", "")
                run_number = run_details.get("run_number")
            except Exception:
                logger.debug(
                    "Backfill: unable to fetch run details for %s/%s run %s",
                    owner, repo, activity.workflow_run_id,
                )
                return False

        try:
            findings = await self._gh_aw_adapter.collect_external_diagnostics(
                owner=owner,
                repo=repo,
                run_id=activity.workflow_run_id,
                head_sha=head_sha,
                run_number=run_number,
            )
        except Exception as exc:
            logger.warning(
                "Backfill: ci-doctor collection failed for %s/%s run %s: %s",
                owner, repo, activity.workflow_run_id, type(exc).__name__,
            )
            return False

        if not findings:
            return False

        # Replace the stale poll_window_exhausted entries with real findings.
        activity.external_diagnostics = [
            d for d in activity.external_diagnostics
            if d.metadata.get("reason_code") != "poll_window_exhausted"
        ] + findings
        if activity.mcp_model_path is not None:
            if self._should_count_fetch_failure_context(activity, findings):
                self._increment_mcp_tool_invocation(
                    activity,
                    tool_name="fetch_failure_context",
                )
            activity.mcp_model_path.source_attribution = _build_source_attribution(
                activity.external_diagnostics
            )
            activity.mcp_model_path.error_count = _count_error_diagnostics(
                activity.external_diagnostics
            )
        await self._storage.update_activity(activity)

        logger.info(
            "Backfill: attached %d ci-doctor finding(s) to activity %s (run %s)",
            len(findings), activity.id, activity.workflow_run_id,
        )
        return True
