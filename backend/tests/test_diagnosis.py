"""Tests for the Diagnosis Agent."""

import pytest

from src.agents.diagnosis import DiagnosisAgent
from src.models import (
    DiagnosisSource,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    FailureType,
    LogAnalysis,
)


class TestPatternBasedDiagnosis:
    """Test pattern-based diagnosis for common failure types."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.agent = DiagnosisAgent()

    def test_detect_npm_dependency_error(self) -> None:
        """Test detection of npm dependency errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="npm ERR! ERESOLVE unable to resolve dependency tree",
            error_lines=["npm ERR! ERESOLVE unable to resolve dependency tree"],
            summary="Dependency resolution failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.DEPENDENCY
        assert diagnosis.confidence >= 0.8
        assert diagnosis.diagnosis_source == DiagnosisSource.PATTERN

    def test_detect_python_module_not_found(self) -> None:
        """Test detection of Python ModuleNotFoundError."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="test",
            raw_logs="ModuleNotFoundError: No module named 'requests'",
            error_lines=["ModuleNotFoundError: No module named 'requests'"],
            summary="Import failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.DEPENDENCY
        assert diagnosis.error_details.get("package_name") == "requests"
        assert diagnosis.error_details.get("package_manager") == "pip"
        assert diagnosis.error_details.get("manifest_file") == "pyproject.toml"
        assert diagnosis.error_details.get("resolution_kind") == "missing"
        assert diagnosis.suggested_fix == (
            "Add Python dependency `requests` in pyproject.toml or requirements.txt "
            "and reinstall dependencies."
        )

    def test_detect_python_submodule_not_found_normalizes_package_name(self) -> None:
        """Top-level import names should drive Python package suggestions."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="test",
            raw_logs="ModuleNotFoundError: No module named 'requests.adapters'",
            error_lines=["ModuleNotFoundError: No module named 'requests.adapters'"],
            summary="Import failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.DEPENDENCY
        assert diagnosis.error_details.get("package_name") == "requests"
        assert diagnosis.suggested_fix == (
            "Add Python dependency `requests` in pyproject.toml or requirements.txt "
            "and reinstall dependencies."
        )

    def test_detect_node_missing_module_suggests_manifest_update(self) -> None:
        """Test that missing Node modules get a package.json-specific suggestion."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Error: Cannot find module 'left-pad'",
            error_lines=["Error: Cannot find module 'left-pad'"],
            summary="Build failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.DEPENDENCY
        assert diagnosis.error_details.get("package_name") == "left-pad"
        assert diagnosis.error_details.get("package_manager") == "npm"
        assert diagnosis.error_details.get("manifest_file") == "package.json"
        assert diagnosis.error_details.get("resolution_kind") == "missing"
        assert diagnosis.suggested_fix == (
            "Add `left-pad` to package.json and refresh the lockfile."
        )

    def test_detect_npm_resolution_conflict_suggests_compatible_version(self) -> None:
        """ERESOLVE signatures should produce version-conflict guidance."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="npm ERR! ERESOLVE unable to resolve dependency tree",
            error_lines=["npm ERR! ERESOLVE unable to resolve dependency tree"],
            summary="Dependency resolution failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.DEPENDENCY
        assert diagnosis.suggested_fix == "Update package.json dependencies and refresh the lockfile."

    def test_generic_missing_package_does_not_assume_python_manifest(self) -> None:
        """Generic package errors should stay neutral instead of pointing at pyproject.toml."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Package 'libpq-dev' was not found",
            error_lines=["Package 'libpq-dev' was not found"],
            summary="System package missing",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.DEPENDENCY
        assert diagnosis.error_details.get("package_manager") == "generic"
        assert diagnosis.suggested_fix == (
            "Install or restore the missing package/resource `libpq-dev` and re-run the workflow."
        )

    def test_detect_eslint_error(self) -> None:
        """Test detection of ESLint errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="lint",
            raw_logs="eslint error: Unexpected console statement",
            error_lines=["eslint error: Unexpected console statement"],
            summary="Linting failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.LINT
        assert "eslint" in diagnosis.error_details.get("linter", "")
        assert diagnosis.error_details.get("missing_file", "") == ""
        assert diagnosis.error_details.get("autofix_command") == "npx eslint --fix ."
        assert diagnosis.suggested_fix == (
            "Run `npx eslint --fix .` locally and commit the resulting lint fixes."
        )

    def test_detect_flake8_error_is_not_auto_fixable(self) -> None:
        """Flake8 violations should stay review-only without a deterministic autofix command."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="lint",
            raw_logs="flake8 error: F401 imported but unused",
            error_lines=["flake8 error: F401 imported but unused"],
            summary="Linting failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.LINT
        assert diagnosis.error_details.get("linter") == "flake8"
        assert diagnosis.error_details.get("autofix_command") == ""
        assert diagnosis.is_auto_fixable is False
        assert diagnosis.suggested_fix == "Fix the reported flake8 violations and re-run the workflow."

    def test_detect_mypy_type_error(self) -> None:
        """Mypy's file:line:error output should classify as lint/static analysis."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="types",
            raw_logs=(
                'backend/src/agents/remediation.py:734: error: Incompatible types in assignment '
                '(expression has type "dict[str, Any] | None", variable has type "dict[str, Any]")  [assignment]'
            ),
            error_lines=[
                'backend/src/agents/remediation.py:734: error: Incompatible types in assignment '
                '(expression has type "dict[str, Any] | None", variable has type "dict[str, Any]")  [assignment]'
            ],
            summary="Type checking failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.LINT
        assert diagnosis.error_details.get("linter") == "mypy"
        assert diagnosis.error_details.get("rule_ids") == ["assignment"]
        assert diagnosis.affected_files == ["backend/src/agents/remediation.py"]
        assert diagnosis.suggested_fix == "Fix the reported mypy violations and re-run the workflow."

    def test_detect_prettier_code_style_message(self) -> None:
        """Test detection of Prettier check output signature."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="format",
            raw_logs="Code style issues found in the above file. Run Prettier with --write to fix.",
            error_lines=["Code style issues found in the above file."],
            summary="Formatting failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.LINT
        assert diagnosis.error_details.get("linter") == "prettier"

    def test_detect_eslint_missing_flat_config(self) -> None:
        """Test detection of missing eslint flat config."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="lint",
            raw_logs="ESLint couldn't find an eslint.config.js file",
            error_lines=["ESLint couldn't find an eslint.config.js file"],
            summary="Linting failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.LINT
        assert diagnosis.error_details.get("linter") == "eslint"
        assert diagnosis.error_details.get("missing_file") == "eslint.config.js"
        assert diagnosis.error_details.get("config_file") == "eslint.config.js"
        assert diagnosis.suggested_fix == (
            "Add `eslint.config.js` so eslint can load its required configuration."
        )

    def test_detect_pytest_failure(self) -> None:
        """Test detection of pytest failures."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="test",
            raw_logs="pytest FAILED test_example.py::test_something",
            error_lines=["pytest FAILED test_example.py::test_something"],
            summary="Tests failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TEST
        assert diagnosis.error_details.get("test_framework") == "pytest"
        assert diagnosis.error_details.get("classification_signal") == "pytest test failed"
        assert diagnosis.error_details.get("failed_tests") == ["test_example.py::test_something"]
        assert diagnosis.error_details.get("test_errors") == {
            "test_example.py::test_something": "pytest FAILED test_example.py::test_something"
        }
        assert diagnosis.error_details.get("failure_scope") == "test_case"
        assert diagnosis.error_details.get("suspected_files") == ["test_example.py"]
        assert diagnosis.suggested_fix == (
            "Run pytest locally for `test_example.py::test_something`, fix the failing assertions, "
            "and re-run the workflow."
        )

    def test_detect_pytest_collection_failure(self) -> None:
        """Pytest collection blockers should be classified distinctly from zero-test failures."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="test",
            raw_logs=(
                "ERROR collecting backend/tests/test_agent_factory.py\n"
                "SyntaxError: f-string expression part cannot include a backslash"
            ),
            error_lines=[
                "ERROR collecting backend/tests/test_agent_factory.py",
                "SyntaxError: f-string expression part cannot include a backslash",
            ],
            summary="Test collection failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TEST
        assert diagnosis.error_details.get("test_framework") == "pytest"
        assert diagnosis.error_details.get("failure_scope") == "collection"
        assert diagnosis.error_details.get("failed_tests") == []
        assert diagnosis.error_details.get("suspected_files") == ["backend/tests/test_agent_factory.py"]
        assert diagnosis.error_details.get("test_errors") == {
            "summary": "ERROR collecting backend/tests/test_agent_factory.py"
        }
        assert diagnosis.suggested_fix == (
            "Fix the import or syntax error blocking pytest collection for "
            "`backend/tests/test_agent_factory.py`, then re-run the workflow."
        )

    def test_generic_failing_count_without_test_context_not_test(self) -> None:
        """Do not classify generic failing-check counts as test failures."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="ci",
            raw_logs="1 failing check detected in workflow gate",
            error_lines=["1 failing check detected in workflow gate"],
            summary="Workflow gate failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is None or diagnosis.failure_type != FailureType.TEST

    def test_generic_failing_count_with_test_context_is_test(self) -> None:
        """Keep support for frameworks that report `N failing` style test output."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="test",
            raw_logs="mocha run complete: 2 failing",
            error_lines=["mocha run complete: 2 failing"],
            summary="Mocha tests failed",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TEST
        assert diagnosis.error_details.get("test_framework") == "mocha"

    def test_detect_timeout(self) -> None:
        """Test detection of timeout errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Error: timed out waiting for response",
            error_lines=["Error: timed out waiting for response"],
            summary="Operation timed out",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TIMEOUT
        assert diagnosis.error_details.get("resource_signal") == "unknown"
        assert diagnosis.error_details.get("timed_out_job") == "build"

    def test_detect_timeout_exceeded_time_limit(self) -> None:
        """Test detection of 'exceeded time limit' errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Error: step 'Install dependencies' exceeded time limit of 30 minutes",
            error_lines=["Error: step 'Install dependencies' exceeded time limit of 30 minutes"],
            summary="Time limit exceeded",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TIMEOUT
        assert diagnosis.error_details.get("timeout_minutes") == 30
        assert diagnosis.error_details.get("suggested_timeout") == 60
        assert diagnosis.error_details.get("timed_out_step") == "Install dependencies"
        assert diagnosis.error_details.get("likely_fix_kind") == "increase_timeout"
        assert diagnosis.suggested_fix == (
            "Increase `timeout-minutes` above 30 minutes (for example `60`) or optimize "
            "the slow step before re-running the workflow."
        )

    def test_detect_deadline_exceeded(self) -> None:
        """Test detection of 'deadline exceeded' errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Error: deadline exceeded",
            error_lines=["Error: deadline exceeded"],
            summary="Deadline exceeded",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TIMEOUT
        assert diagnosis.error_details.get("likely_fix_kind") == "increase_timeout"

    def test_detect_killed_timeout_without_memory_signal_stays_unknown(self) -> None:
        """Generic killed logs should not be mislabeled as memory pressure."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Error: exceeded time limit of 15 minutes; process was killed",
            error_lines=["Error: exceeded time limit of 15 minutes; process was killed"],
            summary="Time limit exceeded",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TIMEOUT
        assert diagnosis.error_details.get("resource_signal") == "unknown"
        assert diagnosis.error_details.get("likely_fix_kind") == "increase_timeout"

    def test_timeout_setting_not_misclassified(self) -> None:
        """Test that benign 'timeout' config lines are not misclassified as timeout failures."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="setting timeout to 30s\nconnection timeout: 5000ms",
            error_lines=["setting timeout to 30s", "connection timeout: 5000ms"],
            summary="build configuration",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        # Should NOT be classified as timeout — these are config lines, not failure indicators
        assert diagnosis is None or diagnosis.failure_type != FailureType.TIMEOUT

    def test_detect_flaky_test_signature(self) -> None:
        """Test detection of flaky rerun/pass signatures."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="test",
            raw_logs="test_user_login failed, then passed on retry",
            error_lines=["Test suite passed on retry after initial failure"],
            summary="flaky behavior",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TEST
        assert diagnosis.error_details.get("is_flaky") is True
        assert diagnosis.suggested_fix == (
            "Stabilize the flaky test path and remove timing or order dependence before re-running the workflow."
        )

    def test_detect_disk_exhaustion_as_timeout_resource_signal(self) -> None:
        """Classify disk exhaustion as timeout/resource issue with specific guidance."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="write error: no space left on device",
            error_lines=["write error: no space left on device"],
            summary="disk exhausted",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TIMEOUT
        assert diagnosis.error_details.get("resource_signal") == "disk"
        assert diagnosis.error_details.get("likely_fix_kind") == "runner_capacity"
        assert diagnosis.suggested_fix == (
            "Free runner disk space or reduce cache, artifact, and workspace usage before "
            "re-running the workflow."
        )

    def test_detect_rate_limit_as_build_config_issue(self) -> None:
        """Test detection of API/rate-limit infrastructure failures."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="HTTP 403 API rate limit exceeded",
            error_lines=["HTTP 403 API rate limit exceeded"],
            summary="rate limit failure",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.BUILD_CONFIG
        assert diagnosis.error_details.get("misconfiguration_kind") == "rate_limit"
        assert diagnosis.suggested_fix == (
            "Reduce request volume, add retry/backoff, or use credentials with a higher API "
            "limit before retrying."
        )

    def test_detect_missing_secret_from_gh_aw_message(self) -> None:
        """Classify missing COPILOT token validation as build config."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="agent",
            raw_logs=(
                "Error: None of the following secrets are set: COPILOT_GITHUB_TOKEN\n"
                "The GitHub Copilot CLI engine requires either COPILOT_GITHUB_TOKEN secret "
                "to be configured."
            ),
            error_lines=[
                "Error: None of the following secrets are set: COPILOT_GITHUB_TOKEN",
                "The GitHub Copilot CLI engine requires either COPILOT_GITHUB_TOKEN secret to be configured.",
            ],
            summary="missing secret",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.BUILD_CONFIG
        assert diagnosis.root_cause == "Secret not configured"
        assert "COPILOT_GITHUB_TOKEN" in diagnosis.error_details.get("missing_env_vars", [])
        assert diagnosis.error_details.get("misconfiguration_kind") == "secret"
        assert diagnosis.suggested_fix == (
            "Configure the missing repository or environment secret(s): `COPILOT_GITHUB_TOKEN`."
        )

    def test_detect_build_config_extracts_config_file(self) -> None:
        """Build-config failures should capture referenced workflow/config files."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="ci",
            raw_logs="Secret not configured in .github/workflows/ci.yml",
            error_lines=["Secret not configured in .github/workflows/ci.yml"],
            summary="missing secret",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.BUILD_CONFIG
        assert diagnosis.error_details.get("config_file") == ".github/workflows/ci.yml"

    def test_detect_workflow_permission_error(self) -> None:
        """Test detection of GitHub token permission errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="403 Resource not accessible by integration",
            error_lines=["403 Resource not accessible by integration"],
            summary="Insufficient permissions",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.BUILD_CONFIG
        assert diagnosis.is_auto_fixable is True
        assert diagnosis.error_details.get("workflow_permissions_fix") is True
        assert diagnosis.error_details.get("misconfiguration_kind") == "workflow_permission"
        assert diagnosis.error_details.get("config_file") == ".github/workflows/ci.yml"
        assert diagnosis.suggested_fix == (
            "Add a minimal workflow `permissions` block so `GITHUB_TOKEN` can perform the required action."
        )

    def test_no_pattern_match_returns_none(self) -> None:
        """Test that unrecognized errors return None."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Some random log output",
            error_lines=[],
            summary="Unknown",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is None

    def test_changed_file_correlation_boosts_pattern_confidence(self) -> None:
        """Test deterministic confidence boost when error references changed file."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="lint",
            raw_logs="eslint error in src/utils/validator.ts",
            error_lines=["eslint error in src/utils/validator.ts"],
            summary="lint failed",
        )
        pattern = self.agent._pattern_based_diagnosis([log_analysis])
        assert pattern is not None

        correlated = self.agent._apply_changed_file_correlation(
            pattern,
            [log_analysis],
            {"changed_files": ["src/utils/validator.ts"]},
        )
        assert correlated is not None
        assert correlated.confidence > 0.9
        assert "src/utils/validator.ts" in correlated.affected_files

    def test_external_diagnostics_signal_boosts_confidence_with_reason(self) -> None:
        """Apply available external signal deltas and record provenance in error_details."""
        diagnosis = self.agent._pattern_based_diagnosis(
            [
                LogAnalysis(
                    job_id=1,
                    job_name="test",
                    raw_logs="pytest FAILED test_example.py::test_something",
                    error_lines=["pytest FAILED test_example.py::test_something"],
                    summary="Tests failed",
                )
            ]
        )
        assert diagnosis is not None
        before = diagnosis.confidence

        boosted = self.agent._apply_external_diagnostics_signal(
            diagnosis,
            [
                ExternalDiagnostic(
                    source="github-mcp",
                    status=ExternalDiagnosticStatus.AVAILABLE,
                    summary="github context",
                    confidence_delta=0.07,
                    metadata={"confidence_reason": "failing jobs + changed files"},
                ),
                ExternalDiagnostic(
                    source="gh_aw",
                    status=ExternalDiagnosticStatus.UNAVAILABLE,
                    summary="no findings",
                    confidence_delta=0.09,
                ),
            ],
        )

        assert boosted.confidence > before
        assert boosted.error_details.get("external_signal_confidence_delta") == pytest.approx(0.07)
        sources = boosted.error_details.get("external_signal_sources")
        assert isinstance(sources, list)
        assert len(sources) == 1
        assert sources[0]["source"] == "github-mcp"
        assert sources[0]["reason"] == "failing jobs + changed files"

    @pytest.mark.asyncio
    async def test_external_signal_can_lift_pattern_to_skip_llm(self, monkeypatch) -> None:
        """When pattern confidence is near threshold, external signal can avoid LLM call."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="test",
            raw_logs="test_user_login failed, then passed on retry",
            error_lines=["Test suite passed on retry after initial failure"],
            summary="flaky behavior",
        )

        async def should_not_call_llm() -> None:
            raise AssertionError("LLM path should not be called for this test")

        monkeypatch.setattr(self.agent, "_get_agent", should_not_call_llm)
        diagnosis = await self.agent.diagnose(
            [log_analysis],
            external_diagnostics=[
                ExternalDiagnostic(
                    source="github-mcp",
                    status=ExternalDiagnosticStatus.AVAILABLE,
                    summary="failing run metadata aligns with flaky signature",
                    confidence_delta=0.04,
                    metadata={"confidence_reason": "run metadata corroborates flaky test pattern"},
                )
            ],
        )

        assert diagnosis.diagnosis_source == DiagnosisSource.PATTERN
        assert diagnosis.confidence >= 0.8
        assert diagnosis.error_details.get("external_signal_confidence_delta") == pytest.approx(0.04)

    @pytest.mark.asyncio
    async def test_external_runner_acquisition_signal_produces_diagnosis_without_logs(self) -> None:
        """Use external diagnostics to classify infra-side runner acquisition failures when logs are absent."""
        diagnosis = await self.agent.diagnose(
            [],
            external_diagnostics=[
                ExternalDiagnostic(
                    source="github-mcp",
                    status=ExternalDiagnosticStatus.AVAILABLE,
                    summary="GitHub Actions hosted runner acquisition failed for: Frontend Lint and Build",
                    metadata={
                        "reason_code": "github_runner_acquisition_failed",
                        "failed_jobs": ["Frontend Lint and Build", "Version Sync"],
                        "messages": [
                            "The job was not acquired by Runner of type hosted even after multiple attempts"
                        ],
                    },
                )
            ],
        )

        assert diagnosis.failure_type == FailureType.BUILD_CONFIG
        assert diagnosis.diagnosis_source == DiagnosisSource.PATTERN
        assert diagnosis.confidence == pytest.approx(0.88)
        assert "hosted runner" in diagnosis.root_cause
        assert diagnosis.error_details.get("reason_code") == "github_runner_acquisition_failed"
        assert diagnosis.error_details.get("infrastructure_failure") is True
