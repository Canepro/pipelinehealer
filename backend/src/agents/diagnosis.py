"""Diagnosis Agent for root cause analysis of CI/CD failures."""

import json
import logging
import re
from typing import Any

from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import Diagnosis, ExternalDiagnostic, FailureType, LogAnalysis
from ..tools.github_tools import GitHubTools
from .base import create_cloud_agent, get_agent_prompt

logger = logging.getLogger(__name__)


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
                settings=self._settings,
            )

        return self._agent

    def refresh_runtime_settings(self) -> None:
        """Refresh mutable settings and rebuild cloud client on next call."""
        self._settings = get_settings()
        self._agent = None

    async def diagnose(
        self,
        log_analyses: list[LogAnalysis],
        workflow_info: dict[str, Any] | None = None,
        external_diagnostics: list[ExternalDiagnostic] | None = None,
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
            return Diagnosis(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                root_cause="No log analyses provided",
                is_auto_fixable=False,
            )

        # First, try pattern-based detection for common cases
        pattern_diagnosis = self._pattern_based_diagnosis(log_analyses)
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

        if pattern_diagnosis and pattern_diagnosis.confidence >= 0.8:
            logger.info(f"Pattern-based diagnosis: {pattern_diagnosis.failure_type}")
            logger.debug(
                "[debug-mode] Pattern matched: type=%s confidence=%.2f root_cause=%s",
                pattern_diagnosis.failure_type.value,
                pattern_diagnosis.confidence,
                pattern_diagnosis.root_cause[:200] if pattern_diagnosis.root_cause else "N/A",
            )
            return pattern_diagnosis

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

        prompt = f"""Analyze the following CI/CD failure and provide a diagnosis.

{analysis_summary}

{context_summary}

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
            (r"failed to resolve source metadata for", "Docker base image not found"),
            (r"manifest.*not found", "Docker image manifest not found"),
            (r"(?:pull access denied|repository does not exist)", "Docker image pull failed"),
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
        flaky_patterns = [
            (r"(?:flaky|intermittent)\s+test", "Flaky test behavior detected"),
            (r"(?:passed|succeeded)\s+on\s+retry", "Test passed on retry (flaky behavior)"),
            (r"rerun.*(?:passed|succeeded)", "Rerun succeeded after prior test failure"),
        ]
        for pattern, description in flaky_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                return Diagnosis(
                    failure_type=FailureType.TEST,
                    confidence=0.78,
                    root_cause=description,
                    is_auto_fixable=False,
                    suggested_fix="Stabilize flaky test and remove timing/order dependence",
                    error_details={
                        "is_flaky": True,
                        "test_framework": self._detect_test_framework(error_text),
                    },
                )

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
            (r"timed?\s*out(?!\s*(?:to|=|:)\s*\d)", "Operation timed out"),
            (r"exceeded.*time.*limit", "Time limit exceeded"),
            (r"killed.*signal.*9", "Process killed (likely OOM or timeout)"),
            (r"no space left on device", "Runner disk space exhausted"),
            (r"deadline\s+exceeded", "Deadline exceeded"),
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
            (r"(?:api|rate)\s*limit(?:ed)?", "External API rate limit reached"),
            (r"http\s*403.*rate", "External API rate limit reached"),
            (r"runner.*environment", "CI runner environment issue"),
            (r"disk\s+space", "Runner disk space exhausted"),
            (r"resource temporarily unavailable", "Transient infrastructure resource issue"),
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

        for candidate in self._extract_json_candidates(cleaned):
            try:
                data = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue

            # Must look like a diagnosis object (at minimum a failure_type key).
            if not isinstance(data, dict) or "failure_type" not in data:
                continue

            failure_type_str = str(data.get("failure_type", "unknown")).lower()
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

        logger.warning(
            "Failed to extract valid diagnosis JSON from agent response (len=%d)",
            len(response_text),
        )

        # Return fallback or create unknown diagnosis
        if fallback:
            return fallback

        return Diagnosis(
            failure_type=FailureType.UNKNOWN,
            confidence=0.3,
            root_cause="Could not determine root cause",
            is_auto_fixable=False,
        )
