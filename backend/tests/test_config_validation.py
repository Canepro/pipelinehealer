from pydantic import ValidationError

from src.config import Settings


def test_rejects_malformed_azure_openai_endpoint_with_path() -> None:
    try:
        Settings(
            _env_file=None,
            azure_openai_endpoint="https://ai-foundry-canepro.cognitiveservices.azure.com/penai.azure.com/",
        )
    except ValidationError as exc:
        assert "base service URL only" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for malformed endpoint")


def test_accepts_valid_cognitiveservices_endpoint() -> None:
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://ai-foundry-canepro.cognitiveservices.azure.com/",
    )
    assert settings.azure_openai_endpoint == "https://ai-foundry-canepro.cognitiveservices.azure.com/"
