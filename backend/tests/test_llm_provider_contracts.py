"""Provider contract and runtime retry tests for model portability."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.base import create_cloud_agent
from src.agents.diagnosis import DiagnosisAgent
from src.config import Settings
from src.models import DiagnosisSource, FailureType, LogAnalysis


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "response_text"),
    [
        (
            "azure_openai",
            '{"failure_type":"build_config","confidence":0.81,"root_cause":"missing env var",'
            '"affected_files":[".github/workflows/ci.yml"],"is_auto_fixable":true,'
            '"suggested_fix":"add required env var","error_details":{"source":"azure"}}',
        ),
        (
            "openai_compatible",
            "Here is the diagnosis:\n```json\n"
            '{"failure_type":"build_config","confidence":0.81,"root_cause":"missing env var",'
            '"affected_files":[".github/workflows/ci.yml"],"is_auto_fixable":true,'
            '"suggested_fix":"add required env var","error_details":{"source":"openai_compatible"}}'
            "\n```",
        ),
    ],
)
async def test_diagnosis_contract_shape_is_consistent_across_provider_outputs(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    response_text: str,
) -> None:
    """Both provider paths must normalize into the same Diagnosis model shape."""
    log_analysis = LogAnalysis(
        job_id=1,
        job_name="ci",
        raw_logs="workflow failed unexpectedly",
        error_lines=["workflow failed unexpectedly"],
        summary="unknown failure",
    )

    settings = Settings(
        _env_file=None,
        llm_provider=provider,
        azure_openai_deployment_name="gpt-5-mini",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_api_key="key",
        openai_compatible_model="gpt-4o-mini",
    )

    agent = DiagnosisAgent()
    agent._settings = settings  # noqa: SLF001 - test override for provider path.

    class _FakeAgent:
        async def run(self, prompt: str) -> str:
            _ = prompt
            return response_text

    async def _fake_get_agent() -> _FakeAgent:
        return _FakeAgent()

    monkeypatch.setattr(agent, "_get_agent", _fake_get_agent)

    diagnosis = await agent.diagnose([log_analysis])

    assert diagnosis.failure_type == FailureType.BUILD_CONFIG
    assert diagnosis.diagnosis_source == DiagnosisSource.LLM
    assert diagnosis.confidence == pytest.approx(0.81)
    assert diagnosis.is_auto_fixable is True

    payload = diagnosis.model_dump()
    assert set(payload.keys()) == {
        "failure_type",
        "confidence",
        "root_cause",
        "affected_files",
        "error_details",
        "suggested_fix",
        "is_auto_fixable",
        "diagnosis_source",
    }
    assert isinstance(payload["affected_files"], list)
    assert isinstance(payload["error_details"], dict)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_message",
    [
        "HTTP 429 Too Many Requests",
        "HTTP 500 Internal Server Error",
        "connection timeout while calling model",
    ],
)
@patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
async def test_openai_compatible_provider_path_retries_transient_errors(
    mock_sleep: AsyncMock,
    error_message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI-compatible path must use shared retry/backoff policy for transient errors."""

    class _FlakyOpenAICompatibleAgent:
        run_calls = 0

        def __init__(self, *, base_url: str, api_key: str, model: str, instructions: str):
            _ = base_url, api_key, model, instructions

        async def run(self, prompt: str) -> str:
            _ = prompt
            type(self).run_calls += 1
            if type(self).run_calls == 1:
                raise Exception(error_message)
            return "ok"

    monkeypatch.setattr("src.agents.base.OpenAICompatibleAgent", _FlakyOpenAICompatibleAgent)

    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_api_key="key",
        openai_compatible_model="gpt-4o-mini",
    )

    runtime_agent = create_cloud_agent(
        name="Test",
        instructions="diag",
        credential=None,  # type: ignore[arg-type]
        settings=settings,
    )

    result = await runtime_agent.run("hello")
    assert result == "ok"
    assert _FlakyOpenAICompatibleAgent.run_calls == 2
    assert mock_sleep.call_count == 1


@pytest.mark.asyncio
@patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
async def test_openai_compatible_provider_path_does_not_retry_non_retryable_errors(
    mock_sleep: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI-compatible path should fail fast on non-retryable errors (for example 401)."""

    class _AuthFailingOpenAICompatibleAgent:
        run_calls = 0

        def __init__(self, *, base_url: str, api_key: str, model: str, instructions: str):
            _ = base_url, api_key, model, instructions

        async def run(self, prompt: str) -> str:
            _ = prompt
            type(self).run_calls += 1
            raise Exception("HTTP 401 Unauthorized")

    monkeypatch.setattr("src.agents.base.OpenAICompatibleAgent", _AuthFailingOpenAICompatibleAgent)

    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_api_key="key",
        openai_compatible_model="gpt-4o-mini",
    )

    runtime_agent = create_cloud_agent(
        name="Test",
        instructions="diag",
        credential=None,  # type: ignore[arg-type]
        settings=settings,
    )

    with pytest.raises(Exception, match="401"):
        await runtime_agent.run("hello")

    assert _AuthFailingOpenAICompatibleAgent.run_calls == 1
    assert mock_sleep.call_count == 0


@pytest.mark.asyncio
@patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
async def test_openai_compatible_provider_path_retries_timeout_without_message(
    mock_sleep: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI-compatible path should retry bare timeout exceptions (empty error message)."""

    class _TimeoutThenSuccessAgent:
        run_calls = 0

        def __init__(self, *, base_url: str, api_key: str, model: str, instructions: str):
            _ = base_url, api_key, model, instructions

        async def run(self, prompt: str) -> str:
            _ = prompt
            type(self).run_calls += 1
            if type(self).run_calls == 1:
                raise TimeoutError()
            return "ok"

    monkeypatch.setattr("src.agents.base.OpenAICompatibleAgent", _TimeoutThenSuccessAgent)

    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_api_key="key",
        openai_compatible_model="gpt-4o-mini",
    )

    runtime_agent = create_cloud_agent(
        name="Test",
        instructions="diag",
        credential=None,  # type: ignore[arg-type]
        settings=settings,
    )

    result = await runtime_agent.run("hello")
    assert result == "ok"
    assert _TimeoutThenSuccessAgent.run_calls == 2
    assert mock_sleep.call_count == 1
