"""Compatibility tests for cloud agent creation helpers."""

from src.agents.base import _as_agent_compat


class _ClientWithAsAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def as_agent(self, *, name: str, instructions: str) -> str:
        self.calls.append((name, instructions))
        return "agent-from-as-agent"


def test_as_agent_compat_prefers_client_as_agent() -> None:
    client = _ClientWithAsAgent()
    result = _as_agent_compat(client, name="demo", instructions="test")
    assert result == "agent-from-as-agent"
    assert client.calls == [("demo", "test")]


def test_as_agent_compat_falls_back_to_chat_agent(monkeypatch) -> None:
    class _ClientWithoutAsAgent:
        pass

    class _FakeChatAgent:
        def __init__(self, chat_client, instructions=None, *, name=None, **kwargs) -> None:
            self.chat_client = chat_client
            self.instructions = instructions
            self.name = name

    monkeypatch.setattr("agent_framework.ChatAgent", _FakeChatAgent, raising=False)

    client = _ClientWithoutAsAgent()
    result = _as_agent_compat(client, name="demo", instructions="test")

    assert isinstance(result, _FakeChatAgent)
    assert result.chat_client is client
    assert result.instructions == "test"
    assert result.name == "demo"


def test_as_agent_compat_falls_back_to_agent_when_chat_agent_missing(monkeypatch) -> None:
    class _ClientWithoutAsAgent:
        pass

    class _FakeAgent:
        def __init__(self, chat_client, instructions=None, *, name=None, **kwargs) -> None:
            self.chat_client = chat_client
            self.instructions = instructions
            self.name = name

    monkeypatch.delattr("agent_framework.ChatAgent", raising=False)
    monkeypatch.setattr("agent_framework.Agent", _FakeAgent, raising=False)

    client = _ClientWithoutAsAgent()
    result = _as_agent_compat(client, name="demo", instructions="test")

    assert isinstance(result, _FakeAgent)
    assert result.chat_client is client
    assert result.instructions == "test"
    assert result.name == "demo"
