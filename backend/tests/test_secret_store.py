"""Tests for runtime secret storage backends."""

from __future__ import annotations

from typing import Any

import pytest

from src import secret_store
from src.config import reset_settings
from src.secret_store import (
    AzureKeyVaultSecretStore,
    EncryptedDatabaseSecretStore,
    build_secret_store,
)
from src.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SETTINGS_SECRET_BACKEND", raising=False)
    monkeypatch.delenv("SETTINGS_DB_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("KEY_VAULT_URL", raising=False)
    monkeypatch.delenv("SETTINGS_KEY_VAULT_PREFIX", raising=False)
    reset_settings()
    yield
    reset_settings()


@pytest.mark.asyncio
async def test_encrypted_db_secret_store_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETTINGS_SECRET_BACKEND", "encrypted_db")
    monkeypatch.setenv("SETTINGS_DB_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
    reset_settings()

    storage = InMemoryStorage()
    store = build_secret_store(storage)
    assert isinstance(store, EncryptedDatabaseSecretStore)

    await store.set("openai_compatible_api_key", "sk-test-1234567890")
    record = await store.get("openai_compatible_api_key")
    assert record is not None
    assert record.value == "sk-test-1234567890"

    metadata = await store.describe("openai_compatible_api_key")
    assert metadata.configured is True
    assert metadata.backend == "encrypted_db"
    assert metadata.safe_hint == "...7890"

    await store.delete("openai_compatible_api_key")
    assert await store.get("openai_compatible_api_key") is None
    assert (await store.describe("openai_compatible_api_key")).configured is False


class _FakeCredential:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeSecret:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeSecretClient:
    instances: list[_FakeSecretClient] = []

    def __init__(self, *, vault_url: str, credential: Any) -> None:
        self.vault_url = vault_url
        self.credential = credential
        self.closed = False
        self.secrets: dict[str, str] = {}
        self.deleted: list[str] = []
        _FakeSecretClient.instances.append(self)

    async def get_secret(self, name: str) -> _FakeSecret:
        return _FakeSecret(self.secrets[name])

    async def set_secret(self, name: str, value: str) -> None:
        self.secrets[name] = value

    async def delete_secret(self, name: str) -> None:
        self.deleted.append(name)
        self.secrets.pop(name, None)
        return None

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_azure_key_vault_secret_store_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETTINGS_SECRET_BACKEND", "azure_key_vault")
    monkeypatch.setenv("KEY_VAULT_URL", "https://vault.example.vault.azure.net/")
    monkeypatch.setenv("SETTINGS_KEY_VAULT_PREFIX", "ph-")
    reset_settings()

    monkeypatch.setattr(secret_store, "DefaultAzureCredential", _FakeCredential)
    monkeypatch.setattr(secret_store, "SecretClient", _FakeSecretClient)
    _FakeSecretClient.instances.clear()

    storage = InMemoryStorage()
    store = build_secret_store(storage)
    assert isinstance(store, AzureKeyVaultSecretStore)

    await store.set("agent_handoff_webhook_url", "https://agent.example.com/api/agent-handoff")
    metadata = await store.describe("agent_handoff_webhook_url")
    assert metadata.configured is True
    assert metadata.backend == "azure_key_vault"
    assert metadata.safe_hint == "agent.example.com"
    assert metadata.reference == "ph-agent-handoff-webhook-url"

    record = await store.get("agent_handoff_webhook_url")
    assert record is not None
    assert record.value == "https://agent.example.com/api/agent-handoff"
    assert record.safe_hint == "agent.example.com"

    await store.delete("agent_handoff_webhook_url")
    assert await store.get("agent_handoff_webhook_url") is None
    assert (await store.describe("agent_handoff_webhook_url")).configured is False

    client = _FakeSecretClient.instances[0]
    assert client.deleted == ["ph-agent-handoff-webhook-url"]
    await store.close()
    assert client.closed is True
    assert client.credential.closed is True
