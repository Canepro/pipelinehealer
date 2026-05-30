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


def test_accepts_infisical_secret_backend() -> None:
    settings = Settings(
        _env_file=None,
        settings_secret_backend="infisical",
        infisical_project_id="project-id",
    )
    assert settings.settings_secret_backend == "infisical"
    assert settings.infisical_project_id == "project-id"


def test_accepts_agent_control_plane_targets() -> None:
    settings = Settings(
        _env_file=None,
        agent_handoff_default_target="openclaw",
        agent_handoff_enabled_targets="codex_app_server,openclaw,hermes",
    )
    assert settings.agent_handoff_default_target == "openclaw"
    assert settings.agent_handoff_enabled_targets == [
        "codex_app_server",
        "openclaw",
        "hermes",
    ]


def test_rejects_default_agent_handoff_target_not_enabled() -> None:
    try:
        Settings(
            _env_file=None,
            agent_handoff_default_target="custom",
            agent_handoff_enabled_targets="codex_app_server,openclaw,hermes",
        )
    except ValidationError as exc:
        assert (
            "AGENT_HANDOFF_DEFAULT_TARGET must be included in "
            "AGENT_HANDOFF_ENABLED_TARGETS"
        ) in str(exc)
    else:
        raise AssertionError("Expected ValidationError for disabled default handoff target")


def test_rejects_invalid_codex_app_server_transport() -> None:
    try:
        Settings(
            _env_file=None,
            codex_app_server_transport="bad_transport",
        )
    except ValidationError as exc:
        assert "CODEX_APP_SERVER_TRANSPORT must be one of" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid Codex App Server transport")


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
