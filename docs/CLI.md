# PipelineHealer CLI Reference

<!-- LAST_VERIFIED: eac467e -->

Canonical reference for `scripts/ph.sh` — the one-command operator interface for PipelineHealer.

All commands run from the repo root:

```bash
bash scripts/ph.sh <command> [options]
```

Important: execute with `bash scripts/...`, never `source` or `. scripts/...`.

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
| `settings:persist` | Persist settings to `backend/.env` and optionally redeploy |
| `audit:proof` | Create two traceable audit entries and print latest records |
| `aoai:check` | Verify Azure OpenAI connectivity from local backend container |

```bash
bash scripts/ph.sh settings:check
bash scripts/ph.sh settings:audit --limit 20
bash scripts/ph.sh audit:proof --limit 5
bash scripts/ph.sh aoai:check
```

#### `settings:persist`

Two modes: pull from live backend, or set directly via flags.

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
bash scripts/ph.sh settings:persist --azure-openai-deployment-name gpt-4o --skip-redeploy
bash scripts/ph.sh settings:persist --clear-repos
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
| `--gh-aw-tools-enabled` | `true`, `false` | Set `GH_AW_TOOLS_ENABLED` |
| `--gh-aw-ingestion-mode` | `disabled`, `passive` | Set `GH_AW_INGESTION_MODE` |
| `--gh-aw-known-workflows` | CSV | Set `GH_AW_KNOWN_WORKFLOWS` |
| `--azure-openai-deployment-name` | string | Set `AZURE_OPENAI_DEPLOYMENT_NAME` |
| `--skip-redeploy` | — | Write `.env` only, skip Azure env sync |

Enum values are validated before writing. Invalid values exit with a clear error.

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
- **Enum validation**: `--heal-mode`, `--auto-create-pr`, `--gh-aw-tools-enabled`, and `--gh-aw-ingestion-mode` validate against allowed values before proceeding.
- **Strict mode**: `set -euo pipefail` is enabled throughout. Log grep pipelines use `|| true` to remain tolerant of empty results.

## Local Mode

By default, all commands target your Azure deployment. To use `ph.sh` against a local backend, set `PH_BACKEND_URL`:

```bash
export PH_BACKEND_URL=http://127.0.0.1:8000
bash scripts/ph.sh settings:check
bash scripts/ph.sh logs --tail 100
bash scripts/ph.sh backfill
```

### Commands That Work Locally

| Command | Local behavior |
|---------|---------------|
| `settings:check` | Hits local backend API |
| `settings:audit` | Hits local backend API |
| `audit:proof` | Creates audit entries on local backend |
| `backfill` | Triggers backfill sweep on local backend |
| `logs` | Uses `docker compose logs` (filtered) |
| `logs:raw` | Uses `docker compose logs` (unfiltered) |
| `logs:grep` | Uses `docker compose logs` + grep |
| `demo:proof` | Lists PRs/issues via GitHub CLI (no backend needed) |
| `demo:reset` | Resets demo fixtures via GitHub CLI (no backend needed) |
| `aoai:check` | Runs Azure OpenAI connectivity check inside backend container |

### Azure-Only Commands

These commands manage Azure infrastructure and will print a clear error when `PH_BACKEND_URL` is set:

`deploy`, `deploy:env`, `deploy:bg`, `deploy:logs`, `deploy:status`, `urls`, `status`, `warm`, `lowcost`, `webhook:add`, `webhook:disable`, `rollout:canary`, `demo:e2e`.

### Switching Back to Azure

```bash
unset PH_BACKEND_URL
```

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
