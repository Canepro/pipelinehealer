"""Configuration management for PipelineHealer."""

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default="gpt-4o",
        description="Azure OpenAI deployment name",
    )
    azure_openai_api_version: str = Field(
        default="2025-03-01-preview",
        description="Azure OpenAI API version (Agent Framework Responses client requires 2025-03-01-preview or later)",
    )
    azure_openai_api_key: str = Field(
        default="",
        description="Azure OpenAI API key (optional; recommended for local dev if you don't want Azure CLI login)",
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
    github_private_key_secret_name: str = Field(
        default="github-app-private-key",
        description="Name of the secret in Key Vault containing GitHub App private key",
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

    # CORS
    cors_allowed_origins: list[str] = Field(
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
        description="Healing mode: 'safe' (conservative) or 'demo' (more aggressive, hackathon-friendly)",
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
    supported_failure_types: list[str] = Field(
        default=[
            "dependency",
            "test",
            "lint",
            "build_config",
            "timeout",
        ],
        description="List of failure types the agent can handle",
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
