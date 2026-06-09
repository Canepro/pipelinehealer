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


class LLMCapabilityState(StrEnum):
    """Operator-facing maturity states for the active LLM runtime."""

    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    PROVIDER_READY = "provider_ready"
    OPERATION_COMPATIBLE = "operation_compatible"
    FULL_CAPABILITY = "full_capability"
    DEGRADED = "degraded"
    NOT_IMPLEMENTED = "not_implemented"


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


class AgentHandoffMode(StrEnum):
    """Supported Assign-to-Agent handoff modes."""

    COPY_ONLY = "copy_only"
    WEBHOOK = "webhook"


class AgentHandoffStatus(StrEnum):
    """Handoff request outcome status values."""

    COPIED = "copied"
    QUEUED = "queued"
    FAILED = "failed"
    DISABLED = "disabled"


class ExternalAgentTarget(StrEnum):
    """Supported external agent-control-plane handoff targets."""

    CODEX_APP_SERVER = "codex_app_server"
    OPENCLAW = "openclaw"
    HERMES = "hermes"
    CUSTOM = "custom"


class HandoffSessionStatus(StrEnum):
    """Durable lifecycle states for delegated external-agent work."""

    CREATED = "created"
    QUEUED = "queued"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    WAITING_ON_PIPELINEHEALER = "waiting_on_pipelinehealer"
    PR_OPENED = "pr_opened"
    COMPLETED = "completed"
    FAILED = "failed"


class HandoffMessageDirection(StrEnum):
    """Direction of one handoff-session message."""

    OUTBOUND = "outbound"
    INBOUND = "inbound"
    INTERNAL = "internal"


class HandoffEventType(StrEnum):
    """Allowed event types in the external-agent callback contract."""

    DELEGATED = "delegated"
    ACKNOWLEDGED = "acknowledged"
    STARTED_WORK = "started_work"
    NEEDS_MORE_INFO = "needs_more_info"
    PR_OPENED = "pr_opened"
    ISSUE_COMMENTED = "issue_commented"
    LABEL_APPLIED = "label_applied"
    WORKFLOW_RERUN = "workflow_rerun"
    COMPLETED = "completed"
    FAILED = "failed"


class HandoffGitHubRefs(BaseModel):
    """GitHub references reported by PipelineHealer or an external agent."""

    repository: str = ""
    run_id: int | None = None
    issue_url: str | None = None
    pr_url: str | None = None
    comment_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    workflow_rerun_url: str | None = None


class HandoffSession(BaseModel):
    """Durable system-of-record session for delegated external-agent work."""

    id: str = Field(default_factory=lambda: "")
    activity_id: str
    target: ExternalAgentTarget
    status: HandoffSessionStatus = HandoffSessionStatus.CREATED
    goal: str = Field(default="", max_length=4000)
    created_by: str | None = None
    request_id: str | None = None
    delivery_id: str | None = None
    external_thread_id: str | None = None
    github: HandoffGitHubRefs = Field(default_factory=HandoffGitHubRefs)
    labels: list[str] = Field(default_factory=list)
    policy_decision: str = "operator_requested"
    callback_url: str | None = None
    context_sha256: str = ""
    context_preview: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class HandoffMessage(BaseModel):
    """One redacted message or event in a handoff session."""

    id: str = Field(default_factory=lambda: "")
    session_id: str
    event_type: HandoffEventType
    direction: HandoffMessageDirection
    actor: str = ""
    body: str = Field(default="", max_length=20000)
    payload_sha256: str = ""
    payload_redacted: dict[str, Any] = Field(default_factory=dict)
    github: HandoffGitHubRefs = Field(default_factory=HandoffGitHubRefs)
    labels: list[str] = Field(default_factory=list)
    signature_verified: bool = False
    request_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


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


class JenkinsBridgeJob(BaseModel):
    """Jenkins bridge job descriptor."""

    name: str
    url: str
    build_number: int
    result: str
    duration_ms: int | None = None


class JenkinsBridgeFailure(BaseModel):
    """Jenkins bridge failure payload section."""

    stage: str = ""
    step: str = ""
    result: str = ""
    tool: str = ""
    command: str = ""
    exit_code: int | None = None
    summary: str
    error_lines: list[str] = Field(default_factory=list)
    log_excerpt: str = Field(default="", max_length=20000)


class JenkinsBridgeArtifact(BaseModel):
    """Jenkins bridge artifact reference."""

    name: str
    url: str


class JenkinsBridgePayload(BaseModel):
    """Signed Jenkins bridge ingest payload."""

    schema_version: str = "1.0"
    provider: str
    delivery_id: str
    sent_at: datetime
    repository: str
    branch: str
    commit_sha: str = Field(default="", pattern=r"^[0-9a-fA-F]{40}$|^$")
    job: JenkinsBridgeJob
    failure: JenkinsBridgeFailure
    artifacts: list[JenkinsBridgeArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class LLMDiagnosisRejection(BaseModel):
    """Structured explanation for why an LLM diagnosis payload was discarded."""

    rejected: bool = False
    reason: str = ""
    candidate_count: int = 0


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
    llm_rejection: LLMDiagnosisRejection | None = None


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


class LLMCapabilityEvidenceView(BaseModel):
    """Recent activity evidence used to classify current LLM capability."""

    activity_id: str
    workflow_run_id: int
    observed_at: datetime
    model: str
    fallback_used: bool = False
    error_count: int = 0
    failure_type: str | None = None
    diagnosis_source: str | None = None
    diagnosis_confidence: float | None = None
    remediation_action: str | None = None
    remediation_success: bool | None = None


class MCPActionAuditEntry(BaseModel):
    """Audit record for one MCP tool-policy decision or invocation."""

    actor: str
    provider: str = "unknown"
    tool: str
    payload_hash: str
    result: str
    request_id: str
    latency_ms: float = 0.0
    success: bool = False
    error_class: str | None = None


class MCPModelPath(BaseModel):
    """Observed MCP execution path and source attribution for one activity."""

    provider: str
    enabled: bool = False
    available: bool = False
    read_only: bool = True
    reason: str = "disabled"
    configured_tools: list[str] = Field(default_factory=list)
    tool_invocations: dict[str, int] = Field(default_factory=dict)
    total_latency_ms: float = 0.0
    source_attribution: dict[str, int] = Field(default_factory=dict)
    error_count: int = 0
    action_audit: list[MCPActionAuditEntry] = Field(default_factory=list)


class FailureContext(BaseModel):
    """Normalized failure context extracted from run evidence."""

    failing_job: str | None = None
    failing_step: str | None = None
    failing_command: str | None = None
    signal: str | None = None


class LearningContextMatch(BaseModel):
    """One ranked active learning artifact injected into runtime context."""

    id: str
    title: str
    failure_type: FailureType | None = None
    reason_code: str | None = None
    suggested_playbook: str = ""
    repositories: list[str] = Field(default_factory=list)
    verification_pass_rate: float = 0.0
    occurrence_count: int = 0
    match_basis: list[str] = Field(default_factory=list)
    match_rank: int = 0
    match_score: float = 0.0


class LearningContextTrace(BaseModel):
    """Trace of retrieval-backed learning context used during one activity."""

    diagnosis_matches: list[LearningContextMatch] = Field(default_factory=list)
    remediation_matches: list[LearningContextMatch] = Field(default_factory=list)
    diagnosis_injected: bool = False
    remediation_injected: bool = False


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
    learning_context_trace: LearningContextTrace | None = None
    llm_model_path: LLMModelPath | None = None
    mcp_model_path: MCPModelPath | None = None
    remediation_result: RemediationResult | None = None
    external_diagnostics: list[ExternalDiagnostic] = Field(default_factory=list)
    source_selection_path: str | None = None
    source_delivery_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    agent_handoff_audit: list["AgentHandoffAuditEntry"] = Field(default_factory=list)
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
    storage_mode: str
    storage_backend: str
    heal_mode: str
    auto_apply_remediation: bool
    auto_create_pr: bool
    jenkins_bridge_allow_pr: bool
    auto_create_issue: bool
    auto_retry_workflow: bool
    auto_create_tracking_issue_for_prs: bool
    auto_close_on_workflow_success: bool
    auto_merge_remediation_prs: bool
    auto_merge_strategy: str
    auto_merge_poll_seconds: float
    auto_merge_require_clean_checks: bool
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
    settings_secret_backend: str
    api_auth_enabled: bool
    admin_api_auth_enabled: bool
    auth_mode: str
    entra_auth_enabled: bool
    entra_admin_roles: list[str]
    github_app_id: str
    github_pat_configured: bool
    github_app_configured: bool
    github_auth_mode: str
    jenkins_bridge_enabled: bool
    jenkins_bridge_max_skew_seconds: int
    jenkins_bridge_replay_ttl_seconds: int
    jenkins_bridge_max_body_bytes: int
    gh_aw_tools_enabled: bool
    gh_aw_ingestion_mode: str
    gh_aw_known_workflows: list[str]
    external_diagnostics_wait_seconds: float
    external_diagnostics_poll_interval_seconds: float
    agent_handoff_enabled: bool
    agent_handoff_mode: str
    agent_handoff_webhook_configured: bool
    agent_handoff_webhook_host: str
    agent_handoff_webhook_allowlist: list[str]
    agent_handoff_timeout_seconds: float
    agent_handoff_max_retries: int
    agent_handoff_default_target: str
    agent_handoff_enabled_targets: list[str]
    codex_app_server_handoff_configured: bool
    openclaw_handoff_configured: bool
    hermes_handoff_configured: bool
    ph_allowed_repos: list[str]
    cors_allowed_origins: list[str]
    cors_allow_origin_regex: str
    llm_provider: str
    openai_compatible_base_url: str
    openai_compatible_model: str
    codex_app_server_transport: str
    codex_app_server_command: str
    codex_app_server_model: str
    codex_app_server_turn_timeout_ms: int
    codex_app_server_ws_url: str
    codex_app_server_ws_allow_remote: bool
    llm_model_analysis: str
    llm_model_diagnosis: str
    llm_model_remediation: str
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
    infisical_project_id: str
    infisical_environment: str
    infisical_secret_path: str
    infisical_cli_path: str
    infisical_api_url: str
    setup_status: "SetupStatusView"
    settings_metadata: dict[str, "AppSettingMetadataView"] = Field(default_factory=dict)


class SetupCheckView(BaseModel):
    """One setup-readiness check displayed in the admin UI."""

    ready: bool = False
    detail: str = ""


class SetupStatusView(BaseModel):
    """Grouped setup-readiness summary for the UI-first configuration flow."""

    ready: bool = False
    storage_bootstrap: SetupCheckView = Field(default_factory=SetupCheckView)
    auth_bootstrap: SetupCheckView = Field(default_factory=SetupCheckView)
    secret_backend: SetupCheckView = Field(default_factory=SetupCheckView)
    llm_runtime: SetupCheckView = Field(default_factory=SetupCheckView)
    github_runtime: SetupCheckView = Field(default_factory=SetupCheckView)
    jenkins_bridge: SetupCheckView = Field(default_factory=SetupCheckView)
    webhook_secrets: SetupCheckView = Field(default_factory=SetupCheckView)


class AppSettingSource(StrEnum):
    """Observable provenance categories for settings shown in the admin UI."""

    DEFAULT = "default"
    ENV = "env"
    RUNTIME_OVERRIDE = "runtime_override"
    PERSISTED_RUNTIME_OVERRIDE = "persisted_runtime_override"
    COMPUTED = "computed"


class AppSettingMetadataView(BaseModel):
    """Operator-facing metadata about one exposed settings field."""

    source: AppSettingSource
    mutable: bool = False
    requires_restart: bool = False
    durable: bool = True
    sensitive: bool = False
    note: str = ""


class AdminSettingsUpdateRequest(BaseModel):
    """Admin runtime settings overrides persisted through durable runtime config."""

    heal_mode: str | None = None
    auto_apply_remediation: bool | None = None
    auto_create_pr: bool | None = None
    jenkins_bridge_allow_pr: bool | None = None
    auto_create_issue: bool | None = None
    auto_retry_workflow: bool | None = None
    auto_create_tracking_issue_for_prs: bool | None = None
    auto_close_on_workflow_success: bool | None = None
    auto_merge_remediation_prs: bool | None = None
    auto_merge_strategy: str | None = None
    auto_merge_poll_seconds: float | None = Field(default=None, ge=0.0, le=900.0)
    auto_merge_require_clean_checks: bool | None = None
    max_remediation_attempts: int | None = Field(default=None, ge=1, le=50)
    verify_webhook_signature: bool | None = None
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
    agent_handoff_enabled: bool | None = None
    agent_handoff_mode: str | None = None
    agent_handoff_webhook_allowlist: list[str] | None = None
    agent_handoff_timeout_seconds: float | None = Field(default=None, gt=0.0, le=30.0)
    agent_handoff_max_retries: int | None = Field(default=None, ge=0, le=5)
    agent_handoff_default_target: str | None = None
    agent_handoff_enabled_targets: list[str] | None = None
    ph_allowed_repos: list[str] | None = None
    llm_provider: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_chat_api_version: str | None = None
    openai_compatible_base_url: str | None = None
    openai_compatible_model: str | None = None
    codex_app_server_transport: str | None = None
    codex_app_server_command: str | None = None
    codex_app_server_model: str | None = None
    codex_app_server_turn_timeout_ms: int | None = Field(default=None, ge=1000, le=900000)
    codex_app_server_ws_url: str | None = None
    codex_app_server_ws_allow_remote: bool | None = None
    llm_model_analysis: str | None = None
    llm_model_diagnosis: str | None = None
    llm_model_remediation: str | None = None
    github_app_id: str | None = None
    mcp_enabled: bool | None = None
    mcp_provider: str | None = None
    mcp_read_only: bool | None = None
    mcp_timeout_seconds: float | None = Field(default=None, gt=0.0, le=120.0)
    mcp_max_retries: int | None = Field(default=None, ge=0, le=10)
    mcp_tool_policies: dict[str, str] | None = None
    mcp_repo_allowlist: list[str] | None = None
    jenkins_bridge_enabled: bool | None = None
    jenkins_bridge_max_skew_seconds: int | None = Field(default=None, ge=1, le=3600)
    jenkins_bridge_replay_ttl_seconds: int | None = Field(default=None, ge=60, le=604800)
    jenkins_bridge_max_body_bytes: int | None = Field(default=None, ge=1024, le=4194304)
    azure_openai_deployment_name: str | None = None
    infisical_project_id: str | None = None
    infisical_environment: str | None = None
    infisical_secret_path: str | None = None
    infisical_cli_path: str | None = None
    infisical_api_url: str | None = None


class SecretWriteRequest(BaseModel):
    """Request payload for writing or clearing one runtime-managed secret."""

    value: str | None = None
    clear: bool = False


class AdminSecretsUpdateRequest(BaseModel):
    """Secret-write payload for runtime-managed sensitive settings."""

    secrets: dict[str, SecretWriteRequest] = Field(default_factory=dict)


class SecretSettingView(BaseModel):
    """Non-sensitive UI view for one runtime-managed secret."""

    key: str
    configured: bool = False
    source: str = "missing"
    backend: str = "unknown"
    requires_restart: bool = False
    overridden_by_env: bool = False
    last_updated_at: str | None = None
    safe_hint: str | None = None
    note: str = ""


class LLMProviderHealthView(BaseModel):
    """Health/status payload for configured LLM provider adapter."""

    provider: str
    implemented: bool
    configured: bool = False
    available: bool
    provider_ready: bool = False
    operation_compatible: bool = False
    full_capability: bool = False
    capability_state: LLMCapabilityState = LLMCapabilityState.NOT_CONFIGURED
    capability_summary: str = ""
    reason: str
    message: str
    endpoint: str | None = None
    deployment_name: str | None = None
    api_version: str | None = None
    last_validated_at: datetime | None = None
    last_validation: LLMCapabilityEvidenceView | None = None


class MCPProviderHealthView(BaseModel):
    """Health/status payload for configured MCP provider adapter."""

    provider: str
    enabled: bool
    read_only: bool
    available: bool
    reason: str
    message: str
    configured_tools: list[str] = Field(default_factory=list)


class AgentHandoffConfigView(BaseModel):
    """Runtime-safe handoff config exposed to activity views."""

    enabled: bool
    mode: AgentHandoffMode
    webhook_configured: bool
    timeout_seconds: float
    max_retries: int
    default_target: ExternalAgentTarget = ExternalAgentTarget.CODEX_APP_SERVER
    enabled_targets: list[ExternalAgentTarget] = Field(default_factory=list)
    target_configured: dict[ExternalAgentTarget, bool] = Field(default_factory=dict)
    reason: str = "ok"


class NotificationTargetHealthView(BaseModel):
    """Receiver-side notification target health surfaced to operators."""

    configured_targets: int
    enabled_targets: int
    invalid_targets: int
    supported_target_types: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AgentHandoffIntegrationStatusView(BaseModel):
    """Live operator-facing status for the external handoff receiver boundary."""

    enabled: bool
    mode: AgentHandoffMode
    webhook_configured: bool
    webhook_host: str = ""
    receiver_health_url: str | None = None
    receiver_status: str
    reason: str
    checked_at: str
    notifications: NotificationTargetHealthView | None = None


class AgentHandoffRequest(BaseModel):
    """Request payload for Assign-to-Agent handoff."""

    mode: AgentHandoffMode | None = None
    context: str = Field(min_length=1, max_length=20000)
    context_format: str = "markdown"


class AgentHandoffResponse(BaseModel):
    """API response for Assign-to-Agent handoff requests."""

    status: AgentHandoffStatus
    mode: AgentHandoffMode
    activity_id: str
    delivery_id: str | None = None
    message: str = ""
    request_id: str | None = None


class AgentHandoffAuditEntry(BaseModel):
    """Audit record for one Assign-to-Agent handoff attempt."""

    status: AgentHandoffStatus
    mode: AgentHandoffMode
    actor: str | None = None
    request_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    context_chars: int = 0
    context_sha256: str = ""
    context_preview: str = ""
    delivery_id: str | None = None
    destination_host: str | None = None
    error: str | None = None


class HandoffSessionCreateRequest(BaseModel):
    """Request payload for creating a durable external-agent handoff session."""

    target: ExternalAgentTarget = ExternalAgentTarget.CODEX_APP_SERVER
    goal: str = Field(min_length=1, max_length=4000)
    context: str = Field(default="", max_length=20000)
    context_format: str = "markdown"
    send: bool = True
    labels: list[str] = Field(default_factory=list)
    policy_decision: str = "operator_requested"
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffSessionEventRequest(BaseModel):
    """External-agent callback payload for one handoff session event."""

    event_type: HandoffEventType
    message: str = Field(default="", max_length=20000)
    actor: str = "external_agent"
    external_thread_id: str | None = None
    github: HandoffGitHubRefs = Field(default_factory=HandoffGitHubRefs)
    labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffSessionView(BaseModel):
    """Session plus recent messages returned to operator surfaces."""

    session: HandoffSession
    messages: list[HandoffMessage] = Field(default_factory=list)


class HandoffSessionCreateResponse(BaseModel):
    """Response after creating and optionally dispatching a handoff session."""

    session: HandoffSession
    initial_message: HandoffMessage
    delivery_status: AgentHandoffStatus
    message: str = ""


class LearningQueueStatus(StrEnum):
    """Status values for remediation learning queue items."""

    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    RETIRED = "retired"


class LearningVerificationOutcome(StrEnum):
    """Allowed operator verification outcomes for learning feedback."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class LearningGuidanceEffectiveness(StrEnum):
    """Operator-rated impact of promoted learning guidance on one activity."""

    HELPED = "helped"
    NEUTRAL = "neutral"
    HURT = "hurt"


class LearningPromotionReadiness(BaseModel):
    """Promotion-readiness evaluation for activating a learned playbook."""

    ready: bool = False
    status_gate_passed: bool = False
    occurrence_gate_passed: bool = False
    success_rate_gate_passed: bool = False
    sample_gate_passed: bool = False
    verification_sample_gate_passed: bool = False
    verification_gate_passed: bool = False
    requires_force_activate: bool = True
    reasons: list[str] = Field(default_factory=list)
    min_occurrences: int = 2
    min_success_rate: float = 0.8
    min_sample_size: int = 2
    min_verification_sample_size: int = 1
    min_verification_pass_rate: float = 0.8
    occurrence_count: int = 0
    success_rate: float = 0.0
    sample_size: int = 0
    verification_sample_count: int = 0
    verification_pass_rate: float = 0.0


class LearningQueueItem(BaseModel):
    """Governance-reviewed remediation learning queue item."""

    id: str
    fingerprint: str
    title: str
    failure_type: FailureType | None = None
    reason_code: str | None = None
    proposed_action: str = "skip"
    suggested_playbook: str = ""
    repositories: list[str] = Field(default_factory=list)
    occurrence_count: int = 0
    success_count: int = 0
    sample_activity_ids: list[str] = Field(default_factory=list)
    verification_sample_count: int = 0
    verification_pass_count: int = 0
    verification_partial_count: int = 0
    verification_fail_count: int = 0
    verification_pass_rate: float = 0.0
    guidance_application_count: int = 0
    guidance_feedback_count: int = 0
    guidance_helped_count: int = 0
    guidance_neutral_count: int = 0
    guidance_hurt_count: int = 0
    guidance_help_rate: float = 0.0
    latest_activity_at: datetime | None = None
    status: LearningQueueStatus = LearningQueueStatus.CANDIDATE
    decision_reason: str = ""
    decision_actor: str | None = None
    promotion_readiness: LearningPromotionReadiness | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LearningQueueRefreshResponse(BaseModel):
    """Result payload for learning queue candidate refresh."""

    status: str = "ok"
    considered_activities: int
    generated_candidates: int
    upserted_candidates: int


class LearningQueueDecisionRequest(BaseModel):
    """Decision request payload for one learning queue candidate."""

    action: str
    reason: str = ""
    force_activate: bool = False


class LearningVerificationFeedbackRequest(BaseModel):
    """Operator verification payload for one completed activity."""

    activity_id: str
    identification: LearningVerificationOutcome
    diagnosis: LearningVerificationOutcome
    remediation: LearningVerificationOutcome
    guidance_effectiveness: LearningGuidanceEffectiveness | None = None
    notes: str = ""
    issue_number: int | None = Field(default=None, ge=1)
    issue_url: str | None = None
    target_version: str | None = None


class LearningVerificationFeedbackResponse(BaseModel):
    """Result payload for verification feedback writes."""

    status: str = "ok"
    activity_id: str
    verification_overall: LearningVerificationOutcome
    updated_candidate_ids: list[str] = Field(default_factory=list)


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
    deprecated: bool = False
