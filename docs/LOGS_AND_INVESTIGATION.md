# Logs And Investigation Guide

<!-- LAST_VERIFIED: fadd4cf -->

Use this guide to debug PipelineHealer behavior quickly in local, Docker, and Azure runs.

## Fast Triage (Recommended)

1. Confirm runtime is healthy.
2. Confirm effective settings.
3. Pull filtered backend logs.
4. Correlate logs with one activity ID and GitHub run.
5. Decide whether the issue is auth, ingestion, diagnosis, remediation, or integration policy.

```bash
bash scripts/ph.sh status
bash scripts/ph.sh settings:check | jq
bash scripts/ph.sh logs
```

## Issue Quality Gate (Required)

When PipelineHealer creates or updates a remediation issue, record an explicit accuracy check before closure:

- Identification: was the failure type/scope correct?
- Diagnosis: did root cause match workflow/job logs?
- Remediation: did proposed action resolve the failure (or was defer reason valid)?
- Target version: set a milestone/version label before closing.

Recommended issue section heading:

```markdown
### PipelineHealer Accuracy Assessment
- Identification: ✅ / ⚠️ / ❌
- Diagnosis: ✅ / ⚠️ / ❌
- Remediation: ✅ / ⚠️ / ❌
```

## Deploy Warning Triage (Release QA)

Use this before cutting tags to avoid shipping untracked warning debt:

```bash
bash scripts/ph.sh deploy
bash scripts/release_scope_check.sh
```

If deployment warnings are present:
- confirm they are listed in `docs/FUTURE_PLAN.md` with an explicit status
- confirm they are referenced in `CHANGELOG.md` `Unreleased`
- if warning is upstream/transient, link the tracking issue in both locations

## Core Commands

- `bash scripts/ph.sh logs`:
  - filtered backend logs (best default for operators)
- `bash scripts/ph.sh logs:raw`:
  - unfiltered backend logs (use for edge debugging)
- `bash scripts/ph.sh logs:grep --pattern "<regex>"`:
  - focused search for error signatures
- `bash scripts/ph.sh settings:check`:
  - confirms effective runtime settings currently loaded
- `bash scripts/ph.sh status`:
  - confirms backend/frontend app status and scale

## Command Scope Matrix

Use the right command path for your runtime to avoid false troubleshooting starts.

### Azure deployment path (requires `az` login)

```bash
bash scripts/ph.sh status
bash scripts/ph.sh logs
bash scripts/ph.sh logs:grep --pattern "error|timeout|traceback|401|403"
bash scripts/ph.sh settings:check
bash scripts/ph.sh settings:audit --limit 10
```

### Local/Docker path (no Azure CLI required)

```bash
PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh logs
PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh logs:grep --pattern "error|timeout|traceback"
PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh settings:check
```

Notes:
- `PH_BACKEND_URL` points CLI/API commands at your local backend.
- This is the recommended path when running `docker compose` locally or backend host-native.
- In UI, Control Center now shows these grouped command scopes with copy actions.

Useful grep patterns:

```bash
bash scripts/ph.sh logs:grep --pattern "401|403|Invalid bearer token|admin API key"
bash scripts/ph.sh logs:grep --pattern "AzureOpenAI|openai|responses|chat.completions|FallbackAgent"
bash scripts/ph.sh logs:grep --pattern "mcp|fetch_failure_context|tool_policy|repo_not_allowlisted"
```

## Activity-Centric Investigation

Start from one activity page:

- capture `activity_id`
- capture `workflow_run_id`
- capture `repository_name`

Then correlate:

- Activity Detail -> `Failure Context` (`failing_job`, `failing_step`, `failing_command`, `signal`)
- Activity Detail -> `Diagnosis` and confidence
- Activity Detail -> `Model Path` and `MCP Observability`
- GitHub run URL: `https://github.com/<owner>/<repo>/actions/runs/<workflow_run_id>`

## Common Incident Playbooks

### 1) `401` from `/api/*` or `/api/settings*`

Check:

- `AUTH_MODE` and Entra values (`ENTRA_*`)
- whether frontend token/session is stale
- key mode headers (`X-API-Key`, `X-Admin-Key`) when using key/hybrid flows

Actions:

```bash
bash scripts/ph.sh settings:check | jq '.auth_mode,.entra_auth_enabled,.entra_admin_roles'
bash scripts/ph.sh deploy:env
```

UI hint: if login session appears stale, re-login and clear site data for the app origin.

### 2) `403` creating issue/PR

Likely causes:

- fine-grained PAT missing Issues/PR write permissions
- repo not granted to token
- target repo has Issues disabled or is archived/read-only

Checks:

```bash
gh auth status
bash scripts/ph.sh settings:check | jq '.github_auth_mode,.ph_allowed_repos'
```

### 3) Diagnosis failed or LLM connection errors

Check:

- endpoint/deployment/api version values from `settings:check`
- backend logs for retry/fallback messages
- whether provider fallback occurred (`llm_model_path.fallback_used`)

Checks:

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.azure_openai_endpoint,.azure_openai_deployment_name,.llm_model_analysis,.llm_model_diagnosis,.llm_model_remediation,.azure_openai_api_version,.azure_openai_chat_api_version'
bash scripts/ph.sh logs:grep --pattern "Diagnosis failed|AzureOpenAIResponsesClient|API version not supported|FallbackAgent"
```

### 4) MCP appears limited/unavailable

Check:

- `mcp_enabled`, `mcp_provider`, `mcp_read_only`
- allowlist and per-tool policy blocks
- activity-level `mcp_model_path.reason` and `action_audit`:
  - UI now shows friendly interpretation and raw codes together for both fields.

Checks:

```bash
bash scripts/ph.sh settings:check | jq '.mcp_enabled,.mcp_provider,.mcp_read_only,.mcp_tool_policies,.mcp_repo_allowlist'
bash scripts/ph.sh logs:grep --pattern "mcp_disabled|repo_not_allowlisted|tool_policy|approval_required|blocked_by_read_only_mode"
```

## Misclassification Or Low-Confidence Diagnosis

Use this order:

1. validate `failure_context` (job/step/command/signal)
2. inspect `diagnosis.error_details` and evidence lines
3. check external diagnostics status and reason codes
4. compare with exact GitHub failing job/step text

If needed, run with broader logs and gather one reproducible run ID before changing detection logic.

## Evidence Collection Template

For bug reports or review handoff, include:

- activity ID
- repository and workflow run ID
- failure type shown in UI
- diagnosis source (`pattern` or `llm`)
- failure context values
- model path (`provider:model`, fallback used)
- MCP status/reason (if enabled)
- 10-30 relevant backend log lines

## Related Docs

- `API.md`
- `CLI.md`
- `LOCAL_DEMO_RUNBOOK.md`
- `features/05-explainability-and-observability.md`
