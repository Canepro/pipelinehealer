from src.config import Settings
from src.llm.adapters import get_llm_provider_adapter


def test_azure_adapter_health_ok() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="azure_openai",
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_deployment_name="gpt-5-mini",
    )
    adapter = get_llm_provider_adapter(settings)
    health = adapter.health(settings)
    assert health["provider"] == "azure_openai"
    assert health["implemented"] is True
    assert health["available"] is True
    assert health["reason"] == "ok"


def test_placeholder_adapter_health_not_implemented() -> None:
    settings = Settings(_env_file=None, llm_provider="openai_compatible")
    adapter = get_llm_provider_adapter(settings)
    health = adapter.health(settings)
    assert health["provider"] == "openai_compatible"
    assert health["implemented"] is False
    assert health["available"] is False
    assert health["reason"] == "not_implemented"
