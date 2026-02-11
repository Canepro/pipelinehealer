"""Fix generators for different failure types."""

import json
import logging
import re
from typing import Any

from ..models import Diagnosis, FailureType, RemediationAction, RemediationPlan

logger = logging.getLogger(__name__)


class FixGenerators:
    """Generators for creating fixes based on diagnosed failures."""

    def __init__(self, heal_mode: str = "safe") -> None:
        """Initialize fix generators."""
        self._heal_mode = (heal_mode or "safe").strip().lower()
        self._is_demo_mode = self._heal_mode == "demo"
        self._generators = {
            FailureType.DEPENDENCY: self._generate_dependency_fix,
            FailureType.LINT: self._generate_lint_fix,
            FailureType.TEST: self._generate_test_fix,
            FailureType.BUILD_CONFIG: self._generate_build_config_fix,
            FailureType.TIMEOUT: self._generate_timeout_fix,
        }

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

    def _format_issue_body(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> str:
        """Format the issue body with diagnosis details."""
        affected_files = (
            "\n".join(f"- `{f}`" for f in diagnosis.affected_files) or "None identified"
        )

        return f"""## CI/CD Failure Analysis

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
            file_changes.append(
                {
                    "file": "pyproject.toml",
                    "type": "toml_update",
                    "section": "project.dependencies",
                    "package": package_name,
                    "version": required_version,
                }
            )

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
        auto_fix_commands = {
            "eslint": "npx eslint --fix .",
            "prettier": "npx prettier --write .",
            "black": "black .",
            "ruff": "ruff check --fix . && ruff format .",
            "isort": "isort .",
        }

        fix_command = auto_fix_commands.get(linter)

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
            issue_body=f"""## Lint Violations

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
                issue_body=f"""## Flaky Test Detected

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
            )

        # For regular test failures, create detailed issue
        test_errors = error_details.get("test_errors", {})
        error_details_str = "\n\n".join(
            f"**{test}**\n```\n{error}\n```" for test, error in list(test_errors.items())[:5]
        )

        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description="Create issue for test failure investigation",
            issue_title=f"[PipelineHealer] Test failures: {len(failed_tests)} test(s) failed",
            issue_body=f"""## Test Failures

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
        )

    async def _generate_build_config_fix(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
    ) -> RemediationPlan:
        """Generate a fix for build configuration issues."""
        error_details = diagnosis.error_details

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
                issue_body=f"""## Missing Environment Variables

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
            )

        # Generic build config issue
        return RemediationPlan(
            action=RemediationAction.CREATE_ISSUE,
            description="Create issue for build configuration error",
            issue_title="[PipelineHealer] Build configuration error",
            issue_body=f"""## Build Configuration Error

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
            issue_body=f"""## Workflow Timeout

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
        )
