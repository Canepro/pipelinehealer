from src.agents.base import FallbackAgent, _create_azure_cloud_agent
from src.config import Settings


def test_cognitiveservices_endpoint_uses_responses_with_chat_fallback(monkeypatch) -> None:
    class _FakeResponsesClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class _FakeChatClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(
        "agent_framework.azure.AzureOpenAIResponsesClient",
        _FakeResponsesClient,
        raising=False,
    )
    monkeypatch.setattr(
        "agent_framework.azure.AzureOpenAIChatClient",
        _FakeChatClient,
        raising=False,
    )
    monkeypatch.setattr(
        "src.agents.base._as_agent_compat",
        lambda client, *, name, instructions: {
            "client_type": type(client).__name__,
            "name": name,
            "instructions": instructions,
            "kwargs": client.kwargs,
        },
    )

    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.cognitiveservices.azure.com/",
        azure_openai_deployment_name="gpt-5.1-codex-mini",
        azure_openai_api_key="key",
        azure_openai_api_version="2025-04-01-preview",
        azure_openai_chat_api_version="2024-12-01-preview",
    )

    agent = _create_azure_cloud_agent(
        name="demo",
        instructions="test",
        credential=None,
        settings=settings,
    )

    assert isinstance(agent, FallbackAgent)
    assert agent._primary["client_type"] == "_FakeResponsesClient"
    assert agent._primary["kwargs"]["endpoint"] == "https://example.cognitiveservices.azure.com/"
    assert agent._primary["kwargs"]["api_version"] == "2025-04-01-preview"
    assert agent._fallback["client_type"] == "_FakeChatClient"
    assert agent._fallback["kwargs"]["api_version"] == "2024-12-01-preview"
