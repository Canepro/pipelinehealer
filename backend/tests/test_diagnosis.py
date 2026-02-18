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

    def test_detect_timeout_exceeded_time_limit(self) -> None:
        """Test detection of 'exceeded time limit' errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Error: exceeded time limit of 30 minutes",
            error_lines=["Error: exceeded time limit of 30 minutes"],
            summary="Time limit exceeded",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TIMEOUT

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
