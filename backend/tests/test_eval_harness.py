"""Tests for the built-in diagnosis/remediation eval harness."""

import pytest

from src.evals.diagnosis_remediation import (
    EvalGateThresholds,
    builtin_eval_fixtures,
    evaluate_builtin_fixture_set,
)
from src.models import RemediationAction


@pytest.mark.asyncio
async def test_builtin_eval_fixture_set_passes_rollout_gate() -> None:
    result = await evaluate_builtin_fixture_set()

    assert result.gate_passed is True
    assert result.classification_accuracy == 1.0
    assert result.action_correctness == 1.0
    assert result.validation_pass_rate == 1.0
    assert result.field_completeness == 1.0


def test_builtin_eval_fixtures_cover_all_supported_failure_types() -> None:
    fixtures = {fixture.fixture_id: fixture for fixture in builtin_eval_fixtures()}

    assert set(fixtures) == {
        "dependency_missing_node_module",
        "lint_missing_eslint_config",
        "test_pytest_assertion_failure",
        "timeout_named_step_limit",
        "build_config_missing_secret",
    }
    assert fixtures["dependency_missing_node_module"].expected_action == RemediationAction.CREATE_PR
    assert "test_errors" in fixtures["test_pytest_assertion_failure"].required_error_details
    assert fixtures["timeout_named_step_limit"].expected_error_details["timed_out_step"] == "Install dependencies"
    assert fixtures["build_config_missing_secret"].expected_error_details["config_file"] == (
        ".github/workflows/ci.yml"
    )


@pytest.mark.asyncio
async def test_eval_gate_fails_when_threshold_exceeds_metric() -> None:
    result = await evaluate_builtin_fixture_set(
        thresholds=EvalGateThresholds(field_completeness_min=1.01)
    )

    assert result.gate_passed is False
