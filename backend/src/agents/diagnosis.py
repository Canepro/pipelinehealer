"""Diagnosis Agent for root cause analysis of CI/CD failures."""

import json
import logging
import re
from typing import Any

from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import (
    Diagnosis,
    DiagnosisSource,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    FailureType,
    LearningContextMatch,
    LLMDiagnosisRejection,
    LogAnalysis,
)
from ..tools.github_tools import GitHubTools
from ..tools.lint_autofix import lint_autofix_command
from .base import create_cloud_agent, get_agent_prompt

logger = logging.getLogger(__name__)


LLM_REQUIRED_TOP_LEVEL_FIELDS = (
    "failure_type",
    "confidence",
    "root_cause",
    "affected_files",
    "is_auto_fixable",
    "suggested_fix",
    "error_details",
)

LLM_ERROR_DETAILS_SCHEMA: dict[FailureType, dict[str, Any]] = {
    FailureType.DEPENDENCY: {
        "package_name": "",
        "package_manager": "",
        "manifest_file": "",
        "current_version": "",
        "required_version": "",
        "resolution_kind": "",
    },
    FailureType.LINT: {
        "linter": "",
        "missing_file": "",
        "config_file": "",
        "autofix_command": "",
        "violations": [],
        "rule_ids": [],
    },
    FailureType.TEST: {
        "test_framework": "",
        "failed_tests": [],
        "test_errors": {},
        "is_flaky": False,
        "failure_scope": "",
        "suspected_files": [],
    },
    FailureType.TIMEOUT: {
        "timed_out_job": "",
        "timed_out_step": "",
        "timeout_minutes": 0,
        "suggested_timeout": 0,
        "resource_signal": "",
        "likely_fix_kind": "",
    },
    FailureType.BUILD_CONFIG: {
        "config_file": "",
        "config_error": "",
        "missing_env_vars": [],
        "workflow_permissions_fix": False,
        "permissions": {},
        "misconfiguration_kind": "",
    },
    FailureType.UNKNOWN: {
        "additional": "",
    },
}


class DiagnosisAgent:
    """Agent for diagnosing the root cause of CI/CD failures.

    This agent analyzes log analysis results and determines
    the failure type and root cause.
    """

    def __init__(
        self,
        github_tools: GitHubTools | None = None,
        azure_credential: DefaultAzureCredential | None = None,
    ):
        """Initialize the Diagnosis Agent.

        Args:
            github_tools: GitHub tools for optional repo-history correlation
            azure_credential: Azure credential for OpenAI
        """
        self._github_tools = github_tools
        self._credential = azure_credential or DefaultAzureCredential()
        self._settings = get_settings()
        self._agent: Any | None = None

    async def _get_agent(self) -> Any:
        """Get or create the agent instance."""
        if self._agent is None:
            self._agent = create_cloud_agent(
                name="Diagnosis",
                instructions=get_agent_prompt("diagnosis"),
                credential=self._credential,
                task="diagnosis",
                settings=self._settings,
            )

        return self._agent

    def refresh_runtime_settings(self) -> None:
        """Refresh mutable settings and rebuild cloud client on next call."""
        self._settings = get_settings()
        self._agent = None

    def _build_llm_error_details_schema_text(self) -> str:
        """Render the failure-type-specific error_details contract for the diagnosis prompt."""
        schema_lines = []
        for failure_type in (
            FailureType.DEPENDENCY,
            FailureType.LINT,
            FailureType.TEST,
            FailureType.TIMEOUT,
            FailureType.BUILD_CONFIG,
            FailureType.UNKNOWN,
        ):
            template = json.dumps(LLM_ERROR_DETAILS_SCHEMA[failure_type], ensure_ascii=True)
            schema_lines.append(f'- `{failure_type.value}`: {template}')
        return "\n".join(schema_lines)

    @staticmethod
    def _prepare_learning_context_summary(
        matches: list[LearningContextMatch] | None,
    ) -> str:
        """Serialize matched active learning artifacts for diagnosis context."""
        if not matches:
            return "Learning context: none"

        lines = []
        for match in matches[:3]:
            basis = ", ".join(match.match_basis[:4]) if match.match_basis else "ranked retrieval"
            line = (
                f"- id={match.id} title={match.title[:120]} "
                f"score={match.match_score:.2f} basis={basis}"
            )
            if match.reason_code:
                line += f" reason_code={match.reason_code}"
            if match.suggested_playbook:
                line += f" suggested_playbook={match.suggested_playbook[:220]}"
            lines.append(line)
        return "Learning context:\n" + "\n".join(lines)

    def preview_pattern_diagnosis(
        self,
        log_analyses: list[LogAnalysis],
    ) -> Diagnosis | None:
        """Expose deterministic pattern diagnosis as a hint for orchestration layers."""
        return self._pattern_based_diagnosis(log_analyses)

    async def diagnose(
        self,
        log_analyses: list[LogAnalysis],
        workflow_info: dict[str, Any] | None = None,
        external_diagnostics: list[ExternalDiagnostic] | None = None,
        learning_context: list[LearningContextMatch] | None = None,
        pattern_diagnosis_hint: Diagnosis | None = None,
    ) -> Diagnosis:
        """Diagnose the root cause of a failure based on log analyses.

        Args:
            log_analyses: List of log analysis results
            workflow_info: Additional workflow information
            external_diagnostics: Optional supplemental diagnostics findings

        Returns:
            Diagnosis result
        """
        logger.info(f"Diagnosing failure from {len(log_analyses)} log analyses")

        if not log_analyses:
            external_only = self._diagnosis_from_external_diagnostics(external_diagnostics)
            if external_only is not None:
                return self._with_source(external_only, DiagnosisSource.PATTERN)
            return Diagnosis(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                root_cause="No log analyses provided",
                is_auto_fixable=False,
            )

        # First, try pattern-based detection for common cases
        pattern_diagnosis = pattern_diagnosis_hint or self._pattern_based_diagnosis(log_analyses)
        pattern_diagnosis = self._apply_changed_file_correlation(
            pattern_diagnosis,
            log_analyses,
            workflow_info,
        )

        similar_issues = await self._search_similar_issues(log_analyses, workflow_info)
        if similar_issues and pattern_diagnosis:
            pattern_diagnosis = self._apply_historical_issue_signal(
                pattern_diagnosis,
                similar_issues[0],
            )
        if pattern_diagnosis and external_diagnostics:
            pattern_diagnosis = self._apply_external_diagnostics_signal(
                pattern_diagnosis,
                external_diagnostics,
            )

        if pattern_diagnosis and pattern_diagnosis.confidence >= 0.8:
            logger.info(f"Pattern-based diagnosis: {pattern_diagnosis.failure_type}")
            logger.debug(
                "[debug-mode] Pattern matched: type=%s confidence=%.2f root_cause=%s",
                pattern_diagnosis.failure_type.value,
                pattern_diagnosis.confidence,
                pattern_diagnosis.root_cause[:200] if pattern_diagnosis.root_cause else "N/A",
            )
            return self._with_source(pattern_diagnosis, DiagnosisSource.PATTERN)

        if external_diagnostics:
            logger.debug(
                "[debug-mode] Received %d external diagnostics signal(s) for diagnosis context",
                len(external_diagnostics),
            )

        # Use the agent for more complex analysis
        agent = await self._get_agent()

        # Prepare the analysis summary for the agent
        analysis_summary = self._prepare_analysis_summary(log_analyses)
        context_summary = self._prepare_context_summary(
            workflow_info=workflow_info,
            similar_issues=similar_issues,
        )
        external_summary = self._prepare_external_diagnostics_summary(external_diagnostics)
        learning_summary = self._prepare_learning_context_summary(learning_context)
        error_details_schema_text = self._build_llm_error_details_schema_text()

        prompt = f"""Analyze the following CI/CD failure and provide a diagnosis.

{analysis_summary}

{context_summary}

{external_summary}

{learning_summary}

Provide your diagnosis in the following JSON format:
{{
    "failure_type": "dependency|test|lint|build_config|timeout|unknown",
    "confidence": 0.0-1.0,
    "root_cause": "Clear explanation of what went wrong",
    "affected_files": ["list", "of", "files"],
    "is_auto_fixable": true/false,
    "suggested_fix": "High-level suggestion",
    "error_details": {{ "see failure-type-specific schema below" }}
}}

Return exactly one JSON object with no markdown fences and no extra commentary.
For the chosen `failure_type`, `error_details` must include every key from the matching schema below.
Use empty strings, empty arrays/objects, `false`, or `0` when a field is unknown, but do not omit keys.

Failure-type-specific `error_details` schemas:
{error_details_schema_text}

Be specific about:
1. The exact failure type category
2. Your confidence level based on the evidence
3. Whether this can be automatically fixed
4. What files are likely involved
"""

        try:
            logger.debug(
                "[debug-mode] Pattern match did not reach 0.8 threshold (got %s); calling LLM. prompt_len=%d",
                f"{pattern_diagnosis.confidence:.2f}" if pattern_diagnosis else "no match",
                len(prompt),
            )
            response = await agent.run(prompt)
            response_text = str(response) if response else ""
            logger.debug(
                "[debug-mode] LLM response_len=%d response_preview=%s",
                len(response_text),
                response_text[:500],
            )

            # Extract JSON from response
            diagnosis = self._parse_diagnosis_response(response_text, pattern_diagnosis)
        except Exception as e:
            logger.error(f"Agent diagnosis failed: {e}")
            # Fall back to pattern-based diagnosis if available
            if pattern_diagnosis:
                return self._with_source(pattern_diagnosis, DiagnosisSource.PATTERN)

            return Diagnosis(
                failure_type=FailureType.UNKNOWN,
                confidence=0.3,
                root_cause=f"Diagnosis failed: {e}",
                is_auto_fixable=False,
                diagnosis_source=DiagnosisSource.LLM,
            )

        if external_diagnostics:
            diagnosis = self._apply_external_diagnostics_signal(diagnosis, external_diagnostics)
        if diagnosis.diagnosis_source is None:
            diagnosis = self._with_source(diagnosis, DiagnosisSource.LLM)
        return diagnosis

    def _prepare_external_diagnostics_summary(
        self,
        diagnostics: list[ExternalDiagnostic] | None,
    ) -> str:
        """Serialize external diagnostics into compact prompt context."""
        if not diagnostics:
            return "External diagnostics: none"

        lines: list[str] = []
        for diagnostic in diagnostics[:8]:
            status = diagnostic.status.value
            source = diagnostic.source or "unknown"
            delta_pct = int(round(diagnostic.confidence_delta * 100))
            summary = diagnostic.summary.strip() if diagnostic.summary else ""
            confidence_reason = ""
            metadata = diagnostic.metadata if isinstance(diagnostic.metadata, dict) else {}
            if isinstance(metadata.get("confidence_reason"), str):
                confidence_reason = metadata["confidence_reason"].strip()
            line = (
                f"- source={source} status={status} "
                f"delta={delta_pct:+d}%"
            )
            if summary:
                line += f" summary={summary[:220]}"
            if confidence_reason:
                line += f" reason={confidence_reason[:180]}"
            lines.append(line)
        return "External diagnostics:\n" + "\n".join(lines)

    def _apply_external_diagnostics_signal(
        self,
        diagnosis: Diagnosis,
        diagnostics: list[ExternalDiagnostic],
    ) -> Diagnosis:
        """Apply deterministic confidence adjustments from external diagnostics."""
        applied: list[dict[str, Any]] = []
        total_delta = 0.0

        for diagnostic in diagnostics:
            if diagnostic.status != ExternalDiagnosticStatus.AVAILABLE:
                continue
            delta = float(diagnostic.confidence_delta)
            if delta == 0:
                continue
            metadata = diagnostic.metadata if isinstance(diagnostic.metadata, dict) else {}
            reason = ""
            if isinstance(metadata.get("confidence_reason"), str):
                reason = metadata["confidence_reason"].strip()
            if not reason and diagnostic.summary:
                reason = diagnostic.summary.strip()[:200]

            total_delta += delta
            applied.append(
                {
                    "source": diagnostic.source or "unknown",
                    "delta": round(delta, 4),
                    "reason": reason,
                    "status": diagnostic.status.value,
                }
            )

        if not applied:
            return diagnosis

        before = float(diagnosis.confidence)
        after = max(0.0, min(0.95, before + total_delta))
        applied_delta = round(after - before, 4)
        diagnosis.confidence = after

        details = diagnosis.error_details if isinstance(diagnosis.error_details, dict) else {}
        details["external_signal_confidence_before"] = round(before, 4)
        details["external_signal_confidence_after"] = round(after, 4)
        details["external_signal_confidence_delta"] = applied_delta
        details["external_signal_sources"] = applied
        diagnosis.error_details = details
        return diagnosis

    def _diagnosis_from_external_diagnostics(
        self,
        diagnostics: list[ExternalDiagnostic] | None,
    ) -> Diagnosis | None:
        """Build a deterministic diagnosis from strong external diagnostics when logs are absent."""
        if not diagnostics:
            return None

        for diagnostic in diagnostics:
            if diagnostic.status != ExternalDiagnosticStatus.AVAILABLE:
                continue
            metadata = diagnostic.metadata if isinstance(diagnostic.metadata, dict) else {}
            reason_code = str(metadata.get("reason_code", "")).strip().lower()
            if reason_code != "github_runner_acquisition_failed":
                continue

            failed_jobs_raw = metadata.get("failed_jobs")
            failed_jobs = [
                str(job).strip()
                for job in (failed_jobs_raw if isinstance(failed_jobs_raw, list) else [])
                if str(job).strip()
            ]
            messages_raw = metadata.get("messages")
            messages = [
                str(message).strip()
                for message in (messages_raw if isinstance(messages_raw, list) else [])
                if str(message).strip()
            ]
            root_cause = "GitHub Actions could not acquire a hosted runner for required jobs"
            if failed_jobs:
                root_cause += f": {', '.join(failed_jobs[:3])}"

            return Diagnosis(
                failure_type=FailureType.BUILD_CONFIG,
                confidence=0.88,
                root_cause=root_cause,
                affected_files=[".github/workflows/"],
                is_auto_fixable=False,
                suggested_fix=(
                    "Re-run the workflow first. If it repeats, inspect GitHub Actions runner "
                    "availability and workflow queue posture before changing repository code."
                ),
                error_details={
                    "reason_code": "github_runner_acquisition_failed",
                    "classification_signal": "github_runner_acquisition_failed",
                    "signal": "github_runner_acquisition_failed",
                    "failing_job": ", ".join(failed_jobs[:3]) if failed_jobs else "",
                    "infrastructure_messages": messages,
                    "infrastructure_failure": True,
                },
            )

        return None

    def _pattern_based_diagnosis(
        self,
        log_analyses: list[LogAnalysis],
    ) -> Diagnosis | None:
        """Perform pattern-based diagnosis for common failure types.

        Args:
            log_analyses: List of log analysis results

        Returns:
            Diagnosis if a pattern matches, None otherwise
        """
        all_error_lines = []
        for analysis in log_analyses:
            all_error_lines.extend(analysis.error_lines)

        error_text = "\n".join(all_error_lines)

        # Check for dependency issues
        dep_patterns = [
            (r"npm ERR!.*peer dep", "npm peer dependency conflict"),
            (r"npm ERR!.*ERESOLVE", "npm dependency resolution failed"),
            (r"Could not find a version that satisfies", "pip version conflict"),
            (r"ModuleNotFoundError.*No module named", "missing Python module"),
            (r"Cannot find module", "missing Node.js module"),
            (r"Package .* was not found", "missing package"),
            (r"failed to resolve source metadata for", "Docker base image not found"),
            (r"manifest.*not found", "Docker image manifest not found"),
            (r"(?:pull access denied|repository does not exist)", "Docker image pull failed"),
        ]

        for pattern, description in dep_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                # Extract package name if possible
                # Allow scoped names and path segments (e.g. "@scope/pkg", "lodash/fp").
                package_name = ""
                python_missing_match = re.search(
                    r"No module named ['\"]([^'\"]+)['\"]",
                    error_text,
                    flags=re.IGNORECASE,
                )
                if python_missing_match:
                    raw_module = python_missing_match.group(1)
                    package_name = raw_module.split(".")[0] if raw_module else ""

                if not package_name:
                    package_match = re.search(
                        r"(?:module|package)[:\s]+['\"]?([@a-zA-Z0-9_./-]+)",
                        error_text,
                        flags=re.IGNORECASE,
                    )
                    if package_match:
                        package_name = package_match.group(1)

                # Common Node-style message: "Cannot find module 'left-pad'".
                if not package_name:
                    node_missing_match = re.search(
                        r"Cannot find module ['\"]([^'\"]+)['\"]",
                        error_text,
                        flags=re.IGNORECASE,
                    )
                    if node_missing_match:
                        package_name = node_missing_match.group(1)

                # Infer package manager from the matched pattern/context, not from incidental words.
                # This keeps Node "Cannot find module ..." from defaulting to pip.
                normalized_error_text = error_text.lower()
                normalized_description = description.lower()
                package_manager = (
                    "npm"
                    if (
                        "npm" in pattern
                        or "npm" in normalized_error_text
                        or "bun" in normalized_error_text
                        or "Cannot find module" in pattern
                    )
                    else "pip"
                    if (
                        "python" in normalized_description
                        or "pip" in normalized_description
                        or "modulenotfounderror" in normalized_error_text
                    )
                    else "docker"
                    if "docker" in normalized_description or "manifest" in normalized_description
                    else "generic"
                )
                manifest_file = self._infer_dependency_manifest_file(package_manager, error_text)
                resolution_kind = self._classify_dependency_resolution_kind(
                    description=description,
                    package_manager=package_manager,
                    error_text=error_text,
                )
                is_auto_fixable = package_manager in {"npm", "pip"} and resolution_kind in {
                    "missing",
                    "version_conflict",
                }

                return Diagnosis(
                    failure_type=FailureType.DEPENDENCY,
                    confidence=0.85,
                    root_cause=description,
                    affected_files=[manifest_file] if manifest_file else [],
                    is_auto_fixable=is_auto_fixable,
                    suggested_fix=self._build_dependency_suggested_fix(
                        package_manager=package_manager,
                        package_name=package_name,
                        description=description,
                    ),
                    diagnosis_source=DiagnosisSource.PATTERN,
                    error_details=self._build_classification_details(
                        family=FailureType.DEPENDENCY,
                        pattern=pattern,
                        signal=description,
                        details={
                            "package_name": package_name,
                            "package_manager": package_manager,
                            "manifest_file": manifest_file,
                            "resolution_kind": resolution_kind,
                        },
                    ),
                )

        # Check for lint/format issues
        lint_patterns = [
            (r"eslint.*error", "eslint", "ESLint violation", False),
            # ESLint v9+ uses flat config by default; missing config is common and fixable by adding eslint.config.js.
            (r"eslint.*eslint\.config\.(?:js|mjs|cjs)", "eslint", "ESLint missing flat config", True),
            (r"prettier.*error", "prettier", "Prettier formatting issue", False),
            (r"code style issues found", "prettier", "Prettier formatting issue", False),
            (r"black.*would reformat", "black", "Black formatting required", False),
            (r"ruff.*error", "ruff", "Ruff linting error", False),
            (r"flake8.*error", "flake8", "Flake8 violation", False),
            (
                r"(?:[A-Za-z0-9_./-]+\.py:\d+:\s*error:.*\[[a-z0-9-]+\])|(?:mypy.*error)",
                "mypy",
                "Mypy type-check failure",
                False,
            ),
        ]

        for pattern, linter, description, is_missing_config in lint_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                autofix_command = lint_autofix_command(linter)
                is_auto_fixable = is_missing_config or bool(autofix_command)
                affected_files = self._extract_file_references(error_text)[:20]
                return Diagnosis(
                    failure_type=FailureType.LINT,
                    confidence=0.9,
                    root_cause=description,
                    affected_files=affected_files,
                    is_auto_fixable=is_auto_fixable,
                    suggested_fix=self._build_lint_suggested_fix(
                        linter=linter,
                        is_missing_config=is_missing_config,
                        missing_file="eslint.config.js" if is_missing_config else "",
                    ),
                    diagnosis_source=DiagnosisSource.PATTERN,
                    error_details=self._build_classification_details(
                        family=FailureType.LINT,
                        pattern=pattern,
                        signal=description,
                        details={
                            "linter": linter,
                            "missing_file": "eslint.config.js" if is_missing_config else "",
                            "config_file": "eslint.config.js" if is_missing_config else "",
                            "autofix_command": autofix_command,
                            "violations": [],
                            "rule_ids": self._extract_lint_rule_ids(error_text, linter),
                        },
                    ),
                )

        # Check for test failures
        flaky_patterns = [
            (r"(?:flaky|intermittent)\s+test", "Flaky test behavior detected"),
            (r"(?:passed|succeeded)\s+on\s+retry", "Test passed on retry (flaky behavior)"),
            (r"rerun.*(?:passed|succeeded)", "Rerun succeeded after prior test failure"),
        ]
        for pattern, description in flaky_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                framework = self._detect_test_framework(error_text)
                failed_tests = self._extract_failed_tests(error_text)
                return Diagnosis(
                    failure_type=FailureType.TEST,
                    confidence=0.78,
                    root_cause=description,
                    is_auto_fixable=False,
                    suggested_fix=self._build_test_suggested_fix(
                        framework=framework,
                        failed_tests=failed_tests,
                        is_flaky=True,
                    ),
                    diagnosis_source=DiagnosisSource.PATTERN,
                    error_details=self._build_classification_details(
                        family=FailureType.TEST,
                        pattern=pattern,
                        signal=description,
                        details={
                            "is_flaky": True,
                            "test_framework": framework,
                            "failed_tests": failed_tests,
                            "test_errors": self._extract_test_errors(error_text, failed_tests),
                            "failure_scope": "suite",
                            "suspected_files": self._suspected_files_from_tests(failed_tests),
                        },
                    ),
                )

        test_patterns = [
            (r"ERROR collecting\s+[^\n]+", "Pytest test collection failed", False),
            (r"FAIL\s+.*\.test\.", "Test suite failed", False),
            (r"AssertionError", "Assertion failed in test", False),
            (r"pytest.*FAILED", "pytest test failed", False),
            (r"jest.*FAIL", "Jest test failed", False),
            (
                r"\b\d+\s+failing\b(?!\s+(?:check|checks|job|jobs|workflow|workflows|step|steps|stage|stages|lint|build|config))",
                "Tests failing",
                True,
            ),
        ]

        for pattern, description, requires_test_context in test_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                has_test_context = self._has_test_context(error_text)
                if requires_test_context and not has_test_context:
                    logger.debug(
                        "[debug-mode] Skipping ambiguous test signature '%s' due to missing test context.",
                        pattern,
                    )
                    continue
                # Check if it might be flaky
                is_flaky = "timeout" in error_text.lower() or "intermittent" in error_text.lower()
                framework = self._detect_test_framework(error_text)
                if framework == "unknown" and "error collecting" in error_text.lower():
                    framework = "pytest"
                failed_tests = self._extract_failed_tests(error_text)
                collection_targets = self._extract_collection_targets(error_text)
                suspected_files = (
                    collection_targets if collection_targets else self._suspected_files_from_tests(failed_tests)
                )
                failure_scope = (
                    "collection"
                    if collection_targets
                    else "test_case"
                    if failed_tests
                    else "suite"
                )

                return Diagnosis(
                    failure_type=FailureType.TEST,
                    confidence=0.85,
                    root_cause=description,
                    affected_files=suspected_files[:20],
                    is_auto_fixable=False,
                    suggested_fix=self._build_test_suggested_fix(
                        framework=framework,
                        failed_tests=failed_tests,
                        is_flaky=is_flaky,
                        failure_scope=failure_scope,
                        suspected_files=suspected_files,
                    ),
                    diagnosis_source=DiagnosisSource.PATTERN,
                    error_details=self._build_classification_details(
                        family=FailureType.TEST,
                        pattern=pattern,
                        signal=description,
                        details={
                            "is_flaky": is_flaky,
                            "test_framework": framework,
                            "failed_tests": failed_tests,
                            "test_errors": self._extract_test_errors(error_text, failed_tests),
                            "failure_scope": failure_scope,
                            "suspected_files": suspected_files,
                        },
                    ),
                )

        # Check for timeout issues
        timeout_patterns = [
            (r"timed?\s*out(?!\s*(?:to|=|:)\s*\d)", "Operation timed out"),
            (r"exceeded.*time.*limit", "Time limit exceeded"),
            (r"killed.*signal.*9", "Process killed (likely OOM or timeout)"),
            (r"no space left on device", "Runner disk space exhausted"),
            (r"deadline\s+exceeded", "Deadline exceeded"),
        ]

        for pattern, description in timeout_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                timeout_minutes = self._extract_timeout_minutes(error_text)
                timed_out_job = str(log_analyses[0].job_name or "Unknown").strip() if log_analyses else "Unknown"
                timed_out_step = self._extract_timed_out_step(error_text)
                resource_signal = self._detect_timeout_resource_signal(error_text)
                likely_fix_kind = self._detect_timeout_fix_kind(description, resource_signal)
                suggested_timeout = (
                    max(timeout_minutes * 2, timeout_minutes + 5) if timeout_minutes > 0 else 0
                )
                return Diagnosis(
                    failure_type=FailureType.TIMEOUT,
                    confidence=0.8,
                    root_cause=description,
                    is_auto_fixable=False,
                    suggested_fix=self._build_timeout_suggested_fix(
                        description=description,
                        timeout_minutes=timeout_minutes,
                        suggested_timeout=suggested_timeout,
                        resource_signal=resource_signal,
                    ),
                    diagnosis_source=DiagnosisSource.PATTERN,
                    error_details=self._build_classification_details(
                        family=FailureType.TIMEOUT,
                        pattern=pattern,
                        signal=description,
                        details={
                            "timed_out_job": timed_out_job,
                            "timed_out_step": timed_out_step,
                            "timeout_minutes": timeout_minutes,
                            "suggested_timeout": suggested_timeout,
                            "resource_signal": resource_signal,
                            "likely_fix_kind": likely_fix_kind,
                        },
                    ),
                )

        # Check for build config issues
        workflow_permission_patterns = [
            (
                r"resource not accessible by integration",
                "Insufficient GitHub Actions token permissions",
            ),
            (
                r"insufficient permissions",
                "Insufficient GitHub Actions token permissions",
            ),
        ]

        for pattern, description in workflow_permission_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                return Diagnosis(
                    failure_type=FailureType.BUILD_CONFIG,
                    confidence=0.9,
                    root_cause=description,
                    is_auto_fixable=True,
                    suggested_fix=self._build_build_config_suggested_fix(
                        description=description,
                        missing_vars=[],
                        misconfiguration_kind="workflow_permission",
                    ),
                    diagnosis_source=DiagnosisSource.PATTERN,
                    error_details=self._build_classification_details(
                        family=FailureType.BUILD_CONFIG,
                        pattern=pattern,
                        signal=description,
                        details={
                            "workflow_permissions_fix": True,
                            "misconfiguration_kind": "workflow_permission",
                            "config_file": ".github/workflows/ci.yml",
                            "permissions": {
                                "contents": "write",
                                "pull-requests": "write",
                            },
                        },
                    ),
                )

        config_patterns = [
            (r"env.*not.*set", "Environment variable not set"),
            (r"secret.*not.*found", "Secret not configured"),
            (r"secret.*not.*configured", "Secret not configured"),
            (r"none of the following secrets?\s+are\s+set", "Secret not configured"),
            (r"requires?.*secret.*configured", "Secret not configured"),
            (r"permission.*denied", "Permission denied"),
            (r"file.*not.*found", "Required file not found"),
            (r"(?:api|rate)\s*limit(?:ed)?", "External API rate limit reached"),
            (r"http\s*403.*rate", "External API rate limit reached"),
            (r"runner.*environment", "CI runner environment issue"),
            (r"disk\s+space", "Runner disk space exhausted"),
            (r"resource temporarily unavailable", "Transient infrastructure resource issue"),
        ]

        for pattern, description in config_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                # Try to extract missing env vars/secrets from common message formats.
                missing_vars: list[str] = []
                for env_var in re.findall(
                    r"(?:env(?:ironment)?(?:\s+variable)?|variable|secret)[:\s]+['\"]?([A-Z_][A-Z0-9_]*)",
                    error_text,
                    flags=re.IGNORECASE,
                ):
                    if env_var.upper() != env_var:
                        continue
                    if env_var not in missing_vars:
                        missing_vars.append(env_var)

                list_match = re.search(
                    r"none of the following secrets?\s+are\s+set:\s*([A-Z0-9_, ]+)",
                    error_text,
                    flags=re.IGNORECASE,
                )
                if list_match:
                    for env_var in re.split(r"[,\s]+", list_match.group(1).strip()):
                        if (
                            env_var
                            and re.fullmatch(r"[A-Z_][A-Z0-9_]*", env_var)
                            and env_var not in missing_vars
                        ):
                            missing_vars.append(env_var)
                misconfiguration_kind = self._classify_build_config_kind(description, missing_vars)

                return Diagnosis(
                    failure_type=FailureType.BUILD_CONFIG,
                    confidence=0.75,
                    root_cause=description,
                    is_auto_fixable=False,
                    suggested_fix=self._build_build_config_suggested_fix(
                        description=description,
                        missing_vars=missing_vars,
                        misconfiguration_kind=misconfiguration_kind,
                    ),
                    diagnosis_source=DiagnosisSource.PATTERN,
                    error_details=self._build_classification_details(
                        family=FailureType.BUILD_CONFIG,
                        pattern=pattern,
                        signal=description,
                        details={
                            "missing_env_vars": missing_vars,
                            "misconfiguration_kind": misconfiguration_kind,
                            "config_file": self._extract_config_file(error_text),
                            "config_error": description,
                        },
                    ),
                )

        return None

    def _build_dependency_suggested_fix(
        self,
        *,
        package_manager: str,
        package_name: str,
        description: str,
    ) -> str:
        """Build a dependency fix suggestion from the matched package context."""
        normalized_manager = package_manager.strip().lower()
        normalized_package = package_name.strip()
        normalized_description = description.lower()
        is_version_conflict = any(
            marker in normalized_description
            for marker in (
                "conflict",
                "resolve",
                "resolution",
                "eresolve",
                "peer dep",
                "peer dependency",
                "unable to resolve dependency tree",
            )
        )

        if normalized_manager == "npm":
            if normalized_package:
                if is_version_conflict:
                    return (
                        f"Update `{normalized_package}` in package.json to a compatible version and "
                        "refresh the lockfile."
                    )
                return f"Add `{normalized_package}` to package.json and refresh the lockfile."
            return "Update package.json dependencies and refresh the lockfile."

        if normalized_manager in {"pip", "uv", "python"}:
            if normalized_package:
                if is_version_conflict:
                    return (
                        f"Update Python dependency `{normalized_package}` in pyproject.toml or "
                        "requirements.txt to a compatible version and reinstall dependencies."
                    )
                return (
                    f"Add Python dependency `{normalized_package}` in pyproject.toml or "
                    "requirements.txt and reinstall dependencies."
                )
            if is_version_conflict:
                return "Update the dependency version constraint to a compatible release and reinstall."
            return "Add the missing dependency to the project manifest and reinstall dependencies."

        if normalized_manager == "docker":
            if normalized_package:
                return (
                    f"Update the referenced image or package `{normalized_package}` to one that exists "
                    "in the configured registry and re-run the workflow."
                )
            return "Update the referenced container image or registry path and re-run the workflow."

        if normalized_package:
            return f"Install or restore the missing package/resource `{normalized_package}` and re-run the workflow."
        if is_version_conflict:
            return "Update the conflicting dependency or package version to a compatible release and re-run the workflow."
        return "Install or restore the missing package/resource and re-run the workflow."

    def _build_classification_details(
        self,
        *,
        family: FailureType,
        pattern: str,
        signal: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Attach transparent classification metadata for operator trust surfaces."""
        payload = dict(details or {})
        payload["classification_signal"] = signal
        payload["classification_family"] = family.value
        payload["classification_pattern"] = pattern
        return payload

    @staticmethod
    def _infer_dependency_manifest_file(package_manager: str, error_text: str) -> str:
        normalized_manager = package_manager.strip().lower()
        lowered = error_text.lower()
        if normalized_manager == "npm":
            return "package.json"
        if normalized_manager == "pip":
            return "requirements.txt" if "requirements.txt" in lowered else "pyproject.toml"
        if normalized_manager == "uv":
            return "pyproject.toml"
        return ""

    @staticmethod
    def _classify_dependency_resolution_kind(
        *,
        description: str,
        package_manager: str,
        error_text: str,
    ) -> str:
        lowered_description = description.lower()
        lowered_error = error_text.lower()
        if any(marker in lowered_description for marker in ("conflict", "resolution", "resolve")):
            return "version_conflict"
        if package_manager == "docker":
            if "pull access denied" in lowered_error or "repository does not exist" in lowered_error:
                return "image_pull"
            return "registry_access"
        return "missing"

    def _build_lint_suggested_fix(
        self,
        *,
        linter: str,
        is_missing_config: bool,
        missing_file: str,
    ) -> str:
        if is_missing_config and missing_file:
            return f"Add `{missing_file}` so {linter} can load its required configuration."
        autofix_command = lint_autofix_command(linter)
        if autofix_command:
            return f"Run `{autofix_command}` locally and commit the resulting lint fixes."
        return f"Fix the reported {linter} violations and re-run the workflow."

    @staticmethod
    def _extract_lint_rule_ids(error_text: str, linter: str) -> list[str]:
        if linter != "mypy":
            return []
        rule_ids: list[str] = []
        for match in re.findall(r"\[([a-z0-9-]+)\]", error_text, flags=re.IGNORECASE):
            value = str(match).strip().lower()
            if value and value not in rule_ids:
                rule_ids.append(value)
        return rule_ids

    def _extract_failed_tests(self, error_text: str) -> list[str]:
        matches: list[str] = []
        patterns = [
            r"pytest\s+FAILED\s+([^\s]+)",
            r"FAIL\s+([^\s]+\.(?:test|spec)\.[^\s:]+(?:::[^\s]+)?)",
            r"AssertionError.*?([A-Za-z0-9_./:-]+::[A-Za-z0-9_./:-]+)",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, error_text, flags=re.IGNORECASE):
                value = str(match).strip().rstrip(".,:")
                if value and value not in matches:
                    matches.append(value)
        return matches

    def _extract_collection_targets(self, error_text: str) -> list[str]:
        targets: list[str] = []
        for match in re.findall(r"ERROR collecting\s+([^\s:]+)", error_text, flags=re.IGNORECASE):
            value = str(match).strip().rstrip(".,:")
            if value and value not in targets:
                targets.append(value)
        return targets

    def _suspected_files_from_tests(self, failed_tests: list[str]) -> list[str]:
        files: list[str] = []
        for test_name in failed_tests:
            candidate = test_name.split("::", 1)[0].strip()
            if candidate and candidate not in files:
                files.append(candidate)
        return files

    @staticmethod
    def _extract_test_errors(error_text: str, failed_tests: list[str]) -> dict[str, str]:
        lines = [line.strip() for line in error_text.splitlines() if line.strip()]
        interesting = [
            line
            for line in lines
            if "assertionerror" in line.lower()
            or line.startswith("E ")
            or "expected" in line.lower()
            or "syntaxerror" in line.lower()
            or "importerror" in line.lower()
            or "modulenotfounderror" in line.lower()
            or "error collecting" in line.lower()
            or "traceback" in line.lower()
        ]
        if not interesting:
            interesting = lines[:1]
        if not interesting:
            return {}

        summary = interesting[0][:240]
        if not failed_tests:
            return {"summary": summary}
        return dict.fromkeys(failed_tests[:5], summary)

    def _build_test_suggested_fix(
        self,
        *,
        framework: str,
        failed_tests: list[str],
        is_flaky: bool,
        failure_scope: str = "",
        suspected_files: list[str] | None = None,
    ) -> str:
        if is_flaky:
            if failed_tests:
                return (
                    f"Stabilize flaky {framework} test(s) {', '.join(f'`{name}`' for name in failed_tests[:3])} "
                    "and remove timing or order dependence before re-running the workflow."
                )
            return "Stabilize the flaky test path and remove timing or order dependence before re-running the workflow."
        if failure_scope == "collection":
            file_refs = [str(item).strip() for item in (suspected_files or []) if str(item).strip()]
            if file_refs:
                rendered = ", ".join(f"`{name}`" for name in file_refs[:3])
                return (
                    f"Fix the import or syntax error blocking {framework} collection for {rendered}, "
                    "then re-run the workflow."
                )
            return (
                f"Fix the import or syntax error blocking {framework} test collection and re-run the workflow."
            )
        if failed_tests:
            return (
                f"Run {framework} locally for {', '.join(f'`{name}`' for name in failed_tests[:3])}, "
                "fix the failing assertions, and re-run the workflow."
            )
        return f"Run the failing {framework} tests locally, fix the failure, and re-run the workflow."

    def _extract_timeout_minutes(self, error_text: str) -> int:
        patterns = [
            r"exceeded.*time.*limit\s+of\s+(\d+)\s+minutes?",
            r"timeout-minutes:\s*(\d+)",
            r"timed?\s*out.*after\s+(\d+)\s+minutes?",
        ]
        for pattern in patterns:
            match = re.search(pattern, error_text, flags=re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    return 0
        return 0

    @staticmethod
    def _extract_timed_out_step(error_text: str) -> str:
        patterns = [
            r"step ['\"]([^'\"]+)['\"]",
            r"Step:\s*([^\n]+)",
            r"during (?:the )?step ['\"]?([^\n'\":]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, error_text, flags=re.IGNORECASE)
            if match:
                return str(match.group(1)).strip().rstrip(".,:")
        return ""

    def _detect_timeout_resource_signal(self, error_text: str) -> str:
        text = error_text.lower()
        if "no space left on device" in text or "disk space" in text:
            return "disk"
        if (
            "oom" in text
            or "out of memory" in text
            or ("signal 9" in text and "memory" in text)
        ):
            return "memory"
        if "network" in text or "connection reset" in text:
            return "network"
        return "unknown"

    def _detect_timeout_fix_kind(self, description: str, resource_signal: str) -> str:
        if resource_signal == "disk":
            return "runner_capacity"
        if resource_signal == "memory":
            return "runner_capacity"
        if "time limit" in description.lower() or "deadline" in description.lower():
            return "increase_timeout"
        return "optimize_step"

    def _build_timeout_suggested_fix(
        self,
        *,
        description: str,
        timeout_minutes: int,
        suggested_timeout: int,
        resource_signal: str,
    ) -> str:
        if resource_signal == "disk":
            return "Free runner disk space or reduce cache, artifact, and workspace usage before re-running the workflow."
        if resource_signal == "memory":
            return "Inspect memory pressure, reduce peak memory usage, or use a larger runner before re-running the workflow."
        if timeout_minutes > 0 and suggested_timeout > timeout_minutes:
            return (
                f"Increase `timeout-minutes` above {timeout_minutes} minutes "
                f"(for example `{suggested_timeout}`) or optimize the slow step before re-running the workflow."
            )
        if "deadline" in description.lower():
            return "Increase the workflow timeout or reduce the slow operation so the job completes before the deadline."
        return "Optimize the slow operation or increase the workflow timeout before re-running the job."

    def _classify_build_config_kind(self, description: str, missing_vars: list[str]) -> str:
        lowered = description.lower()
        if "secret" in lowered:
            return "secret"
        if "environment variable" in lowered or missing_vars:
            return "env_var"
        if "permission denied" in lowered:
            return "runner_env"
        if "file not found" in lowered:
            return "file_path"
        if "rate limit" in lowered:
            return "rate_limit"
        if "runner" in lowered:
            return "runner_env"
        return "env_var"

    def _extract_config_file(self, error_text: str) -> str:
        for ref in self._extract_file_references(error_text):
            if ref.startswith(".github/workflows/"):
                return ref
        refs = self._extract_file_references(error_text)
        return refs[0] if refs else ""

    def _build_build_config_suggested_fix(
        self,
        *,
        description: str,
        missing_vars: list[str],
        misconfiguration_kind: str,
    ) -> str:
        if misconfiguration_kind == "workflow_permission":
            return "Add a minimal workflow `permissions` block so `GITHUB_TOKEN` can perform the required action."
        if missing_vars and misconfiguration_kind == "secret":
            rendered = ", ".join(f"`{name}`" for name in missing_vars[:5])
            return f"Configure the missing repository or environment secret(s): {rendered}."
        if missing_vars:
            rendered = ", ".join(f"`{name}`" for name in missing_vars[:5])
            return f"Configure the missing CI variable(s) or secret(s): {rendered}."
        if misconfiguration_kind == "file_path":
            return "Restore the required file or correct the configured path before re-running the workflow."
        if misconfiguration_kind == "rate_limit":
            return "Reduce request volume, add retry/backoff, or use credentials with a higher API limit before retrying."
        if "permission denied" in description.lower():
            return "Verify file, credential, or runner permissions for the failing command before re-running the workflow."
        if "runner" in description.lower():
            return "Verify the runner environment has the required tools, capacity, and access before re-running the workflow."
        return "Review the build configuration and correct the missing or invalid environment settings."

    def _detect_test_framework(self, error_text: str) -> str:
        """Detect which test framework is being used.

        Args:
            error_text: Error text to analyze

        Returns:
            Detected test framework name
        """
        frameworks = [
            ("pytest", "pytest"),
            ("jest", "jest"),
            ("mocha", "mocha"),
            ("vitest", "vitest"),
            ("unittest", "unittest"),
            ("rspec", "rspec"),
        ]

        for keyword, framework in frameworks:
            if keyword in error_text.lower():
                return framework

        return "unknown"

    def _has_test_context(self, error_text: str) -> bool:
        """Return True when logs include clear test-specific signals."""
        text = error_text.lower()
        markers = (
            "pytest",
            "jest",
            "vitest",
            "mocha",
            "rspec",
            "unittest",
            "error collecting",
            "assertionerror",
            "test suite",
            "tests failed",
            ".test.",
            "::test",
            "failing test",
        )
        return any(marker in text for marker in markers)

    def _prepare_analysis_summary(self, log_analyses: list[LogAnalysis]) -> str:
        """Prepare a summary of log analyses for the agent.

        Args:
            log_analyses: List of log analysis results

        Returns:
            Formatted summary string
        """
        summary_parts = []

        for analysis in log_analyses:
            part = f"""
## Job: {analysis.job_name}

### Summary
{analysis.summary}

### Error Lines (top 20)
{chr(10).join(analysis.error_lines[:20])}

### Key Events
{chr(10).join(analysis.key_events[:10])}
"""
            summary_parts.append(part)

        return "\n---\n".join(summary_parts)

    def _prepare_context_summary(
        self,
        workflow_info: dict[str, Any] | None,
        similar_issues: list[dict[str, Any]],
    ) -> str:
        """Prepare supplemental deterministic context for LLM fallback."""
        if not workflow_info and not similar_issues:
            return "Additional Repository Context: none"

        lines: list[str] = ["Additional Repository Context:"]
        if workflow_info:
            changed_files = workflow_info.get("changed_files")
            if isinstance(changed_files, list) and changed_files:
                lines.append("Changed files in related PR(s):")
                for filename in changed_files[:20]:
                    lines.append(f"- {filename}")

            recent_commits = workflow_info.get("recent_commits")
            if isinstance(recent_commits, list) and recent_commits:
                lines.append("Recent commits around failure:")
                for commit in recent_commits[:5]:
                    if not isinstance(commit, dict):
                        continue
                    sha = str(commit.get("sha", ""))[:8]
                    message = str(commit.get("message", "")).strip()
                    if sha or message:
                        lines.append(f"- {sha} {message}".strip())

        if similar_issues:
            lines.append("Potentially similar historical issues:")
            for issue in similar_issues[:3]:
                number = issue.get("number")
                title = str(issue.get("title", "")).strip()
                url = str(issue.get("html_url", "")).strip()
                lines.append(f"- #{number}: {title} {url}".strip())

        return "\n".join(lines)

    async def _search_similar_issues(
        self,
        log_analyses: list[LogAnalysis],
        workflow_info: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Search repo issues for similar recent failures."""
        if self._github_tools is None or not workflow_info:
            return []

        owner = str(workflow_info.get("owner", "")).strip()
        repo = str(workflow_info.get("repo", "")).strip()
        if not owner or not repo:
            return []

        keywords = self._extract_error_keywords(log_analyses)
        if not keywords:
            return []

        query = "in:title,body " + " ".join(keywords[:4])

        try:
            issues = await self._github_tools.search_issues(
                owner=owner,
                repo=repo,
                query=query,
                state="all",
                per_page=6,
            )
            return [issue for issue in issues if isinstance(issue, dict)]
        except Exception as exc:
            logger.debug("Issue-history search unavailable for %s/%s: %s", owner, repo, exc)
            return []

    @staticmethod
    def _extract_error_keywords(log_analyses: list[LogAnalysis]) -> list[str]:
        """Extract concise search keywords from error lines."""
        stopwords = {
            "error",
            "failed",
            "failure",
            "exception",
            "with",
            "from",
            "that",
            "this",
            "into",
            "while",
            "during",
            "build",
            "test",
            "tests",
            "lint",
            "job",
            "step",
            "module",
            "package",
            "cannot",
            "could",
            "find",
            "not",
            "none",
            "null",
        }

        tokens: list[str] = []
        for analysis in log_analyses:
            for line in analysis.error_lines[:20]:
                for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", line):
                    normalized = token.lower()
                    if normalized in stopwords:
                        continue
                    if normalized not in tokens:
                        tokens.append(normalized)
                    if len(tokens) >= 10:
                        return tokens
        return tokens

    def _apply_historical_issue_signal(
        self,
        diagnosis: Diagnosis,
        issue: dict[str, Any],
    ) -> Diagnosis:
        """Boost confidence when historical issue evidence aligns with diagnosis."""
        issue_text = (
            str(issue.get("title", "")).lower()
            + "\n"
            + str(issue.get("body", "")).lower()
        )

        keywords_by_failure_type: dict[FailureType, tuple[str, ...]] = {
            FailureType.DEPENDENCY: ("dependency", "module", "package", "install", "resolve"),
            FailureType.TEST: ("test", "assert", "flake", "flaky", "pytest", "jest"),
            FailureType.LINT: ("lint", "eslint", "prettier", "ruff", "flake8"),
            FailureType.BUILD_CONFIG: ("workflow", "permission", "secret", "config", "runner"),
            FailureType.TIMEOUT: ("timeout", "timed out", "slow", "hanging"),
            FailureType.UNKNOWN: (),
        }

        matches = sum(
            1 for keyword in keywords_by_failure_type.get(diagnosis.failure_type, ()) if keyword in issue_text
        )
        if matches == 0:
            return diagnosis

        issue_number = issue.get("number")
        issue_url = issue.get("html_url")
        diagnosis.confidence = min(0.95, diagnosis.confidence + 0.05 + (0.02 * min(matches, 3)))
        diagnosis.root_cause = (
            f"{diagnosis.root_cause} (similar historical issue #{issue_number})"
            if issue_number
            else diagnosis.root_cause
        )
        diagnosis.error_details["similar_issue_number"] = issue_number
        diagnosis.error_details["similar_issue_url"] = issue_url
        return diagnosis

    def _apply_changed_file_correlation(
        self,
        diagnosis: Diagnosis | None,
        log_analyses: list[LogAnalysis],
        workflow_info: dict[str, Any] | None,
    ) -> Diagnosis | None:
        """Correlate changed files with log references to improve confidence."""
        if diagnosis is None or not workflow_info:
            return diagnosis

        changed_files_raw = workflow_info.get("changed_files")
        if not isinstance(changed_files_raw, list) or not changed_files_raw:
            return diagnosis

        changed_files = [str(path).strip() for path in changed_files_raw if str(path).strip()]
        if not changed_files:
            return diagnosis

        error_text = "\n".join(line for analysis in log_analyses for line in analysis.error_lines)
        referenced_files = set(self._extract_file_references(error_text))
        changed_basenames = {path.split("/")[-1]: path for path in changed_files}

        overlaps: list[str] = []
        for ref in referenced_files:
            if ref in changed_files:
                overlaps.append(ref)
                continue
            basename = ref.split("/")[-1]
            if basename in changed_basenames:
                overlaps.append(changed_basenames[basename])

        if overlaps:
            unique_overlaps = sorted(set(overlaps))
            diagnosis.affected_files = sorted({*diagnosis.affected_files, *unique_overlaps})[:20]
            diagnosis.error_details["changed_file_overlap"] = unique_overlaps
            diagnosis.confidence = min(0.95, diagnosis.confidence + 0.06)
            return diagnosis

        # Keep context hints for operator visibility even when no direct overlap is found.
        diagnosis.error_details["changed_files_considered"] = changed_files[:20]
        return diagnosis

    @staticmethod
    def _extract_file_references(text: str) -> list[str]:
        """Extract likely file-path tokens from error text."""
        path_pattern = re.compile(
            r"([A-Za-z0-9_./-]+\.(?:py|pyi|js|jsx|ts|tsx|json|ya?ml|toml|ini|cfg|md|sh|go|rs|java|kt|cs))"
        )
        refs: list[str] = []
        for match in path_pattern.findall(text):
            if match not in refs:
                refs.append(match)
        return refs

    @staticmethod
    def _extract_json_candidates(text: str) -> list[str]:
        """Extract candidate JSON object strings from *text* using brace-balancing.

        The greedy regex ``r"\\{[\\s\\S]*\\}"`` fails when the LLM wraps JSON in
        markdown fences or appends commentary containing extra braces.  Instead we
        walk through the text tracking brace depth and yield every balanced
        ``{ ... }`` substring, longest-first. ``json.loads`` is attempted on each
        candidate so only syntactically valid JSON survives.
        """
        candidates: list[str] = []
        i = 0
        while i < len(text):
            if text[i] == "{":
                depth = 0
                in_string = False
                escape = False
                for j in range(i, len(text)):
                    ch = text[j]
                    if escape:
                        escape = False
                        continue
                    if ch == "\\":
                        escape = True
                        continue
                    if ch == '"' and not escape:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidates.append(text[i : j + 1])
                            break
            i += 1
        # Prefer longer candidates (the outermost balanced object is usually correct).
        candidates.sort(key=len, reverse=True)
        return candidates

    @staticmethod
    def _required_llm_error_details_keys(failure_type: FailureType) -> tuple[str, ...]:
        template = LLM_ERROR_DETAILS_SCHEMA.get(failure_type, LLM_ERROR_DETAILS_SCHEMA[FailureType.UNKNOWN])
        return tuple(template.keys())

    def _validate_llm_diagnosis_payload(
        self,
        data: dict[str, Any],
        failure_type: FailureType,
    ) -> tuple[bool, str]:
        """Validate that an LLM diagnosis payload matches the structured contract."""
        missing_top_level = [field for field in LLM_REQUIRED_TOP_LEVEL_FIELDS if field not in data]
        if missing_top_level:
            return False, f"missing top-level field(s): {', '.join(missing_top_level)}"

        confidence_raw = data.get("confidence")
        if confidence_raw is None:
            return False, "confidence is missing"
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            return False, "confidence is not numeric"
        if not 0.0 <= confidence <= 1.0:
            return False, "confidence is outside 0.0-1.0"

        if not isinstance(data.get("root_cause"), str) or not str(data.get("root_cause")).strip():
            return False, "root_cause must be a non-empty string"
        if not isinstance(data.get("suggested_fix"), str):
            return False, "suggested_fix must be a string"
        if not isinstance(data.get("is_auto_fixable"), bool):
            return False, "is_auto_fixable must be a boolean"

        affected_files = data.get("affected_files")
        if not isinstance(affected_files, list) or any(not isinstance(item, str) for item in affected_files):
            return False, "affected_files must be a list of strings"

        error_details = data.get("error_details")
        if not isinstance(error_details, dict):
            return False, "error_details must be an object"

        missing_error_detail_keys = [
            key
            for key in self._required_llm_error_details_keys(failure_type)
            if key not in error_details
        ]
        if missing_error_detail_keys:
            return False, f"missing error_details field(s): {', '.join(missing_error_detail_keys)}"

        return True, ""

    @staticmethod
    def _record_llm_payload_rejection(
        diagnosis: Diagnosis,
        *,
        reason: str,
        candidate_count: int,
    ) -> Diagnosis:
        """Annotate a fallback diagnosis with LLM payload rejection context."""
        details = dict(diagnosis.error_details or {})
        details["llm_payload_rejected"] = True
        details["llm_payload_rejection_reason"] = reason
        details["llm_payload_candidate_count"] = candidate_count
        return diagnosis.model_copy(
            update={
                "error_details": details,
                "llm_rejection": LLMDiagnosisRejection(
                    rejected=True,
                    reason=reason,
                    candidate_count=candidate_count,
                ),
            }
        )

    @staticmethod
    def _extract_diagnosis_json_candidates(raw_candidates: list[str]) -> list[dict[str, Any]]:
        """Return parsed diagnosis-shaped JSON objects from brace-balanced candidates."""
        parsed_candidates: list[dict[str, Any]] = []
        for candidate in raw_candidates:
            try:
                data = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(data, dict) and "failure_type" in data:
                parsed_candidates.append(data)
        return parsed_candidates

    def _parse_diagnosis_response(
        self,
        response_text: str,
        fallback: Diagnosis | None,
    ) -> Diagnosis:
        """Parse the diagnosis response from the agent.

        Args:
            response_text: Response text from the agent
            fallback: Fallback diagnosis if parsing fails

        Returns:
            Parsed diagnosis
        """
        failure_type_map = {
            "dependency": FailureType.DEPENDENCY,
            "test": FailureType.TEST,
            "lint": FailureType.LINT,
            "build_config": FailureType.BUILD_CONFIG,
            "timeout": FailureType.TIMEOUT,
        }

        # Strip markdown code fences that some LLMs wrap around JSON.
        cleaned = re.sub(r"```(?:json)?\s*", "", response_text)
        cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
        raw_candidates = self._extract_json_candidates(cleaned)
        candidates = self._extract_diagnosis_json_candidates(raw_candidates)
        rejection_reasons: list[str] = []

        for data in candidates:
            failure_type_str = str(data.get("failure_type", "unknown")).lower()
            failure_type = failure_type_map.get(failure_type_str, FailureType.UNKNOWN)
            is_valid, reason = self._validate_llm_diagnosis_payload(data, failure_type)
            if not is_valid:
                logger.warning(
                    "Rejected LLM diagnosis payload for %s: %s",
                    failure_type.value,
                    reason,
                )
                rejection_reasons.append(f"{failure_type.value}: {reason}")
                continue

            return Diagnosis(
                failure_type=failure_type,
                confidence=float(data.get("confidence", 0.5)),
                root_cause=data.get("root_cause", "Unknown"),
                affected_files=data.get("affected_files", []),
                is_auto_fixable=bool(data.get("is_auto_fixable", False)),
                suggested_fix=data.get("suggested_fix", ""),
                error_details=data.get("error_details", {}),
                diagnosis_source=DiagnosisSource.LLM,
            )

        logger.warning(
            "Failed to extract valid diagnosis JSON from agent response (len=%d)",
            len(response_text),
        )
        rejection_reason = (
            rejection_reasons[0]
            if rejection_reasons
            else "No valid structured diagnosis JSON candidate was found"
        )

        # Return fallback or create unknown diagnosis
        if fallback:
            return self._record_llm_payload_rejection(
                fallback,
                reason=rejection_reason,
                candidate_count=len(candidates),
            )

        return self._record_llm_payload_rejection(
            Diagnosis(
                failure_type=FailureType.UNKNOWN,
                confidence=0.3,
                root_cause="Could not determine root cause",
                is_auto_fixable=False,
                diagnosis_source=DiagnosisSource.LLM,
            ),
            reason=rejection_reason,
            candidate_count=len(candidates),
        )

    @staticmethod
    def _with_source(diagnosis: Diagnosis, source: DiagnosisSource) -> Diagnosis:
        """Ensure diagnosis source is set for observability/UI trust surface."""
        if diagnosis.diagnosis_source is not None:
            return diagnosis
        return diagnosis.model_copy(update={"diagnosis_source": source})
