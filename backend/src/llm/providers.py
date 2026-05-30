"""Provider selection primitives for model platform portability."""

from enum import StrEnum


class LLMProviderName(StrEnum):
    """Supported LLM provider IDs."""

    AZURE_OPENAI = "azure_openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    CODEX_APP_SERVER = "codex_app_server"
    CUSTOM = "custom"


def resolve_llm_provider(value: str | None) -> LLMProviderName:
    """Resolve a provider string into a supported enum value."""
    normalized = (value or "").strip().lower()
    if not normalized:
        return LLMProviderName.AZURE_OPENAI
    try:
        return LLMProviderName(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LLMProviderName)
        raise ValueError(f"LLM_PROVIDER must be one of: {allowed}") from exc
