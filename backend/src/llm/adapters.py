"""LLM provider adapters (phase 2 scaffold, Azure-first behavior)."""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from ..agents.base import validate_azure_openai_endpoint
from .providers import LLMProviderName, resolve_llm_provider


class LLMProviderAdapter(Protocol):
    """Provider adapter contract for health/introspection."""

    @property
    def name(self) -> LLMProviderName:
        """Adapter provider name."""

    def health(self, settings: Any) -> dict[str, Any]:
        """Return provider health/status payload."""


@dataclass(frozen=True)
class AzureOpenAIProviderAdapter:
    """Current production provider adapter."""

    name: LLMProviderName = LLMProviderName.AZURE_OPENAI

    def health(self, settings: Any) -> dict[str, Any]:
        endpoint = str(getattr(settings, "azure_openai_endpoint", "") or "").strip()
        deployment = str(getattr(settings, "azure_openai_deployment_name", "") or "").strip()
        api_version = str(getattr(settings, "azure_openai_api_version", "") or "").strip()

        if not endpoint:
            return {
                "provider": self.name.value,
                "implemented": True,
                "available": False,
                "reason": "missing_endpoint",
                "message": "AZURE_OPENAI_ENDPOINT is not configured.",
            }
        if not deployment:
            return {
                "provider": self.name.value,
                "implemented": True,
                "available": False,
                "reason": "missing_deployment",
                "message": "AZURE_OPENAI_DEPLOYMENT_NAME is not configured.",
            }

        try:
            validate_azure_openai_endpoint(endpoint)
        except Exception as exc:
            return {
                "provider": self.name.value,
                "implemented": True,
                "available": False,
                "reason": "invalid_endpoint",
                "message": str(exc),
            }

        return {
            "provider": self.name.value,
            "implemented": True,
            "available": True,
            "reason": "ok",
            "message": "Azure OpenAI provider configuration looks valid.",
            "endpoint": endpoint,
            "deployment_name": deployment,
            "api_version": api_version,
        }


@dataclass(frozen=True)
class PlaceholderProviderAdapter:
    """Placeholder adapters for future providers."""

    name: LLMProviderName

    def health(self, settings: Any) -> dict[str, Any]:
        _ = settings
        return {
            "provider": self.name.value,
            "implemented": False,
            "available": False,
            "reason": "not_implemented",
            "message": f"{self.name.value} provider adapter is scaffolded but not implemented yet.",
        }


@dataclass(frozen=True)
class OpenAICompatibleProviderAdapter:
    """OpenAI-compatible provider adapter with connectivity probe."""

    name: LLMProviderName = LLMProviderName.OPENAI_COMPATIBLE

    @staticmethod
    def _probe_error_payload(exc: Exception) -> dict[str, str]:
        """Normalize provider probe errors into actionable reason codes."""
        if isinstance(exc, httpx.TimeoutException):
            return {
                "reason": "probe_timeout",
                "message": "Provider probe timed out while calling /models.",
            }
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code if exc.response is not None else None
            if status in (401, 403):
                return {
                    "reason": "probe_auth_failed",
                    "message": f"Provider probe auth failed with HTTP {status}.",
                }
            if status == 429:
                return {
                    "reason": "probe_rate_limited",
                    "message": "Provider probe was rate limited (HTTP 429).",
                }
            if status is not None and status >= 500:
                return {
                    "reason": "probe_provider_error",
                    "message": f"Provider probe failed with server error HTTP {status}.",
                }
            return {
                "reason": "probe_http_error",
                "message": f"Provider probe failed with HTTP {status}.",
            }
        if isinstance(exc, httpx.RequestError):
            return {
                "reason": "probe_network_error",
                "message": f"Provider probe network failure: {exc}",
            }
        return {
            "reason": "connectivity_probe_failed",
            "message": f"Provider probe failed: {exc}",
        }

    def health(self, settings: Any) -> dict[str, Any]:
        base_url = str(getattr(settings, "openai_compatible_base_url", "") or "").strip()
        model = str(getattr(settings, "openai_compatible_model", "") or "").strip()
        api_key = str(getattr(settings, "openai_compatible_api_key", "") or "").strip()
        if not base_url:
            return {
                "provider": self.name.value,
                "implemented": True,
                "available": False,
                "reason": "missing_base_url",
                "message": "OPENAI_COMPATIBLE_BASE_URL is not configured.",
            }
        if not model:
            return {
                "provider": self.name.value,
                "implemented": True,
                "available": False,
                "reason": "missing_model",
                "message": "OPENAI_COMPATIBLE_MODEL is not configured.",
            }
        if not api_key:
            return {
                "provider": self.name.value,
                "implemented": True,
                "available": False,
                "reason": "missing_api_key",
                "message": "OPENAI_COMPATIBLE_API_KEY is not configured.",
            }

        probe_url = base_url.rstrip("/") + "/models"
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(probe_url, headers={"Authorization": f"Bearer {api_key}"})
                response.raise_for_status()
        except Exception as exc:
            normalized = self._probe_error_payload(exc)
            return {
                "provider": self.name.value,
                "implemented": True,
                "available": False,
                "reason": normalized["reason"],
                "message": normalized["message"],
            }

        return {
            "provider": self.name.value,
            "implemented": True,
            "available": True,
            "reason": "ok",
            "message": "OpenAI-compatible provider connectivity probe succeeded.",
            "endpoint": base_url,
            "deployment_name": model,
            "api_version": "",
        }


def get_llm_provider_adapter(settings: Any) -> LLMProviderAdapter:
    """Return adapter for current runtime provider selection."""
    provider = resolve_llm_provider(getattr(settings, "llm_provider", "azure_openai"))
    if provider == LLMProviderName.AZURE_OPENAI:
        return AzureOpenAIProviderAdapter()
    if provider == LLMProviderName.OPENAI_COMPATIBLE:
        return OpenAICompatibleProviderAdapter()
    return PlaceholderProviderAdapter(name=provider)
