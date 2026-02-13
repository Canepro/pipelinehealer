# Local Demo Runbook (PipelineHealer)

This runbook documents the detailed operator workflow for both Azure and local execution.

Positioning for this project:

- Azure deployment is the primary runtime path for hackathon submission requirements.
- Local mode is an evaluation and troubleshooting fallback for fast iteration.

Local validation workflow:

- GitHub Actions workflow fails in a demo repo
- Webhook is forwarded into local FastAPI via `smee.io`
- PipelineHealer analyzes, diagnoses, and remediates
- Frontend dashboard shows the activity

If you are recording the hackathon video, use `docs/DEMO_SCRIPT.md` first.
This file is the detailed operator runbook for setup/troubleshooting.

## Prereqs

- Python 3.11+ (repo uses 3.12 fine)
- Bun installed (`bun --version`)
- GitHub CLI installed and authenticated (`gh auth status`)
- A demo GitHub repo with a workflow dispatch input `failure_type` (see `demo-repo/`)

## Shell Safety (Recommended For Multi-Step Blocks)

For long copy-paste scripts in this runbook, start with:

```bash
set -euo pipefail
```

This is optional for simple one-liners, but recommended for deployment/webhook blocks so the script stops on errors instead of continuing in a partial state.

## Fast Path (Recommended: Scripted Azure E2E)

Instead of running many manual commands, use:

```bash
cd <repo-root>/pipelinehealer
bash scripts/ph.sh demo:e2e
```

What it does:

- Resolves Azure backend URL from Container Apps
- Disables stale `smee.io` hook and enables Azure webhook
- Resets demo fixtures (dependency/lint scenarios)
- Triggers all 5 failure types
- Prints PR/issue/activity verification output

Common variations:

```bash
# Keep existing webhook config, only run reset/trigger/verify
bash scripts/ph.sh demo:e2e --skip-webhook-sync

# Reset demo fixtures only
bash scripts/ph.sh demo:reset

# Re-run quickly with shorter wait
bash scripts/ph.sh demo:e2e --wait-seconds 40
```

## 1) Backend Setup (Host-Native)

From the repo root (`pipelinehealer/`):

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"

cp .env.example .env
```

Edit `backend/.env`:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME` (current dev deployment: `gpt-5-mini`)
- `AZURE_OPENAI_API_VERSION` (use the version shown in your Azure deployment target URI; current working value here is `2025-04-01-preview`)
- `AZURE_OPENAI_API_KEY` (recommended for local)
- `GITHUB_PERSONAL_ACCESS_TOKEN` (recommended for local)
- `ADMIN_API_KEY` (required for `/api/settings` admin read/write)
- `HEAL_MODE=safe` (recommended) or `HEAL_MODE=demo`
- Optional reliability knobs:
  - `PIPELINE_STEP_TIMEOUT_SECONDS=120`
  - `GITHUB_API_MAX_RETRIES=3`
  - `GITHUB_API_RETRY_BASE_SECONDS=0.5`
  - `GITHUB_API_RETRY_MAX_SECONDS=8.0`
  - `LOG_PROMPT_MAX_CHARS=18000`
  - `LOG_PROMPT_HEAD_CHARS=9000`
  - `LOG_PROMPT_TAIL_CHARS=9000`

## 1B) Backend Setup (Containerized, Recommended on this machine)

From repo root:

```bash
cp backend/.env.example backend/.env
# edit backend/.env with your values

podman compose --env-file backend/.env build backend frontend
podman compose --env-file backend/.env up -d backend frontend
podman compose --env-file backend/.env ps
curl -sS http://127.0.0.1:8000/health
```

Notes:

- Use `--env-file backend/.env` for all `podman compose` commands to avoid empty-env warnings.
- `docker compose` works too if your Podman setup aliases Docker.
- Frontend container now uses `BACKEND_UPSTREAM` (defaults to `http://backend:8000` in compose).
- When backend API auth is enabled, set `API_AUTH_KEY` for frontend as well; Nginx injects `X-API-Key` for `/api/*`.
- After changing values in `backend/.env`, re-create containers (not just restart) so new env vars are applied:
  ```bash
  podman compose --env-file backend/.env up -d --force-recreate backend frontend
  ```

## 1C) Azure Dev Environment Quick Check

If your Azure dev stack is already provisioned:

```bash
RG="rg-canepro-ph-dev-eus"
az containerapp list -g "$RG" --query "[].{name:name,fqdn:properties.configuration.ingress.fqdn}" -o table
```

Verify:

- Backend: `https://<backend-fqdn>/health`
- Frontend: `https://<frontend-fqdn>`

## 1F) Redeploy Azure Apps After New Commits (Recommended)

Use this when `main` has new commits and you want Azure Container Apps to reflect them.
Run as a script (not inline) to avoid shell restarts in interactive terminals.

```bash
cd <repo-root>/pipelinehealer
bash scripts/ph.sh deploy
```

Important:
- Run with `bash ...` (execute), not `. scripts/...` or `source scripts/...`.

Sync env vars only (if image is already current):

```bash
cd <repo-root>/pipelinehealer
bash scripts/ph.sh deploy:env
```

`deploy:env` now syncs backend runtime keys from `backend/.env`, including `MAX_REMEDIATION_ATTEMPTS`.

Script help:

```bash
bash scripts/ph.sh help

# Force Docker engine if Podman is unavailable
bash scripts/ph.sh deploy --engine docker
```

## 1D) Local Dev vs Azure Dev (Important)

- Local dev = your laptop/WSL containers (`http://127.0.0.1:8000`, `http://127.0.0.1:3000`)
- Azure dev = Container Apps URLs (`https://<app>.azurecontainerapps.io`)

If Azure is down or slow, local dev can still work normally.
Always check local endpoints first when debugging.

## 1E) Scale-To-Zero (What It Is)

Container Apps often use `minReplicas: 0` to save cost.

- When idle, app instances stop.
- First request may be slow (cold start) while Azure starts containers.
- This is expected behavior, not always an outage.

Check min replicas:

```bash
bash scripts/ph.sh status
```

Keep apps warm during active demos:

```bash
bash scripts/ph.sh warm
```

Return to low-cost mode afterward:

```bash
bash scripts/ph.sh lowcost
```

## 2) Azure OpenAI Smoke Test (Optional But Recommended)

```bash
cd backend
source .venv/bin/activate

python3 scripts/aoai_smoke.py
```

Expected output ends with:

- `model connectivity OK.`

If you see "API version not supported", use the exact API version shown in your Azure OpenAI deployment **Target URI**.
For this current environment, `2025-04-01-preview` is working.

## 3) Run Backend (FastAPI, host-native only)

```bash
cd backend
source .venv/bin/activate

uvicorn src.main:app --reload --port 8000
```

Health check:

```bash
curl -sS http://127.0.0.1:8000/health
```

## 4) Run Frontend (Dashboard)

```bash
cd frontend
bun install
bun run dev
```

Open the printed Vite URL (usually `http://127.0.0.1:5173`).

## 5) Webhook Forwarding (smee.io)

1. Create a webhook proxy channel at `https://smee.io/` and copy the URL.
2. In another terminal:

```bash
# from repo root
bunx smee-client --url https://smee.io/<your-channel> --target http://127.0.0.1:8000/webhook/github
```

Expected: it prints `Connected` and you see `POST ... 200` when events arrive.

## 6) Trigger The Five Failure Types

In your demo repo checkout (or from anywhere), run:

```bash
gh workflow run CI -R <owner>/<repo> -f failure_type=dependency
gh workflow run CI -R <owner>/<repo> -f failure_type=lint
gh workflow run CI -R <owner>/<repo> -f failure_type=test
gh workflow run CI -R <owner>/<repo> -f failure_type=build_config
gh workflow run CI -R <owner>/<repo> -f failure_type=timeout
```

Notes:

- In `HEAL_MODE=safe`: expect PRs only for dependency/lint; issues for the rest.
- In `HEAL_MODE=demo`: expect demo-friendly behavior:
  - `test` flaky failures: PipelineHealer retries failed jobs once.
  - `timeout`: PipelineHealer opens a PR bumping `timeout-minutes` in `.github/workflows/ci.yml` (if present).
  - `build_config`: PipelineHealer can open a PR only when the workflow contains a placeholder line like `REQUIRED_CONFIG: ""`.

## 7) Verify From API

List activities:

```bash
curl -sS "http://127.0.0.1:8000/api/activities?limit=20"
```

If you are not running in `ENVIRONMENT=development`, include `X-API-Key`:

```bash
curl -H "X-API-Key: $API_AUTH_KEY" -sS "http://127.0.0.1:8000/api/activities?limit=20"
```

You should see records with:

- `failure_type` set
- `diagnosis` populated
- `remediation_result` containing a PR URL or issue URL

Also check GitHub side:

```bash
gh pr list -R <owner>/<repo>
gh issue list -R <owner>/<repo> --state open
```

## 8) Repo Quality Gates (Backend)

```bash
cd backend
source .venv/bin/activate

ruff check src
mypy src
pytest
```

## 9) One-Shot E2E Command Set (PR + Issue paths)

Use this exact sequence:

```bash
cd <your-pipelinehealer-repo-root>
podman compose --env-file backend/.env up -d backend frontend
curl -sS http://127.0.0.1:8000/health
```

In a second terminal:

```bash
cd <your-pipelinehealer-repo-root>
bunx smee-client --url https://smee.io/<your-channel> --target http://127.0.0.1:8000/webhook/github
```

In a third terminal:

```bash
cd demo-repo
gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=dependency
gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=lint
gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=test
gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=build_config
gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=timeout
```

Verify:

```bash
curl -sS "http://127.0.0.1:8000/api/activities?limit=20"
gh pr list -R Canepro/pipelinehealer-demo
gh issue list -R Canepro/pipelinehealer-demo --state open
```

Expected:

- `dependency` and `lint` => PR created
- `test`, `build_config`, `timeout` => issue created

Optional settings check (runtime config snapshot):

```bash
curl -sS -H "X-Admin-Key: $ADMIN_API_KEY" "http://127.0.0.1:8000/api/settings"
```

Optional runtime override check (applies immediately, resets on backend restart):

```bash
curl -sS -X PATCH \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"heal_mode":"safe","pipeline_step_timeout_seconds":120}' \
  "http://127.0.0.1:8000/api/settings"
```

Frontend Settings page:

- Open `/settings` in the UI (for example `http://127.0.0.1:3000/settings` in dev), paste `ADMIN_API_KEY`, and use **Load Settings**.

## Troubleshooting

- Azure URL loads slowly after idle (first hit)
  - Likely cold start from scale-to-zero.
  - Try the same URL again after 10-60 seconds.
  - If demos must be instant, set `--min-replicas 1` on backend + frontend.

- Error: `'AzureOpenAIChatClient' object has no attribute 'as_agent'`
  - Cause: older Agent Framework builds in some container images expose chat clients without `as_agent()`.
  - Fix: pull latest `main` and rebuild backend image:
    ```bash
    cd <your-pipelinehealer-repo-root>
    git pull --ff-only
    podman compose --env-file backend/.env build --no-cache backend frontend
    podman compose --env-file backend/.env up -d backend frontend
    ```

- Error: `Max remediation attempts reached for this repository`
  - Cause: the safety guard blocks additional remediations after repeated failed attempts.
  - Fix (local demo with in-memory storage): restart backend to clear in-memory activities.
    ```bash
    podman compose --env-file backend/.env restart backend
    ```
  - Or raise the limit in `backend/.env`:
    ```bash
    MAX_REMEDIATION_ATTEMPTS=10
    ```

- Warning during frontend image build: `unknown file mode ?rw-rw-rw-` under `frontend/node_modules/.bin/*`
  - Cause: Docker/Podman build context includes host `node_modules` on Windows filesystems.
  - Fix: keep `frontend/.dockerignore` (includes `node_modules/`) and rebuild from repo root:
    ```bash
    cd <your-pipelinehealer-repo-root>
    podman compose --env-file backend/.env build --no-cache frontend
    ```

- Error from agent calls: `404 Resource not found` using Azure OpenAI
  - Cause: malformed `AZURE_OPENAI_ENDPOINT` in `backend/.env` (for example accidental concatenation or non-root URL path).
  - Fix:
    ```bash
    cd <your-pipelinehealer-repo-root>
    sed -i 's|^AZURE_OPENAI_ENDPOINT=.*|AZURE_OPENAI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/|' backend/.env
    podman compose --env-file backend/.env up -d --force-recreate backend
    ```

- Azure `/api/activities` stays empty after workflow failures
  - Cause: webhook deliveries are not reaching the active backend (wrong hook URL, stale smee hook still active, or signature mismatch).
  - Fix:
    ```bash
    REPO="<owner>/<repo>"
    gh api repos/$REPO/hooks --jq '.[] | {id,active,url:.config.url,events,last_response:.last_response.code}'
    ```
    - Keep only one active `workflow_run` hook for the target mode:
      - local mode: `https://smee.io/<channel>`
      - Azure mode: `https://<backend-fqdn>/webhook/github`
    - Ensure webhook secret matches `GITHUB_WEBHOOK_SECRET` in the active backend runtime.

- GitHub webhook deliveries return `401` in repo hook history
  - Cause: signature verification is enabled but the webhook secret on GitHub does not match backend runtime.
  - Fix:
    1. Re-set webhook secret in GitHub hook configuration.
    2. Confirm backend runtime `GITHUB_WEBHOOK_SECRET` value.
    3. Re-send ping and check `status_code=200`:
       ```bash
       gh api -X POST repos/<owner>/<repo>/hooks/<hook_id>/pings
       gh api repos/<owner>/<repo>/hooks/<hook_id>/deliveries --jq '.[0] | {event,status_code,delivered_at}'
       ```

- PR remediation fails with `422 Unprocessable Entity` on `POST /git/refs`
  - Cause: target fix branch already exists (common after repeated dependency/lint demo runs).
  - Fix:
    - Merge/close existing fix PRs first (for example `fix/update-left-pad`, `fix/lint-eslint-config`).
    - Or manually delete stale fix branches in the demo repo before re-running that failure type.

- Azure backend can read webhooks but cannot call GitHub API
  - Symptom: webhook creates activity, then failures appear when fetching jobs/logs or creating refs/PRs.
  - Fix: ensure `GITHUB_PERSONAL_ACCESS_TOKEN` (or GitHub App credentials) is set in backend Container App env.
