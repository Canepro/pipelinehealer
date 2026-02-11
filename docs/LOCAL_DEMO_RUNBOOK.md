# Local Demo Runbook (PipelineHealer)

This runbook documents the exact local workflow used to validate the end-to-end demo:

- GitHub Actions workflow fails in a demo repo
- Webhook is forwarded into local FastAPI via `smee.io`
- PipelineHealer analyzes, diagnoses, and remediates
- Frontend dashboard shows the activity

## Prereqs

- Python 3.11+ (repo uses 3.12 fine)
- Bun installed (`bun --version`)
- GitHub CLI installed and authenticated (`gh auth status`)
- A demo GitHub repo with a workflow dispatch input `failure_type` (see `demo-repo/`)

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
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION` (for Agent Framework: `2025-03-01-preview` or later)
- `AZURE_OPENAI_API_KEY` (recommended for local)
- `GITHUB_PERSONAL_ACCESS_TOKEN` (recommended for local)
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

## 2) Azure OpenAI Smoke Test (Optional But Recommended)

```bash
cd backend
source .venv/bin/activate

python3 scripts/aoai_smoke.py
```

Expected output ends with:

- `model connectivity OK.`

If you see "API version not supported", set `AZURE_OPENAI_API_VERSION=2025-03-01-preview`.

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
curl -sS "http://127.0.0.1:8000/api/settings"
```

Frontend Settings page:

- Open `/settings` in the UI (for example `http://127.0.0.1:3000/settings` in dev).

## Troubleshooting

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
