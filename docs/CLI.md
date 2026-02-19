# PipelineHealer CLI Reference

<!-- LAST_VERIFIED: b191408 -->

Canonical reference for `scripts/ph.sh` — the one-command operator interface for PipelineHealer.

All commands run from the repo root:

```bash
bash scripts/ph.sh <command> [options]
```

Important: execute with `bash scripts/...`, never `source` or `. scripts/...`.

---

## Command Scope Cheat Sheet

`scripts/ph.sh` supports multiple operating scopes. Pick the right one before running commands.

| Scope | Typical use | Requires `az` | Requires backend URL | Notes |
|------|-------------|---------------|----------------------|-------|
| Azure infra | deploy/manage Azure Container Apps | Yes | No | Uses configured resource group/app names |
| Kubernetes infra | deploy/manage with Helm | No | No | Use `helm` + `kubectl`; see `docs/KUBERNETES_HELM_RUNBOOK.md` |
| Backend API | read/update runtime via API | No | No | Defaults to Azure backend; set `PH_BACKEND_URL` for local/non-Azure backend |
| GitHub-only | inspect/reset demo artifacts | No | No | Uses `gh` only |
| Local container ops | container logs + AOAI smoke | No | No | Requires local Docker/Podman compose stack |
| Repo maintenance | version sync + release prep | No | No | Uses `scripts/check_version_sync.sh` and `scripts/release.sh` |

Quick examples:

```bash
# Backend API scope (local OR any reachable backend URL)
PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh settings:check

# Azure infra scope
bash scripts/ph.sh deploy

# GitHub-only scope
bash scripts/ph.sh demo:proof --repo owner/repo --limit 10

# Repo maintenance scope
bash scripts/check_version_sync.sh
```

Kubernetes deploy path is intentionally kept outside `scripts/ph.sh` right now to avoid cloud-lock assumptions in the CLI. Use Helm runbook commands directly.

---

## Commands

### Deploy

| Command | Description |
|---------|-------------|
| `deploy` | Full Azure redeploy (build, push, update, verify) |
| `deploy:env` | Sync backend runtime env vars only (no image rebuild) |
| `deploy:bg` | Run redeploy in background |
| `deploy:logs` | Follow detached redeploy logs |
| `deploy:status` | Show detached redeploy process status |

```bash
bash scripts/ph.sh deploy
bash scripts/ph.sh deploy:env
bash scripts/ph.sh deploy:bg
bash scripts/ph.sh deploy:logs
bash scripts/ph.sh deploy:status

# Use a specific container engine (default: auto-detect)
bash scripts/ph.sh deploy --engine docker
bash scripts/ph.sh deploy --engine podman
```

Important:

- Use `deploy:env` when changing backend runtime values (for example `AUTH_MODE`, `ENTRA_*`, policy settings).
- Use full `deploy` when changing frontend `VITE_*` values, because those are build-time inputs.

Background deploy state files are namespaced under `/tmp/ph-deploy-<resource-group>/` to prevent collisions between concurrent runs.

### Webhook Management

| Command | Description |
|---------|-------------|
| `webhook:add` | Add/update Azure webhook for one repo and disable stale hooks |
| `webhook:disable` | Disable PipelineHealer webhooks for one repo |

```bash
bash scripts/ph.sh webhook:add --repo owner/repo
bash scripts/ph.sh webhook:disable --repo owner/repo
```

Webhook sync matches hooks by URL path suffix (`/webhook/github`), not just the current FQDN. This catches stale hooks from previous Azure deployments and disables them before activating the canonical one.

### Canary Rollout

| Command | Description |
|---------|-------------|
| `rollout:canary` | Configure issue-only canary mode for selected repos and attach webhooks |

```bash
# Issue-only observation (default: HEAL_MODE=safe, AUTO_CREATE_PR=false)
bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2

# Allow PR creation while still using allowlist
bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2 --allow-prs

# Skip env sync (webhook-only)
bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2 --skip-env-sync
```

### Demo

| Command | Description |
|---------|-------------|
| `demo:e2e` | Run scripted Azure E2E demo flow |
| `demo:proof` | Show latest CI runs, PRs, and issues for a repo |
| `demo:reset` | Reset demo fixture repo for dependency/lint failures |

```bash
bash scripts/ph.sh demo:e2e
bash scripts/ph.sh demo:e2e --skip-webhook-sync
bash scripts/ph.sh demo:e2e --triggers dependency,lint,test --wait-seconds 120
bash scripts/ph.sh demo:proof --repo owner/repo --limit 10
bash scripts/ph.sh demo:reset
```

### Scale Management

| Command | Description |
|---------|-------------|
| `warm` | Set backend/frontend min-replicas to 1 (disable scale-to-zero) |
| `lowcost` | Set backend/frontend min-replicas to 0 (re-enable scale-to-zero) |

```bash
bash scripts/ph.sh warm      # before demos
bash scripts/ph.sh lowcost   # after demos
```

### Status and URLs

| Command | Description |
|---------|-------------|
| `urls` | Print Azure backend/frontend URLs |
| `status` | Show Container App status (min replicas, FQDNs, latest revision) |

```bash
bash scripts/ph.sh urls
bash scripts/ph.sh status
```

### Settings

| Command | Description |
|---------|-------------|
| `settings:check` | GET `/api/settings` using keys from `backend/.env` |
| `settings:audit` | GET `/api/settings/audit` (admin audit trail) |
| `settings:persist` | Persist settings to `backend/.env`, API-audit when reachable, optionally redeploy |
| `settings:persist:verify` | Run persist flow and verify audit entry via request ID (defaults to `--skip-redeploy`) |
| `audit:proof` | Create two traceable audit entries and print latest records |
| `aoai:check` | Verify Azure OpenAI connectivity from local backend container |

```bash
bash scripts/ph.sh settings:check
bash scripts/ph.sh settings:audit --limit 20
bash scripts/ph.sh settings:persist:verify --from-settings
bash scripts/ph.sh audit:proof --limit 5
bash scripts/ph.sh aoai:check
```

#### `settings:persist`

Two modes: pull from live backend, or set directly via flags.

Behavior notes:
- Direct flags are applied to runtime via `PATCH /api/settings` first when backend/API auth is reachable (creates admin audit entries).
- Command then calls `POST /api/settings/persist` with `skip_redeploy=true` to record durable persistence in backend storage/audit.
- Local `.env` write + optional `deploy:env` redeploy still run as before.
- If backend/API auth is unavailable, command falls back to local `.env` persistence only and prints an explicit unaudited warning.

**Pull from live settings** (snapshots all mutable values):

```bash
bash scripts/ph.sh settings:persist --from-settings
bash scripts/ph.sh settings:persist --from-settings --skip-redeploy
```

**Direct flags** (set specific values):

```bash
bash scripts/ph.sh settings:persist --repos owner/repo1,owner/repo2
bash scripts/ph.sh settings:persist --heal-mode safe --auto-create-pr false
bash scripts/ph.sh settings:persist --gh-aw-tools-enabled true --gh-aw-ingestion-mode passive
bash scripts/ph.sh settings:persist --external-diagnostics-wait-seconds 60 --external-diagnostics-poll-interval-seconds 15
bash scripts/ph.sh settings:persist --mcp-enabled true --mcp-provider github --mcp-read-only true
bash scripts/ph.sh settings:persist --mcp-tool-policies "fetch_failure_context=read_only,fetch_runbook_context=read_only,publish_artifact=write_with_approval,rerun_pipeline=write_with_approval"
bash scripts/ph.sh settings:persist --mcp-repo-allowlist owner/repo1,owner/repo2
bash scripts/ph.sh settings:persist --azure-openai-deployment-name gpt-4o --skip-redeploy
bash scripts/ph.sh settings:persist --llm-model-analysis gpt-5-mini-fast --llm-model-diagnosis gpt-5-mini-reasoner --llm-model-remediation gpt-5-mini
bash scripts/ph.sh settings:persist --clear-repos
bash scripts/ph.sh settings:persist --clear-mcp-repo-allowlist
```

| Flag | Values | Description |
|------|--------|-------------|
| `--from-settings` | — | Pull all mutable settings from live backend |
| `--repos` | CSV | Set `PH_ALLOWED_REPOS` |
| `--clear-repos` | — | Clear `PH_ALLOWED_REPOS` |
| `--heal-mode` | `safe`, `demo`, `debug` | Set `HEAL_MODE` |
| `--auto-create-pr` | `true`, `false` | Set `AUTO_CREATE_PR` |
| `--max-remediation-attempts` | int | Set `MAX_REMEDIATION_ATTEMPTS` |
| `--pipeline-step-timeout-seconds` | float | Set `PIPELINE_STEP_TIMEOUT_SECONDS` |
| `--external-diagnostics-wait-seconds` | float | Set `EXTERNAL_DIAGNOSTICS_WAIT_SECONDS` |
| `--external-diagnostics-poll-interval-seconds` | float | Set `EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS` |
| `--gh-aw-tools-enabled` | `true`, `false` | Set `GH_AW_TOOLS_ENABLED` |
| `--gh-aw-ingestion-mode` | `disabled`, `passive` | Set `GH_AW_INGESTION_MODE` |
| `--gh-aw-known-workflows` | CSV | Set `GH_AW_KNOWN_WORKFLOWS` |
| `--mcp-enabled` | `true`, `false` | Set `MCP_ENABLED` |
| `--mcp-provider` | `disabled`, `github`, `azure_monitor`, `custom` | Set `MCP_PROVIDER` |
| `--mcp-read-only` | `true`, `false` | Set `MCP_READ_ONLY` |
| `--mcp-timeout-seconds` | float | Set `MCP_TIMEOUT_SECONDS` (>0) |
| `--mcp-max-retries` | int | Set `MCP_MAX_RETRIES` (>=0) |
| `--mcp-tool-policies` | CSV (`tool=mode`) | Set `MCP_TOOL_POLICIES` |
| `--mcp-repo-allowlist` | CSV | Set `MCP_REPO_ALLOWLIST` |
| `--clear-mcp-repo-allowlist` | — | Clear `MCP_REPO_ALLOWLIST` |
| `--azure-openai-deployment-name` | string | Set `AZURE_OPENAI_DEPLOYMENT_NAME` |
| `--llm-model-analysis` | string | Set `LLM_MODEL_ANALYSIS` |
| `--llm-model-diagnosis` | string | Set `LLM_MODEL_DIAGNOSIS` |
| `--llm-model-remediation` | string | Set `LLM_MODEL_REMEDIATION` |
| `--skip-redeploy` | — | Write `.env` only, skip Azure env sync |

Enum values are validated before writing. Invalid values exit with a clear error.
For `--mcp-tool-policies`, allowed policy modes are `disabled`, `read_only`, `write_with_approval`, and `auto`.
Common MCP tools are `fetch_failure_context`, `fetch_runbook_context`, `publish_artifact`, and `rerun_pipeline`.

#### `settings:persist:verify`

Runs `settings:persist`, extracts the persist request ID, and verifies a matching `persist_settings` record exists in `settings:audit`.

Behavior notes:
- Defaults to `--skip-redeploy` when not specified (safer for verification-only runs).
- Fails if persist succeeds but the expected audit entry is not found.
- Useful before demos/releases to prove persistence was both applied and audited.

Examples:

```bash
bash scripts/ph.sh settings:persist:verify --from-settings
bash scripts/ph.sh settings:persist:verify --from-settings --skip-redeploy
bash scripts/ph.sh settings:persist:verify --heal-mode safe --auto-create-pr false --skip-redeploy
```

### Versioning and Release (Repo Maintenance)

These helper scripts are intentionally separate from `scripts/ph.sh`.

| Command | Description |
|---------|-------------|
| `bash scripts/check_version_sync.sh` | Verifies `VERSION`, backend, and frontend versions match |
| `bash scripts/release_checklist.sh [bump]` | Prints ordered release commands (dry-run, no file changes) |
| `bash scripts/release.sh <patch|minor|major|x.y.z>` | Bumps versions and prepares `CHANGELOG.md` release section |

```bash
bash scripts/check_version_sync.sh
bash scripts/release_checklist.sh minor
bash scripts/release.sh patch
```

Suggested release flow:
1. Confirm working tree is clean and CI is green.
2. Run `bash scripts/release.sh patch` (or `minor`/`major`).
3. Edit release notes in `CHANGELOG.md` under the new `vX.Y.Z` section.
4. Commit release files, tag `vX.Y.Z`, then push with `--follow-tags`.

For full release prep through post-release verification, use `docs/RELEASE_RUNBOOK.md`.

### Log Inspection

| Command | Description |
|---------|-------------|
| `logs` | Filtered backend logs (Cosmos SDK noise removed) |
| `logs:raw` | Unfiltered backend logs |
| `logs:grep` | Grep backend logs for a pattern |

```bash
bash scripts/ph.sh logs
bash scripts/ph.sh logs --tail 500
bash scripts/ph.sh logs:raw --tail 50
bash scripts/ph.sh logs:grep --pattern "debug-mode"
bash scripts/ph.sh logs:grep --pattern "error" --tail 1000
```

Log commands are grep-tolerant: empty output (no matches) exits 0, not failure.

If you run log commands on a local Docker setup without Azure CLI installed, first point `ph.sh` at local backend mode:

```bash
export PH_BACKEND_URL=http://127.0.0.1:8000
bash scripts/ph.sh logs:grep --pattern "openai|responses|chat.completions"
```

Otherwise `ph.sh` stays in Azure mode and may fail with `Missing required command: az`.

### Testing Safety Wrapper

Use the safe pytest wrapper to prevent indefinitely hanging test runs:

```bash
bash scripts/pytest_safe.sh backend/tests/test_phase1_correctness.py -q
PYTEST_TIMEOUT_SECONDS=2400 bash scripts/pytest_safe.sh backend/tests -q
```

Defaults:

- timeout: `1800s` (30 minutes)
- graceful stop: `TERM`, then forced kill after 30s if needed

### External Diagnostics

| Command | Description |
|---------|-------------|
| `backfill` | Trigger on-demand backfill sweep for ci-doctor external diagnostics |

```bash
bash scripts/ph.sh backfill
bash scripts/ph.sh backfill --max-age-hours 48
```

| Flag | Default | Description |
|------|---------|-------------|
| `--max-age-hours` | `24` | Only consider activities created within this many hours (1–168) |

Finds completed activities whose ci-doctor poll window was exhausted and attaches findings that have been published since. A background sweep also runs automatically every 10 minutes, so manual triggering is only needed for immediate results.

The same action is available in the UI via the "Backfill Diagnostics" button on the Activity Detail page.

---

## Error Handling

- **Missing flag values**: All `--flag value` arguments are guarded by `require_arg`. Running `--repo` without a value produces `Error: --repo requires a value argument.` (exit 2) instead of a shell crash.
- **Unknown arguments**: Unrecognized flags produce a clear message and exit 2.
- **Enum validation**: `--heal-mode`, `--auto-create-pr`, `--gh-aw-tools-enabled`, `--gh-aw-ingestion-mode`, and `--mcp-provider` validate against allowed values before proceeding.
- **Strict mode**: `set -euo pipefail` is enabled throughout. Log grep pipelines use `|| true` to remain tolerant of empty results.

## Local Mode

By default, all commands target your Azure deployment. To use backend API commands against local or non-Azure deployments, set `PH_BACKEND_URL`:

```bash
export PH_BACKEND_URL=http://127.0.0.1:8000
bash scripts/ph.sh settings:check
bash scripts/ph.sh logs --tail 100
bash scripts/ph.sh backfill
```

Use any reachable backend URL, for example:

```bash
export PH_BACKEND_URL=https://your-backend.example.com
bash scripts/ph.sh settings:check
```

### Commands That Work Locally

| Command | Local behavior |
|---------|---------------|
| `settings:check` | Hits local backend API |
| `settings:audit` | Hits local backend API |
| `settings:persist --skip-redeploy` | Updates local `backend/.env` only |
| `settings:persist:verify --skip-redeploy` | Persists locally and verifies `persist_settings` audit entry |
| `audit:proof` | Creates audit entries on local backend |
| `backfill` | Triggers backfill sweep on local backend |
| `logs` | Uses `docker compose logs` (filtered) |
| `logs:raw` | Uses `docker compose logs` (unfiltered) |
| `logs:grep` | Uses `docker compose logs` + grep |
| `demo:proof` | Lists PRs/issues via GitHub CLI (no backend needed) |
| `demo:reset` | Resets demo fixtures via GitHub CLI (no backend needed) |
| `aoai:check` | Runs Azure OpenAI connectivity check inside backend container |

Important:
- `logs*` and `aoai:check` are local-container commands. They do **not** read logs from a remote `PH_BACKEND_URL`.
- For host-native backend (no containers), read terminal logs directly from the `uvicorn` process.

### Azure-Only Commands

These commands manage Azure infrastructure and will print a clear error when `PH_BACKEND_URL` is set:

`deploy`, `deploy:env`, `deploy:bg`, `deploy:logs`, `deploy:status`, `urls`, `status`, `warm`, `lowcost`, `webhook:add`, `webhook:disable`, `rollout:canary`, `demo:e2e`.

### Switching Back to Azure

```bash
unset PH_BACKEND_URL
```

### `settings:persist` Scope Notes

- Without `--skip-redeploy`, `settings:persist` writes `backend/.env` and runs Azure env redeploy.
- With `--skip-redeploy`, it updates only local `backend/.env` (useful for non-Azure or local workflows).

## Environment Overrides

| Variable | Default | Description |
|----------|---------|-------------|
| `PH_BACKEND_URL` | *(unset — Azure mode)* | Set to target a local backend (for example `http://127.0.0.1:8000`) |
| `PH_RG` | `rg-canepro-ph-dev-eus` | Azure resource group |
| `PH_BACKEND_APP` | `ca-canepro-ph-backend` | Backend Container App name |
| `PH_FRONTEND_APP` | `ca-canepro-ph-frontend` | Frontend Container App name |
| `PH_DEPLOY_LOG` | `/tmp/ph-deploy-<rg>/redeploy.log` | Background deploy log path |
| `PH_DEPLOY_PID` | `/tmp/ph-deploy-<rg>/redeploy.pid` | Background deploy PID path |

## Quality Gate

`scripts/ph.sh` and all sub-scripts (`scripts/deploy/*.sh`, `scripts/demo/*.sh`) pass [ShellCheck](https://www.shellcheck.net/) in CI via `.github/workflows/ci.yml`.
