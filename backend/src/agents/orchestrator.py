"""Orchestrator Agent for coordinating the healing pipeline."""

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import timedelta
from functools import partial
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
    Diagnosis,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    FailureContext,
    LogAnalysis,
    MCPActionAuditEntry,
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
_MCP_TOOL_POLICY_VALUES = {"disabled", "read_only", "write_with_approval", "auto"}
_MCP_DEFAULT_TOOL_POLICIES = {
    "fetch_failure_context": "read_only",
    "fetch_runbook_context": "read_only",
    "publish_artifact": "write_with_approval",
    "rerun_pipeline": "write_with_approval",
}
_MCP_WRITE_TOOLS = {"publish_artifact", "rerun_pipeline"}
_MCP_RUNBOOK_PATH_PREFERENCE = (
    "docs/local_demo_runbook.md",
    "docs/runbook.md",
    "docs/troubleshooting.md",
    "docs/ci_runbook.md",
    "readme.md",
)


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


def _decode_github_file_content(payload: dict[str, Any]) -> str:
    """Decode GitHub contents API payload into UTF-8 text."""
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return ""
    encoding = str(payload.get("encoding", "")).strip().lower()
    if encoding == "base64":
        compact = "".join(content.splitlines())
        try:
            return base64.b64decode(compact).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            return ""
    return content


def _select_runbook_path(tree_entries: list[dict[str, Any]]) -> str | None:
    """Pick the best runbook-like markdown path from repository tree entries."""
    candidate_paths: list[str] = []
    for entry in tree_entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type", "")).strip().lower() != "blob":
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        normalized = raw_path.strip()
        if not normalized:
            continue
        lower = normalized.lower()
        if not lower.endswith(".md"):
            continue
        if (
            "runbook" in lower
            or "troubleshoot" in lower
            or "incident" in lower
            or lower == "readme.md"
        ):
            candidate_paths.append(normalized)

    if not candidate_paths:
        return None

    by_lower = {path.lower(): path for path in candidate_paths}
    for preferred in _MCP_RUNBOOK_PATH_PREFERENCE:
        resolved = by_lower.get(preferred)
        if resolved:
            return resolved
    return sorted(candidate_paths)[0]


def _build_runbook_excerpt(content: str, workflow_name: str | None = None) -> str:
    """Build a concise runbook excerpt with keyword-biased lines first."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""

    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", (workflow_name or "").lower())
        if len(token) >= 4
    }
    selected: list[str] = []
    if tokens:
        for line in lines:
            lower = line.lower()
            if any(token in lower for token in tokens):
                selected.append(line)
            if len(selected) >= 8:
                break

    if not selected:
        selected = lines[:8]

    excerpt = "\n".join(selected)
    if len(excerpt) > 900:
        excerpt = excerpt[:897].rstrip() + "..."
    return excerpt


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
    def _normalize_failure_context_key(key: str) -> str:
        """Normalize free-form context keys into stable lookup form."""
        return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")

    @classmethod
    def _normalize_failure_context_map(cls, details: dict[str, Any]) -> dict[str, str]:
        """Normalize diagnosis detail keys/values for failure-context extraction."""
        normalized: dict[str, str] = {}
        for raw_key, raw_value in details.items():
            key = cls._normalize_failure_context_key(str(raw_key))
            if not key:
                continue
            value: str | None = None
            if isinstance(raw_value, (str, int, float, bool)):
                value = str(raw_value).strip()
            elif isinstance(raw_value, list):
                first_scalar = next(
                    (
                        item
                        for item in raw_value
                        if isinstance(item, (str, int, float, bool))
                        and str(item).strip()
                    ),
                    None,
                )
                if first_scalar is not None:
                    value = str(first_scalar).strip()
            if not value:
                continue
            normalized[key] = re.sub(r"\s+", " ", value)[:240]
        return normalized

    @staticmethod
    def _extract_command_from_line(line: str) -> str | None:
        """Best-effort command extraction from step/event/error log lines."""
        text = line.strip()
        if not text:
            return None
        patterns = (
            r"^Run\s+(.+)$",
            r"^\$\s+(.+)$",
            r"^npm ERR!\s+command\s+(.+)$",
            r"^Command\s+(.+?)\s+failed\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            command = match.group(1).strip().strip("`\"'")
            if command:
                return command[:240]
        return None

    def _derive_failure_context(
        self,
        *,
        log_analyses: list[LogAnalysis],
        diagnosis: Diagnosis | None,
        external_diagnostics: list[ExternalDiagnostic],
    ) -> FailureContext | None:
        """Build normalized failure context for UI/API consumers."""
        details_raw = diagnosis.error_details if diagnosis and isinstance(diagnosis.error_details, dict) else {}
        details = self._normalize_failure_context_map(details_raw)

        failing_job = (
            details.get("failing_job")
            or details.get("job_name")
            or details.get("job")
            or details.get("failed_job")
        )
        if not failing_job and log_analyses:
            first_job = next((analysis.job_name.strip() for analysis in log_analyses if analysis.job_name), "")
            failing_job = first_job or None

        failing_step = (
            details.get("failing_step")
            or details.get("step_name")
            or details.get("step")
            or details.get("failed_step")
        )

        failing_command = (
            details.get("failing_command")
            or details.get("command")
            or details.get("run_command")
            or details.get("cmd")
        )
        if not failing_command and failing_step:
            failing_command = self._extract_command_from_line(failing_step)
        if not failing_command:
            for analysis in log_analyses:
                for line in [*analysis.key_events, *analysis.error_lines]:
                    extracted = self._extract_command_from_line(line)
                    if extracted:
                        failing_command = extracted
                        break
                if failing_command:
                    break

        signal = (
            details.get("signal")
            or details.get("signature")
            or details.get("trigger")
            or details.get("reason_code")
            or details.get("error_code")
        )
        if not signal:
            for diagnostic in external_diagnostics:
                metadata = diagnostic.metadata if isinstance(diagnostic.metadata, dict) else {}
                reason_code = metadata.get("reason_code")
                if isinstance(reason_code, str) and reason_code.strip():
                    signal = reason_code.strip()[:120]
                    break

        if not any([failing_job, failing_step, failing_command, signal]):
            return None
        return FailureContext(
            failing_job=failing_job,
            failing_step=failing_step,
            failing_command=failing_command,
            signal=signal,
        )

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

    @staticmethod
    def _normalize_repo_full_name(owner: str, repo: str) -> str:
        owner_norm = (owner or "").strip().lower()
        repo_norm = (repo or "").strip().lower()
        if not owner_norm or not repo_norm:
            return ""
        return f"{owner_norm}/{repo_norm}"

    def _effective_mcp_repo_allowlist(self) -> set[str]:
        """Resolve MCP repo allowlist with PH allowlist as fallback."""
        raw = self._settings.mcp_repo_allowlist or self._settings.ph_allowed_repos
        normalized = {
            str(repo).strip().lower()
            for repo in raw
            if str(repo).strip()
        }
        return normalized

    def _resolve_mcp_tool_policy(self, tool_name: str) -> str:
        """Resolve policy mode for an MCP tool with safe defaults."""
        normalized_tool = (tool_name or "").strip().lower()
        if not normalized_tool:
            return "disabled"
        override = (self._settings.mcp_tool_policies or {}).get(normalized_tool, "")
        normalized_override = str(override).strip().lower()
        if normalized_override in _MCP_TOOL_POLICY_VALUES:
            return normalized_override
        return _MCP_DEFAULT_TOOL_POLICIES.get(normalized_tool, "disabled")

    @staticmethod
    def _is_mcp_write_tool(tool_name: str) -> bool:
        return (tool_name or "").strip().lower() in _MCP_WRITE_TOOLS

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        """Build deterministic payload hash for MCP action audit entries."""
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def _record_mcp_action_audit(
        self,
        activity: ActivityRecord,
        *,
        tool_name: str,
        payload: dict[str, Any],
        result: str,
        latency_ms: float = 0.0,
        success: bool = False,
        error_class: str | None = None,
    ) -> None:
        """Attach one MCP action audit entry to activity model-path metadata."""
        model_path = activity.mcp_model_path
        if model_path is None:
            return
        model_path.action_audit.append(
            MCPActionAuditEntry(
                actor=f"orchestrator:{activity.repository_name}",
                provider=model_path.provider or "unknown",
                tool=(tool_name or "unknown").strip().lower(),
                payload_hash=self._payload_hash(payload),
                result=result,
                request_id=activity.id,
                latency_ms=round(max(0.0, float(latency_ms)), 2),
                success=success,
                error_class=error_class,
            )
        )
        if latency_ms > 0:
            model_path.total_latency_ms = round(
                float(model_path.total_latency_ms) + float(latency_ms), 2
            )
        if len(model_path.action_audit) > 100:
            model_path.action_audit = model_path.action_audit[-100:]

    def _check_mcp_tool_policy(
        self,
        activity: ActivityRecord,
        *,
        owner: str,
        repo: str,
        tool_name: str,
        default_branch: str | None,
    ) -> tuple[bool, str]:
        """Apply MCP repo allowlist + policy guardrails for one tool call."""
        repo_full_name = self._normalize_repo_full_name(owner, repo)
        if not self._settings.mcp_enabled:
            return False, "mcp_disabled"

        provider = (self._settings.mcp_provider or "").strip().lower()
        if provider != "github":
            return False, "provider_not_github"

        allowlist = self._effective_mcp_repo_allowlist()
        if allowlist and repo_full_name not in allowlist:
            return False, "repo_not_allowlisted"

        policy_mode = self._resolve_mcp_tool_policy(tool_name)
        if policy_mode == "disabled":
            return False, "tool_policy_disabled"

        is_write_tool = self._is_mcp_write_tool(tool_name)
        if is_write_tool and self._settings.mcp_read_only:
            return False, "blocked_by_read_only_mode"
        if is_write_tool and policy_mode == "read_only":
            return False, "tool_policy_read_only"
        if is_write_tool and policy_mode == "write_with_approval":
            return False, "approval_required"
        if is_write_tool:
            # Preserve branch protections by requiring explicit future write-path logic.
            return False, f"branch_protection_respected:{default_branch or 'unknown'}"

        return True, "ok"

    async def _run_mcp_tool_call(
        self,
        activity: ActivityRecord,
        *,
        tool_name: str,
        payload: dict[str, Any],
        operation_factory: Callable[[], Awaitable[T]],
    ) -> T:
        """Execute one MCP tool operation with hard timeout + bounded retries."""
        timeout_seconds = max(0.1, float(self._settings.mcp_timeout_seconds))
        max_attempts = max(1, int(self._settings.mcp_max_retries) + 1)
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._increment_mcp_tool_invocation(activity, tool_name=tool_name)
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(operation_factory(), timeout_seconds)
                latency_ms = (time.monotonic() - started) * 1000.0
                self._record_mcp_action_audit(
                    activity,
                    tool_name=tool_name,
                    payload=payload,
                    result=f"success:attempt_{attempt}",
                    latency_ms=latency_ms,
                    success=True,
                )
                return result
            except TimeoutError as exc:
                last_error = exc
                latency_ms = (time.monotonic() - started) * 1000.0
                self._record_mcp_action_audit(
                    activity,
                    tool_name=tool_name,
                    payload=payload,
                    result=f"timeout:attempt_{attempt}",
                    latency_ms=latency_ms,
                    success=False,
                    error_class=type(exc).__name__,
                )
            except Exception as exc:  # pragma: no cover - defensive + provider variability
                last_error = exc
                latency_ms = (time.monotonic() - started) * 1000.0
                self._record_mcp_action_audit(
                    activity,
                    tool_name=tool_name,
                    payload=payload,
                    result=f"error:{type(exc).__name__}:attempt_{attempt}",
                    latency_ms=latency_ms,
                    success=False,
                    error_class=type(exc).__name__,
                )
            if attempt < max_attempts:
                await asyncio.sleep(0)
        assert last_error is not None
        raise last_error

    def _gh_aw_passive_enabled(self) -> bool:
        """Return whether gh-aw passive diagnostics collection is enabled."""
        return (
            self._settings.gh_aw_tools_enabled
            and self._settings.gh_aw_ingestion_mode == "passive"
        )

    def _github_mcp_collection_enabled(
        self,
        activity: ActivityRecord,
        *,
        owner: str,
        repo: str,
        default_branch: str | None,
    ) -> tuple[bool, str]:
        """Return whether direct GitHub MCP context collection can run."""
        allowed, reason = self._check_mcp_tool_policy(
            activity,
            owner=owner,
            repo=repo,
            tool_name="fetch_failure_context",
            default_branch=default_branch,
        )
        if not allowed:
            self._record_mcp_action_audit(
                activity,
                tool_name="fetch_failure_context",
                payload={"owner": owner, "repo": repo, "run_id": activity.workflow_run_id},
                result=f"blocked:{reason}",
            )
            return False, reason
        try:
            health = get_mcp_provider(self._settings).health(self._settings)
        except Exception:
            self._record_mcp_action_audit(
                activity,
                tool_name="fetch_failure_context",
                payload={"owner": owner, "repo": repo, "run_id": activity.workflow_run_id},
                result="blocked:provider_health_error",
            )
            return False, "provider_health_error"
        if not (health.enabled and health.available):
            self._record_mcp_action_audit(
                activity,
                tool_name="fetch_failure_context",
                payload={"owner": owner, "repo": repo, "run_id": activity.workflow_run_id},
                result=f"blocked:{health.reason}",
            )
            return False, health.reason
        return True, "ok"

    async def _collect_runbook_context_from_github_mcp(
        self,
        activity: ActivityRecord,
        *,
        owner: str,
        repo: str,
        event: WorkflowRunEvent,
    ) -> list[ExternalDiagnostic]:
        """Collect runbook/knowledge context from repository markdown docs via MCP."""
        run_id = event.workflow_run.id
        payload_base = {"owner": owner, "repo": repo, "run_id": run_id}
        allowed, reason = self._check_mcp_tool_policy(
            activity,
            owner=owner,
            repo=repo,
            tool_name="fetch_runbook_context",
            default_branch=event.repository.default_branch,
        )
        if not allowed:
            self._record_mcp_action_audit(
                activity,
                tool_name="fetch_runbook_context",
                payload={**payload_base, "operation": "policy_check"},
                result=f"blocked:{reason}",
            )
            return []

        try:
            tree_entries = await self._run_mcp_tool_call(
                activity,
                tool_name="fetch_runbook_context",
                payload={**payload_base, "operation": "get_repository_tree"},
                operation_factory=partial(
                    self._github_tools.get_repository_tree,
                    owner,
                    repo,
                    "HEAD",
                    True,
                ),
            )
        except Exception:
            logger.debug(
                "GitHub MCP runbook lookup failed while reading repository tree for %s/%s",
                owner,
                repo,
                exc_info=True,
            )
            return []

        runbook_path = _select_runbook_path(tree_entries)
        if not runbook_path:
            return []

        try:
            runbook_payload = await self._run_mcp_tool_call(
                activity,
                tool_name="fetch_runbook_context",
                payload={
                    **payload_base,
                    "operation": "get_file_contents",
                    "path": runbook_path,
                },
                operation_factory=partial(
                    self._github_tools.get_file_contents,
                    owner,
                    repo,
                    runbook_path,
                ),
            )
        except Exception:
            logger.debug(
                "GitHub MCP runbook lookup failed while reading %s/%s:%s",
                owner,
                repo,
                runbook_path,
                exc_info=True,
            )
            return []

        runbook_content = _decode_github_file_content(runbook_payload)
        runbook_excerpt = _build_runbook_excerpt(runbook_content, event.workflow_run.name)
        if not runbook_excerpt:
            return []

        return [
            ExternalDiagnostic(
                source="knowledge-mcp",
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary=f"Repository runbook context retrieved from {runbook_path}.",
                matched_run_id=run_id,
                confidence_delta=0.01,
                metadata={
                    "runbook_path": runbook_path,
                    "details": {
                        "summary": (
                            f"Knowledge context loaded from `{runbook_path}` "
                            "to support diagnosis guidance."
                        ),
                        "recommended_actions": runbook_excerpt,
                    },
                },
            )
        ]

    async def _collect_external_diagnostics_from_github_mcp(
        self,
        activity: ActivityRecord,
        owner: str,
        repo: str,
        event: WorkflowRunEvent,
    ) -> list[ExternalDiagnostic]:
        """Collect baseline run context from GitHub when MCP github provider is enabled."""
        run_id = event.workflow_run.id
        payload_base = {"owner": owner, "repo": repo, "run_id": run_id}
        try:
            run_details = await self._run_mcp_tool_call(
                activity,
                tool_name="fetch_failure_context",
                payload={**payload_base, "operation": "get_workflow_run"},
                operation_factory=lambda: self._github_tools.get_workflow_run(owner, repo, run_id),
            )
            jobs = await self._run_mcp_tool_call(
                activity,
                tool_name="fetch_failure_context",
                payload={**payload_base, "operation": "get_workflow_jobs"},
                operation_factory=lambda: self._github_tools.get_workflow_jobs(owner, repo, run_id),
            )
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
            pr_number_for_call = pr_number
            try:
                files = await self._run_mcp_tool_call(
                    activity,
                    tool_name="fetch_failure_context",
                    payload={
                        **payload_base,
                        "operation": "get_pull_request_files",
                        "pull_request": pr_number_for_call,
                    },
                    operation_factory=partial(
                        self._github_tools.get_pull_request_files,
                        owner,
                        repo,
                        pr_number_for_call,
                        per_page=100,
                    ),
                )
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

        diagnostics: list[ExternalDiagnostic] = [
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
        diagnostics.extend(
            await self._collect_runbook_context_from_github_mcp(
                activity,
                owner=owner,
                repo=repo,
                event=event,
            )
        )
        return diagnostics

    async def _collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        event: WorkflowRunEvent,
        activity: ActivityRecord,
    ) -> list[ExternalDiagnostic]:
        """Collect external diagnostics from all available gh-aw sources.

        Ambient sources (breaking-change-checker, etc.) are collected
        immediately in a single pass.  ci-doctor is polled with bounded
        backoff because it triggers asynchronously after a CI failure and
        needs time to publish its issue.
        """
        if not self._gh_aw_passive_enabled():
            mcp_enabled, mcp_reason = self._github_mcp_collection_enabled(
                activity,
                owner=owner,
                repo=repo,
                default_branch=event.repository.default_branch,
            )
            if mcp_enabled:
                return await self._collect_external_diagnostics_from_github_mcp(
                    activity,
                    owner,
                    repo,
                    event,
                )
            if (
                self._settings.mcp_enabled
                and (self._settings.mcp_provider or "").strip().lower() == "github"
            ):
                return [
                    ExternalDiagnostic(
                        source="github-mcp",
                        status=ExternalDiagnosticStatus.UNAVAILABLE,
                        summary="GitHub MCP context collection blocked by policy guardrails",
                        matched_run_id=event.workflow_run.id,
                        metadata={
                            "reason_code": mcp_reason,
                            "provider": "github",
                        },
                    )
                ]
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
            external_diagnostics = await self._collect_external_diagnostics(
                owner,
                repo,
                event,
                activity,
            )
            if external_diagnostics:
                activity.external_diagnostics = external_diagnostics
            if activity.mcp_model_path is not None:
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
            activity.failure_context = self._derive_failure_context(
                log_analyses=log_analyses,
                diagnosis=diagnosis,
                external_diagnostics=external_diagnostics,
            )

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
