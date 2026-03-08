"""Fix generators for different failure types."""

import json
import logging
import re
from enum import StrEnum
from typing import Any

from ..models import Diagnosis, FailureType, RemediationAction, RemediationPlan
from .lint_autofix import lint_autofix_command

logger = logging.getLogger(__name__)


class NotAutoApplyReason(StrEnum):
    """Machine-readable reasons for review-only issue output."""

    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    AMBIGUOUS_RESOLUTION = "AMBIGUOUS_RESOLUTION"
    OUTSIDE_ALLOWED_FILES = "OUTSIDE_ALLOWED_FILES"
    REQUIRES_ENV_CONTEXT = "REQUIRES_ENV_CONTEXT"
    SAFETY_BOUND = "SAFETY_BOUND"


class FixGenerators:
    """Generators for creating fixes based on diagnosed failures."""

    def __init__(self, heal_mode: str = "safe") -> None:
        """Initialize fix generators."""
        self._max_proposed_fix_chars = 3000
        self._proposed_fix_allowed_exact = {
            "package.json",
            "requirements.txt",
            "eslint.config.js",
            "eslint.config.mjs",
            ".github/workflows/ci.yml",
        }
        self._proposed_fix_allowed_prefixes = (
            ".github/workflows/",
            ".eslintrc",
            ".prettierrc",
            "prettier.config.",
            "pyproject.toml",
        )
        self._heal_mode = ""
        self._is_demo_mode = False
        self._is_debug_mode = False
        self.set_heal_mode(heal_mode)
        self._generators = {
            FailureType.DEPENDENCY: self._generate_dependency_fix,
            FailureType.LINT: self._generate_lint_fix,
            FailureType.TEST: self._generate_test_fix,
            FailureType.BUILD_CONFIG: self._generate_build_config_fix,
            FailureType.TIMEOUT: self._generate_timeout_fix,
        }

    def set_heal_mode(self, heal_mode: str) -> None:
        """Update healing mode without recreating the generator object."""
        normalized = (heal_mode or "safe").strip().lower()
        self._heal_mode = (
            normalized if normalized in {"safe", "demo", "freestyle", "debug"} else "safe"
        )
        # debug behaves like safe for all remediation decisions
        self._is_demo_mode = self._heal_mode in {"demo", "freestyle"}
        self._is_debug_mode = self._heal_mode == "debug"

    async def generate_fix(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate a fix plan based on the diagnosis.

        Args:
            diagnosis: The diagnosis of the failure
            repository_info: Information about the repository

        Returns:
            A remediation plan
        """
        generator = self._generators.get(diagnosis.failure_type)

        if generator is None:
            logger.warning(f"No generator for failure type: {diagnosis.failure_type}")
            return self._generate_issue_only(diagnosis, repository_info)

        try:
            return await generator(diagnosis, repository_info)
        except Exception as e:
            logger.exception(f"Failed to generate fix: {e}")
            return self._generate_issue_only(diagnosis, repository_info)

    def _generate_issue_only(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate an issue-only remediation plan."""
        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description=f"Creating issue for {diagnosis.failure_type.value} failure",
            issue_title=f"[PipelineHealer] CI Failure: {diagnosis.failure_type.value}",
            issue_body=self._format_issue_body(diagnosis, repository_info),
        )

    def generate_review_issue(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
        not_auto_reason: str,
        reason_code: NotAutoApplyReason = NotAutoApplyReason.LOW_CONFIDENCE,
    ) -> RemediationPlan:
        """Generate an issue plan with explicit non-auto-apply reason."""
        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description=f"Creating review-only issue for {diagnosis.failure_type.value} failure",
            issue_title=f"[PipelineHealer] Review required: {diagnosis.failure_type.value}",
            issue_body=self._format_issue_body(
                diagnosis,
                repository_info,
                not_auto_reason=not_auto_reason,
                reason_code=reason_code,
            ),
        )

    def _format_issue_body(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
        not_auto_reason: str | None = None,
        reason_code: NotAutoApplyReason | None = None,
    ) -> str:
        """Format the issue body with diagnosis details."""
        affected_files = (
            "\n".join(f"- `{f}`" for f in diagnosis.affected_files) or "None identified"
        )
        issue = f"""## CI/CD Failure Analysis

**Failure Type:** {diagnosis.failure_type.value}
**Confidence:** {diagnosis.confidence:.0%}

### Root Cause
{diagnosis.root_cause}

### Affected Files
{affected_files}

### Suggested Fix
{diagnosis.suggested_fix or "Manual investigation required"}

### Error Details
```json
{json.dumps(diagnosis.error_details, indent=2)}
```

---
*This issue was automatically created by PipelineHealer*
"""
        return self._append_review_only_proposal(
            issue,
            diagnosis,
            not_auto_reason=not_auto_reason,
            reason_code=reason_code,
        )

    def _default_not_auto_reason(self, diagnosis: Diagnosis) -> tuple[NotAutoApplyReason, str]:
        """Generate a user-facing reason and code for why a fix was not auto-applied."""
        if diagnosis.confidence < 0.5:
            return (
                NotAutoApplyReason.LOW_CONFIDENCE,
                "Confidence is below the automatic remediation threshold.",
            )
        if not diagnosis.is_auto_fixable:
            return (
                NotAutoApplyReason.REQUIRES_ENV_CONTEXT,
                "This failure type requires human judgment or environment-specific context.",
            )
        return (
            NotAutoApplyReason.SAFETY_BOUND,
            "Automatic application is disabled for this remediation path.",
        )

    def _sanitize_proposed_fix_text(self, text: str) -> str:
        """Trim and redact obvious secret-like content in proposed fixes."""
        cleaned = (text or "").strip()
        if not cleaned:
            return "No deterministic proposal available."
        cleaned = re.sub(r"ghp_[A-Za-z0-9]{20,}", "[REDACTED_GITHUB_TOKEN]", cleaned)
        cleaned = re.sub(r"sk-[A-Za-z0-9]{20,}", "[REDACTED_API_KEY]", cleaned)
        cleaned = re.sub(
            r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[^'\"\s]{6,}",
            r"\1=[REDACTED]",
            cleaned,
        )
        if len(cleaned) > self._max_proposed_fix_chars:
            cleaned = cleaned[: self._max_proposed_fix_chars].rstrip() + "\n...[truncated]"
        return cleaned

    def _is_allowed_proposal_path(self, path: str) -> bool:
        normalized = path.strip().strip("`").strip("/")
        if not normalized or " " in normalized:
            return False
        if normalized in self._proposed_fix_allowed_exact:
            return True
        return any(normalized.startswith(prefix) for prefix in self._proposed_fix_allowed_prefixes)

    def _validate_proposed_fix_scope(self, diagnosis: Diagnosis) -> tuple[bool, str]:
        """Verify proposed fix scope is limited to safe path domains."""
        for file_path in diagnosis.affected_files:
            if file_path and not self._is_allowed_proposal_path(file_path):
                return False, file_path
        return True, ""

    def _build_validation_steps(self, diagnosis: Diagnosis) -> str:
        """Build concise verification steps for manual review path."""
        details = diagnosis.error_details or {}
        lines = [
            "1. Apply the proposed change in a branch.",
            "2. Re-run the failing GitHub Actions workflow.",
            "3. Confirm the original failing step now passes and no new failures are introduced.",
        ]
        if diagnosis.failure_type == FailureType.TEST:
            framework = str(details.get("test_framework") or "test")
            lines.insert(2, f"3. Run the related {framework} tests locally before pushing.")
            lines[3] = "4. Re-run the failing GitHub Actions workflow."
            lines.append("5. Confirm the original failing step now passes and no new failures are introduced.")
        return "\n".join(lines)

    def _build_pipelinehealer_assessment(
        self,
        diagnosis: Diagnosis,
        reason_code: NotAutoApplyReason,
    ) -> str:
        """Build a structured accuracy review section for operator validation."""
        if diagnosis.failure_type == FailureType.UNKNOWN or diagnosis.confidence < 0.5:
            identification_status = "needs operator confirmation"
        elif diagnosis.confidence >= 0.8:
            identification_status = "high-confidence signal"
        else:
            identification_status = "moderate-confidence signal"

        if diagnosis.confidence >= 0.8:
            diagnosis_status = "likely correct from available evidence"
        elif diagnosis.confidence >= 0.5:
            diagnosis_status = "plausible but requires log verification"
        else:
            diagnosis_status = "low-confidence and must be treated as a hypothesis"

        return (
            f"- Identification: `{diagnosis.failure_type.value}` at `{diagnosis.confidence:.0%}` confidence "
            f"({identification_status}).\n"
            f"- Diagnosis: {diagnosis_status}.\n"
            f"- Remediation: review-only proposal path (`{reason_code.value}`), not auto-applied.\n"
            "- Target Version: assign milestone/version label before closure.\n\n"
            "### Operator Verification Checklist\n"
            "- [ ] Identification is correct (failure type and scope match failing logs).\n"
            "- [ ] Diagnosis is correct (root cause validated against workflow/job logs).\n"
            "- [ ] Remediation is correct (proposal validated by branch + rerun, or deferred with reason).\n"
        )

    def _build_proposed_fix_text(self, diagnosis: Diagnosis) -> str:
        """Build a review-only proposed fix snippet for issue bodies."""
        details = diagnosis.error_details or {}
        explicit_patch = str(details.get("proposed_patch") or "").strip()
        if explicit_patch:
            return explicit_patch

        if diagnosis.failure_type == FailureType.DEPENDENCY:
            package = str(details.get("package_name") or "").strip()
            version = str(details.get("required_version") or "latest").strip()
            manager = str(details.get("package_manager") or "npm").strip().lower()
            if package and manager == "npm":
                return (
                    "package.json\n"
                    f'  "dependencies": {{\n    "{package}": "{version}"\n  }}'
                )
            if package and manager in {"pip", "uv"}:
                pin = f"{package}=={version}" if version and version != "latest" else package
                return f"requirements.txt\n  {pin}"

        if diagnosis.failure_type == FailureType.LINT:
            linter = str(details.get("linter") or "").strip().lower()
            missing_file = str(details.get("missing_file") or "").strip()
            if linter == "eslint" and missing_file.startswith("eslint.config"):
                return (
                    f"{missing_file}\n"
                    "export default [\n"
                    "  {\n"
                    "    files: [\"**/*.{js,mjs,cjs}\"],\n"
                    "    rules: {},\n"
                    "  },\n"
                    "];"
                )
            fix_cmd = lint_autofix_command(linter)
            if fix_cmd:
                return f"Run locally:\n{fix_cmd}"

        if diagnosis.failure_type == FailureType.BUILD_CONFIG:
            if bool(details.get("workflow_permissions_fix")):
                perms = details.get("permissions", {})
                contents = str(perms.get("contents") or "write")
                prs = str(perms.get("pull-requests") or "write")
                return (
                    ".github/workflows/ci.yml\n"
                    "permissions:\n"
                    f"  contents: {contents}\n"
                    f"  pull-requests: {prs}\n"
                    "jobs:"
                )
            missing_vars = details.get("missing_env_vars") or []
            if missing_vars:
                lines = "\n".join(f"- {v}" for v in missing_vars if v)
                if lines:
                    return "Configure missing repository variables/secrets:\n" + lines

        if diagnosis.failure_type == FailureType.TIMEOUT:
            suggested = details.get("suggested_timeout")
            if isinstance(suggested, int) and suggested > 0:
                return (
                    ".github/workflows/ci.yml\n"
                    f"timeout-minutes: {suggested}"
                )

        if diagnosis.failure_type == FailureType.TEST:
            framework = str(details.get("test_framework") or "test framework")
            return (
                "Run locally and verify failing tests:\n"
                f"- {framework} test run\n"
                "- re-run flaky candidates once before code changes"
            )

        if diagnosis.suggested_fix:
            return diagnosis.suggested_fix
        return "No deterministic proposal available."

    def _append_review_only_proposal(
        self,
        issue_body: str,
        diagnosis: Diagnosis,
        not_auto_reason: str | None = None,
        reason_code: NotAutoApplyReason | None = None,
    ) -> str:
        """Append a clear review-only proposal block to issue bodies."""
        default_code, default_reason = self._default_not_auto_reason(diagnosis)
        final_code = reason_code or default_code
        final_reason = not_auto_reason or default_reason
        scope_ok, out_of_scope_path = self._validate_proposed_fix_scope(diagnosis)
        if not scope_ok:
            final_code = NotAutoApplyReason.OUTSIDE_ALLOWED_FILES
            final_reason = (
                f"Proposed change touches non-allowlisted path `{out_of_scope_path}`; "
                "manual review is required."
            )
            proposal = (
                "No patch body included because suggested changes touch non-allowlisted files.\n"
                f"Out-of-scope path: {out_of_scope_path}"
            )
        else:
            proposal = self._sanitize_proposed_fix_text(self._build_proposed_fix_text(diagnosis))
        validate = self._build_validation_steps(diagnosis)
        assessment = self._build_pipelinehealer_assessment(diagnosis, final_code)
        return (
            issue_body.rstrip()
            + "\n\n### Proposed Fix (For Review Only)\n"
            + "> WARNING: UNVERIFIED AI SUGGESTION - not applied automatically.\n\n"
            + "```text\n"
            + proposal
            + "\n```\n\n"
            + "### Why Not Auto-Applied\n"
            + f"- Reason Code: {final_code.value}\n"
            + f"- Detail: {final_reason}\n\n"
            + "### How to Validate\n"
            + validate
            + "\n\n### PipelineHealer Assessment\n"
            + assessment
            + "\n"
        )

    async def _generate_dependency_fix(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate a fix for dependency issues."""
        error_details = diagnosis.error_details

        # Extract package information from error details
        package_name = error_details.get("package_name", "")
        current_version = error_details.get("current_version", "")
        required_version = error_details.get("required_version", "")
        package_manager = error_details.get("package_manager", "npm")

        # Best-effort extraction when the diagnosis came from an LLM and didn't include `package_name`.
        # This supports demo scenarios like: "Cannot find module 'left-pad'".
        if not package_name:
            additional = json.dumps(error_details)
            m = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", additional, flags=re.IGNORECASE)
            if m:
                package_name = m.group(1)
                package_manager = error_details.get("package_manager", "npm")

        if not package_name:
            return self._generate_issue_only(diagnosis, repository_info)

        # Determine which file to update
        file_changes: list[dict[str, Any]] = []

        if package_manager == "npm":
            file_changes.append(
                {
                    "file": "package.json",
                    "type": "json_update",
                    "path": f"dependencies.{package_name}",
                    "value": required_version or "latest",
                }
            )
        elif package_manager == "pip":
            file_changes.append(
                {
                    "file": "requirements.txt",
                    "type": "line_update",
                    "pattern": f"^{re.escape(package_name)}.*$",
                    "replacement": f"{package_name}=={required_version}"
                    if required_version
                    else package_name,
                }
            )
        elif package_manager == "uv":
            logger.warning(
                "UV package manager remediation not yet supported; "
                "falling back to issue-only remediation plan."
            )
            return self._generate_issue_only(diagnosis, repository_info)

        version_info = f" to {required_version}" if required_version else ""

        return RemediationPlan(
            action=RemediationAction.CREATE_PR,
            description=f"Update {package_name}{version_info}",
            file_changes=file_changes,
            branch_name=f"fix/update-{package_name.replace('/', '-')}",
            pr_title=f"fix(deps): Update {package_name}{version_info}",
            pr_body=f"""## Dependency Update

This PR updates `{package_name}` to resolve a CI failure.

### Changes
- Updated `{package_name}` from `{current_version}` to `{required_version or "latest"}`

### Root Cause
{diagnosis.root_cause}

### Suggested by
PipelineHealer automated analysis

---
*This PR was automatically created by PipelineHealer*
""",
        )

    async def _generate_lint_fix(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate a fix for linting issues."""
        error_details = diagnosis.error_details

        linter = error_details.get("linter", "unknown")
        violations = error_details.get("violations", [])

        # ESLint v9+ requires a flat config (`eslint.config.*`). If missing, we can create a minimal config
        # as a safe, deterministic PR that unblocks linting (especially for demo repos).
        missing_file = str(error_details.get("missing_file") or "")
        if linter == "unknown" and "eslint.config" in json.dumps(error_details):
            linter = "eslint"
            missing_file = missing_file or "eslint.config.js"

        if linter == "eslint" and missing_file.startswith("eslint.config"):
            config_filename = missing_file or "eslint.config.js"
            config_content = """export default [\n  {\n    files: [\"**/*.{js,mjs,cjs}\"],\n    languageOptions: {\n      ecmaVersion: \"latest\",\n      sourceType: \"module\",\n    },\n    rules: {},\n  },\n];\n"""
            return RemediationPlan(
                action=RemediationAction.CREATE_PR,
                description=f"Add {config_filename} (ESLint flat config)",
                file_changes=[
                    {
                        "file": config_filename,
                        "content": config_content,
                    }
                ],
                branch_name="fix/lint-eslint-config",
                pr_title=f"fix(lint): add {config_filename}",
                pr_body=f"""## Lint Fix (ESLint)\n\nThis PR adds a minimal ESLint flat config (`{config_filename}`) so ESLint can run.\n\n### Root Cause\n{diagnosis.root_cause}\n\n### Notes\n- This config is intentionally minimal to unblock CI.\n- You can extend it with project-specific rules later.\n\n---\n*This PR was automatically created by PipelineHealer*\n""",
            )

        # For auto-fixable linters, suggest running the fix command
        fix_command = lint_autofix_command(linter)

        if fix_command and diagnosis.is_auto_fixable:
            # Create a workflow that runs the fix
            workflow_content = f"""# Auto-fix workflow triggered by PipelineHealer
name: Auto-fix {linter}

on:
  workflow_dispatch:

jobs:
  fix:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run {linter} fix
        run: {fix_command}
      - name: Commit changes
        run: |
          git config user.name "PipelineHealer"
          git config user.email "pipelinehealer@example.com"
          git add -A
          git diff --staged --quiet || git commit -m "fix: Auto-fix {linter} issues"
          git push
"""
            return RemediationPlan(
                action=RemediationAction.CREATE_PR,
                description=f"Create auto-fix workflow for {linter}",
                file_changes=[
                    {
                        "file": f".github/workflows/auto-fix-{linter}.yml",
                        "content": workflow_content,
                    }
                ],
                branch_name=f"fix/lint-{linter}",
                pr_title=f"fix(lint): Add auto-fix workflow for {linter}",
                pr_body=f"""## Lint Fix

This PR adds an auto-fix workflow for {linter} issues.

### How to use
1. Merge this PR
2. Run the "Auto-fix {linter}" workflow manually
3. The workflow will automatically fix and commit the changes

### Violations Found
{len(violations)} violation(s) detected

### Root Cause
{diagnosis.root_cause}

---
*This PR was automatically created by PipelineHealer*
""",
            )

        # If not auto-fixable, create an issue with details
        violations_list = "\n".join(
            f"- {v.get('file', 'unknown')}: {v.get('message', 'Unknown violation')}"
            for v in violations[:20]  # Limit to 20 violations
        )

        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description=f"Create issue for {linter} violations",
            issue_title=f"[PipelineHealer] Fix {linter} violations ({len(violations)} issues)",
            issue_body=self._append_review_only_proposal(
                f"""## Lint Violations

**Linter:** {linter}
**Total Violations:** {len(violations)}

### Violations
{violations_list}
{"... and more" if len(violations) > 20 else ""}

### Suggested Fix
Run `{fix_command or f"{linter} --fix"}` locally to fix these issues.

### Root Cause
{diagnosis.root_cause}

---
*This issue was automatically created by PipelineHealer*
""",
                diagnosis=diagnosis,
            ),
        )

    async def _generate_test_fix(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate a fix for test failures."""
        error_details = diagnosis.error_details

        failed_tests = error_details.get("failed_tests", [])
        is_flaky = error_details.get("is_flaky", False)
        test_framework = error_details.get("test_framework", "unknown")

        if is_flaky and self._is_demo_mode:
            # Demo mode: if the diagnosis indicates flakiness, the most reliable "self-heal"
            # is to re-run the failed jobs once.
            return RemediationPlan(
                action=RemediationAction.RETRY_WORKFLOW,
                description="Retry flaky workflow run (demo mode)",
            )

        if is_flaky:
            # Safe mode: create an issue so a human can investigate.
            return RemediationPlan(
                action=RemediationAction.CREATE_ISSUE,
                description="Create issue for flaky test investigation",
                issue_title="[PipelineHealer] Flaky test detected",
                issue_body=self._append_review_only_proposal(
                    f"""## Flaky Test Detected

The following test(s) appear to be flaky (intermittent failures):

### Failed Tests
{chr(10).join(f"- `{t}`" for t in failed_tests)}

### Recommendations
1. **Retry Strategy**: Consider adding retry logic for these tests
2. **Investigation**: Check for race conditions, timing issues, or external dependencies
3. **Quarantine**: If unable to fix immediately, consider quarantining the test

### Test Framework
{test_framework}

### Root Cause Analysis
{diagnosis.root_cause}

---
*This issue was automatically created by PipelineHealer*
""",
                    diagnosis=diagnosis,
                ),
            )

        # For regular test failures, create detailed issue
        test_errors = error_details.get("test_errors", {})
        affected_blob = " ".join(diagnosis.affected_files).lower()
        workflow_step_failure = (
            len(failed_tests) == 0
            and (
                "workflow" in affected_blob
                or "github_run_attempt" in str(diagnosis.root_cause).lower()
                or "process.exit(1)" in str(diagnosis.root_cause).lower()
            )
        )
        error_details_str = "\n\n".join(
            f"**{test}**\n```\n{error}\n```" for test, error in list(test_errors.items())[:5]
        )
        issue_title = (
            "[PipelineHealer] Workflow step failure (non-test)"
            if workflow_step_failure
            else f"[PipelineHealer] Test failures: {len(failed_tests)} test(s) failed"
        )
        heading = "## Workflow Step Failure" if workflow_step_failure else "## Test Failures"

        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description="Create issue for test failure investigation",
            issue_title=issue_title,
            issue_body=self._append_review_only_proposal(
                f"""{heading}

**Test Framework:** {test_framework}
**Failed Tests:** {len(failed_tests)}

### Failed Tests
{chr(10).join(f"- `{t}`" for t in failed_tests[:10])}
{"... and more" if len(failed_tests) > 10 else ""}

### Error Details
{error_details_str or "No detailed errors captured"}

### Affected Files
{chr(10).join(f"- `{f}`" for f in diagnosis.affected_files) or "None identified"}

### Root Cause Analysis
{diagnosis.root_cause}

### Suggested Fix
{diagnosis.suggested_fix or "Manual investigation required"}

---
*This issue was automatically created by PipelineHealer*
""",
                diagnosis=diagnosis,
            ),
        )

    async def _generate_build_config_fix(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate a fix for build configuration issues."""
        error_details = diagnosis.error_details

        if bool(error_details.get("workflow_permissions_fix")):
            permissions = error_details.get("permissions", {})
            contents_level = str(permissions.get("contents") or "write")
            pr_level = str(permissions.get("pull-requests") or "write")
            permissions_block = (
                "permissions:\n"
                f"  contents: {contents_level}\n"
                f"  pull-requests: {pr_level}\n\n"
                "jobs:"
            )
            return RemediationPlan(
                action=RemediationAction.CREATE_PR,
                description="Add minimal GitHub Actions workflow permissions",
                file_changes=[
                    {
                        "type": "line_update",
                        "files": [
                            ".github/workflows/ci.yml",
                            ".github/workflows/ci.yaml",
                        ],
                        "pattern": r"^jobs:\s*$",
                        "replacement": permissions_block,
                        "append_if_missing": False,
                        "all_matches": False,
                        "require_existing": True,
                    }
                ],
                branch_name="fix/ci-workflow-permissions",
                pr_title="fix(ci): add minimal workflow permissions",
                pr_body=(
                    "## CI Permission Fix\n\n"
                    "This PR adds a minimal workflow `permissions` block to resolve "
                    "`GITHUB_TOKEN` authorization failures.\n\n"
                    "### Added Permissions\n"
                    f"- `contents: {contents_level}`\n"
                    f"- `pull-requests: {pr_level}`\n\n"
                    "### Root Cause\n"
                    f"{diagnosis.root_cause}\n\n"
                    "---\n"
                    "*This PR was automatically created by PipelineHealer*\n"
                ),
            )

        missing_vars = error_details.get("missing_env_vars", [])
        config_file = error_details.get("config_file", "")
        config_error = error_details.get("config_error", "")

        if missing_vars and self._is_demo_mode:
            # Demo mode: only auto-fix non-secret-looking variables, and only in workflow files
            # (never attempt to "set secrets").
            safe_vars: list[str] = []
            for v in missing_vars:
                v = str(v or "").strip()
                if not v:
                    continue
                if re.search(r"(SECRET|TOKEN|PASSWORD|PRIVATE|KEY)", v, flags=re.IGNORECASE):
                    continue
                safe_vars.append(v)

            if safe_vars:
                file_changes: list[dict[str, Any]] = []
                for v in safe_vars:
                    file_changes.append(
                        {
                            "type": "line_update",
                            "files": [
                                ".github/workflows/ci.yml",
                                ".github/workflows/ci.yaml",
                            ],
                            "pattern": rf"^(?P<indent>\s*){re.escape(v)}:\s*.*$",
                            "replacement": rf"\g<indent>{v}: demo",
                            "append_if_missing": False,
                            "all_matches": False,
                            "require_existing": True,
                        }
                    )

                return RemediationPlan(
                    action=RemediationAction.CREATE_PR,
                    description="Set missing CI config vars (demo mode)",
                    file_changes=file_changes,
                    branch_name="fix/config-add-missing-vars",
                    pr_title="fix(ci): add missing config vars",
                    pr_body=(
                        "## Build Config Fix (Demo Mode)\n\n"
                        "This PR sets non-secret CI config variables directly in the workflow so the pipeline can run.\n\n"
                        "### Missing Variables\n"
                        + "\n".join(f"- `{v}`" for v in safe_vars)
                        + "\n\n"
                        "### Safety\n"
                        "- Secrets are never set by PipelineHealer.\n"
                        "- Only non-secret-looking vars are set, with placeholder values.\n\n"
                        "---\n"
                        "*This PR was automatically created by PipelineHealer*\n"
                    ),
                )

        if missing_vars:
            # Create issue about missing environment variables
            vars_list = "\n".join(f"- `{v}`" for v in missing_vars)

            return RemediationPlan(
                action=RemediationAction.CREATE_ISSUE,
                description="Create issue for missing environment variables",
                issue_title="[PipelineHealer] Missing environment variables in CI",
                issue_body=self._append_review_only_proposal(
                    f"""## Missing Environment Variables

The CI workflow failed due to missing environment variables.

### Missing Variables
{vars_list}

### How to Fix
1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets/variables:
{vars_list}

### Root Cause
{diagnosis.root_cause}

---
*This issue was automatically created by PipelineHealer*
""",
                    diagnosis=diagnosis,
                ),
            )

        # Generic build config issue
        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description="Create issue for build configuration error",
            issue_title="[PipelineHealer] Build configuration error",
            issue_body=self._append_review_only_proposal(
                f"""## Build Configuration Error

**Config File:** {config_file or "Unknown"}

### Error
```
{config_error or diagnosis.root_cause}
```

### Affected Files
{chr(10).join(f"- `{f}`" for f in diagnosis.affected_files) or "None identified"}

### Suggested Fix
{diagnosis.suggested_fix or "Review the configuration file for syntax errors or missing fields"}

---
*This issue was automatically created by PipelineHealer*
""",
                diagnosis=diagnosis,
            ),
        )

    async def _generate_timeout_fix(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate a fix for timeout issues."""
        error_details = diagnosis.error_details

        timed_out_step = error_details.get("timed_out_step", "Unknown")
        timeout_minutes = error_details.get("timeout_minutes", 0)
        suggested_timeout = error_details.get("suggested_timeout", timeout_minutes * 2)

        if self._is_demo_mode:
            # Demo mode: open a deterministic PR that bumps timeout-minutes in the demo workflow.
            # This is intentionally conservative: if we can't find the key, the PR will not be created
            # and PipelineHealer should fall back to an issue.
            bump_to = suggested_timeout if isinstance(suggested_timeout, int) and suggested_timeout > 0 else 5
            bump_to = max(5, bump_to)

            return RemediationPlan(
                action=RemediationAction.CREATE_PR,
                description=f"Bump workflow timeout to {bump_to} minutes (demo mode)",
                file_changes=[
                    {
                        "type": "line_update",
                        "files": [
                            ".github/workflows/ci.yml",
                            ".github/workflows/ci.yaml",
                        ],
                        "pattern": r"^(?P<indent>\s*)timeout-minutes:\s*\d+\s*$",
                        "replacement": rf"\g<indent>timeout-minutes: {bump_to}",
                        "append_if_missing": False,
                        "all_matches": True,
                        "require_existing": True,
                    }
                ],
                branch_name="fix/ci-timeout-minutes",
                pr_title=f"fix(ci): bump timeout-minutes to {bump_to}",
                pr_body=(
                    "## Timeout Fix (Demo Mode)\n\n"
                    "This PR bumps `timeout-minutes` in the workflow to reduce false failures from slow steps.\n\n"
                    f"- Step: `{timed_out_step}`\n"
                    f"- New timeout-minutes: `{bump_to}`\n\n"
                    "---\n"
                    "*This PR was automatically created by PipelineHealer*\n"
                ),
            )

        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description="Create issue for timeout investigation",
            issue_title=f"[PipelineHealer] Workflow timeout in '{timed_out_step}'",
            issue_body=self._append_review_only_proposal(
                f"""## Workflow Timeout

The CI workflow timed out during execution.

### Details
- **Step:** {timed_out_step}
- **Current Timeout:** {timeout_minutes} minutes
- **Suggested Timeout:** {suggested_timeout} minutes

### Recommendations
1. **Increase Timeout**: If the step legitimately needs more time, increase the timeout
2. **Optimize**: Look for ways to speed up the step:
   - Use caching for dependencies
   - Parallelize tests
   - Use faster runners
3. **Split**: Consider splitting the job into smaller jobs

### How to Increase Timeout
Add `timeout-minutes` to the step or job in your workflow:
```yaml
jobs:
  build:
    timeout-minutes: {suggested_timeout}
    steps:
      - name: {timed_out_step}
        timeout-minutes: {suggested_timeout}
```

### Root Cause
{diagnosis.root_cause}

---
*This issue was automatically created by PipelineHealer*
""",
                diagnosis=diagnosis,
            ),
        )
