import pytest
from pydantic import ValidationError

from src.agents.base import NoopAgent, _resolve_model_for_task, create_cloud_agent
from src.config import Settings
from src.llm.codex_app_server import CodexAppServerAgent
from src.llm.providers import LLMProviderName, resolve_llm_provider


def test_resolve_llm_provider_defaults_to_azure() -> None:
    assert resolve_llm_provider(None) == LLMProviderName.AZURE_OPENAI
    assert resolve_llm_provider("") == LLMProviderName.AZURE_OPENAI


def test_resolve_llm_provider_accepts_supported_values() -> None:
    assert resolve_llm_provider("azure_openai") == LLMProviderName.AZURE_OPENAI
    assert resolve_llm_provider("openai_compatible") == LLMProviderName.OPENAI_COMPATIBLE
    assert resolve_llm_provider("codex_app_server") == LLMProviderName.CODEX_APP_SERVER
    assert resolve_llm_provider("custom") == LLMProviderName.CUSTOM


def test_resolve_llm_provider_rejects_invalid_value() -> None:
    try:
        resolve_llm_provider("some_new_provider")
    except ValueError as exc:
        assert "LLM_PROVIDER must be one of" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid LLM provider")


def test_settings_validate_llm_provider() -> None:
    settings = Settings(_env_file=None, llm_provider="openai_compatible")
    assert settings.llm_provider == "openai_compatible"


def test_settings_reject_invalid_llm_provider() -> None:
    try:
        Settings(_env_file=None, llm_provider="bad_provider")
    except ValidationError as exc:
        assert "LLM_PROVIDER must be one of" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid LLM provider")


def test_create_cloud_agent_returns_noop_for_custom_provider() -> None:
    settings = Settings(_env_file=None, llm_provider="custom")
    agent = create_cloud_agent(
        name="Test",
        instructions="test",
        credential=None,  # type: ignore[arg-type]
        settings=settings,
    )
    assert isinstance(agent, NoopAgent)


def test_create_cloud_agent_openai_compatible_without_required_config_returns_noop() -> None:
    settings = Settings(_env_file=None, llm_provider="openai_compatible")
    agent = create_cloud_agent(
        name="Test",
        instructions="test",
        credential=None,  # type: ignore[arg-type]
        settings=settings,
    )
    assert isinstance(agent, NoopAgent)


def test_resolve_model_for_task_uses_task_override_first() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="azure_openai",
        azure_openai_deployment_name="gpt-5-mini",
        llm_model_analysis="gpt-5-mini-fast",
    )
    model = _resolve_model_for_task(
        settings=settings,
        provider=LLMProviderName.AZURE_OPENAI,
        task="analysis",
    )
    assert model == "gpt-5-mini-fast"


def test_resolve_model_for_task_falls_back_to_provider_default() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_model="gpt-4o-mini",
    )
    model = _resolve_model_for_task(
        settings=settings,
        provider=LLMProviderName.OPENAI_COMPATIBLE,
        task="diagnosis",
    )
    assert model == "gpt-4o-mini"


def test_resolve_model_for_patch_drafting_uses_remediation_override() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="azure_openai",
        azure_openai_deployment_name="gpt-5-mini",
        llm_model_remediation="gpt-5.1-codex-mini",
    )
    model = _resolve_model_for_task(
        settings=settings,
        provider=LLMProviderName.AZURE_OPENAI,
        task="patch_drafting",
    )
    assert model == "gpt-5.1-codex-mini"


def test_create_cloud_agent_openai_compatible_accepts_task_override_model() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_base_url="https://api.openai.com/v1",
        openai_compatible_api_key="test-key",
        openai_compatible_model="",
        llm_model_analysis="gpt-4o-mini",
    )
    agent = create_cloud_agent(
        name="Test",
        instructions="test",
        credential=None,  # type: ignore[arg-type]
        task="analysis",
        settings=settings,
    )
    assert not isinstance(agent, NoopAgent)


def test_resolve_model_for_task_uses_codex_app_server_model() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="codex_app_server",
        codex_app_server_model="gpt-5.4",
    )
    model = _resolve_model_for_task(
        settings=settings,
        provider=LLMProviderName.CODEX_APP_SERVER,
        task="diagnosis",
    )
    assert model == "gpt-5.4"


def test_create_cloud_agent_codex_app_server_returns_runtime_agent() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="codex_app_server",
        codex_app_server_model="gpt-5.4",
    )
    agent = create_cloud_agent(
        name="Test",
        instructions="test",
        credential=None,  # type: ignore[arg-type]
        settings=settings,
    )
    assert not isinstance(agent, NoopAgent)


@pytest.mark.asyncio
async def test_codex_app_server_runtime_rejects_remote_websocket_without_opt_in() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="codex_app_server",
        codex_app_server_transport="websocket",
        codex_app_server_ws_url="wss://codex.example.com/app-server",
        codex_app_server_ws_bearer_token="token",
    )
    agent = CodexAppServerAgent(settings=settings, instructions="test")

    with pytest.raises(RuntimeError, match="ALLOW_REMOTE"):
        await agent._run_websocket("prompt")
