from pydantic import ValidationError

from src.agents.base import NoopAgent, create_cloud_agent
from src.config import Settings
from src.llm.providers import LLMProviderName, resolve_llm_provider


def test_resolve_llm_provider_defaults_to_azure() -> None:
    assert resolve_llm_provider(None) == LLMProviderName.AZURE_OPENAI
    assert resolve_llm_provider("") == LLMProviderName.AZURE_OPENAI


def test_resolve_llm_provider_accepts_supported_values() -> None:
    assert resolve_llm_provider("azure_openai") == LLMProviderName.AZURE_OPENAI
    assert resolve_llm_provider("openai_compatible") == LLMProviderName.OPENAI_COMPATIBLE
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
