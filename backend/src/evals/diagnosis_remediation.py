"""Built-in fixture evaluation for diagnosis and remediation quality."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..agents.diagnosis import DiagnosisAgent
from ..models import Diagnosis, FailureType, LogAnalysis, RemediationAction, RemediationPlan
from ..tools.fix_generators import FixGenerators


@dataclass(frozen=True)
class EvalFixture:
    """One incident fixture for diagnosis/remediation evaluation."""

    fixture_id: str
    failure_type: FailureType
    job_name: str
    summary: str
    error_lines: tuple[str, ...]
    expected_action: RemediationAction
    required_error_details: tuple[str, ...]
    expected_error_details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalGateThresholds:
    """Minimum passing thresholds for the built-in fixture gate."""

    classification_accuracy_min: float = 1.0
    field_completeness_min: float = 0.95
    expected_detail_accuracy_min: float = 1.0
    action_correctness_min: float = 1.0
    validation_pass_rate_min: float = 1.0


@dataclass(frozen=True)
class EvalFixtureResult:
    """Per-fixture evaluation result."""

    fixture_id: str
    classification_correct: bool
    field_completeness: float
    action_correct: bool
    validation_passed: bool
    missing_fields: tuple[str, ...]
    mismatched_error_details: tuple[str, ...]
    diagnosis: Diagnosis
    plan: RemediationPlan


@dataclass(frozen=True)
class EvalSuiteResult:
    """Aggregated fixture-set evaluation metrics."""

    fixtures: tuple[EvalFixtureResult, ...]
    classification_accuracy: float
    field_completeness: float
    expected_detail_accuracy: float
    action_correctness: float
    validation_pass_rate: float
    gate_passed: bool
    thresholds: EvalGateThresholds


def builtin_eval_fixtures() -> tuple[EvalFixture, ...]:
    """Return the built-in deterministic fixture corpus for v0.6.0."""
    return (
        EvalFixture(
            fixture_id="dependency_missing_python_module",
            failure_type=FailureType.DEPENDENCY,
            job_name="test",
            summary="Pytest import failed due to missing Python dependency",
            error_lines=("ModuleNotFoundError: No module named 'requests'",),
            expected_action=RemediationAction.CREATE_PR,
            required_error_details=("package_name", "package_manager", "manifest_file", "resolution_kind"),
            expected_error_details={
                "package_name": "requests",
                "package_manager": "pip",
                "manifest_file": "pyproject.toml",
                "resolution_kind": "missing",
            },
        ),
        EvalFixture(
            fixture_id="dependency_missing_node_module",
            failure_type=FailureType.DEPENDENCY,
            job_name="build",
            summary="Build failed due to a missing Node dependency",
            error_lines=("Error: Cannot find module 'left-pad'",),
            expected_action=RemediationAction.CREATE_PR,
            required_error_details=("package_name", "package_manager", "manifest_file", "resolution_kind"),
            expected_error_details={
                "package_name": "left-pad",
                "package_manager": "npm",
                "manifest_file": "package.json",
                "resolution_kind": "missing",
            },
        ),
        EvalFixture(
            fixture_id="lint_missing_eslint_config",
            failure_type=FailureType.LINT,
            job_name="lint",
            summary="ESLint flat config is missing",
            error_lines=("ESLint couldn't find an eslint.config.js file",),
            expected_action=RemediationAction.CREATE_PR,
            required_error_details=("linter", "missing_file", "config_file", "autofix_command"),
            expected_error_details={
                "linter": "eslint",
                "missing_file": "eslint.config.js",
                "config_file": "eslint.config.js",
            },
        ),
        EvalFixture(
            fixture_id="lint_mypy_assignment_type_error",
            failure_type=FailureType.LINT,
            job_name="types",
            summary="Mypy rejected an Optional-to-dict assignment",
            error_lines=(
                'backend/src/agents/remediation.py:734: error: Incompatible types in assignment '
                '(expression has type "dict[str, Any] | None", variable has type "dict[str, Any]")  [assignment]',
            ),
            expected_action=RemediationAction.CREATE_ISSUE,
            required_error_details=("linter", "rule_ids", "classification_signal"),
            expected_error_details={
                "linter": "mypy",
                "classification_signal": "Mypy type-check failure",
            },
        ),
        EvalFixture(
            fixture_id="test_pytest_assertion_failure",
            failure_type=FailureType.TEST,
            job_name="test",
            summary="Pytest assertion failed",
            error_lines=(
                "pytest FAILED backend/tests/test_eval.py::test_example",
                "AssertionError: expected 200 == 500",
            ),
            expected_action=RemediationAction.CREATE_ISSUE,
            required_error_details=("test_framework", "failed_tests", "test_errors", "failure_scope", "suspected_files"),
            expected_error_details={
                "test_framework": "pytest",
                "failure_scope": "test_case",
            },
        ),
        EvalFixture(
            fixture_id="test_pytest_collection_syntax_failure",
            failure_type=FailureType.TEST,
            job_name="test",
            summary="Pytest could not collect the test module",
            error_lines=(
                "ERROR collecting backend/tests/test_agent_factory.py",
                "SyntaxError: f-string expression part cannot include a backslash",
            ),
            expected_action=RemediationAction.CREATE_ISSUE,
            required_error_details=("test_framework", "test_errors", "failure_scope", "suspected_files"),
            expected_error_details={
                "test_framework": "pytest",
                "failure_scope": "collection",
            },
        ),
        EvalFixture(
            fixture_id="timeout_named_step_limit",
            failure_type=FailureType.TIMEOUT,
            job_name="build",
            summary="Named workflow step exceeded timeout",
            error_lines=("Error: step 'Install dependencies' exceeded time limit of 15 minutes",),
            expected_action=RemediationAction.CREATE_ISSUE,
            required_error_details=(
                "timed_out_job",
                "timed_out_step",
                "timeout_minutes",
                "suggested_timeout",
                "resource_signal",
                "likely_fix_kind",
            ),
            expected_error_details={
                "timed_out_job": "build",
                "timed_out_step": "Install dependencies",
                "resource_signal": "unknown",
                "likely_fix_kind": "increase_timeout",
            },
        ),
        EvalFixture(
            fixture_id="build_config_missing_secret",
            failure_type=FailureType.BUILD_CONFIG,
            job_name="deploy",
            summary="Workflow secret is missing",
            error_lines=(
                "None of the following secrets are set: API_TOKEN",
                "Secret not configured in .github/workflows/ci.yml",
            ),
            expected_action=RemediationAction.CREATE_ISSUE,
            required_error_details=("missing_env_vars", "misconfiguration_kind", "config_file", "config_error"),
            expected_error_details={
                "misconfiguration_kind": "secret",
                "config_file": ".github/workflows/ci.yml",
            },
        ),
    )


async def evaluate_builtin_fixture_set(
    *,
    thresholds: EvalGateThresholds | None = None,
    heal_mode: str = "safe",
) -> EvalSuiteResult:
    """Evaluate the built-in fixture corpus against the current deterministic flow."""
    diagnosis_agent = DiagnosisAgent()
    fix_generators = FixGenerators(heal_mode=heal_mode)
    fixture_results = []
    gate_thresholds = thresholds or EvalGateThresholds()

    for fixture in builtin_eval_fixtures():
        log_analyses = [
            LogAnalysis(
                job_id=1,
                job_name=fixture.job_name,
                raw_logs="\n".join(fixture.error_lines),
                error_lines=list(fixture.error_lines),
                summary=fixture.summary,
            )
        ]
        diagnosis = diagnosis_agent._pattern_based_diagnosis(log_analyses)
        if diagnosis is None:
            raise ValueError(
                f"Built-in eval fixture '{fixture.fixture_id}' did not match the deterministic diagnosis path."
            )
        plan = await fix_generators.generate_fix(diagnosis, repository_info={})
        fixture_results.append(_evaluate_fixture(fixture, diagnosis, plan))

    count = len(fixture_results)
    classification_accuracy = sum(result.classification_correct for result in fixture_results) / count
    field_completeness = sum(result.field_completeness for result in fixture_results) / count
    expected_detail_accuracy = (
        sum(not result.mismatched_error_details for result in fixture_results) / count
    )
    action_correctness = sum(result.action_correct for result in fixture_results) / count
    validation_pass_rate = sum(result.validation_passed for result in fixture_results) / count
    gate_passed = (
        classification_accuracy >= gate_thresholds.classification_accuracy_min
        and field_completeness >= gate_thresholds.field_completeness_min
        and expected_detail_accuracy >= gate_thresholds.expected_detail_accuracy_min
        and action_correctness >= gate_thresholds.action_correctness_min
        and validation_pass_rate >= gate_thresholds.validation_pass_rate_min
    )

    return EvalSuiteResult(
        fixtures=tuple(fixture_results),
        classification_accuracy=classification_accuracy,
        field_completeness=field_completeness,
        expected_detail_accuracy=expected_detail_accuracy,
        action_correctness=action_correctness,
        validation_pass_rate=validation_pass_rate,
        gate_passed=gate_passed,
        thresholds=gate_thresholds,
    )


def _evaluate_fixture(
    fixture: EvalFixture,
    diagnosis: Diagnosis,
    plan: RemediationPlan,
) -> EvalFixtureResult:
    missing_fields = tuple(
        field_name
        for field_name in fixture.required_error_details
        if not _is_present(diagnosis.error_details.get(field_name))
    )
    mismatched_error_details = tuple(
        key
        for key, expected in fixture.expected_error_details.items()
        if diagnosis.error_details.get(key) != expected
    )
    completeness_total = len(fixture.required_error_details)
    field_completeness = (
        (completeness_total - len(missing_fields)) / completeness_total
        if completeness_total
        else 1.0
    )

    return EvalFixtureResult(
        fixture_id=fixture.fixture_id,
        classification_correct=diagnosis.failure_type == fixture.failure_type,
        field_completeness=field_completeness,
        action_correct=plan.action == fixture.expected_action,
        validation_passed=_plan_validation_passed(plan),
        missing_fields=missing_fields,
        mismatched_error_details=mismatched_error_details,
        diagnosis=diagnosis,
        plan=plan,
    )


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return False
        return value != 0
    return True


def _plan_validation_passed(plan: RemediationPlan) -> bool:
    if plan.action == RemediationAction.CREATE_PR:
        if not plan.branch_name or not plan.pr_title or not plan.pr_body or not plan.file_changes:
            return False
        for change in plan.file_changes:
            if not isinstance(change, dict):
                return False
            change_type = str(change.get("type") or "").strip()
            if change_type in {"json_update", "line_update"}:
                if not (change.get("file") or change.get("files")):
                    return False
                continue
            if change_type == "bounded_patch":
                if not change.get("file"):
                    return False
                if not str(change.get("instructions") or "").strip():
                    return False
                validation = change.get("validation")
                if not isinstance(validation, dict):
                    return False
                if not str(change.get("fallback_content") or "").strip():
                    return False
                continue
            if change.get("file") and change.get("content") is not None:
                continue
            return False
        return True
    if plan.action == RemediationAction.CREATE_ISSUE:
        return bool(plan.issue_title and plan.issue_body)
    return True
