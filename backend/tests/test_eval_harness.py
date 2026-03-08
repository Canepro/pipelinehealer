"""Tests for the built-in diagnosis/remediation eval harness."""

from dataclasses import replace

import pytest

import src.evals.diagnosis_remediation as diagnosis_eval
from src.agents.diagnosis import DiagnosisAgent
from src.evals.diagnosis_remediation import (
    EvalGateThresholds,
    _is_present,
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
    assert result.expected_detail_accuracy == 1.0


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


@pytest.mark.asyncio
async def test_eval_harness_stays_on_deterministic_pattern_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("evaluate_builtin_fixture_set should not call DiagnosisAgent.diagnose")

    monkeypatch.setattr(DiagnosisAgent, "diagnose", _fail_if_called)

    result = await evaluate_builtin_fixture_set()

    assert result.gate_passed is True


@pytest.mark.asyncio
async def test_eval_gate_fails_when_expected_detail_values_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixtures = list(builtin_eval_fixtures())
    fixtures[0] = replace(
        fixtures[0],
        expected_error_details={
            **fixtures[0].expected_error_details,
            "manifest_file": "wrong.json",
        },
    )
    monkeypatch.setattr(diagnosis_eval, "builtin_eval_fixtures", lambda: tuple(fixtures))

    result = await evaluate_builtin_fixture_set()

    assert result.expected_detail_accuracy < 1.0
    assert result.gate_passed is False


def test_is_present_treats_zero_and_nan_as_missing() -> None:
    assert _is_present(0) is False
    assert _is_present(0.0) is False
    assert _is_present(float("nan")) is False
    assert _is_present(15) is True
