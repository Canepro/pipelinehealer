"""Data models for PipelineHealer."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class FailureType(StrEnum):
    """Types of CI/CD failures the agent can handle."""

    DEPENDENCY = "dependency"
    TEST = "test"
    LINT = "lint"
    BUILD_CONFIG = "build_config"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class DiagnosisSource(StrEnum):
    """Source used to produce a diagnosis."""

    PATTERN = "pattern"
    LLM = "llm"


class RemediationStatus(StrEnum):
    """Status of a remediation attempt."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    DIAGNOSING = "diagnosing"
    REMEDIATING = "remediating"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RemediationAction(StrEnum):
    """Types of remediation actions."""

    CREATE_PR = "create_pr"
    CREATE_ISSUE = "create_issue"
    RETRY_WORKFLOW = "retry_workflow"
    NOTIFY = "notify"
    SKIP = "skip"


class ExternalDiagnosticStatus(StrEnum):
    """Status of an external diagnostics signal."""

    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"
    ERROR = "error"


# =============================================================================
# GitHub Webhook Models
# =============================================================================


class GitHubRepository(BaseModel):
    """GitHub repository information."""

    id: int
    name: str
    full_name: str
    owner: dict[str, Any]
    default_branch: str = "main"
    html_url: str


class GitHubWorkflowRun(BaseModel):
    """GitHub Actions workflow run information."""

    id: int
    name: str | None = None
    workflow_id: int
    head_branch: str
    head_sha: str
    status: str
    conclusion: str | None = None
    html_url: str
    created_at: datetime
    updated_at: datetime
    run_attempt: int = 1
    run_number: int


class GitHubWorkflowJob(BaseModel):
    """GitHub Actions workflow job information."""

    id: int
    name: str
    status: str
    conclusion: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRunEvent(BaseModel):
    """GitHub workflow_run webhook event payload."""

    action: str
    workflow_run: GitHubWorkflowRun
    repository: GitHubRepository
    sender: dict[str, Any]


# =============================================================================
# Agent Models
# =============================================================================


class LogAnalysis(BaseModel):
    """Result of log analysis."""

    job_id: int
    job_name: str
    raw_logs: str
    error_lines: list[str] = Field(default_factory=list)
    warning_lines: list[str] = Field(default_factory=list)
    key_events: list[str] = Field(default_factory=list)
    summary: str = ""


class Diagnosis(BaseModel):
    """Root cause diagnosis result."""

    failure_type: FailureType
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause: str
    affected_files: list[str] = Field(default_factory=list)
    error_details: dict[str, Any] = Field(default_factory=dict)
    suggested_fix: str = ""
    is_auto_fixable: bool = False
    diagnosis_source: DiagnosisSource | None = None


class RemediationPlan(BaseModel):
    """Plan for remediating a failure."""

    action: RemediationAction
    description: str
    file_changes: list[dict[str, Any]] = Field(default_factory=list)
    pr_title: str | None = None
    pr_body: str | None = None
    issue_title: str | None = None
    issue_body: str | None = None
    branch_name: str | None = None


class RemediationResult(BaseModel):
    """Result of a remediation attempt."""

    success: bool
    action_taken: RemediationAction
    pr_url: str | None = None
    issue_url: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ExternalDiagnostic(BaseModel):
    """Structured external diagnostic evidence linked to an activity."""

    source: str
    status: ExternalDiagnosticStatus
    summary: str = ""
    url: str | None = None
    matched_run_id: int | None = None
    confidence_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=utcnow)


class LLMModelPath(BaseModel):
    """Observed model execution path for one activity."""

    provider: str
    model: str
    fallback_used: bool = False
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0


class MCPActionAuditEntry(BaseModel):
    """Audit record for one MCP tool-policy decision or invocation."""

    actor: str
    tool: str
    payload_hash: str
    result: str
    request_id: str


class MCPModelPath(BaseModel):
    """Observed MCP execution path and source attribution for one activity."""

    provider: str
    enabled: bool = False
    available: bool = False
    read_only: bool = True
    reason: str = "disabled"
    configured_tools: list[str] = Field(default_factory=list)
    tool_invocations: dict[str, int] = Field(default_factory=dict)
    source_attribution: dict[str, int] = Field(default_factory=dict)
    error_count: int = 0
    action_audit: list[MCPActionAuditEntry] = Field(default_factory=list)


class FailureContext(BaseModel):
    """Normalized failure context extracted from run evidence."""

    failing_job: str | None = None
    failing_step: str | None = None
    failing_command: str | None = None
    signal: str | None = None


# =============================================================================
# Activity Tracking Models
# =============================================================================


class ActivityRecord(BaseModel):
    """Record of agent activity for tracking and dashboard."""

    id: str = Field(default_factory=lambda: "")
    repository_id: str = Field(alias="repositoryId")
    repository_name: str
    workflow_run_id: int
    workflow_name: str
    status: RemediationStatus
    failure_type: FailureType | None = None
    diagnosis: Diagnosis | None = None
    failure_context: FailureContext | None = None
    llm_model_path: LLMModelPath | None = None
    mcp_model_path: MCPModelPath | None = None
    remediation_result: RemediationResult | None = None
    external_diagnostics: list[ExternalDiagnostic] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    duration_seconds: float | None = None
    error: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class DashboardStats(BaseModel):
    """Statistics for the dashboard."""

    total_runs_processed: int = 0
    actioned_remediations: int = 0
    successful_remediations: int = 0
    failed_remediations: int = 0
    pending_remediations: int = 0
    auto_pr_remediations: int = 0
    issue_remediations: int = 0
    safety_blocked_remediations: int = 0
    mcp_enabled_runs_30d: int = 0
    llm_fallback_rate_30d: float = 0.0
    by_failure_type: dict[str, int] = Field(default_factory=dict)
    by_repository: dict[str, int] = Field(default_factory=dict)
    average_resolution_time_seconds: float = 0.0
    last_updated: datetime = Field(default_factory=utcnow)


class AppSettingsView(BaseModel):
    """Non-secret runtime settings exposed to the frontend settings page."""

    environment: str
    storage_backend: str
    heal_mode: str
    auto_create_pr: bool
    auto_create_tracking_issue_for_prs: bool
    max_remediation_attempts: int
    pipeline_step_timeout_seconds: float
    github_api_max_retries: int
    github_api_retry_base_seconds: float
    github_api_retry_max_seconds: float
    log_prompt_max_chars: int
    log_prompt_head_chars: int
    log_prompt_tail_chars: int
    verify_webhook_signature: bool
    verify_webhook_signature_in_development: bool
    api_auth_enabled: bool
    admin_api_auth_enabled: bool
    auth_mode: str
    entra_auth_enabled: bool
    entra_admin_roles: list[str]
    github_pat_configured: bool
    github_app_configured: bool
    github_auth_mode: str
    gh_aw_tools_enabled: bool
    gh_aw_ingestion_mode: str
    gh_aw_known_workflows: list[str]
    external_diagnostics_wait_seconds: float
    external_diagnostics_poll_interval_seconds: float
    ph_allowed_repos: list[str]
    cors_allowed_origins: list[str]
    cors_allow_origin_regex: str
    llm_provider: str
    openai_compatible_base_url: str
    openai_compatible_model: str
    openai_compatible_api_key_configured: bool
    mcp_enabled: bool
    mcp_provider: str
    mcp_read_only: bool
    mcp_timeout_seconds: float
    mcp_max_retries: int
    mcp_tool_policies: dict[str, str]
    mcp_repo_allowlist: list[str]
    azure_openai_endpoint: str
    azure_openai_deployment_name: str
    azure_openai_api_version: str
    azure_openai_chat_api_version: str


class AdminSettingsUpdateRequest(BaseModel):
    """Admin runtime settings overrides (in-memory until process restart)."""

    heal_mode: str | None = None
    auto_create_pr: bool | None = None
    auto_create_tracking_issue_for_prs: bool | None = None
    max_remediation_attempts: int | None = Field(default=None, ge=1, le=50)
    verify_webhook_signature_in_development: bool | None = None
    pipeline_step_timeout_seconds: float | None = Field(default=None, gt=0.0, le=600.0)
    github_api_max_retries: int | None = Field(default=None, ge=0, le=10)
    github_api_retry_base_seconds: float | None = Field(default=None, gt=0.0, le=30.0)
    github_api_retry_max_seconds: float | None = Field(default=None, gt=0.0, le=120.0)
    log_prompt_max_chars: int | None = Field(default=None, ge=1000, le=200000)
    log_prompt_head_chars: int | None = Field(default=None, ge=100, le=200000)
    log_prompt_tail_chars: int | None = Field(default=None, ge=100, le=200000)
    gh_aw_tools_enabled: bool | None = None
    gh_aw_ingestion_mode: str | None = None
    gh_aw_known_workflows: list[str] | None = None
    external_diagnostics_wait_seconds: float | None = Field(default=None, ge=0.0, le=900.0)
    external_diagnostics_poll_interval_seconds: float | None = Field(
        default=None, gt=0.0, le=120.0
    )
    ph_allowed_repos: list[str] | None = None
    llm_provider: str | None = None
    openai_compatible_base_url: str | None = None
    openai_compatible_model: str | None = None
    mcp_enabled: bool | None = None
    mcp_provider: str | None = None
    mcp_read_only: bool | None = None
    mcp_timeout_seconds: float | None = Field(default=None, gt=0.0, le=120.0)
    mcp_max_retries: int | None = Field(default=None, ge=0, le=10)
    mcp_tool_policies: dict[str, str] | None = None
    mcp_repo_allowlist: list[str] | None = None
    azure_openai_deployment_name: str | None = None


class LLMProviderHealthView(BaseModel):
    """Health/status payload for configured LLM provider adapter."""

    provider: str
    implemented: bool
    available: bool
    reason: str
    message: str
    endpoint: str | None = None
    deployment_name: str | None = None
    api_version: str | None = None


class MCPProviderHealthView(BaseModel):
    """Health/status payload for configured MCP provider adapter."""

    provider: str
    enabled: bool
    read_only: bool
    available: bool
    reason: str
    message: str
    configured_tools: list[str] = Field(default_factory=list)


class AdminSettingsAuditEntry(BaseModel):
    """Admin settings change audit record (in-memory, runtime-scoped)."""

    timestamp: datetime = Field(default_factory=utcnow)
    changed_keys: list[str] = Field(default_factory=list)
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    actor: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None


class AdminSettingsPersistRequest(BaseModel):
    """Persist current mutable runtime settings to backend/.env and optionally redeploy."""

    skip_redeploy: bool = False


class AdminSettingsPersistResponse(BaseModel):
    """Result payload for admin settings persistence action."""

    env_file: str
    persisted_keys: list[str]
    redeploy_attempted: bool
    redeploy_started: bool
    redeploy_message: str
