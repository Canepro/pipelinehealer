# PipelineHealer API Reference

<!-- LAST_VERIFIED: f8910da -->

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

Admin endpoints under `/api/settings*` (for example `/api/settings`, `/api/settings/audit`, `/api/settings/persist`, `/api/settings/learning/*`) require **both** `X-API-Key` and `X-Admin-Key` when using key-based authentication.

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
  "service": "PipelineHealer",
  "version": "0.5.7",
  "status": "healthy",
  "environment": "production",
  "storage_backend": "cosmos_db"
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

#### `POST /webhook/jenkins`

Receives signed Jenkins bridge payloads when `JENKINS_BRIDGE_ENABLED=true`.

Required headers:

- `X-PH-Bridge-Provider: jenkins`
- `X-PH-Bridge-Timestamp: <unix_epoch_seconds>`
- `X-PH-Bridge-Nonce: <unique_nonce>`
- `X-PH-Bridge-Signature: sha256=<hmac>`

Behavior:

- Verifies HMAC signature using `JENKINS_BRIDGE_SHARED_SECRET`.
- Enforces timestamp skew (`JENKINS_BRIDGE_MAX_SKEW_SECONDS`) and replay protections.
- Replay protection is atomic for concurrent requests (in-flight nonce/delivery reservations prevent TOCTOU duplicate bypass).
- Enforces `PH_ALLOWED_REPOS` allowlist before processing.
- Starts a synthetic activity path with `source_selection_path=jenkins_bridge`.
- Uses issue-first output by default for bridge events; set `JENKINS_BRIDGE_ALLOW_PR=true` (and `AUTO_CREATE_PR=true`) to allow PR artifacts from bridge-sourced remediations.

**Response** `200 OK` (processing):

```json
{
  "status": "processing",
  "activity_id": "uuid-string",
  "source": "jenkins_bridge",
  "repository": "owner/repo",
  "delivery_id": "jenkins:job/path#1234"
}
```

**Response** `200 OK` (ignored duplicate nonce):

```json
{
  "status": "ignored",
  "reason": "duplicate_nonce"
}
```

**Response** `200 OK` (ignored duplicate delivery):

```json
{
  "status": "ignored",
  "reason": "duplicate_delivery",
  "delivery_id": "jenkins:job/path#1234"
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
  "mcp_enabled_runs_30d": 6,
  "llm_fallback_rate_30d": 12.5,
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
        "package_manager": "npm",
        "classification_signal": "missing Node.js module",
        "classification_family": "dependency",
        "classification_pattern": "Cannot find module"
      },
      "suggested_fix": "Add `left-pad` to package.json and refresh the lockfile.",
      "is_auto_fixable": true
    },
    "failure_context": {
      "failing_job": "build",
      "failing_step": "Run npm run build",
      "failing_command": "npm run build",
      "signal": "poll_window_exhausted"
    },
    "llm_model_path": {
      "provider": "azure_openai",
      "model": "gpt-5-mini",
      "fallback_used": false,
      "call_count": 2,
      "total_latency_ms": 742.11,
      "error_count": 0
    },
    "mcp_model_path": {
      "provider": "github",
      "enabled": true,
      "available": true,
      "read_only": true,
      "reason": "ok",
      "configured_tools": ["fetch_failure_context", "fetch_runbook_context", "publish_artifact", "rerun_pipeline"],
      "tool_invocations": {
        "fetch_failure_context": 2,
        "fetch_runbook_context": 2
      },
      "total_latency_ms": 183.4,
      "source_attribution": {
        "github-mcp": 1,
        "knowledge-mcp": 1
      },
      "error_count": 0,
      "action_audit": [
        {
          "actor": "orchestrator:external_diagnostics",
          "provider": "github",
          "tool": "fetch_failure_context",
          "payload_hash": "a2cc8f03e1f5",
          "result": "success:attempt_1",
          "request_id": "req-019c6882",
          "latency_ms": 61.8,
          "success": true,
          "error_class": null
        }
      ]
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

#### `GET /api/agent-handoff/config`

Returns runtime-safe Assign-to-Agent integration config used by Activity Detail UI.

**Auth**: `X-API-Key`

**Response** `200 OK`:

```json
{
  "enabled": true,
  "mode": "webhook",
  "webhook_configured": true,
  "timeout_seconds": 8.0,
  "max_retries": 1,
  "reason": "ok"
}
```

#### `GET /api/agent-handoff/integration-status`

Returns live operator-facing receiver and notification dependency status for Assign-to-Agent webhook mode.

**Auth**: `X-API-Key`

**Response** `200 OK`:

```json
{
  "enabled": true,
  "mode": "webhook",
  "webhook_configured": true,
  "webhook_host": "ph-agent-handoff-dev-zarrajk1.azurewebsites.net",
  "receiver_health_url": "https://ph-agent-handoff-dev-zarrajk1.azurewebsites.net/api/healthz",
  "receiver_status": "available",
  "reason": "no_notification_targets",
  "checked_at": "2026-03-06T13:35:35.239697+00:00",
  "notifications": {
    "configured_targets": 0,
    "enabled_targets": 0,
    "invalid_targets": 0,
    "supported_target_types": [
      "rocketchat_webhook",
      "email",
      "slack_webhook",
      "teams_webhook",
      "webhook"
    ],
    "errors": []
  }
}
```

Notes:

- `receiver_status=not_required` means webhook delivery is currently not needed (`copy_only` mode or feature disabled).
- `receiver_status=available` means the backend reached the receiver health endpoint successfully.
- `receiver_status=degraded` means the receiver is reachable but one or more configured notification targets are invalid.
- `receiver_status=unreachable` means the receiver health endpoint probe failed.
- The probe only exposes operator-safe health metadata; it does not return the secret webhook URL.
- `supported_target_types` now includes `email` when the reference receiver build includes SMTP-backed notification delivery.

#### `POST /api/activities/{activity_id}/agent-handoff`

Submit one Assign-to-Agent handoff request in `copy_only` or `webhook` mode.

**Auth**: `X-API-Key`

**Request body**:

```json
{
  "mode": "webhook",
  "context": "# PipelineHealer Activity Context ...",
  "context_format": "markdown"
}
```

Behavior:

- Applies redaction-safe context handling before audit/delivery.
- `copy_only`: records auditable handoff event only (no network call).
- `webhook`: sends bounded outbound POST with timeout/retry and destination allowlist checks.
- Returns structured failure responses for delivery errors (non-blocking to activity page operations).

**Response** `200 OK`:

```json
{
  "status": "queued",
  "mode": "webhook",
  "activity_id": "uuid-string",
  "delivery_id": "handoff:uuid:uuid",
  "message": "Handoff delivered to configured webhook",
  "request_id": "request-id"
}
```

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

The payload now includes a `settings_metadata` map so the operator surface can distinguish
configured value from effective provenance. Source values are portable, app-observable categories only:
`default`, `env`, `runtime_override`, `persisted_runtime_override`, and `computed`.

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Response** `200 OK` (`AppSettingsView`):

```json
{
  "environment": "production",
  "storage_mode": "cosmos",
  "storage_backend": "cosmos_db",
  "heal_mode": "safe",
  "auto_apply_remediation": true,
  "auto_create_pr": true,
  "jenkins_bridge_allow_pr": false,
  "auto_create_issue": true,
  "auto_retry_workflow": true,
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
  "llm_model_analysis": "",
  "llm_model_diagnosis": "",
  "llm_model_remediation": "",
  "mcp_enabled": false,
  "mcp_provider": "disabled",
  "mcp_read_only": true,
  "mcp_timeout_seconds": 15.0,
  "mcp_max_retries": 1,
  "mcp_tool_policies": {
    "fetch_failure_context": "read_only",
    "fetch_runbook_context": "read_only",
    "publish_artifact": "write_with_approval",
    "rerun_pipeline": "write_with_approval"
  },
  "mcp_repo_allowlist": ["Canepro/pipelinehealer-demo"],
  "gh_aw_tools_enabled": false,
  "gh_aw_ingestion_mode": "disabled",
  "gh_aw_known_workflows": ["ci-doctor", "schema-consistency-checker", "breaking-change-checker"],
  "external_diagnostics_wait_seconds": 60.0,
  "external_diagnostics_poll_interval_seconds": 15.0,
  "agent_handoff_enabled": false,
  "agent_handoff_mode": "copy_only",
  "agent_handoff_webhook_configured": false,
  "agent_handoff_webhook_host": "",
  "agent_handoff_webhook_allowlist": [],
  "agent_handoff_timeout_seconds": 8.0,
  "agent_handoff_max_retries": 1,
  "cors_allowed_origins": ["http://localhost:3000", "http://localhost:5173"],
  "cors_allow_origin_regex": "https://.*\\.azurecontainerapps\\.io",
  "azure_openai_endpoint": "https://your-resource.cognitiveservices.azure.com/",
  "azure_openai_deployment_name": "gpt-5-mini",
  "azure_openai_api_version": "2025-04-01-preview",
  "azure_openai_chat_api_version": "2024-12-01-preview",
  "openai_compatible_base_url": "",
  "openai_compatible_model": "",
  "openai_compatible_api_key_configured": false,
  "settings_metadata": {
    "heal_mode": {
      "source": "env",
      "mutable": true,
      "requires_restart": false,
      "durable": true,
      "sensitive": false,
      "note": ""
    },
    "storage_mode": {
      "source": "computed",
      "mutable": false,
      "requires_restart": false,
      "durable": true,
      "sensitive": false,
      "note": ""
    },
    "agent_handoff_webhook_host": {
      "source": "env",
      "mutable": false,
      "requires_restart": true,
      "durable": true,
      "sensitive": false,
      "note": "Derived from the startup-only Assign-to-Agent webhook URL; only the destination host is exposed."
    },
    "agent_handoff_enabled": {
      "source": "runtime_override",
      "mutable": true,
      "requires_restart": false,
      "durable": false,
      "sensitive": false,
      "note": ""
    }
  }
}
```

Notes:
- `settings_metadata.<field>.source=env` means startup-managed config. The app intentionally does not guess whether that startup value arrived via plain env, ACA `secretref`, Helm secret, or another deployment adapter.
- `agent_handoff_webhook_host` exposes only the configured destination hostname; the full webhook URL remains startup-only configuration in this release.
- `settings_metadata.<field>.sensitive=true` means the field is a presence-only or operator-safe projection of hidden sensitive startup configuration.
- `settings_metadata.<field>.durable=false` means the current value only exists in this running process until `POST /api/settings/persist` is called.
- `computed` fields are derived status/projection values, not directly mutable settings.

#### `PATCH /api/settings`

Applies runtime overrides (immediate effect; persist durably via `POST /api/settings/persist`).

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Optional Headers**:

| Header | Description |
|--------|-------------|
| `X-Request-Id` | Client-supplied request ID for audit correlation |

**Request Body** (`AdminSettingsUpdateRequest`): all fields optional, include only what you want to change.

```json
{
  "heal_mode": "debug",
  "auto_apply_remediation": true,
  "auto_create_pr": false,
  "jenkins_bridge_allow_pr": false,
  "auto_create_issue": true,
  "auto_retry_workflow": false,
  "max_remediation_attempts": 5,
  "pipeline_step_timeout_seconds": 180.0,
  "log_prompt_max_chars": 20000,
  "log_prompt_head_chars": 10000,
  "log_prompt_tail_chars": 10000,
  "llm_model_analysis": "gpt-5-mini-fast",
  "llm_model_diagnosis": "gpt-5-mini-reasoner",
  "llm_model_remediation": "gpt-5-mini"
}
```

**Mutable Fields** (with constraints):

| Field | Type | Constraints |
|-------|------|-------------|
| `heal_mode` | string | `safe`, `demo`, `freestyle`, or `debug` |
| `auto_apply_remediation` | bool | Global execution gate (`false` = plan-only dry-run) |
| `auto_create_pr` | bool | — |
| `auto_create_issue` | bool | — |
| `auto_retry_workflow` | bool | — |
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
| `gh_aw_ingestion_mode` | string | `disabled`, `passive`, or `hybrid` |
| `gh_aw_known_workflows` | list[string] | Workflow names to detect (e.g. `ci-doctor`, `schema-consistency-checker`) |
| `external_diagnostics_wait_seconds` | float | 0–900 (set `0` for fully async diagnostics/backfill) |
| `external_diagnostics_poll_interval_seconds` | float | >0–120; must be `<= external_diagnostics_wait_seconds` when wait budget is enabled |
| `agent_handoff_enabled` | bool | Enable/disable Assign-to-Agent runtime path |
| `agent_handoff_mode` | string | `copy_only` or `webhook` |
| `agent_handoff_webhook_allowlist` | list[string] | Bare hostnames only; when non-empty and a startup webhook URL is present, it must include that destination host |
| `agent_handoff_timeout_seconds` | float | >0–30 |
| `agent_handoff_max_retries` | int | 0–5 |
| `azure_openai_deployment_name` | string | Non-empty; switches AI model deployment at runtime |
| `llm_provider` | string | `azure_openai`, `openai_compatible`, or `custom` |
| `openai_compatible_base_url` | string | Required when `llm_provider=openai_compatible`; must be `http(s)://...` |
| `openai_compatible_model` | string | Required when `llm_provider=openai_compatible` |
| `llm_model_analysis` | string | Optional per-task model/deployment override for analysis |
| `llm_model_diagnosis` | string | Optional per-task model/deployment override for diagnosis |
| `llm_model_remediation` | string | Optional per-task model/deployment override for remediation |
| `mcp_enabled` | bool | Enable MCP provider integration hooks |
| `mcp_provider` | string | `disabled`, `github`, `azure_monitor`, or `custom` |
| `mcp_read_only` | bool | Restrict MCP actions to read-only mode |
| `mcp_timeout_seconds` | float | 0–120 |
| `mcp_max_retries` | int | 0–10 |
| `mcp_tool_policies` | object | `tool -> policy` map; policy is `disabled`, `read_only`, `write_with_approval`, or `auto` |
| `mcp_repo_allowlist` | list[string] | Optional owner/repo allowlist enforced for MCP actions |

**Validation**:
- `log_prompt_head_chars + log_prompt_tail_chars` must be `<= log_prompt_max_chars`.
- `external_diagnostics_poll_interval_seconds` must be `<= external_diagnostics_wait_seconds` when wait budget is enabled (`wait > 0`).
- `agent_handoff_webhook_allowlist` must contain only bare hostnames. When non-empty and `AGENT_HANDOFF_WEBHOOK_URL` is set, it must include that URL's host; an empty list disables host restrictions.
- `mcp_tool_policies` must use supported policy modes only (`disabled`, `read_only`, `write_with_approval`, `auto`).

**Response** `200 OK`: updated `AppSettingsView` (same shape as GET).

**Response** `422 Unprocessable Entity`: validation failure.

**Side Effects**: Creates an audit entry (persisted to configured durable storage when available, in-memory fallback otherwise). Triggers agent cache invalidation when model-routing fields change (`azure_openai_deployment_name`, `llm_provider`, `openai_compatible_model`, `llm_model_analysis`, `llm_model_diagnosis`, `llm_model_remediation`) so new routing takes effect immediately.

#### `GET /api/settings/llm/provider-health`

Returns health/status for the currently selected LLM provider adapter.

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Response** `200 OK` (`LLMProviderHealthView`):

```json
{
  "provider": "azure_openai",
  "implemented": true,
  "configured": true,
  "available": true,
  "provider_ready": true,
  "operation_compatible": false,
  "full_capability": false,
  "capability_state": "provider_ready",
  "capability_summary": "Provider readiness checks pass, but there is no recent live activity for the current model routing.",
  "reason": "ok",
  "message": "Azure OpenAI provider configuration looks valid.",
  "endpoint": "https://example.openai.azure.com/",
  "deployment_name": "gpt-5-mini",
  "api_version": "2025-04-01-preview",
  "last_validated_at": null,
  "last_validation": null
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

Important:

- This endpoint validates provider configuration shape and adapter readiness.
- It does **not** execute a new live completion/request during the probe itself.
- `available=true` means PipelineHealer has enough configuration to attempt LLM calls, not that every model/operation combination is guaranteed to succeed.
- `capability_state` is derived from both provider readiness and the most recent matching live activity for the current routing.
- `last_validation` reflects recent stored LLM evidence, not a synchronous on-demand canary.
- For Azure deployments, verify live model compatibility separately with `bash scripts/ph.sh aoai:check` or a direct provider smoke test.
- If live LLM calls fail, PipelineHealer can still ingest runs and create safe fallback issues, but diagnosis/remediation should be treated as degraded-mode behavior rather than full-capability behavior.

`capability_state` values:

- `not_configured`: required provider settings are missing
- `configured`: required settings are present, but readiness checks are failing
- `provider_ready`: provider readiness passes, but no recent live validation exists for current routing
- `operation_compatible`: recent live activity completed without LLM call errors
- `full_capability`: recent live activity completed with successful LLM diagnosis/remediation
- `degraded`: recent live activity hit LLM call errors for the current routing
- `not_implemented`: provider is scaffolded only

OpenAI-compatible `reason` codes:

- `missing_base_url`, `missing_model`, `missing_api_key`: required config missing
- `probe_timeout`: probe request timed out
- `probe_auth_failed`: API key rejected (`401`/`403`)
- `probe_rate_limited`: provider returned `429`
- `probe_provider_error`: provider returned `5xx`
- `probe_http_error`: non-success HTTP status outside the categories above
- `probe_network_error`: request could not reach provider endpoint

#### `GET /api/settings/mcp/provider-health`

Returns health/status for the currently selected MCP provider adapter.

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

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

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Request Body** (optional):

```json
{
  "skip_redeploy": false
}
```

- `skip_redeploy` defaults to `false`.
- When `true`, settings are persisted but env-only redeploy is skipped.

**Behavior**:

- Writes all mutable settings to configured durable storage backend (`cosmos` or `postgres`).
- Optionally writes to `backend/.env` when the file is accessible (local development).
- On next startup, persisted settings are loaded and re-applied automatically.
- Appends an admin audit record with `changed_keys=["persist_settings"]` (including `X-Request-Id` when provided).

**Response** `200 OK`:

```json
{
  "env_file": "",
  "persisted_keys": [
    "HEAL_MODE",
    "AUTO_APPLY_REMEDIATION",
    "AUTO_CREATE_PR",
    "JENKINS_BRIDGE_ALLOW_PR",
    "AUTO_CREATE_ISSUE",
    "AUTO_RETRY_WORKFLOW",
    "MAX_REMEDIATION_ATTEMPTS",
    "GH_AW_TOOLS_ENABLED",
    "GH_AW_INGESTION_MODE",
    "MCP_ENABLED",
    "MCP_PROVIDER",
    "MCP_READ_ONLY",
    "MCP_TIMEOUT_SECONDS",
    "MCP_MAX_RETRIES",
    "MCP_TOOL_POLICIES",
    "MCP_REPO_ALLOWLIST",
    "EXTERNAL_DIAGNOSTICS_WAIT_SECONDS",
    "EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS",
    "LLM_MODEL_ANALYSIS",
    "LLM_MODEL_DIAGNOSIS",
    "LLM_MODEL_REMEDIATION",
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

#### `GET /api/settings/learning/queue`

Returns governance learning-queue records (candidate/approved/rejected/active/retired).

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | (all) | Optional filter: `candidate`, `approved`, `rejected`, `active`, `retired` |
| `limit` | int | 50 | Max records (1–200) |

**Response** `200 OK` (array of `LearningQueueItem`):

```json
[
  {
    "id": "learning-f6f9f8a2f30ebf72a81a",
    "fingerprint": "f6f9f8a2f30ebf72a81ab1fd91d2a7b9f7c3024b",
    "title": "build_config: REQUIRES_ENV_CONTEXT",
    "failure_type": "build_config",
    "reason_code": "REQUIRES_ENV_CONTEXT",
    "proposed_action": "create_issue",
    "suggested_playbook": "Add missing environment variable in workflow settings.",
    "repositories": ["owner/repo"],
    "occurrence_count": 4,
    "success_count": 4,
    "sample_activity_ids": ["..."],
    "verification_sample_count": 2,
    "verification_pass_count": 2,
    "verification_partial_count": 0,
    "verification_fail_count": 0,
    "verification_pass_rate": 1.0,
    "latest_activity_at": "2026-02-18T20:14:00Z",
    "status": "candidate",
    "decision_reason": "",
    "decision_actor": null,
    "promotion_readiness": {
      "ready": false,
      "status_gate_passed": false,
      "occurrence_gate_passed": true,
      "success_rate_gate_passed": true,
      "sample_gate_passed": false,
      "verification_sample_gate_passed": true,
      "verification_gate_passed": true,
      "requires_force_activate": true,
      "reasons": [
        "status_candidate_requires_approval",
        "sample_size_below_threshold"
      ],
      "min_occurrences": 2,
      "min_success_rate": 0.8,
      "min_sample_size": 2,
      "min_verification_sample_size": 1,
      "min_verification_pass_rate": 0.8,
      "occurrence_count": 4,
      "success_rate": 1.0,
      "sample_size": 1,
      "verification_sample_count": 2,
      "verification_pass_rate": 1.0
    },
    "created_at": "2026-02-18T20:15:00Z",
    "updated_at": "2026-02-18T20:15:00Z",
    "metadata": {}
  }
]
```

#### `POST /api/settings/learning/queue/refresh`

Scans recent successful completed activities and refreshes recurring learning candidates.

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lookback_hours` | float | 168 | Activity scan window |
| `min_occurrences` | int | 2 | Minimum recurring occurrences required for candidate creation |
| `max_scan` | int | 500 | Max activities scanned per refresh |
| `max_candidates` | int | 100 | Max generated candidates upserted per refresh |

**Response** `200 OK`:

```json
{
  "status": "ok",
  "considered_activities": 128,
  "generated_candidates": 6,
  "upserted_candidates": 6
}
```

Side effects:
- Upserts learning queue entries in durable storage.
- Appends admin audit entry with `changed_keys=["learning_queue_refresh"]`.

#### `POST /api/settings/learning/queue/{candidate_id}/decision`

Applies a governance decision for one learning candidate.

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Request Body**:

```json
{
  "action": "approve",
  "reason": "Validated during operator review",
  "force_activate": false
}
```

Allowed actions:
- `approve`
- `reject`
- `activate`
- `retire`
- `reset_candidate`

`force_activate` notes:
- optional boolean, valid only when `action="activate"`
- bypasses readiness gates and writes forced-activation metadata to the candidate + audit trail

Activation readiness gates:
- status must be `approved` (or already `active`)
- `occurrence_count >= 2`
- `success_rate >= 0.8`
- `sample_activity_ids >= 2`
- verified feedback samples `>= 1`
- verification pass rate `>= 0.8`

**Response** `200 OK`: updated `LearningQueueItem`.

**Response** `409 Conflict`:
- returned when `action="activate"` and readiness gates are not satisfied without `force_activate=true`

Side effects:
- Appends admin audit entry with `changed_keys=["learning_queue_decision"]`.
- Captures decision actor fingerprint and request correlation metadata.
- Includes readiness snapshot before/after the decision in audit `changes.learning_queue_decision`.

#### `POST /api/settings/learning/feedback`

Captures operator verification outcomes for one activity and links that evidence into learning readiness.

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

**Request Body**:

```json
{
  "activity_id": "36f67f2f-62f9-4a5a-8c5b-ff6f11f98591",
  "identification": "pass",
  "diagnosis": "partial",
  "remediation": "pass",
  "notes": "Diagnosis needed minor correction after rerun.",
  "issue_number": 25,
  "target_version": "vX.Y.Z"
}
```

Outcomes are `pass|partial|fail`.

`overall` is derived server-side:
- if any dimension is `fail` -> `fail`
- if all dimensions are `pass` -> `pass`
- otherwise -> `partial`

**Response** `200 OK`:

```json
{
  "status": "ok",
  "activity_id": "36f67f2f-62f9-4a5a-8c5b-ff6f11f98591",
  "verification_overall": "partial",
  "updated_candidate_ids": ["learning-f6f9f8a2f30ebf72a81a"]
}
```

Side effects:
- Updates `remediation_result.details.verification` and appends `verification_history`.
- Recomputes verification counters/readiness for affected learning candidates.
- Appends admin audit entry with `changed_keys=["learning_verification_feedback"]`.

#### `GET /api/settings/audit`

Returns recent admin settings change records (latest first).

**Auth**: admin auth (`Authorization: Bearer <token>` with Entra admin role in `entra`/Bearer flow, or `X-API-Key` + `X-Admin-Key` in key-based flow)

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

- Audit entries are persisted to configured durable storage when available, with in-memory fallback.
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

When `diagnosis_source=pattern`, `error_details` may include classification transparency fields:
- `classification_signal`: human-readable signal that matched
- `classification_family`: failure family used by the matcher
- `classification_pattern`: internal pattern signature used for matching

Pattern and LLM diagnoses may also include failure-type-specific structured fields in `error_details`.

Common examples:
- `dependency`: `package_name`, `package_manager`, `manifest_file`, `required_version`
- `lint`: `linter`, `missing_file`, `config_file`, `autofix_command`, `violations`
- `test`: `test_framework`, `failed_tests`, `test_errors`, `failure_scope`, `suspected_files`
- `timeout`: `timed_out_job`, `timed_out_step`, `timeout_minutes`, `suggested_timeout`, `resource_signal`
- `build_config`: `missing_env_vars`, `workflow_permissions_fix`, `permissions`, `misconfiguration_kind`, `config_file`

### FailureContext (object)

Normalized failure context extracted from diagnosis details, log signals, and external diagnostics reason codes.

| Field | Type | Description |
|-------|------|-------------|
| `failing_job` | string \| null | Best-effort failing job name |
| `failing_step` | string \| null | Best-effort failing step label |
| `failing_command` | string \| null | Best-effort failing command extracted from step/log lines |
| `signal` | string \| null | Structured signal code (for example `poll_window_exhausted`, signature, trigger, reason code) |

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

### MCPModelPath (object)

Observed MCP execution-path metadata for one activity.

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | Effective MCP provider selected at runtime (`disabled`, `github`, `azure_monitor`, `custom`) |
| `enabled` | bool | Whether MCP integration was enabled when activity ran |
| `available` | bool | Provider reported healthy/available state |
| `read_only` | bool | Whether provider was constrained to read-only actions |
| `reason` | string | Short provider-health reason code (`ok`, `disabled`, `missing_github_token`, etc.) |
| `configured_tools` | string[] | Provider-advertised tool names for this runtime |
| `tool_invocations` | object | Per-tool invocation counts captured for the activity (actual successful/attempted calls during the run) |
| `total_latency_ms` | float | Aggregate MCP tool-call latency in milliseconds for the activity |
| `source_attribution` | object | Count of ingested external diagnostic sources by key (for traceability) |
| `error_count` | int | Count of MCP tool invocation errors captured for this activity |
| `action_audit` | MCPActionAuditEntry[] | Audited MCP actions with provider/tool/latency/outcome/request correlation |

### MCPActionAuditEntry (object)

| Field | Type | Description |
|-------|------|-------------|
| `actor` | string | Logical actor that initiated the MCP call (for example orchestrator phase) |
| `provider` | string | MCP provider used for this action (`github`, `azure_monitor`, etc.) |
| `tool` | string | MCP tool name |
| `payload_hash` | string | Short hash of invocation payload for traceability without storing raw sensitive payloads |
| `result` | string | Outcome (`success`, `blocked_policy`, `blocked_scope`, `timeout`, `error`, etc.) |
| `request_id` | string \| null | Request/trace correlation ID when available |
| `latency_ms` | float | Observed call latency in milliseconds (`0` for policy-blocked actions) |
| `success` | bool | Whether the tool operation succeeded |
| `error_class` | string \| null | Error class when failed (`TimeoutError`, `HTTPStatusError`, etc.) |

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
| `metadata.source_selection_path` | string \| null | Collection strategy selected for that diagnostic (`gh_aw_passive`, `github_mcp_direct`, `github_mcp_blocked`); hybrid mode may include multiple paths in one activity |
| `metadata.source_selection_reason` | string \| null | Why that strategy/path was selected |
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

Both Azure OpenAI and OpenAI-compatible runtime paths automatically retry on transient errors (HTTP 429, 5xx, connection errors, timeouts) with exponential backoff and jitter. This is separate from `github_api_max_retries` which covers GitHub REST API calls. LLM retries are internal to the agent pipeline and not configurable via settings (defaults: 3 retries, 1s base delay, 16s max delay).

For provider switching and rollback operations, use `docs/MODEL_PROVIDER_SWITCH_RUNBOOK.md`.

### 9. Storage Considerations

- Runtime config exposes both `storage_mode` (intent) and `storage_backend` (active implementation).
- Supported storage modes:
  - `memory`: ephemeral storage, recommended for local development/demo only.
  - `cosmos`: durable storage using Azure Cosmos DB.
  - `postgres`: durable storage using PostgreSQL (`POSTGRES_DSN`).
- Non-development guardrail:
  - Startup fails fast when the selected durable backend is missing required config (`COSMOS_DB_ENDPOINT` or `POSTGRES_DSN`).
  - Explicit non-development memory mode requires `ALLOW_IN_MEMORY_STORAGE_IN_NON_DEVELOPMENT=true`.
- Admin settings audit trail is persisted to durable storage when available, with in-memory fallback buffer for local/dev paths.

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
  "detail": "heal_mode must be one of: safe, demo, freestyle, debug"
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
