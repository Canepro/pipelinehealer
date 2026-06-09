"""Central registry for operator-visible configuration settings."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingSpec:
    """Metadata describing one application setting."""

    key: str
    env_var: str
    value_type: str
    sensitive: bool
    bootstrap_only: bool
    requires_restart: bool
    section: str
    group: str
    default: Any
    allow_env_override: bool = True
    description: str = ""


RUNTIME_SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec("llm_provider", "LLM_PROVIDER", "string", False, False, False, "llm", "provider", "codex_app_server"),
    SettingSpec("azure_openai_endpoint", "AZURE_OPENAI_ENDPOINT", "string", False, False, False, "llm", "provider", ""),
    SettingSpec("azure_openai_deployment_name", "AZURE_OPENAI_DEPLOYMENT_NAME", "string", False, False, False, "llm", "provider", ""),
    SettingSpec("azure_openai_api_version", "AZURE_OPENAI_API_VERSION", "string", False, False, False, "llm", "provider", "2025-04-01-preview"),
    SettingSpec("azure_openai_chat_api_version", "AZURE_OPENAI_CHAT_API_VERSION", "string", False, False, False, "llm", "provider", "2024-12-01-preview"),
    SettingSpec("openai_compatible_base_url", "OPENAI_COMPATIBLE_BASE_URL", "string", False, False, False, "llm", "provider", ""),
    SettingSpec("openai_compatible_model", "OPENAI_COMPATIBLE_MODEL", "string", False, False, False, "llm", "provider", ""),
    SettingSpec("codex_app_server_transport", "CODEX_APP_SERVER_TRANSPORT", "string", False, False, False, "llm", "codex_app_server", "stdio"),
    SettingSpec("codex_app_server_command", "CODEX_APP_SERVER_COMMAND", "string", False, False, False, "llm", "codex_app_server", "codex app-server"),
    SettingSpec("codex_app_server_model", "CODEX_APP_SERVER_MODEL", "string", False, False, False, "llm", "codex_app_server", "gpt-5.4"),
    SettingSpec("codex_app_server_turn_timeout_ms", "CODEX_APP_SERVER_TURN_TIMEOUT_MS", "integer", False, False, False, "llm", "codex_app_server", 120000),
    SettingSpec("codex_app_server_ws_url", "CODEX_APP_SERVER_WS_URL", "string", False, False, False, "llm", "codex_app_server", ""),
    SettingSpec("codex_app_server_ws_allow_remote", "CODEX_APP_SERVER_WS_ALLOW_REMOTE", "boolean", False, False, False, "llm", "codex_app_server", False),
    SettingSpec("llm_model_analysis", "LLM_MODEL_ANALYSIS", "string", False, False, False, "llm", "model_paths", ""),
    SettingSpec("llm_model_diagnosis", "LLM_MODEL_DIAGNOSIS", "string", False, False, False, "llm", "model_paths", ""),
    SettingSpec("llm_model_remediation", "LLM_MODEL_REMEDIATION", "string", False, False, False, "llm", "model_paths", ""),
    SettingSpec("heal_mode", "HEAL_MODE", "string", False, False, False, "runtime", "policy", "safe"),
    SettingSpec("auto_apply_remediation", "AUTO_APPLY_REMEDIATION", "boolean", False, False, False, "runtime", "policy", True),
    SettingSpec("auto_create_pr", "AUTO_CREATE_PR", "boolean", False, False, False, "runtime", "policy", True),
    SettingSpec("jenkins_bridge_allow_pr", "JENKINS_BRIDGE_ALLOW_PR", "boolean", False, False, False, "runtime", "policy", False),
    SettingSpec("auto_create_issue", "AUTO_CREATE_ISSUE", "boolean", False, False, False, "runtime", "policy", True),
    SettingSpec("auto_retry_workflow", "AUTO_RETRY_WORKFLOW", "boolean", False, False, False, "runtime", "policy", True),
    SettingSpec("auto_create_tracking_issue_for_prs", "AUTO_CREATE_TRACKING_ISSUE_FOR_PRS", "boolean", False, False, False, "runtime", "policy", True),
    SettingSpec("auto_close_on_workflow_success", "AUTO_CLOSE_ON_WORKFLOW_SUCCESS", "boolean", False, False, False, "runtime", "policy", True),
    SettingSpec("auto_merge_remediation_prs", "AUTO_MERGE_REMEDIATION_PRS", "boolean", False, False, False, "runtime", "policy", False),
    SettingSpec("auto_merge_strategy", "AUTO_MERGE_STRATEGY", "string", False, False, False, "runtime", "policy", "merge_when_clean"),
    SettingSpec("auto_merge_poll_seconds", "AUTO_MERGE_POLL_SECONDS", "number", False, False, False, "runtime", "policy", 90.0),
    SettingSpec("auto_merge_require_clean_checks", "AUTO_MERGE_REQUIRE_CLEAN_CHECKS", "boolean", False, False, False, "runtime", "policy", True),
    SettingSpec("max_remediation_attempts", "MAX_REMEDIATION_ATTEMPTS", "integer", False, False, False, "runtime", "policy", 3),
    SettingSpec("pipeline_step_timeout_seconds", "PIPELINE_STEP_TIMEOUT_SECONDS", "number", False, False, False, "runtime", "policy", 120.0),
    SettingSpec("github_api_max_retries", "GITHUB_API_MAX_RETRIES", "integer", False, False, False, "runtime", "policy", 3),
    SettingSpec("github_api_retry_base_seconds", "GITHUB_API_RETRY_BASE_SECONDS", "number", False, False, False, "runtime", "policy", 0.5),
    SettingSpec("github_api_retry_max_seconds", "GITHUB_API_RETRY_MAX_SECONDS", "number", False, False, False, "runtime", "policy", 8.0),
    SettingSpec("log_prompt_max_chars", "LOG_PROMPT_MAX_CHARS", "integer", False, False, False, "runtime", "policy", 18000),
    SettingSpec("log_prompt_head_chars", "LOG_PROMPT_HEAD_CHARS", "integer", False, False, False, "runtime", "policy", 9000),
    SettingSpec("log_prompt_tail_chars", "LOG_PROMPT_TAIL_CHARS", "integer", False, False, False, "runtime", "policy", 9000),
    SettingSpec("verify_webhook_signature", "VERIFY_WEBHOOK_SIGNATURE", "boolean", False, False, False, "security", "webhooks", True),
    SettingSpec("verify_webhook_signature_in_development", "VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT", "boolean", False, False, False, "security", "webhooks", False),
    SettingSpec("ph_allowed_repos", "PH_ALLOWED_REPOS", "string_list", False, False, False, "security", "webhooks", []),
    SettingSpec("github_app_id", "GITHUB_APP_ID", "string", False, False, False, "github", "auth", ""),
    SettingSpec("gh_aw_tools_enabled", "GH_AW_TOOLS_ENABLED", "boolean", False, False, False, "github", "diagnostics", False),
    SettingSpec("gh_aw_ingestion_mode", "GH_AW_INGESTION_MODE", "string", False, False, False, "github", "diagnostics", "disabled"),
    SettingSpec("gh_aw_known_workflows", "GH_AW_KNOWN_WORKFLOWS", "string_list", False, False, False, "github", "diagnostics", ["ci-doctor"]),
    SettingSpec("external_diagnostics_wait_seconds", "EXTERNAL_DIAGNOSTICS_WAIT_SECONDS", "number", False, False, False, "github", "diagnostics", 60.0),
    SettingSpec("external_diagnostics_poll_interval_seconds", "EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS", "number", False, False, False, "github", "diagnostics", 15.0),
    SettingSpec("mcp_enabled", "MCP_ENABLED", "boolean", False, False, False, "mcp", "provider", False),
    SettingSpec("mcp_provider", "MCP_PROVIDER", "string", False, False, False, "mcp", "provider", "disabled"),
    SettingSpec("mcp_read_only", "MCP_READ_ONLY", "boolean", False, False, False, "mcp", "provider", True),
    SettingSpec("mcp_timeout_seconds", "MCP_TIMEOUT_SECONDS", "number", False, False, False, "mcp", "provider", 15.0),
    SettingSpec("mcp_max_retries", "MCP_MAX_RETRIES", "integer", False, False, False, "mcp", "provider", 1),
    SettingSpec("mcp_tool_policies", "MCP_TOOL_POLICIES", "string_map", False, False, False, "mcp", "provider", {}),
    SettingSpec("mcp_repo_allowlist", "MCP_REPO_ALLOWLIST", "string_list", False, False, False, "mcp", "provider", []),
    SettingSpec("jenkins_bridge_enabled", "JENKINS_BRIDGE_ENABLED", "boolean", False, False, False, "jenkins", "bridge", False),
    SettingSpec("jenkins_bridge_max_skew_seconds", "JENKINS_BRIDGE_MAX_SKEW_SECONDS", "integer", False, False, False, "jenkins", "bridge", 300),
    SettingSpec("jenkins_bridge_replay_ttl_seconds", "JENKINS_BRIDGE_REPLAY_TTL_SECONDS", "integer", False, False, False, "jenkins", "bridge", 86400),
    SettingSpec("jenkins_bridge_max_body_bytes", "JENKINS_BRIDGE_MAX_BODY_BYTES", "integer", False, False, False, "jenkins", "bridge", 524288),
    SettingSpec("agent_handoff_enabled", "AGENT_HANDOFF_ENABLED", "boolean", False, False, False, "handoff", "runtime", False),
    SettingSpec("agent_handoff_mode", "AGENT_HANDOFF_MODE", "string", False, False, False, "handoff", "runtime", "copy_only"),
    SettingSpec("agent_handoff_webhook_allowlist", "AGENT_HANDOFF_WEBHOOK_ALLOWLIST", "string_list", False, False, False, "handoff", "runtime", []),
    SettingSpec("agent_handoff_timeout_seconds", "AGENT_HANDOFF_TIMEOUT_SECONDS", "number", False, False, False, "handoff", "runtime", 8.0),
    SettingSpec("agent_handoff_max_retries", "AGENT_HANDOFF_MAX_RETRIES", "integer", False, False, False, "handoff", "runtime", 1),
    SettingSpec("agent_handoff_default_target", "AGENT_HANDOFF_DEFAULT_TARGET", "string", False, False, False, "handoff", "control_plane", "codex_app_server"),
    SettingSpec("agent_handoff_enabled_targets", "AGENT_HANDOFF_ENABLED_TARGETS", "string_list", False, False, False, "handoff", "control_plane", ["codex_app_server", "openclaw", "hermes"]),
    SettingSpec("infisical_project_id", "INFISICAL_PROJECT_ID", "string", False, False, False, "secrets", "infisical", ""),
    SettingSpec("infisical_environment", "INFISICAL_ENVIRONMENT", "string", False, False, False, "secrets", "infisical", "dev"),
    SettingSpec("infisical_secret_path", "INFISICAL_SECRET_PATH", "string", False, False, False, "secrets", "infisical", "/personal/pipelinehealer"),
    SettingSpec("infisical_cli_path", "INFISICAL_CLI_PATH", "string", False, False, False, "secrets", "infisical", "infisical"),
    SettingSpec("infisical_api_url", "INFISICAL_API_URL", "string", False, False, False, "secrets", "infisical", ""),
)

SECRET_SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec("azure_openai_api_key", "AZURE_OPENAI_API_KEY", "secret", True, False, False, "secrets", "llm", ""),
    SettingSpec("openai_compatible_api_key", "OPENAI_COMPATIBLE_API_KEY", "secret", True, False, False, "secrets", "llm", ""),
    SettingSpec("github_personal_access_token", "GITHUB_PERSONAL_ACCESS_TOKEN", "secret", True, False, False, "secrets", "github", ""),
    SettingSpec("github_webhook_secret", "GITHUB_WEBHOOK_SECRET", "secret", True, False, False, "secrets", "github", ""),
    SettingSpec("jenkins_bridge_shared_secret", "JENKINS_BRIDGE_SHARED_SECRET", "secret", True, False, False, "secrets", "jenkins", ""),
    SettingSpec("agent_handoff_webhook_url", "AGENT_HANDOFF_WEBHOOK_URL", "secret_url", True, False, False, "secrets", "handoff", ""),
    SettingSpec("agent_handoff_callback_secret", "AGENT_HANDOFF_CALLBACK_SECRET", "secret", True, False, False, "secrets", "handoff", ""),
    SettingSpec("codex_app_server_handoff_url", "CODEX_APP_SERVER_HANDOFF_URL", "secret_url", True, False, False, "secrets", "handoff", ""),
    SettingSpec("openclaw_handoff_url", "OPENCLAW_HANDOFF_URL", "secret_url", True, False, False, "secrets", "handoff", ""),
    SettingSpec("hermes_handoff_url", "HERMES_HANDOFF_URL", "secret_url", True, False, False, "secrets", "handoff", ""),
    SettingSpec("codex_app_server_ws_bearer_token", "CODEX_APP_SERVER_WS_BEARER_TOKEN", "secret", True, False, False, "secrets", "llm", ""),
    SettingSpec("github_app_private_key", "GITHUB_APP_PRIVATE_KEY", "secret", True, False, False, "secrets", "github", ""),
    SettingSpec("infisical_token", "INFISICAL_TOKEN", "secret", True, False, False, "secrets", "infisical", ""),
)

BOOTSTRAP_SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec("environment", "ENVIRONMENT", "string", False, True, True, "bootstrap", "process", "development"),
    SettingSpec("api_host", "API_HOST", "string", False, True, True, "bootstrap", "process", "0.0.0.0"),
    SettingSpec("api_port", "API_PORT", "integer", False, True, True, "bootstrap", "process", 8000),
    SettingSpec("log_level", "LOG_LEVEL", "string", False, True, True, "bootstrap", "process", "INFO"),
    SettingSpec("storage_mode", "STORAGE_MODE", "string", False, True, True, "bootstrap", "storage", ""),
    SettingSpec("allow_in_memory_storage_in_non_development", "ALLOW_IN_MEMORY_STORAGE_IN_NON_DEVELOPMENT", "boolean", False, True, True, "bootstrap", "storage", False),
    SettingSpec("cosmos_db_endpoint", "COSMOS_DB_ENDPOINT", "string", False, True, True, "bootstrap", "storage", ""),
    SettingSpec("cosmos_db_database", "COSMOS_DB_DATABASE", "string", False, True, True, "bootstrap", "storage", "pipelinehealer"),
    SettingSpec("postgres_dsn", "POSTGRES_DSN", "secret", True, True, True, "bootstrap", "storage", ""),
    SettingSpec("auth_mode", "AUTH_MODE", "string", False, True, True, "bootstrap", "auth", "api_key"),
    SettingSpec("api_auth_key", "API_AUTH_KEY", "secret", True, True, True, "bootstrap", "auth", ""),
    SettingSpec("admin_api_key", "ADMIN_API_KEY", "secret", True, True, True, "bootstrap", "auth", ""),
    SettingSpec("entra_tenant_id", "ENTRA_TENANT_ID", "string", False, True, True, "bootstrap", "auth", ""),
    SettingSpec("entra_client_id", "ENTRA_CLIENT_ID", "string", False, True, True, "bootstrap", "auth", ""),
    SettingSpec("entra_issuer", "ENTRA_ISSUER", "string", False, True, True, "bootstrap", "auth", ""),
    SettingSpec("entra_jwks_url", "ENTRA_JWKS_URL", "string", False, True, True, "bootstrap", "auth", ""),
    SettingSpec("entra_allowed_audiences", "ENTRA_ALLOWED_AUDIENCES", "string_list", False, True, True, "bootstrap", "auth", []),
    SettingSpec("entra_admin_roles", "ENTRA_ADMIN_ROLES", "string_list", False, True, True, "bootstrap", "auth", ["PipelineHealer.Admin"]),
    SettingSpec("audit_salt", "AUDIT_SALT", "secret", True, True, True, "bootstrap", "auth", ""),
    SettingSpec("settings_secret_backend", "SETTINGS_SECRET_BACKEND", "string", False, True, True, "bootstrap", "secrets", "encrypted_db"),
    SettingSpec("settings_db_encryption_key", "SETTINGS_DB_ENCRYPTION_KEY", "secret", True, True, True, "bootstrap", "secrets", ""),
    SettingSpec("key_vault_url", "KEY_VAULT_URL", "string", False, True, True, "bootstrap", "secrets", ""),
    SettingSpec("settings_key_vault_prefix", "SETTINGS_KEY_VAULT_PREFIX", "string", False, True, True, "bootstrap", "secrets", "pipelinehealer-"),
    SettingSpec("cors_allowed_origins", "CORS_ALLOWED_ORIGINS", "string_list", False, True, True, "bootstrap", "http", ["http://localhost:3000", "http://localhost:5173"]),
    SettingSpec("cors_allow_origin_regex", "CORS_ALLOW_ORIGIN_REGEX", "string", False, True, True, "bootstrap", "http", r"https://.*\.azurecontainerapps\.io"),
    SettingSpec("applicationinsights_connection_string", "APPLICATIONINSIGHTS_CONNECTION_STRING", "string", True, True, True, "bootstrap", "observability", ""),
)

RUNTIME_SETTING_SPECS_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in RUNTIME_SETTING_SPECS}
SECRET_SETTING_SPECS_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SECRET_SETTING_SPECS}
BOOTSTRAP_SETTING_SPECS_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in BOOTSTRAP_SETTING_SPECS}
ALL_SETTING_SPECS_BY_KEY: dict[str, SettingSpec] = {
    **BOOTSTRAP_SETTING_SPECS_BY_KEY,
    **RUNTIME_SETTING_SPECS_BY_KEY,
    **SECRET_SETTING_SPECS_BY_KEY,
}

RUNTIME_NON_SECRET_ENV_KEYS: tuple[tuple[str, str], ...] = tuple(
    (spec.key, spec.env_var) for spec in RUNTIME_SETTING_SPECS
)
