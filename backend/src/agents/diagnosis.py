"""Diagnosis Agent for root cause analysis of CI/CD failures."""

import json
import logging
import re
from typing import Any

from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import Diagnosis, FailureType, LogAnalysis
from .base import create_cloud_agent, get_agent_prompt

logger = logging.getLogger(__name__)


class DiagnosisAgent:
    """Agent for diagnosing the root cause of CI/CD failures.

    This agent analyzes log analysis results and determines
    the failure type and root cause.
    """

    def __init__(
        self,
        azure_credential: DefaultAzureCredential | None = None,
    ):
        """Initialize the Diagnosis Agent.

        Args:
            azure_credential: Azure credential for OpenAI
        """
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
                settings=self._settings,
            )

        return self._agent

    async def diagnose(
        self,
        log_analyses: list[LogAnalysis],
        workflow_info: dict[str, Any] | None = None,
    ) -> Diagnosis:
        """Diagnose the root cause of a failure based on log analyses.

        Args:
            log_analyses: List of log analysis results
            workflow_info: Additional workflow information

        Returns:
            Diagnosis result
        """
        logger.info(f"Diagnosing failure from {len(log_analyses)} log analyses")

        if not log_analyses:
            return Diagnosis(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                root_cause="No log analyses provided",
                is_auto_fixable=False,
            )

        # First, try pattern-based detection for common cases
        pattern_diagnosis = self._pattern_based_diagnosis(log_analyses)

        if pattern_diagnosis and pattern_diagnosis.confidence >= 0.8:
            logger.info(f"Pattern-based diagnosis: {pattern_diagnosis.failure_type}")
            logger.debug(
                "[debug-mode] Pattern matched: type=%s confidence=%.2f root_cause=%s",
                pattern_diagnosis.failure_type.value,
                pattern_diagnosis.confidence,
                pattern_diagnosis.root_cause[:200] if pattern_diagnosis.root_cause else "N/A",
            )
            return pattern_diagnosis

        # Use the agent for more complex analysis
        agent = await self._get_agent()

        # Prepare the analysis summary for the agent
        analysis_summary = self._prepare_analysis_summary(log_analyses)

        prompt = f"""Analyze the following CI/CD failure and provide a diagnosis.

{analysis_summary}

Provide your diagnosis in the following JSON format:
{{
    "failure_type": "dependency|test|lint|build_config|timeout|unknown",
    "confidence": 0.0-1.0,
    "root_cause": "Clear explanation of what went wrong",
    "affected_files": ["list", "of", "files"],
    "is_auto_fixable": true/false,
    "suggested_fix": "High-level suggestion",
    "error_details": {{
        "additional": "context-specific details"
    }}
}}

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
                return pattern_diagnosis

            return Diagnosis(
                failure_type=FailureType.UNKNOWN,
                confidence=0.3,
                root_cause=f"Diagnosis failed: {e}",
                is_auto_fixable=False,
            )

        return diagnosis

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
        ]

        for pattern, description in dep_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                # Extract package name if possible
                # Allow scoped names and path segments (e.g. "@scope/pkg", "lodash/fp").
                package_name = ""
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
                package_manager = "npm" if (
                    "npm" in pattern
                    or "npm" in error_text.lower()
                    or "bun" in error_text.lower()
                    or "Cannot find module" in pattern
                ) else "pip"

                return Diagnosis(
                    failure_type=FailureType.DEPENDENCY,
                    confidence=0.85,
                    root_cause=description,
                    is_auto_fixable=True,
                    suggested_fix="Update or install the missing dependency",
                    error_details={
                        "package_name": package_name,
                        "package_manager": package_manager,
                    },
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
        ]

        for pattern, linter, description, is_missing_config in lint_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                return Diagnosis(
                    failure_type=FailureType.LINT,
                    confidence=0.9,
                    root_cause=description,
                    is_auto_fixable=True,
                    suggested_fix="Add eslint.config.js (flat config)" if is_missing_config else f"Run {linter} with --fix flag",
                    error_details={
                        "linter": linter,
                        "missing_file": "eslint.config.js" if is_missing_config else "",
                        "violations": [],
                    },
                )

        # Check for test failures
        test_patterns = [
            (r"FAIL\s+.*\.test\.", "Test suite failed"),
            (r"AssertionError", "Assertion failed in test"),
            (r"pytest.*FAILED", "pytest test failed"),
            (r"jest.*FAIL", "Jest test failed"),
            (r"\d+ failing", "Tests failing"),
        ]

        for pattern, description in test_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                # Check if it might be flaky
                is_flaky = "timeout" in error_text.lower() or "intermittent" in error_text.lower()

                return Diagnosis(
                    failure_type=FailureType.TEST,
                    confidence=0.85,
                    root_cause=description,
                    is_auto_fixable=False,
                    suggested_fix="Review and fix the failing tests",
                    error_details={
                        "is_flaky": is_flaky,
                        "test_framework": self._detect_test_framework(error_text),
                    },
                )

        # Check for timeout issues
        timeout_patterns = [
            (r"timeout", "Operation timed out"),
            (r"exceeded.*time.*limit", "Time limit exceeded"),
            (r"killed.*signal.*9", "Process killed (likely OOM or timeout)"),
        ]

        for pattern, description in timeout_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                return Diagnosis(
                    failure_type=FailureType.TIMEOUT,
                    confidence=0.8,
                    root_cause=description,
                    is_auto_fixable=False,
                    suggested_fix="Increase timeout or optimize the slow operation",
                    error_details={},
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
                    suggested_fix="Add minimal `permissions` block to the workflow",
                    error_details={
                        "workflow_permissions_fix": True,
                        "permissions": {
                            "contents": "write",
                            "pull-requests": "write",
                        },
                    },
                )

        config_patterns = [
            (r"env.*not.*set", "Environment variable not set"),
            (r"secret.*not.*found", "Secret not configured"),
            (r"permission.*denied", "Permission denied"),
            (r"file.*not.*found", "Required file not found"),
        ]

        for pattern, description in config_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                # Try to extract missing env vars
                env_var_match = re.search(
                    r"(?:env|variable|secret)[:\s]+['\"]?([A-Z_]+)", error_text
                )
                missing_vars = [env_var_match.group(1)] if env_var_match else []

                return Diagnosis(
                    failure_type=FailureType.BUILD_CONFIG,
                    confidence=0.75,
                    root_cause=description,
                    is_auto_fixable=False,
                    suggested_fix="Check repository secrets and environment configuration",
                    error_details={
                        "missing_env_vars": missing_vars,
                    },
                )

        return None

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
        # Try to extract JSON from the response
        json_match = re.search(r"\{[\s\S]*\}", response_text)

        if json_match:
            try:
                data = json.loads(json_match.group())

                # Map failure type string to enum
                failure_type_str = data.get("failure_type", "unknown").lower()
                failure_type_map = {
                    "dependency": FailureType.DEPENDENCY,
                    "test": FailureType.TEST,
                    "lint": FailureType.LINT,
                    "build_config": FailureType.BUILD_CONFIG,
                    "timeout": FailureType.TIMEOUT,
                }
                failure_type = failure_type_map.get(failure_type_str, FailureType.UNKNOWN)

                return Diagnosis(
                    failure_type=failure_type,
                    confidence=float(data.get("confidence", 0.5)),
                    root_cause=data.get("root_cause", "Unknown"),
                    affected_files=data.get("affected_files", []),
                    is_auto_fixable=bool(data.get("is_auto_fixable", False)),
                    suggested_fix=data.get("suggested_fix", ""),
                    error_details=data.get("error_details", {}),
                )
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Failed to parse agent response JSON: {e}")

        # Return fallback or create unknown diagnosis
        if fallback:
            return fallback

        return Diagnosis(
            failure_type=FailureType.UNKNOWN,
            confidence=0.3,
            root_cause="Could not determine root cause",
            is_auto_fixable=False,
        )
