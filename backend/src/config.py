"""Configuration management for PipelineHealer."""

from functools import lru_cache

from pydantic import Field
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
        default="2024-10-21",
        description="Azure OpenAI API version",
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

    # Application Insights
    applicationinsights_connection_string: str = Field(
        default="",
        description="Application Insights connection string",
    )

    # Agent Configuration
    max_remediation_attempts: int = Field(
        default=3,
        description="Maximum number of remediation attempts per failure",
    )
    auto_create_pr: bool = Field(
        default=True,
        description="Automatically create PRs for fixes",
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
