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
    remediation_result: RemediationResult | None = None
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
    github_pat_configured: bool
    github_app_configured: bool
    github_auth_mode: str
    cors_allowed_origins: list[str]
    cors_allow_origin_regex: str
    azure_openai_endpoint: str
    azure_openai_deployment_name: str
    azure_openai_api_version: str


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
