"""Tests for the Diagnosis Agent."""

from src.agents.diagnosis import DiagnosisAgent
from src.models import FailureType, LogAnalysis


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

    def test_detect_timeout(self) -> None:
        """Test detection of timeout errors."""
        log_analysis = LogAnalysis(
            job_id=1,
            job_name="build",
            raw_logs="Error: timeout exceeded waiting for response",
            error_lines=["Error: timeout exceeded waiting for response"],
            summary="Operation timed out",
        )

        diagnosis = self.agent._pattern_based_diagnosis([log_analysis])

        assert diagnosis is not None
        assert diagnosis.failure_type == FailureType.TIMEOUT

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
