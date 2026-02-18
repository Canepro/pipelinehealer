from src.config import Settings
from src.tools.mcp_provider import get_mcp_provider


def test_mcp_disabled_provider_health() -> None:
    settings = Settings(_env_file=None, mcp_enabled=False, mcp_provider="disabled")
    provider = get_mcp_provider(settings)
    health = provider.health(settings)
    assert health.provider == "disabled"
    assert health.enabled is False
    assert health.available is False
    assert health.reason == "disabled"


def test_mcp_github_provider_requires_token() -> None:
    settings = Settings(
        _env_file=None,
        mcp_enabled=True,
        mcp_provider="github",
        github_personal_access_token="",
    )
    provider = get_mcp_provider(settings)
    health = provider.health(settings)
    assert health.provider == "github"
    assert health.enabled is True
    assert health.available is False
    assert health.reason == "missing_github_token"


def test_mcp_github_provider_health_ok_when_token_exists() -> None:
    settings = Settings(
        _env_file=None,
        mcp_enabled=True,
        mcp_provider="github",
        github_personal_access_token="token",
    )
    provider = get_mcp_provider(settings)
    health = provider.health(settings)
    assert health.provider == "github"
    assert health.enabled is True
    assert health.available is True
    assert health.reason == "ok"
    assert "fetch_failure_context" in health.configured_tools
    assert "fetch_runbook_context" in health.configured_tools
