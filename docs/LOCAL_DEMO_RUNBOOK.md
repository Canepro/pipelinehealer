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

## 1) Backend Setup

```bash
cd /mnt/d/repos/pipelinehealer/backend

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

## 2) Azure OpenAI Smoke Test (Optional But Recommended)

```bash
cd /mnt/d/repos/pipelinehealer/backend
source .venv/bin/activate

python3 scripts/aoai_smoke.py
```

Expected output ends with:

- `model connectivity OK.`

If you see "API version not supported", set `AZURE_OPENAI_API_VERSION=2025-03-01-preview`.

## 3) Run Backend (FastAPI)

```bash
cd /mnt/d/repos/pipelinehealer/backend
source .venv/bin/activate

uvicorn src.main:app --reload --port 8000
```

Health check:

```bash
curl -sS http://127.0.0.1:8000/health
```

## 4) Run Frontend (Dashboard)

```bash
cd /mnt/d/repos/pipelinehealer/frontend
bun install
bun run dev
```

Open the printed Vite URL (usually `http://127.0.0.1:5173`).

## 5) Webhook Forwarding (smee.io)

1. Create a webhook proxy channel at `https://smee.io/` and copy the URL.
2. In another terminal:

```bash
cd /mnt/d/repos/pipelinehealer
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

You should see records with:

- `failure_type` set
- `diagnosis` populated
- `remediation_result` containing a PR URL or issue URL

## 8) Repo Quality Gates (Backend)

```bash
cd /mnt/d/repos/pipelinehealer/backend
source .venv/bin/activate

ruff check src
mypy src
pytest
```

