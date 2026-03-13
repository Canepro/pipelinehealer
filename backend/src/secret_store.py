"""Runtime secret storage backends for UI-managed sensitive settings."""

import base64
import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from azure.identity.aio import DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings
from .storage import ActivityStorage


class SecretStoreError(RuntimeError):
    """Raised when runtime secret storage is not available."""


@dataclass(frozen=True)
class SecretRecord:
    """Resolved secret value plus storage metadata."""

    logical_key: str
    value: str
    backend: str
    last_updated_at: str | None = None
    safe_hint: str | None = None


@dataclass(frozen=True)
class SecretMetadata:
    """Non-sensitive runtime metadata about one secret."""

    logical_key: str
    backend: str
    configured: bool
    last_updated_at: str | None = None
    safe_hint: str | None = None
    reference: str | None = None


def _derive_secret_hint(logical_key: str, plaintext: str) -> str | None:
    value = plaintext.strip()
    if not value:
        return None
    if logical_key == "agent_handoff_webhook_url":
        parsed = urlparse(value)
        host = (parsed.hostname or "").strip().lower()
        return host or None
    if len(value) <= 4:
        return None
    return f"...{value[-4:]}"


class SecretStore:
    """Abstract interface for runtime-managed secret storage."""

    backend_name = "unknown"

    async def get(self, logical_key: str) -> SecretRecord | None:
        raise NotImplementedError

    async def set(self, logical_key: str, plaintext: str, metadata: dict[str, Any] | None = None) -> None:
        raise NotImplementedError

    async def delete(self, logical_key: str) -> None:
        raise NotImplementedError

    async def describe(self, logical_key: str) -> SecretMetadata:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class EncryptedDatabaseSecretStore(SecretStore):
    """Stores encrypted secret blobs in the app's durable storage backend."""

    backend_name = "encrypted_db"

    def __init__(self, storage: ActivityStorage, *, master_key: str) -> None:
        self._storage = storage
        self._master_key = master_key.strip()

    def _aes_key(self) -> bytes:
        if not self._master_key:
            raise SecretStoreError(
                "SETTINGS_DB_ENCRYPTION_KEY must be configured to manage runtime secrets"
            )
        candidate = self._master_key.encode("utf-8")
        try:
            decoded = base64.urlsafe_b64decode(candidate + b"=" * (-len(candidate) % 4))
        except Exception:
            decoded = b""
        if len(decoded) == 32:
            return decoded
        return hashlib.sha256(candidate).digest()

    async def get(self, logical_key: str) -> SecretRecord | None:
        payload = await self._storage.get_runtime_secret_record(logical_key)
        if payload is None:
            return None
        aesgcm = AESGCM(self._aes_key())
        nonce = base64.b64decode(str(payload.get("nonce", "")))
        ciphertext = base64.b64decode(str(payload.get("ciphertext", "")))
        plaintext = aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
        return SecretRecord(
            logical_key=logical_key,
            value=plaintext,
            backend=self.backend_name,
            last_updated_at=str(payload.get("updated_at") or "") or None,
            safe_hint=str(payload.get("safe_hint") or "") or None,
        )

    async def set(self, logical_key: str, plaintext: str, metadata: dict[str, Any] | None = None) -> None:
        aesgcm = AESGCM(self._aes_key())
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = {
            "backend": self.backend_name,
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "key_version": 1,
            "safe_hint": _derive_secret_hint(logical_key, plaintext),
        }
        if metadata:
            payload["metadata"] = dict(metadata)
        await self._storage.upsert_runtime_secret_record(logical_key, payload)

    async def delete(self, logical_key: str) -> None:
        await self._storage.delete_runtime_secret_record(logical_key)

    async def describe(self, logical_key: str) -> SecretMetadata:
        payload = await self._storage.get_runtime_secret_record(logical_key)
        if payload is None:
            return SecretMetadata(logical_key=logical_key, backend=self.backend_name, configured=False)
        return SecretMetadata(
            logical_key=logical_key,
            backend=self.backend_name,
            configured=True,
            last_updated_at=str(payload.get("updated_at") or "") or None,
            safe_hint=str(payload.get("safe_hint") or "") or None,
        )


class AzureKeyVaultSecretStore(SecretStore):
    """Stores runtime secrets in Azure Key Vault and only metadata in app storage."""

    backend_name = "azure_key_vault"

    def __init__(self, storage: ActivityStorage, *, vault_url: str, prefix: str) -> None:
        self._storage = storage
        self._vault_url = vault_url.strip()
        self._prefix = prefix.strip() or "pipelinehealer-"
        self._credential: DefaultAzureCredential | None = None
        self._client: SecretClient | None = None

    async def _client_required(self) -> SecretClient:
        if not self._vault_url:
            raise SecretStoreError("KEY_VAULT_URL must be configured to manage runtime secrets")
        if self._client is None:
            self._credential = DefaultAzureCredential()
            self._client = SecretClient(vault_url=self._vault_url, credential=self._credential)
        return self._client

    def _secret_name(self, logical_key: str) -> str:
        normalized = re.sub(r"[^a-z0-9-]", "-", logical_key.strip().lower().replace("_", "-"))
        normalized = re.sub(r"-+", "-", normalized).strip("-")
        return f"{self._prefix}{normalized}"

    async def get(self, logical_key: str) -> SecretRecord | None:
        payload = await self._storage.get_runtime_secret_record(logical_key)
        if payload is None:
            return None
        secret_name = str(payload.get("reference") or self._secret_name(logical_key))
        client = await self._client_required()
        secret = await client.get_secret(secret_name)
        return SecretRecord(
            logical_key=logical_key,
            value=secret.value or "",
            backend=self.backend_name,
            last_updated_at=str(payload.get("updated_at") or "") or None,
            safe_hint=str(payload.get("safe_hint") or "") or None,
        )

    async def set(self, logical_key: str, plaintext: str, metadata: dict[str, Any] | None = None) -> None:
        secret_name = self._secret_name(logical_key)
        client = await self._client_required()
        await client.set_secret(secret_name, plaintext)
        payload: dict[str, Any] = {
            "backend": self.backend_name,
            "reference": secret_name,
            "safe_hint": _derive_secret_hint(logical_key, plaintext),
        }
        if metadata:
            payload["metadata"] = dict(metadata)
        await self._storage.upsert_runtime_secret_record(logical_key, payload)

    async def delete(self, logical_key: str) -> None:
        payload = await self._storage.get_runtime_secret_record(logical_key)
        if payload is not None:
            secret_name = str(payload.get("reference") or self._secret_name(logical_key))
            client = await self._client_required()
            await client.delete_secret(secret_name)
        await self._storage.delete_runtime_secret_record(logical_key)

    async def describe(self, logical_key: str) -> SecretMetadata:
        payload = await self._storage.get_runtime_secret_record(logical_key)
        if payload is None:
            return SecretMetadata(logical_key=logical_key, backend=self.backend_name, configured=False)
        return SecretMetadata(
            logical_key=logical_key,
            backend=self.backend_name,
            configured=True,
            last_updated_at=str(payload.get("updated_at") or "") or None,
            safe_hint=str(payload.get("safe_hint") or "") or None,
            reference=str(payload.get("reference") or "") or None,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
        if self._credential is not None:
            await self._credential.close()


def build_secret_store(storage: ActivityStorage) -> SecretStore:
    """Create the configured runtime secret store for the current process."""
    settings = get_settings()
    if settings.settings_secret_backend == "azure_key_vault":
        return AzureKeyVaultSecretStore(
            storage,
            vault_url=settings.key_vault_url,
            prefix=settings.settings_key_vault_prefix,
        )
    return EncryptedDatabaseSecretStore(storage, master_key=settings.settings_db_encryption_key)
