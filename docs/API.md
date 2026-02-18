# PipelineHealer API Reference

<!-- LAST_VERIFIED: 56fec24 -->

This document describes the PipelineHealer backend REST API, authentication model, request/response contracts, and best practices.

Base URL (Azure): `https://ca-canepro-ph-backend.kinddune-53ac219d.eastus2.azurecontainerapps.io`
Base URL (local): `http://127.0.0.1:8000`

---

## Authentication

Authentication behavior is controlled by `AUTH_MODE`:

- `api_key` (default): legacy headers (`X-API-Key`, `X-Admin-Key`)
- `entra`: OIDC Bearer tokens (Microsoft Entra ID)
- `hybrid`: accepts either Bearer token or legacy key headers (migration mode)

### API Key mode (`AUTH_MODE=api_key`)

All `/api/*` endpoints require `X-API-Key` in non-development environments.

```bash
curl -H "X-API-Key: $API_AUTH_KEY" "$BACKEND_URL/api/stats"
```

- Configured via `API_AUTH_KEY` env var.
- Bypassed automatically when `ENVIRONMENT=development`.

### Entra mode (`AUTH_MODE=entra`)

All `/api/*` endpoints require `Authorization: Bearer <token>`.

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" "$BACKEND_URL/api/stats"
```

- Configure backend with `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, and optional `ENTRA_ALLOWED_AUDIENCES`.
- Admin settings routes require Entra role/scope membership from `ENTRA_ADMIN_ROLES`.
- Token issuer validation accepts both tenant-scoped Microsoft issuer formats:
  - `https://login.microsoftonline.com/<tenant>/v2.0`
  - `https://sts.windows.net/<tenant>/`
- Recommended Entra app registration setting for API apps: `api.requestedAccessTokenVersion = 2`.

Quick registration checklist (beginner):

1. API app (`PipelineHealer API`): expose scope `PipelineHealer.Access`, add role `PipelineHealer.Admin`.
2. SPA app (`PipelineHealer SPA`): configure SPA redirect URIs (root + `/app`), request delegated `PipelineHealer.Access`.
3. Grant admin consent for SPA permissions.
4. Assign users/groups to `PipelineHealer Admin` in Enterprise Applications.

### Hybrid mode (`AUTH_MODE=hybrid`)

`/api/*` accepts either Bearer token or API key header.

- If Bearer token is used for admin endpoints, role checks from `ENTRA_ADMIN_ROLES` apply.
- If key headers are used, `X-API-Key` + `X-Admin-Key` behavior remains unchanged.

### Admin Key (`X-Admin-Key`) in key/hybrid mode

Admin endpoints (`/api/settings`, `/api/settings/audit`) require **both** `X-API-Key` and `X-Admin-Key` when using key-based authentication.

```bash
curl -H "X-API-Key: $API_AUTH_KEY" -H "X-Admin-Key: $ADMIN_API_KEY" "$BACKEND_URL/api/settings"
```

- Configured via `ADMIN_API_KEY` env var.
- In `AUTH_MODE=entra`, admin role authorization replaces `X-Admin-Key`.

### Webhook Signature (`X-Hub-Signature-256`)

The `/webhook/github` endpoint verifies GitHub webhook signatures using HMAC-SHA256 when `VERIFY_WEBHOOK_SIGNATURE=true` (default in non-development).

---

## Endpoints

### Health

#### `GET /health`

Unauthenticated health check.

**Response** `200 OK`:

```json
{
  "status": "healthy"
}
```

---

### Webhook

#### `POST /webhook/github`

Receives GitHub `workflow_run` webhook events. This is the primary ingest point for the healing pipeline.

**Required Headers**:

| Header | Description |
|--------|-------------|
| `X-GitHub-Event` | Event type (must be `workflow_run` or `ping`) |
| `X-GitHub-Delivery` | Unique delivery ID |
| `X-Hub-Signature-256` | HMAC-SHA256 signature (required when verification is enabled) |

**Behavior**:

- Accepts `workflow_run` events with `action: completed` and `conclusion: failure` or `timed_out`.
- Ignores non-failure conclusions (`success`, `cancelled`, etc.).
- Checks `PH_ALLOWED_REPOS` allowlist; rejects repos not in scope.
- Triggers the four-agent healing pipeline asynchronously.

**Response** `200 OK` (processing):

```json
{
  "status": "processing",
  "activity_id": "uuid-string",
  "repository": "owner/repo",
  "workflow_run_id": 12345678,
  "delivery_id": "github-delivery-uuid"
}
```

**Response** `200 OK` (ignored — non-failure):

```json
{
  "status": "ignored",
  "reason": "conclusion is 'success', not a failure",
  "delivery_id": "github-delivery-uuid"
}
```

**Response** `200 OK` (ignored — repo not in allowlist):

```json
{
  "status": "ignored",
  "reason": "repository 'owner/repo' is outside PH_ALLOWED_REPOS",
  "delivery_id": "github-delivery-uuid"
}
```

**Response** `200 OK` (ping):

```json
{
  "status": "pong",
  "delivery_id": "github-delivery-uuid"
}
```

---

### Dashboard Stats

#### `GET /api/stats`

Returns aggregate statistics for the dashboard.

**Auth**: `X-API-Key`

**Response** `200 OK` (`DashboardStats`):

```json
{
  "total_runs_processed": 15,
  "actioned_remediations": 10,
  "successful_remediations": 8,
  "failed_remediations": 2,
  "pending_remediations": 0,
  "auto_pr_remediations": 5,
  "issue_remediations": 3,
  "safety_blocked_remediations": 2,
  "by_failure_type": {
    "dependency": 5,
    "lint": 3,
    "test": 4,
    "timeout": 2,
    "build_config": 1
  },
  "by_repository": {
    "Canepro/pipelinehealer-demo": 15
  },
  "average_resolution_time_seconds": 42.5,
  "last_updated": "2026-02-14T00:48:00Z"
}
```

---

### Activities

#### `GET /api/activities`

Returns activity records with optional filtering and pagination.

**Auth**: `X-API-Key`

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repository` | string | — | Filter by repository full name |
| `status` | enum | — | Filter by status (`pending`, `analyzing`, `diagnosing`, `remediating`, `completed`, `failed`, `skipped`) |
| `failure_type` | enum | — | Filter by failure type (`dependency`, `test`, `lint`, `build_config`, `timeout`, `unknown`) |
| `limit` | int | 50 | Max results (1–200) |
| `offset` | int | 0 | Pagination offset |
| `since` | datetime | — | Filter activities created after this timestamp |

**Response** `200 OK` (array of `ActivityRecord`):

```json
[
  {
    "id": "ce099499-3dd6-4968-a3ce-3337c481e4f5",
    "repositoryId": "1154889327",
    "repository_name": "Canepro/pipelinehealer-demo",
    "workflow_run_id": 22045680912,
    "workflow_name": "CI",
    "status": "completed",
    "failure_type": "dependency",
    "diagnosis": {
      "failure_type": "dependency",
      "diagnosis_source": "pattern",
      "confidence": 0.85,
      "root_cause": "missing Node.js module",
      "affected_files": [],
      "error_details": {
        "package_name": "left-pad",
        "package_manager": "npm"
      },
      "suggested_fix": "Update or install the missing dependency",
      "is_auto_fixable": true
    },
    "llm_model_path": {
      "provider": "azure_openai",
      "model": "gpt-5-mini",
      "fallback_used": false,
      "call_count": 2,
      "total_latency_ms": 742.11,
      "error_count": 0
    },
    "remediation_result": {
      "success": true,
      "action_taken": "create_pr",
      "pr_url": "https://github.com/Canepro/pipelinehealer-demo/pull/91",
      "issue_url": "https://github.com/Canepro/pipelinehealer-demo/issues/90",
      "error_message": null,
      "details": {
        "pr_number": 91,
        "tracking_issue_number": 90,
        "branch_name": "fix/update-left-pad-run-22045680912"
      }
    },
    "external_diagnostics": [
      {
        "source": "ci-doctor",
        "status": "available",
        "summary": "[CI Failure Doctor] Dependency failure due to missing left-pad",
        "url": "https://github.com/Canepro/pipelinehealer-demo/issues/89",
        "matched_run_id": 22045680912,
        "confidence_delta": 0.08,
        "metadata": {
          "issue_number": 89,
          "issue_state": "open",
          "match_basis": "run_url",
          "details": {
            "summary": "The build job halts because left-pad is not declared in package.json...",
            "root_cause": "The dependency check simulates a missing module by requiring left-pad...",
            "recommended_actions": "- [x] Add left-pad as a dependency in package.json.",
            "doctor_engine": "copilot",
            "doctor_model": "gpt-5.1-codex-mini",
            "doctor_run_url": "https://github.com/Canepro/pipelinehealer-demo/actions/runs/22045687770"
          }
        },
        "collected_at": "2026-02-16T00:14:17.991899Z"
      }
    ],
    "created_at": "2026-02-16T00:08:39.168556Z",
    "updated_at": "2026-02-16T00:14:19.911037Z",
    "duration_seconds": 340.7,
    "error": null
  }
]
```

#### `GET /api/activities/{activity_id}`

Returns a single activity record by ID.

**Auth**: `X-API-Key`

**Response** `200 OK`: single `ActivityRecord` (same shape as above).

**Response** `404 Not Found`: `{"detail": "Activity not found"}`

#### `POST /api/activities/{activity_id}/retry`

Triggers a GitHub re-run of failed jobs for the given activity. The original activity record is **not** modified — it retains its `failed` status and error details as a historical record. When the re-run completes, a new `workflow_run.completed` webhook creates a fresh activity record for the retry attempt.

**Auth**: `X-API-Key`

**Constraints**: Activity status must be `failed` or `skipped`.

**Response** `200 OK`:

```json
{
  "status": "queued",
  "activity_id": "uuid-string",
  "message": "GitHub rerun-failed-jobs requested"
}
```

**Response** `400 Bad Request`: Activity status is not retryable.

#### `POST /api/backfill-diagnostics`

Triggers an on-demand sweep that backfills external diagnostics (ci-doctor findings) for completed activities whose original poll window was exhausted.

**Auth**: `X-API-Key`

**Query Parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `max_age_hours` | float | 24.0 | Only consider activities created within this many hours (1–168). |

**Response** `200 OK`:

```json
{
  "status": "completed",
  "backfilled": 2,
  "max_age_hours": 24.0
}
```

**Notes**: A background sweep also runs automatically every 10 minutes, so manual triggering is only needed for immediate results (e.g. after confirming ci-doctor has finished).

---

### Repositories

#### `GET /api/repositories`

Returns repositories with activity counts.

**Auth**: `X-API-Key`

**Response** `200 OK`: array of repository summary objects.

---

### Timeline and Breakdown

#### `GET /api/timeline`

Returns activity timeline data for chart rendering.

**Auth**: `X-API-Key`

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int | 7 | Number of days to include (1–30) |

**Response** `200 OK`: timeline data object.

#### `GET /api/failure-breakdown`

Returns failure count breakdown by type for a given time window.

**Auth**: `X-API-Key`

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int | 30 | Number of days to include (1–90) |

**Response** `200 OK`:

```json
{
  "dependency": 5,
  "lint": 3,
  "test": 4,
  "build_config": 1,
  "timeout": 2
}
```

---

### Admin Settings

#### `GET /api/settings`

Returns the current runtime configuration (non-secret values only).

**Auth**: `X-API-Key` + `X-Admin-Key`

**Response** `200 OK` (`AppSettingsView`):

```json
{
  "environment": "production",
  "storage_backend": "cosmos_db",
  "heal_mode": "safe",
  "auto_create_pr": true,
  "auto_create_tracking_issue_for_prs": true,
  "max_remediation_attempts": 3,
  "pipeline_step_timeout_seconds": 120.0,
  "github_api_max_retries": 3,
  "github_api_retry_base_seconds": 0.5,
  "github_api_retry_max_seconds": 8.0,
  "log_prompt_max_chars": 18000,
  "log_prompt_head_chars": 9000,
  "log_prompt_tail_chars": 9000,
  "verify_webhook_signature": true,
  "verify_webhook_signature_in_development": false,
  "api_auth_enabled": true,
  "admin_api_auth_enabled": true,
  "github_pat_configured": true,
  "github_app_configured": false,
  "github_auth_mode": "pat",
  "ph_allowed_repos": ["Canepro/pipelinehealer-demo"],
  "llm_provider": "azure_openai",
  "mcp_enabled": false,
  "mcp_provider": "disabled",
  "mcp_read_only": true,
  "mcp_timeout_seconds": 15.0,
  "mcp_max_retries": 1,
  "gh_aw_tools_enabled": false,
  "gh_aw_ingestion_mode": "disabled",
  "gh_aw_known_workflows": ["ci-doctor", "schema-consistency-checker", "breaking-change-checker"],
  "external_diagnostics_wait_seconds": 60.0,
  "external_diagnostics_poll_interval_seconds": 15.0,
  "cors_allowed_origins": ["http://localhost:3000", "http://localhost:5173"],
  "cors_allow_origin_regex": "https://.*\\.azurecontainerapps\\.io",
  "azure_openai_endpoint": "https://your-resource.cognitiveservices.azure.com/",
  "azure_openai_deployment_name": "gpt-5-mini",
  "azure_openai_api_version": "2025-04-01-preview",
  "azure_openai_chat_api_version": "2024-12-01-preview",
  "openai_compatible_base_url": null,
  "openai_compatible_model": null,
  "openai_compatible_api_key_configured": false
}
```

#### `PATCH /api/settings`

Applies runtime overrides (immediate effect; persist durably via `POST /api/settings/persist`).

**Auth**: `X-API-Key` + `X-Admin-Key`

**Optional Headers**:

| Header | Description |
|--------|-------------|
| `X-Request-Id` | Client-supplied request ID for audit correlation |

**Request Body** (`AdminSettingsUpdateRequest`): all fields optional, include only what you want to change.

```json
{
  "heal_mode": "debug",
  "auto_create_pr": false,
  "max_remediation_attempts": 5,
  "pipeline_step_timeout_seconds": 180.0,
  "log_prompt_max_chars": 20000,
  "log_prompt_head_chars": 10000,
  "log_prompt_tail_chars": 10000
}
```

**Mutable Fields** (with constraints):

| Field | Type | Constraints |
|-------|------|-------------|
| `heal_mode` | string | `safe`, `demo`, or `debug` |
| `auto_create_pr` | bool | — |
| `auto_create_tracking_issue_for_prs` | bool | — |
| `max_remediation_attempts` | int | 1–50 |
| `verify_webhook_signature_in_development` | bool | — |
| `pipeline_step_timeout_seconds` | float | 0–600 |
| `github_api_max_retries` | int | 0–10 |
| `github_api_retry_base_seconds` | float | 0–30 |
| `github_api_retry_max_seconds` | float | 0–120 |
| `log_prompt_max_chars` | int | 1,000–200,000 |
| `log_prompt_head_chars` | int | 100–200,000 |
| `log_prompt_tail_chars` | int | 100–200,000 |
| `ph_allowed_repos` | list[string] | Each entry must be `owner/repo` format; URLs and SSH paths are normalized |
| `gh_aw_tools_enabled` | bool | Enable/disable GitHub Agentic Workflows integration |
| `gh_aw_ingestion_mode` | string | `disabled` or `passive` |
| `gh_aw_known_workflows` | list[string] | Workflow names to detect (e.g. `ci-doctor`, `schema-consistency-checker`) |
| `external_diagnostics_wait_seconds` | float | 0–900 (set `0` for fully async diagnostics/backfill) |
| `external_diagnostics_poll_interval_seconds` | float | >0–120; must be `<= external_diagnostics_wait_seconds` when wait budget is enabled |
| `azure_openai_deployment_name` | string | Non-empty; switches AI model deployment at runtime |
| `llm_provider` | string | `azure_openai`, `openai_compatible`, or `custom` |
| `openai_compatible_base_url` | string | Required when `llm_provider=openai_compatible`; must be `http(s)://...` |
| `openai_compatible_model` | string | Required when `llm_provider=openai_compatible` |
| `mcp_enabled` | bool | Enable MCP provider integration hooks |
| `mcp_provider` | string | `disabled`, `github`, `azure_monitor`, or `custom` |
| `mcp_read_only` | bool | Restrict MCP actions to read-only mode |
| `mcp_timeout_seconds` | float | 0–120 |
| `mcp_max_retries` | int | 0–10 |

**Validation**:
- `log_prompt_head_chars + log_prompt_tail_chars` must be `<= log_prompt_max_chars`.
- `external_diagnostics_poll_interval_seconds` must be `<= external_diagnostics_wait_seconds` when wait budget is enabled (`wait > 0`).

**Response** `200 OK`: updated `AppSettingsView` (same shape as GET).

**Response** `422 Unprocessable Entity`: validation failure.

**Side Effects**: Creates an audit entry (persisted to Cosmos DB when available, in-memory fallback otherwise). Triggers agent cache invalidation when `azure_openai_deployment_name` changes so the new model takes effect immediately.

#### `GET /api/settings/llm/provider-health`

Returns health/status for the currently selected LLM provider adapter.

**Auth**: `X-API-Key` + `X-Admin-Key`

**Response** `200 OK` (`LLMProviderHealthView`):

```json
{
  "provider": "azure_openai",
  "implemented": true,
  "available": true,
  "reason": "ok",
  "message": "Azure OpenAI provider configuration looks valid.",
  "endpoint": "https://example.openai.azure.com/",
  "deployment_name": "gpt-5-mini",
  "api_version": "2025-04-01-preview"
}
```

Example when using `llm_provider=openai_compatible` with missing config:

```json
{
  "provider": "openai_compatible",
  "implemented": true,
  "available": false,
  "reason": "missing_base_url",
  "message": "OPENAI_COMPATIBLE_BASE_URL is not configured."
}
```

#### `GET /api/settings/mcp/provider-health`

Returns health/status for the currently selected MCP provider adapter.

**Auth**: `X-API-Key` + `X-Admin-Key`

**Response** `200 OK` (`MCPProviderHealthView`):

```json
{
  "provider": "github",
  "enabled": true,
  "read_only": true,
  "available": false,
  "reason": "missing_github_token",
  "message": "GITHUB_PERSONAL_ACCESS_TOKEN is required for GitHub MCP provider.",
  "configured_tools": []
}
```

#### `POST /api/settings/persist`

Durably persists current mutable runtime settings so they survive backend restarts and redeployments.

**Auth**: `X-API-Key` + `X-Admin-Key`

**Request Body** (optional):

```json
{
  "skip_redeploy": false
}
```

- `skip_redeploy` defaults to `false`.
- When `true`, settings are persisted but env-only redeploy is skipped.

**Behavior**:

- Writes all mutable settings to durable storage (Cosmos DB).
- Optionally writes to `backend/.env` when the file is accessible (local development).
- On next startup, persisted settings are loaded and re-applied automatically.

**Response** `200 OK`:

```json
{
  "env_file": "",
  "persisted_keys": [
    "HEAL_MODE",
    "AUTO_CREATE_PR",
    "MAX_REMEDIATION_ATTEMPTS",
    "GH_AW_TOOLS_ENABLED",
    "GH_AW_INGESTION_MODE",
    "EXTERNAL_DIAGNOSTICS_WAIT_SECONDS",
    "EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS",
    "AZURE_OPENAI_DEPLOYMENT_NAME"
  ],
  "redeploy_attempted": false,
  "redeploy_started": false,
  "redeploy_message": "Persisted settings to durable storage. Local backend/.env not available in this runtime, so env-only redeploy was skipped."
}
```

**Notes**:

- In Azure Container Apps, `env_file` is usually empty (no writable local `backend/.env` in the running container).
- Settings are always persisted to durable storage regardless of environment.

#### `GET /api/settings/audit`

Returns recent admin settings change records (latest first).

**Auth**: `X-API-Key` + `X-Admin-Key`

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Max records (1–200) |

**Response** `200 OK` (array of `AdminSettingsAuditEntry`):

```json
[
  {
    "timestamp": "2026-02-14T00:45:00Z",
    "changed_keys": ["heal_mode"],
    "changes": {
      "heal_mode": {
        "old": "debug",
        "new": "safe"
      }
    },
    "actor": "admin_key:sha256:a1b2c3d4e5f6",
    "request_id": "my-trace-id-123",
    "client_ip": "100.100.0.132",
    "user_agent": "curl/8.7.1"
  }
]
```

**Notes**:

- Audit entries are persisted to Cosmos DB when available, with in-memory fallback.
- Capped at 200 entries (oldest dropped when exceeded).
- Actor fingerprints are salted SHA-256 hashes (12 chars), not raw keys.

---

## Data Models

### FailureType (enum)

| Value | Description |
|-------|-------------|
| `dependency` | Missing or incompatible dependency |
| `test` | Test assertion or runtime failure |
| `lint` | Lint/format rule violation |
| `build_config` | Build or workflow configuration error |
| `timeout` | Workflow or job timeout exceeded |
| `unknown` | Unclassifiable failure |

### RemediationStatus (enum)

| Value | Description |
|-------|-------------|
| `pending` | Queued for processing |
| `analyzing` | Log analysis in progress |
| `diagnosing` | Root cause diagnosis in progress |
| `remediating` | Remediation action in progress |
| `completed` | Successfully processed |
| `failed` | Processing failed |
| `skipped` | Deliberately skipped |

### ExternalDiagnosticStatus (enum)

| Value | Description |
|-------|-------------|
| `available` | External diagnostic findings were successfully ingested |
| `unavailable` | External workflow not installed on the monitored repo, or no findings available within bounded polling |
| `disabled` | External diagnostics integration disabled by runtime settings |
| `error` | Error during external diagnostic retrieval |

### DiagnosisSource (enum)

| Value | Description |
|-------|-------------|
| `pattern` | Deterministic pattern-based diagnosis path |
| `llm` | LLM-assisted diagnosis path |

### Diagnosis (object)

| Field | Type | Description |
|-------|------|-------------|
| `failure_type` | FailureType | Failure category |
| `diagnosis_source` | DiagnosisSource \| null | Whether diagnosis came from deterministic pattern logic or LLM path |
| `confidence` | float | Confidence score (`0.0`–`1.0`) |
| `root_cause` | string | Human-readable root cause |
| `affected_files` | string[] | Suspected impacted files |
| `error_details` | object | Additional structured details |
| `suggested_fix` | string | High-level suggested remediation |
| `is_auto_fixable` | bool | Whether safe auto-remediation is supported |

### LLMModelPath (object)

Observed model path telemetry for one activity.

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | Effective provider used for calls (`azure_openai`, `openai_compatible`, etc.) |
| `model` | string | Deployment/model used during activity execution |
| `fallback_used` | bool | Whether compatibility fallback path was used |
| `call_count` | int | Number of observed LLM invocations |
| `total_latency_ms` | float | Aggregate LLM call latency in milliseconds |
| `error_count` | int | Number of failed LLM calls before retry/fallback success |

### ExternalDiagnostic (object)

Represents findings from an external diagnostic tool (e.g. GitHub Agentic Workflows `ci-doctor`).

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Tool name (e.g. `ci-doctor`) |
| `status` | ExternalDiagnosticStatus | Ingestion outcome |
| `summary` | string | Short external finding summary |
| `confidence_delta` | float | Confidence adjustment applied to native diagnosis (`-1.0` to `1.0`) |
| `url` | string \| null | Link to external findings (issue, discussion, etc.) |
| `matched_run_id` | int \| null | GitHub workflow run ID the findings relate to |
| `metadata` | object | Structured diagnostic metadata (reason codes, issue numbers, etc.) |
| `metadata.details` | object \| null | Deep content enrichment extracted from the ci-doctor issue body (see below) |
| `collected_at` | string (ISO datetime) | Timestamp when the external finding was collected |

#### `metadata.details` (deep enrichment)

When `status` is `available` and the ci-doctor issue body contains structured sections, `metadata.details` is populated with sanitized, truncated (≤2000 chars/section) content:

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Short failure summary |
| `root_cause` | string | Root cause analysis narrative |
| `failed_jobs` | string | Failed jobs and error messages |
| `investigation_findings` | string | Investigation details |
| `recommended_actions` | string | Recommended fix steps |
| `prevention_strategies` | string | Prevention guidance |
| `historical_context` | string | Historical pattern context |
| `ai_self_improvement` | string | AI team learning notes |
| `trigger` | string | Workflow trigger type (e.g. `workflow_dispatch`) |
| `doctor_engine` | string | ci-doctor engine (e.g. `copilot`) |
| `doctor_model` | string | ci-doctor model (e.g. `gpt-5.1-codex-mini`) |
| `doctor_run_url` | string | URL to the ci-doctor workflow run |

All fields are optional; only sections present in the issue body are included. Internal boilerplate (HTML comments, setup hints, expiry markers, temp-file paths) is stripped before storage.

### RemediationAction (enum)

| Value | Description |
|-------|-------------|
| `create_pr` | Created a fix pull request |
| `create_issue` | Created a structured issue |
| `retry_workflow` | Re-ran failed GitHub Actions jobs |
| `notify` | Notification only |
| `skip` | No action taken (see `reason_code` in `details` for why) |

When `action_taken` is `skip`, the `remediation_result.details` object may include:

| Field | Description |
|-------|-------------|
| `reason_code` | Machine-readable code (for example `OUTPUT_ISSUES_DISABLED`, `OUTPUT_REPO_READ_ONLY`) |
| `reason_detail` | Human-readable explanation of why the artifact could not be created |

This occurs when diagnosis succeeded but the target repository constraints prevented artifact publication (issues disabled, repo archived, insufficient permissions). The activity still completes as `completed` — not `failed` — because the diagnosis and remediation logic ran successfully.

---

## Best Practices

### 1. Use `X-Request-Id` for Traceability

Include `X-Request-Id` in `PATCH /api/settings` calls. The ID appears in audit entries, backend logs, and API responses, making it easy to correlate changes across systems.

```bash
curl -X PATCH \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: deploy-feb14-safe-mode" \
  -H "Content-Type: application/json" \
  -d '{"heal_mode":"safe"}' \
  "$BACKEND_URL/api/settings"
```

### 2. Prefer One-Command Operations

Instead of composing raw curl calls, use `bash scripts/ph.sh`:

```bash
bash scripts/ph.sh settings:check       # GET /api/settings
bash scripts/ph.sh settings:audit --limit 5  # GET /api/settings/audit
bash scripts/ph.sh audit:proof --limit 5     # PATCH + GET audit proof
bash scripts/ph.sh logs                      # filtered backend logs
bash scripts/ph.sh logs:grep --pattern "error"
```

### 3. Webhook Setup Best Practices

- Use **exactly one** active `workflow_run` webhook per environment (local smee OR Azure direct — never both).
- Always set and verify `GITHUB_WEBHOOK_SECRET` in non-development.
- Verify delivery health after setup:
  ```bash
  gh api repos/<owner>/<repo>/hooks --jq '.[] | {id,active,url:.config.url,events,last_response:.last_response.code}'
  ```
- Use `bash scripts/ph.sh webhook:add --repo owner/repo` for managed webhook creation.

### 4. Safe Mode Defaults

- Use `HEAL_MODE=safe` for production and demo stability.
- Use `HEAL_MODE=debug` when you need verbose pipeline step logging without changing behavior.
- Reserve `HEAL_MODE=demo` for hackathon demos where aggressive behavior (retry flaky tests, bump timeouts) is acceptable.

### 5. Repo Allowlist Scope

- Set `PH_ALLOWED_REPOS` to limit webhook processing to specific repositories.
- Empty allowlist means "all repos" — only appropriate for local development.
- For canary rollout, use:
  ```bash
  bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2
  ```

### 6. Prompt Tuning

If the LLM is producing low-quality summaries due to log truncation, adjust the prompt window:

```bash
curl -X PATCH \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"log_prompt_max_chars":30000,"log_prompt_head_chars":15000,"log_prompt_tail_chars":15000}' \
  "$BACKEND_URL/api/settings"
```

Keep `head_chars + tail_chars <= max_chars`.

### 7. Retry and Timeout Tuning

- `pipeline_step_timeout_seconds`: controls per-step (analyze/diagnose/remediate) timeout. Default 120s is generous; reduce for faster failure feedback.
- `github_api_max_retries`: controls retries for GitHub API transient errors (429, 5xx). Default 3 with exponential backoff.
- `max_remediation_attempts`: caps how many times PipelineHealer will attempt remediation for a given workflow within a repository before stopping. Default 3.

### 8. LLM Transient Error Handling

Azure OpenAI calls (log summarization, diagnosis fallback) automatically retry on transient errors (HTTP 429, 5xx, connection errors, timeouts) with exponential backoff and jitter. This is separate from `github_api_max_retries` which covers GitHub REST API calls. LLM retries are internal to the agent pipeline and not configurable via settings — they use sensible defaults (3 retries, 1s base delay, 30s max delay).

### 9. Storage Considerations

- **Azure Cosmos DB** (`cosmos_db`): used in production. Activities persist across restarts.
- **In-Memory** (`in_memory`): used in development (`ENVIRONMENT=development`). Activities reset on restart.
- Admin settings audit trail is persisted to Cosmos DB when available, with in-memory fallback (capped at 200 entries in memory).

### 10. Error Handling Patterns

API errors follow standard HTTP conventions:

| Status | Meaning |
|--------|---------|
| `200` | Success |
| `400` | Bad request (invalid payload) |
| `401` | Missing or invalid authentication |
| `404` | Resource not found |
| `422` | Validation failure (invalid field values) |
| `500` | Server error (storage/workflow not initialized) |

All error responses include a `detail` field:

```json
{
  "detail": "heal_mode must be one of: safe, demo, debug"
}
```

### 11. CORS Configuration

- `CORS_ALLOWED_ORIGINS`: exact-match origins (CSV or JSON array).
- `CORS_ALLOW_ORIGIN_REGEX`: regex pattern for dynamic Azure Container Apps domains.
- Default allows `localhost:3000` and `localhost:5173` for development, plus `*.azurecontainerapps.io` for Azure.

---

## One-Command Quick Reference

| Command | API Equivalent |
|---------|---------------|
| `bash scripts/ph.sh settings:check` | `GET /api/settings` |
| `bash scripts/ph.sh settings:audit --limit N` | `GET /api/settings/audit?limit=N` |
| `bash scripts/ph.sh audit:proof --limit N` | `PATCH /api/settings` + `GET /api/settings/audit` |
| `bash scripts/ph.sh status` | Azure Container Apps status |
| `bash scripts/ph.sh logs` | `az containerapp logs show` (filtered) |
| `bash scripts/ph.sh logs:raw` | `az containerapp logs show` (unfiltered) |
| `bash scripts/ph.sh logs:grep --pattern X` | `az containerapp logs show` + `grep` |
| `bash scripts/ph.sh demo:e2e` | Trigger + verify full E2E |
| `bash scripts/ph.sh demo:proof` | `gh pr list` + `gh issue list` + activities |
| `bash scripts/ph.sh warm` | Set `minReplicas=1` |
| `bash scripts/ph.sh lowcost` | Set `minReplicas=0` |
