"""Configuration management for PipelineHealer."""

import json
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .llm.providers import LLMProviderName, resolve_llm_provider


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Azure OpenAI Configuration
    azure_openai_endpoint: str = Field(
        default="",
        description="Azure OpenAI service endpoint",
    )
    azure_openai_deployment_name: str = Field(
        default="",
        description="Azure OpenAI deployment name (e.g. gpt-4o, gpt-5-mini)",
    )
    azure_openai_api_version: str = Field(
        default="2025-04-01-preview",
        description=(
            "Azure OpenAI API version for the primary (Responses) client. "
            "Also used for cognitiveservices.azure.com chat completions when set explicitly."
        ),
    )
    azure_openai_chat_api_version: str = Field(
        default="2024-12-01-preview",
        description=(
            "API version for the fallback Chat Completions client. "
            "Used when the primary Responses client returns an API-version error, "
            "and as the default for cognitiveservices.azure.com endpoints."
        ),
    )
    azure_openai_api_key: str = Field(
        default="",
        description="Azure OpenAI API key (optional; recommended for local dev if you don't want Azure CLI login)",
    )
    openai_compatible_base_url: str = Field(
        default="",
        description="Base URL for OpenAI-compatible API provider (e.g. https://api.openai.com/v1)",
    )
    openai_compatible_model: str = Field(
        default="",
        description="Model name for OpenAI-compatible provider (e.g. gpt-4o-mini, claude-compatible alias)",
    )
    openai_compatible_api_key: str = Field(
        default="",
        description="API key for OpenAI-compatible provider",
    )
    llm_provider: str = Field(
        default=LLMProviderName.AZURE_OPENAI.value,
        description=(
            "LLM provider backend. "
            "Current production path is azure_openai; other values are scaffolded for future expansion."
        ),
    )

    # Azure Cosmos DB Configuration
    cosmos_db_endpoint: str = Field(
        default="",
        description="Cosmos DB endpoint URL",
    )
    cosmos_db_database: str = Field(
        default="pipelinehealer",
        description="Cosmos DB database name",
    )

    # Azure Key Vault Configuration
    key_vault_url: str = Field(
        default="",
        description="Azure Key Vault URL",
    )

    # GitHub Configuration
    github_app_id: str = Field(
        default="",
        description="GitHub App ID",
    )
    github_webhook_secret: str = Field(
        default="",
        description="GitHub webhook secret for validation",
    )
    github_personal_access_token: str = Field(
        default="",
        description="GitHub personal access token (recommended for local dev)",
    )
    ph_allowed_repos: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Optional allowlist of repository full names (owner/repo). "
            "When set, webhook events for other repos are ignored."
        ),
    )
    github_private_key_secret_name: str = Field(
        default="github-app-private-key",
        description="Name of the secret in Key Vault containing GitHub App private key",
    )
    gh_aw_tools_enabled: bool = Field(
        default=False,
        description="Enable optional GitHub Agentic Workflows diagnostics integration hooks",
    )
    gh_aw_ingestion_mode: str = Field(
        default="disabled",
        description="External diagnostics ingestion mode: disabled or passive",
    )
    gh_aw_known_workflows: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "ci-doctor",
        ],
        description=(
            "Workflow names to skip when polling ci-doctor for external diagnostics. "
            "ci-doctor is always included to prevent circular self-diagnosis. "
            "Add others only if you explicitly want to suppress polling for them."
        ),
    )

    # Application Configuration
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production)",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    api_host: str = Field(
        default="0.0.0.0",
        description="API host to bind to",
    )
    api_port: int = Field(
        default=8000,
        description="API port to bind to",
    )
    api_auth_key: str = Field(
        default="",
        description="API key required for /api/* routes in non-development environments (sent via X-API-Key)",
    )
    admin_api_key: str = Field(
        default="",
        description="Admin API key required for admin settings operations (sent via X-Admin-Key)",
    )
    auth_mode: str = Field(
        default="api_key",
        description=(
            "Authentication mode for /api routes: "
            "'api_key' (legacy headers), 'entra' (OIDC bearer token), or "
            "'hybrid' (accept either)."
        ),
    )
    entra_tenant_id: str = Field(
        default="",
        description="Microsoft Entra tenant ID for OIDC token validation.",
    )
    entra_client_id: str = Field(
        default="",
        description="Application (client) ID used for backend token audience defaults.",
    )
    entra_issuer: str = Field(
        default="",
        description=(
            "Optional OIDC issuer override. "
            "Default: https://login.microsoftonline.com/<tenant-id>/v2.0"
        ),
    )
    entra_jwks_url: str = Field(
        default="",
        description=(
            "Optional JWKS URL override. "
            "Default: https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys"
        ),
    )
    entra_allowed_audiences: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Accepted JWT audience values for Entra bearer tokens. "
            "Defaults to ['api://<entra_client_id>', '<entra_client_id>'] when empty."
        ),
    )
    entra_admin_roles: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "PipelineHealer.Admin",
        ],
        description=(
            "Accepted Entra app-role (or scope) values for admin-only settings endpoints."
        ),
    )
    audit_salt: str = Field(
        default="",
        description="Optional salt used when generating admin actor fingerprints for audit entries",
    )

    # CORS
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
        ],
        description="Exact CORS allowed origins",
    )
    cors_allow_origin_regex: str = Field(
        default=r"https://.*\.azurecontainerapps\.io",
        description="Regex CORS allow-list for dynamic deploy hosts",
    )

    # Webhook verification policy
    verify_webhook_signature: bool = Field(
        default=True,
        description="Require GitHub webhook signature verification",
    )
    verify_webhook_signature_in_development: bool = Field(
        default=False,
        description="Also require webhook signature verification in development",
    )

    # Application Insights
    applicationinsights_connection_string: str = Field(
        default="",
        description="Application Insights connection string",
    )

    # Agent Configuration
    heal_mode: str = Field(
        default="safe",
        description=(
            "Healing mode: 'safe' (conservative), 'demo' (aggressive, hackathon-friendly), "
            "or 'debug' (same behavior as safe with verbose diagnostic logging)"
        ),
    )
    max_remediation_attempts: int = Field(
        default=3,
        description="Maximum number of remediation attempts per failure",
    )
    auto_create_pr: bool = Field(
        default=True,
        description="Automatically create PRs for fixes",
    )
    auto_create_tracking_issue_for_prs: bool = Field(
        default=True,
        description="Create a tracking issue for PR-based remediations and close it automatically on merge",
    )
    pipeline_step_timeout_seconds: float = Field(
        default=120.0,
        description="Per-step timeout (seconds) for analyze/diagnose/remediate orchestration steps",
    )
    github_api_max_retries: int = Field(
        default=3,
        description="Maximum GitHub API retries for retryable failures (429/5xx and transient network errors)",
    )
    github_api_retry_base_seconds: float = Field(
        default=0.5,
        description="Base backoff delay for GitHub API retries",
    )
    github_api_retry_max_seconds: float = Field(
        default=8.0,
        description="Maximum backoff delay for GitHub API retries",
    )
    log_prompt_max_chars: int = Field(
        default=18000,
        description="Max log characters to send to the LLM prompt",
    )
    log_prompt_head_chars: int = Field(
        default=9000,
        description="Head characters to keep when truncating logs for prompt context",
    )
    log_prompt_tail_chars: int = Field(
        default=9000,
        description="Tail characters to keep when truncating logs for prompt context",
    )
    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: Any) -> Any:
        """Allow CORS origins from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @field_validator("ph_allowed_repos", mode="before")
    @classmethod
    def parse_allowed_repos(cls, value: Any) -> Any:
        """Allow repo allowlist from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [repo.strip() for repo in text.split(",") if repo.strip()]
        if isinstance(value, list):
            return [str(repo).strip() for repo in value if str(repo).strip()]
        return value

    @field_validator("gh_aw_known_workflows", mode="before")
    @classmethod
    def parse_gh_aw_known_workflows(cls, value: Any) -> Any:
        """Allow known gh-aw workflows from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [workflow.strip() for workflow in text.split(",") if workflow.strip()]
        if isinstance(value, list):
            return [str(workflow).strip() for workflow in value if str(workflow).strip()]
        return value

    @field_validator("entra_allowed_audiences", mode="before")
    @classmethod
    def parse_entra_allowed_audiences(cls, value: Any) -> Any:
        """Allow Entra audiences from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [audience.strip() for audience in text.split(",") if audience.strip()]
        if isinstance(value, list):
            return [str(audience).strip() for audience in value if str(audience).strip()]
        return value

    @field_validator("entra_admin_roles", mode="before")
    @classmethod
    def parse_entra_admin_roles(cls, value: Any) -> Any:
        """Allow Entra role list from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [role.strip() for role in text.split(",") if role.strip()]
        if isinstance(value, list):
            return [str(role).strip() for role in value if str(role).strip()]
        return value

    @field_validator("auth_mode")
    @classmethod
    def validate_auth_mode(cls, value: str) -> str:
        """Validate API auth mode."""
        normalized = value.strip().lower()
        if normalized not in {"api_key", "entra", "hybrid"}:
            raise ValueError("AUTH_MODE must be one of: api_key, entra, hybrid")
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        """Validate LLM provider selection."""
        return resolve_llm_provider(value).value

    @field_validator("gh_aw_ingestion_mode")
    @classmethod
    def validate_gh_aw_ingestion_mode(cls, value: str) -> str:
        """Validate external diagnostics ingestion mode."""
        normalized = value.strip().lower()
        if normalized not in {"disabled", "passive"}:
            raise ValueError("GH_AW_INGESTION_MODE must be one of: disabled, passive")
        return normalized

    @field_validator("azure_openai_endpoint")
    @classmethod
    def validate_azure_openai_endpoint(cls, value: str) -> str:
        """Validate endpoint shape to catch common copy/paste mistakes early."""
        endpoint = value.strip()
        if not endpoint:
            return endpoint

        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AZURE_OPENAI_ENDPOINT must be a full URL, e.g. https://<resource>.cognitiveservices.azure.com/")

        # Endpoint should be the service root, not a nested path or concatenated URL.
        if parsed.path and parsed.path != "/":
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT must be a base service URL only (no path). "
                "Example: https://<resource>.cognitiveservices.azure.com/"
            )

        if "openai.azure.com" in parsed.path or "cognitiveservices.azure.com" in parsed.path:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT appears malformed (domain found inside path). "
                "Use only the base endpoint URL."
            )

        return endpoint

    @field_validator("openai_compatible_base_url")
    @classmethod
    def validate_openai_compatible_base_url(cls, value: str) -> str:
        """Validate OpenAI-compatible base URL."""
        base_url = value.strip()
        if not base_url:
            return base_url
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "OPENAI_COMPATIBLE_BASE_URL must be a full URL, e.g. https://api.openai.com/v1"
            )
        return base_url


_settings_singleton: Settings | None = None


def get_settings() -> Settings:
    """Get the application settings singleton.

    Returns a single ``Settings`` instance for the lifetime of the process.
    The object is intentionally mutable at runtime — admin endpoints use
    ``setattr`` to apply in-flight overrides (e.g. ``HEAL_MODE``,
    ``AUTO_CREATE_PR``).  Using an explicit module-level singleton instead
    of ``@lru_cache`` makes this mutation contract visible and avoids
    accidental cache invalidation losing runtime changes.
    """
    global _settings_singleton
    if _settings_singleton is None:
        _settings_singleton = Settings()
    return _settings_singleton


def reset_settings() -> None:
    """Reset the settings singleton (for tests only)."""
    global _settings_singleton
    _settings_singleton = None
