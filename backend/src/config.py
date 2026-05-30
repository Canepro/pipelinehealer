"""Configuration management for PipelineHealer."""

import json
import os
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
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
            "Used first for both openai.azure.com and cognitiveservices.azure.com endpoints."
        ),
    )
    azure_openai_chat_api_version: str = Field(
        default="2024-12-01-preview",
        description=(
            "API version for the fallback Chat Completions client. "
            "Used when the primary Responses client returns a compatibility error."
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
    llm_model_analysis: str = Field(
        default="",
        description=(
            "Optional model/deployment override for analysis tasks. "
            "When empty, provider default model is used."
        ),
    )
    llm_model_diagnosis: str = Field(
        default="",
        description=(
            "Optional model/deployment override for diagnosis tasks. "
            "When empty, provider default model is used."
        ),
    )
    llm_model_remediation: str = Field(
        default="",
        description=(
            "Optional model/deployment override for remediation tasks. "
            "When empty, provider default model is used."
        ),
    )
    openai_compatible_api_key: str = Field(
        default="",
        description="API key for OpenAI-compatible provider",
    )
    codex_app_server_transport: str = Field(
        default="stdio",
        description="Codex App Server transport for model-backed turns: stdio or websocket",
    )
    codex_app_server_command: str = Field(
        default="codex app-server",
        description="Command used when CODEX_APP_SERVER_TRANSPORT=stdio",
    )
    codex_app_server_model: str = Field(
        default="gpt-5.4",
        description="Codex model requested when LLM_PROVIDER=codex_app_server",
    )
    codex_app_server_turn_timeout_ms: int = Field(
        default=120000,
        description="Maximum time to wait for one Codex App Server turn",
    )
    codex_app_server_ws_url: str = Field(
        default="",
        description="WebSocket URL used when CODEX_APP_SERVER_TRANSPORT=websocket",
    )
    codex_app_server_ws_allow_remote: bool = Field(
        default=False,
        description="Allow non-loopback Codex App Server WebSocket endpoints",
    )
    codex_app_server_ws_bearer_token: str = Field(
        default="",
        description="Bearer token for authenticated Codex App Server WebSocket transport",
    )
    codex_app_server_ws_token_file: str = Field(
        default="",
        description="File containing a Codex App Server WebSocket capability token",
    )
    codex_app_server_ws_shared_secret_file: str = Field(
        default="",
        description="File containing a Codex App Server WebSocket shared secret",
    )
    llm_provider: str = Field(
        default=LLMProviderName.AZURE_OPENAI.value,
        description=(
            "LLM provider backend. "
            "Current production path is azure_openai; other values are scaffolded for future expansion."
        ),
    )
    mcp_enabled: bool = Field(
        default=False,
        description="Enable MCP provider integration hooks",
    )
    mcp_provider: str = Field(
        default="disabled",
        description="MCP provider backend: disabled, github, azure_monitor, or custom",
    )
    mcp_read_only: bool = Field(
        default=True,
        description="Allow only read-only MCP actions",
    )
    mcp_timeout_seconds: float = Field(
        default=15.0,
        description="Timeout budget for MCP provider calls",
    )
    mcp_max_retries: int = Field(
        default=1,
        description="Retry budget for MCP provider calls",
    )
    mcp_tool_policies: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict,
        description=(
            "Per-tool MCP policy map. "
            "Supported modes: disabled, read_only, write_with_approval, auto."
        ),
    )
    mcp_repo_allowlist: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Optional MCP-specific repository allowlist (owner/repo). "
            "When set, MCP tool calls are blocked for repos not in this list."
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
    postgres_dsn: str = Field(
        default="",
        description=(
            "PostgreSQL DSN for durable storage when STORAGE_MODE=postgres. "
            "Example: postgresql://user:pass@host:5432/pipelinehealer"
        ),
    )

    # Azure Key Vault Configuration
    key_vault_url: str = Field(
        default="",
        description="Azure Key Vault URL",
    )
    settings_secret_backend: str = Field(
        default="encrypted_db",
        description="Secret backend for runtime-managed secrets: encrypted_db or azure_key_vault",
    )
    settings_db_encryption_key: str = Field(
        default="",
        description="Master key used for encrypted_db runtime secret storage",
    )
    settings_key_vault_prefix: str = Field(
        default="pipelinehealer-",
        description="Prefix used for logical runtime secrets stored in Azure Key Vault",
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
    jenkins_bridge_enabled: bool = Field(
        default=False,
        description="Enable signed Jenkins bridge webhook ingestion",
    )
    jenkins_bridge_shared_secret: str = Field(
        default="",
        description="Shared secret used to verify Jenkins bridge HMAC signatures",
    )
    jenkins_bridge_max_skew_seconds: int = Field(
        default=300,
        description="Maximum allowed timestamp skew for Jenkins bridge requests",
    )
    jenkins_bridge_replay_ttl_seconds: int = Field(
        default=86400,
        description="Replay window TTL for Jenkins bridge nonce/delivery tracking",
    )
    jenkins_bridge_max_body_bytes: int = Field(
        default=524288,
        description="Maximum accepted Jenkins bridge request body size in bytes",
    )
    jenkins_bridge_allow_pr: bool = Field(
        default=False,
        description=(
            "Allow Jenkins bridge sourced remediations to publish PR artifacts when "
            "AUTO_CREATE_PR is also enabled"
        ),
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
    github_app_private_key: str = Field(
        default="",
        description="Logical GitHub App private key secret value used by the UI-first runtime config layer",
    )
    gh_aw_tools_enabled: bool = Field(
        default=False,
        description="Enable optional GitHub Agentic Workflows diagnostics integration hooks",
    )
    gh_aw_ingestion_mode: str = Field(
        default="disabled",
        description="External diagnostics ingestion mode: disabled, passive, or hybrid",
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
    external_diagnostics_wait_seconds: float = Field(
        default=60.0,
        description=(
            "Maximum total wait budget (seconds) for ci-doctor passive diagnostics polling "
            "during primary pipeline execution. Set to 0 for fully async enrichment."
        ),
    )
    external_diagnostics_poll_interval_seconds: float = Field(
        default=15.0,
        description=(
            "Polling cadence (seconds) for ci-doctor passive diagnostics lookup while within "
            "the external diagnostics wait budget."
        ),
    )

    # Application Configuration
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production)",
    )
    storage_mode: str = Field(
        default="",
        description=(
            "Storage backend mode: memory, cosmos, or postgres. "
            "When empty, defaults to memory in development and cosmos otherwise."
        ),
    )
    allow_in_memory_storage_in_non_development: bool = Field(
        default=False,
        description=(
            "Allow explicit in-memory storage in non-development environments. "
            "Intended for demo/evaluation only."
        ),
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
            "'freestyle' (aggressive open-ended automation), or "
            "'debug' (same behavior as safe with verbose diagnostic logging)"
        ),
    )
    auto_apply_remediation: bool = Field(
        default=True,
        description=(
            "Global execution gate. When false, PipelineHealer only plans remediation "
            "actions (dry-run) and does not publish PRs/issues or retry workflows."
        ),
    )
    max_remediation_attempts: int = Field(
        default=3,
        description="Maximum number of remediation attempts per failure",
    )
    auto_create_pr: bool = Field(
        default=True,
        description="Allow publishing PR artifacts for remediation plans that choose create_pr",
    )
    auto_create_issue: bool = Field(
        default=True,
        description="Allow publishing issue artifacts for remediation plans that choose create_issue",
    )
    auto_retry_workflow: bool = Field(
        default=True,
        description=(
            "Allow automatic rerun of failed workflow jobs for remediation plans that choose "
            "retry_workflow"
        ),
    )
    auto_create_tracking_issue_for_prs: bool = Field(
        default=True,
        description=(
            "Create a tracking issue for PR-based remediations and close it automatically on merge "
            "(requires auto_create_issue=true)"
        ),
    )
    pipeline_step_timeout_seconds: float = Field(
        default=120.0,
        description="Per-step timeout (seconds) for analyze/diagnose/remediate orchestration steps",
    )
    agent_handoff_enabled: bool = Field(
        default=False,
        description="Enable optional Assign-to-Agent handoff API",
    )
    agent_handoff_mode: str = Field(
        default="copy_only",
        description="Agent handoff mode: copy_only or webhook",
    )
    agent_handoff_webhook_url: str = Field(
        default="",
        description="Webhook target URL used when AGENT_HANDOFF_MODE=webhook",
    )
    agent_handoff_webhook_allowlist: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Allowed webhook hostnames for agent handoff. "
            "When set, AGENT_HANDOFF_WEBHOOK_URL host must be in this allowlist."
        ),
    )
    agent_handoff_timeout_seconds: float = Field(
        default=8.0,
        description="Timeout budget for outbound Assign-to-Agent webhook delivery",
    )
    agent_handoff_max_retries: int = Field(
        default=1,
        description="Maximum retries for transient Assign-to-Agent webhook failures",
    )
    agent_handoff_default_target: str = Field(
        default="codex_app_server",
        description="Default target for durable external-agent handoff sessions",
    )
    agent_handoff_enabled_targets: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["codex_app_server", "openclaw", "hermes"],
        description="External-agent handoff targets operators may select",
    )
    agent_handoff_callback_secret: str = Field(
        default="",
        description="Optional HMAC secret for external-agent callback events",
    )
    codex_app_server_handoff_url: str = Field(
        default="",
        description="Optional webhook endpoint for Codex App Server handoff delivery",
    )
    openclaw_handoff_url: str = Field(
        default="",
        description="Optional webhook endpoint for OpenClaw handoff delivery",
    )
    hermes_handoff_url: str = Field(
        default="",
        description="Optional webhook endpoint for Hermes handoff delivery",
    )
    infisical_project_id: str = Field(
        default="",
        description="Infisical project id for runtime secret storage",
    )
    infisical_environment: str = Field(
        default="dev",
        description="Infisical environment slug/name for runtime secret storage",
    )
    infisical_secret_path: str = Field(
        default="/personal/pipelinehealer",
        description="Infisical folder path for PipelineHealer runtime secrets",
    )
    infisical_cli_path: str = Field(
        default="infisical",
        description="Infisical CLI executable path",
    )
    infisical_api_url: str = Field(
        default="",
        description="Optional Infisical API URL/domain override",
    )
    infisical_token: str = Field(
        default="",
        description="Optional Infisical service or machine identity token",
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

    @field_validator("mcp_repo_allowlist", mode="before")
    @classmethod
    def parse_mcp_repo_allowlist(cls, value: Any) -> Any:
        """Allow MCP repo allowlist from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(repo).strip() for repo in parsed if str(repo).strip()]
            return [repo.strip() for repo in text.split(",") if repo.strip()]
        if isinstance(value, list):
            return [str(repo).strip() for repo in value if str(repo).strip()]
        return value

    @field_validator("agent_handoff_webhook_allowlist", mode="before")
    @classmethod
    def parse_agent_handoff_webhook_allowlist(cls, value: Any) -> Any:
        """Allow handoff webhook allowlist from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(item).strip().lower() for item in parsed if str(item).strip()]
            return [host.strip().lower() for host in text.split(",") if host.strip()]
        if isinstance(value, list):
            return [str(host).strip().lower() for host in value if str(host).strip()]
        return value

    @field_validator("agent_handoff_enabled_targets", mode="before")
    @classmethod
    def parse_agent_handoff_enabled_targets(cls, value: Any) -> Any:
        """Allow handoff target lists from JSON arrays or comma-separated env values."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(item).strip().lower() for item in parsed if str(item).strip()]
            return [item.strip().lower() for item in text.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return value

    @field_validator("mcp_tool_policies", mode="before")
    @classmethod
    def parse_mcp_tool_policies(cls, value: Any) -> Any:
        """Allow MCP tool policies from JSON object or CSV key=value pairs."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            if text.startswith("{"):
                parsed = json.loads(text)
                if not isinstance(parsed, dict):
                    raise ValueError("MCP_TOOL_POLICIES JSON must be an object")
                return parsed
            parsed_map: dict[str, str] = {}
            for item in text.split(","):
                pair = item.strip()
                if not pair:
                    continue
                if "=" in pair:
                    tool, policy = pair.split("=", 1)
                elif ":" in pair:
                    tool, policy = pair.split(":", 1)
                else:
                    raise ValueError(
                        "MCP_TOOL_POLICIES entries must use tool=policy format"
                    )
                tool_name = str(tool).strip()
                policy_name = str(policy).strip()
                if not tool_name or not policy_name:
                    raise ValueError(
                        "MCP_TOOL_POLICIES entries must use tool=policy format"
                    )
                parsed_map[tool_name] = policy_name
            return parsed_map
        if isinstance(value, dict):
            return {
                str(tool).strip(): str(policy).strip()
                for tool, policy in value.items()
                if str(tool).strip()
            }
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

    @field_validator("agent_handoff_mode")
    @classmethod
    def validate_agent_handoff_mode(cls, value: str) -> str:
        """Validate agent handoff mode."""
        normalized = value.strip().lower()
        if normalized not in {"copy_only", "webhook"}:
            raise ValueError("AGENT_HANDOFF_MODE must be one of: copy_only, webhook")
        return normalized

    @field_validator("agent_handoff_default_target")
    @classmethod
    def validate_agent_handoff_default_target(cls, value: str) -> str:
        """Validate the default external-agent handoff target."""
        normalized = value.strip().lower()
        if normalized not in {"codex_app_server", "openclaw", "hermes", "custom"}:
            raise ValueError(
                "AGENT_HANDOFF_DEFAULT_TARGET must be one of: "
                "codex_app_server, openclaw, hermes, custom"
            )
        return normalized

    @field_validator("agent_handoff_enabled_targets")
    @classmethod
    def validate_agent_handoff_enabled_targets(cls, value: list[str]) -> list[str]:
        """Validate selectable external-agent targets."""
        allowed = {"codex_app_server", "openclaw", "hermes", "custom"}
        normalized = []
        for raw in value:
            target = str(raw).strip().lower()
            if not target:
                continue
            if target not in allowed:
                raise ValueError(
                    "AGENT_HANDOFF_ENABLED_TARGETS values must be one of: "
                    "codex_app_server, openclaw, hermes, custom"
                )
            normalized.append(target)
        return normalized

    @model_validator(mode="after")
    def validate_agent_handoff_default_is_enabled(self) -> "Settings":
        """Require startup default handoff target to be selectable."""
        enabled_targets = {target.strip().lower() for target in self.agent_handoff_enabled_targets}
        if self.agent_handoff_default_target not in enabled_targets:
            raise ValueError(
                "AGENT_HANDOFF_DEFAULT_TARGET must be included in "
                "AGENT_HANDOFF_ENABLED_TARGETS"
            )
        return self

    @field_validator("codex_app_server_transport")
    @classmethod
    def validate_codex_app_server_transport(cls, value: str) -> str:
        """Validate Codex App Server transport selection."""
        normalized = value.strip().lower() or "stdio"
        if normalized not in {"stdio", "websocket"}:
            raise ValueError("CODEX_APP_SERVER_TRANSPORT must be one of: stdio, websocket")
        return normalized

    @field_validator("codex_app_server_turn_timeout_ms")
    @classmethod
    def validate_codex_app_server_turn_timeout_ms(cls, value: int) -> int:
        """Validate bounded Codex App Server turn timeout."""
        if value < 1000 or value > 900000:
            raise ValueError("CODEX_APP_SERVER_TURN_TIMEOUT_MS must be between 1000 and 900000")
        return value

    @field_validator("storage_mode")
    @classmethod
    def validate_storage_mode(cls, value: str) -> str:
        """Validate storage mode selection."""
        normalized = value.strip().lower()
        if not normalized:
            return ""
        if normalized not in {"memory", "cosmos", "postgres"}:
            raise ValueError("STORAGE_MODE must be one of: memory, cosmos, postgres")
        return normalized

    @field_validator("settings_secret_backend")
    @classmethod
    def validate_settings_secret_backend(cls, value: str) -> str:
        """Validate configured runtime secret backend selection."""
        normalized = value.strip().lower()
        if normalized not in {"encrypted_db", "azure_key_vault", "infisical"}:
            raise ValueError(
                "SETTINGS_SECRET_BACKEND must be one of: encrypted_db, azure_key_vault, infisical"
            )
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        """Validate LLM provider selection."""
        return resolve_llm_provider(value).value

    @field_validator("mcp_provider")
    @classmethod
    def validate_mcp_provider(cls, value: str) -> str:
        """Validate MCP provider selection."""
        normalized = value.strip().lower()
        if normalized not in {"disabled", "github", "azure_monitor", "custom"}:
            raise ValueError(
                "MCP_PROVIDER must be one of: disabled, github, azure_monitor, custom"
            )
        return normalized

    @field_validator("mcp_tool_policies")
    @classmethod
    def validate_mcp_tool_policies(cls, value: dict[str, str]) -> dict[str, str]:
        """Validate MCP tool policy map values."""
        allowed = {"disabled", "read_only", "write_with_approval", "auto"}
        normalized: dict[str, str] = {}
        for raw_tool, raw_policy in value.items():
            tool = str(raw_tool).strip().lower()
            policy = str(raw_policy).strip().lower()
            if not tool:
                continue
            if policy not in allowed:
                raise ValueError(
                    "MCP_TOOL_POLICIES values must be one of: "
                    "disabled, read_only, write_with_approval, auto"
                )
            normalized[tool] = policy
        return normalized

    @field_validator("gh_aw_ingestion_mode")
    @classmethod
    def validate_gh_aw_ingestion_mode(cls, value: str) -> str:
        """Validate external diagnostics ingestion mode."""
        normalized = value.strip().lower()
        if normalized not in {"disabled", "passive", "hybrid"}:
            raise ValueError("GH_AW_INGESTION_MODE must be one of: disabled, passive, hybrid")
        return normalized

    @field_validator("external_diagnostics_wait_seconds")
    @classmethod
    def validate_external_diagnostics_wait_seconds(cls, value: float) -> float:
        """Validate bounded wait budget for external diagnostics polling."""
        if value < 0.0 or value > 900.0:
            raise ValueError(
                "EXTERNAL_DIAGNOSTICS_WAIT_SECONDS must be between 0 and 900 seconds"
            )
        return value

    @field_validator("external_diagnostics_poll_interval_seconds")
    @classmethod
    def validate_external_diagnostics_poll_interval_seconds(cls, value: float) -> float:
        """Validate polling interval used inside external diagnostics wait budget."""
        if value <= 0.0 or value > 120.0:
            raise ValueError(
                "EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS must be > 0 and <= 120 seconds"
            )
        return value

    @field_validator("agent_handoff_timeout_seconds")
    @classmethod
    def validate_agent_handoff_timeout_seconds(cls, value: float) -> float:
        """Validate bounded timeout for outbound handoff webhook requests."""
        if value <= 0.0 or value > 30.0:
            raise ValueError("AGENT_HANDOFF_TIMEOUT_SECONDS must be > 0 and <= 30 seconds")
        return value

    @field_validator("agent_handoff_max_retries")
    @classmethod
    def validate_agent_handoff_max_retries(cls, value: int) -> int:
        """Validate bounded retry count for outbound handoff webhook requests."""
        if value < 0 or value > 5:
            raise ValueError("AGENT_HANDOFF_MAX_RETRIES must be between 0 and 5")
        return value

    @field_validator("jenkins_bridge_max_skew_seconds")
    @classmethod
    def validate_jenkins_bridge_max_skew_seconds(cls, value: int) -> int:
        """Validate timestamp skew guardrail for Jenkins bridge ingress."""
        if value < 1 or value > 3600:
            raise ValueError("JENKINS_BRIDGE_MAX_SKEW_SECONDS must be between 1 and 3600")
        return value

    @field_validator("jenkins_bridge_replay_ttl_seconds")
    @classmethod
    def validate_jenkins_bridge_replay_ttl_seconds(cls, value: int) -> int:
        """Validate replay window TTL for Jenkins bridge ingress."""
        if value < 60 or value > 7 * 24 * 3600:
            raise ValueError(
                "JENKINS_BRIDGE_REPLAY_TTL_SECONDS must be between 60 and 604800"
            )
        return value

    @field_validator("jenkins_bridge_max_body_bytes")
    @classmethod
    def validate_jenkins_bridge_max_body_bytes(cls, value: int) -> int:
        """Validate request body cap for Jenkins bridge ingress."""
        if value < 1024 or value > 4 * 1024 * 1024:
            raise ValueError("JENKINS_BRIDGE_MAX_BODY_BYTES must be between 1024 and 4194304")
        return value

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

    @field_validator("llm_model_analysis", "llm_model_diagnosis", "llm_model_remediation")
    @classmethod
    def normalize_llm_task_models(cls, value: str) -> str:
        """Normalize optional per-task model override values."""
        return value.strip()


_settings_singleton: Settings | None = None


def _settings_env_file() -> str | None:
    """Resolve optional env file override for settings loading.

    Tests and local operators can point settings loading at a specific env file
    (or a nonexistent path to disable repo-root `.env` influence) using
    `PIPELINEHEALER_ENV_FILE_PATH`.
    """
    override = os.getenv("PIPELINEHEALER_ENV_FILE_PATH", "").strip()
    return override or None


def load_settings_snapshot() -> Settings:
    """Load a fresh settings snapshot using the current env-file override rules."""
    env_file = _settings_env_file()
    if env_file is None:
        return Settings()
    # pydantic-settings accepts `_env_file` at runtime, but the generated type
    # signature does not declare it, so keep the override localized here.
    return Settings(_env_file=env_file)  # type: ignore[call-arg]


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
        _settings_singleton = load_settings_snapshot()
    return _settings_singleton


def reset_settings() -> None:
    """Reset the settings singleton (for tests only)."""
    global _settings_singleton
    _settings_singleton = None
