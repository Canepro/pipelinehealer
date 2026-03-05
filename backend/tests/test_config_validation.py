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


def test_parses_mcp_tool_policies_from_csv() -> None:
    settings = Settings(
        _env_file=None,
        mcp_tool_policies="fetch_failure_context=read_only,publish_artifact=disabled",
    )
    assert settings.mcp_tool_policies == {
        "fetch_failure_context": "read_only",
        "publish_artifact": "disabled",
    }


def test_rejects_invalid_mcp_tool_policy_mode() -> None:
    try:
        Settings(
            _env_file=None,
            mcp_tool_policies="fetch_failure_context=bad_mode",
        )
    except ValidationError as exc:
        assert "MCP_TOOL_POLICIES values must be one of" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid MCP tool policy mode")


def test_accepts_hybrid_gh_aw_ingestion_mode() -> None:
    settings = Settings(
        _env_file=None,
        gh_aw_ingestion_mode="hybrid",
    )
    assert settings.gh_aw_ingestion_mode == "hybrid"


def test_accepts_postgres_storage_mode() -> None:
    settings = Settings(
        _env_file=None,
        storage_mode="postgres",
    )
    assert settings.storage_mode == "postgres"


def test_rejects_invalid_storage_mode() -> None:
    try:
        Settings(
            _env_file=None,
            storage_mode="sqlite",
        )
    except ValidationError as exc:
        assert "STORAGE_MODE must be one of: memory, cosmos, postgres" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid storage_mode")
