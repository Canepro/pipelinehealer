from unittest.mock import patch

import httpx

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


def test_openai_compatible_adapter_reports_missing_config() -> None:
    settings = Settings(_env_file=None, llm_provider="openai_compatible")
    adapter = get_llm_provider_adapter(settings)
    health = adapter.health(settings)
    assert health["provider"] == "openai_compatible"
    assert health["implemented"] is True
    assert health["available"] is False
    assert health["reason"] == "missing_base_url"


def test_openai_compatible_adapter_reports_probe_timeout() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_model="gpt-4o-mini",
        openai_compatible_api_key="key",
    )
    adapter = get_llm_provider_adapter(settings)

    class _TimeoutClient:
        def __enter__(self):  # noqa: D401
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            _ = exc_type, exc, tb
            return False

        def get(self, *_args, **_kwargs):  # noqa: ANN002
            raise httpx.ReadTimeout("timed out")

    with patch("src.llm.adapters.httpx.Client", return_value=_TimeoutClient()):
        health = adapter.health(settings)

    assert health["available"] is False
    assert health["reason"] == "probe_timeout"


def test_openai_compatible_adapter_reports_probe_auth_failed() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_model="gpt-4o-mini",
        openai_compatible_api_key="key",
    )
    adapter = get_llm_provider_adapter(settings)

    class _AuthFailClient:
        def __enter__(self):  # noqa: D401
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            _ = exc_type, exc, tb
            return False

        def get(self, *_args, **_kwargs):  # noqa: ANN002
            request = httpx.Request("GET", "https://api.example.com/v1/models")
            response = httpx.Response(status_code=401, request=request)
            raise httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)

    with patch("src.llm.adapters.httpx.Client", return_value=_AuthFailClient()):
        health = adapter.health(settings)

    assert health["available"] is False
    assert health["reason"] == "probe_auth_failed"


def test_openai_compatible_adapter_reports_probe_rate_limited() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_compatible_base_url="https://api.example.com/v1",
        openai_compatible_model="gpt-4o-mini",
        openai_compatible_api_key="key",
    )
    adapter = get_llm_provider_adapter(settings)

    class _RateLimitedClient:
        def __enter__(self):  # noqa: D401
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            _ = exc_type, exc, tb
            return False

        def get(self, *_args, **_kwargs):  # noqa: ANN002
            request = httpx.Request("GET", "https://api.example.com/v1/models")
            response = httpx.Response(status_code=429, request=request)
            raise httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)

    with patch("src.llm.adapters.httpx.Client", return_value=_RateLimitedClient()):
        health = adapter.health(settings)

    assert health["available"] is False
    assert health["reason"] == "probe_rate_limited"


def test_codex_app_server_adapter_reports_stdio_ready() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="codex_app_server",
        codex_app_server_transport="stdio",
        codex_app_server_command="python3 --version",
        codex_app_server_model="gpt-5.4",
    )
    adapter = get_llm_provider_adapter(settings)
    health = adapter.health(settings)
    assert health["provider"] == "codex_app_server"
    assert health["implemented"] is True
    assert health["available"] is True
    assert health["reason"] == "ok"


def test_codex_app_server_adapter_reports_missing_websocket_auth() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="codex_app_server",
        codex_app_server_transport="websocket",
        codex_app_server_ws_url="ws://127.0.0.1:4500",
        codex_app_server_model="gpt-5.4",
    )
    adapter = get_llm_provider_adapter(settings)
    health = adapter.health(settings)
    assert health["available"] is False
    assert health["reason"] == "missing_ws_auth"


def test_codex_app_server_adapter_rejects_remote_websocket_without_opt_in() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="codex_app_server",
        codex_app_server_transport="websocket",
        codex_app_server_ws_url="wss://codex.example.com/app-server",
        codex_app_server_ws_bearer_token="token",
        codex_app_server_model="gpt-5.4",
    )
    adapter = get_llm_provider_adapter(settings)
    health = adapter.health(settings)
    assert health["available"] is False
    assert health["reason"] == "remote_ws_not_allowed"
