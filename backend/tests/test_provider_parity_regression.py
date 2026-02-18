"""Regression checks for diagnosis/remediation parity across LLM providers."""

from __future__ import annotations

import pytest

from src.agents.diagnosis import DiagnosisAgent
from src.agents.remediation import RemediationAgent
from src.config import Settings, reset_settings
from src.models import (
    Diagnosis,
    DiagnosisSource,
    FailureType,
    LogAnalysis,
    RemediationAction,
)


class _NoopGitHubTools:
    """Dry-run tests do not need GitHub API behavior."""


def _provider_settings(provider: str) -> Settings:
    return Settings(
        _env_file=None,
        llm_provider=provider,
        azure_openai_deployment_name="gpt-5-mini",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_api_key="key",
        openai_compatible_model="gpt-4o-mini",
    )


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    reset_settings()
    yield
    reset_settings()


@pytest.mark.asyncio
async def test_diagnosis_pattern_fallback_parity_across_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When LLM calls fail transiently, both providers should fall back to identical pattern output."""

    log_analysis = LogAnalysis(
        job_id=1,
        job_name="lint",
        raw_logs="eslint error: Unexpected console statement",
        error_lines=["eslint error: Unexpected console statement"],
        summary="Linting failed",
    )

    async def _run(provider: str) -> tuple[FailureType, float, DiagnosisSource, str]:
        agent = DiagnosisAgent()
        agent._settings = _provider_settings(provider)  # noqa: SLF001 - test runtime override

        class _FailingAgent:
            async def run(self, prompt: str) -> str:
                _ = prompt
                raise TimeoutError()

        async def _fake_get_agent() -> _FailingAgent:
            return _FailingAgent()

        monkeypatch.setattr(agent, "_get_agent", _fake_get_agent)
        diagnosis = await agent.diagnose([log_analysis])
        return (
            diagnosis.failure_type,
            diagnosis.confidence,
            diagnosis.diagnosis_source or DiagnosisSource.PATTERN,
            diagnosis.root_cause,
        )

    azure = await _run("azure_openai")
    openai = await _run("openai_compatible")

    assert azure == openai
    assert azure[0] == FailureType.LINT
    assert azure[2] == DiagnosisSource.PATTERN


@pytest.mark.asyncio
async def test_remediation_dry_run_plan_parity_across_providers() -> None:
    """The same diagnosis should produce the same remediation dry-run plan across providers."""

    diagnosis = Diagnosis(
        failure_type=FailureType.DEPENDENCY,
        confidence=0.92,
        root_cause="Cannot find module 'left-pad'",
        affected_files=["package.json"],
        error_details={
            "package_name": "left-pad",
            "current_version": "1.1.0",
            "required_version": "1.3.0",
            "package_manager": "npm",
        },
        suggested_fix="Update left-pad dependency to required version.",
        is_auto_fixable=True,
        diagnosis_source=DiagnosisSource.LLM,
    )
    repository_info = {"name": "demo-repo", "owner": {"login": "owner"}, "default_branch": "main"}

    async def _run(provider: str) -> dict:
        agent = RemediationAgent(github_tools=_NoopGitHubTools())  # type: ignore[arg-type]
        agent._settings = _provider_settings(provider)  # noqa: SLF001 - test runtime override
        agent._fix_generators.set_heal_mode(agent._settings.heal_mode)  # noqa: SLF001
        result = await agent.remediate(
            diagnosis=diagnosis,
            repository_info=repository_info,
            workflow_run_id=123456,
            dry_run=True,
        )
        assert result.success is True
        assert result.action_taken == RemediationAction.CREATE_PR
        assert result.details is not None
        return result.details["plan"]

    azure_plan = await _run("azure_openai")
    openai_plan = await _run("openai_compatible")

    assert azure_plan == openai_plan
