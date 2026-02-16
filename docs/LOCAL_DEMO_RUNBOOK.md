# Local Demo Runbook (PipelineHealer)

<!-- LAST_VERIFIED: f6bd5be -->

This guide walks you through setting up PipelineHealer locally, triggering CI failures in a demo repo, and verifying the results on the dashboard.

**What you'll end up with:**

- A running backend (FastAPI) and frontend (React dashboard) on your machine
- A webhook bridge so GitHub can notify your local backend when a workflow fails
- PipelineHealer automatically analyzing failures and creating PRs or Issues

---

## Prerequisites

Before you start, make sure you have:

- **Python 3.11+** — check with `python3 --version`
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip — `uv --version`
- **[Bun](https://bun.sh/)** — `bun --version`
- **[GitHub CLI](https://cli.github.com/)** — `gh auth status` (must be logged in)
- **Docker** (for containerized setup) — `docker --version`
- **An Azure OpenAI resource** with a deployed model — see Step 1 below
- **A GitHub Personal Access Token** with `repo` and `workflow` scopes — [create one here](https://github.com/settings/tokens)

---

## Step 1 — Set Up Azure OpenAI

PipelineHealer uses Azure OpenAI for log analysis, diagnosis, and remediation. **The backend will not process failures without it.**

If you already have an Azure OpenAI resource and deployment, skip to step 1.3.

### 1.1 Create an Azure OpenAI resource

- Go to the [Azure Portal](https://portal.azure.com) → search for *Azure OpenAI* → click **Create**.
- Pick any region (`East US 2` and `Sweden Central` usually have the widest model availability).
- Pricing tier: `Standard S0` is fine for development.

### 1.2 Deploy a model

- Open your new resource → **Model deployments** → **Manage Deployments** (this opens Azure AI Foundry).
- Click **Deploy model** → **Deploy base model** → select a chat model (for example `gpt-4o` or `gpt-4o-mini`).
- Give it a deployment name you'll remember (for example `gpt-4o`). You'll need this name later.

### 1.3 Gather your credentials

In the Azure Portal, open your OpenAI resource page → **Keys and Endpoint**:

- **Endpoint**: for example `https://your-resource.openai.azure.com/`
- **API Key**: copy Key 1 or Key 2

> **Note:** If your endpoint uses the `cognitiveservices.azure.com` domain, that works too. PipelineHealer auto-detects the endpoint style.

---

## Step 2 — Configure Environment

From the repo root:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` in your editor and fill in these values:

```dotenv
# Azure OpenAI (from Step 1)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o       # the name you chose in step 1.2
AZURE_OPENAI_API_KEY=your-key-here         # Key 1 or Key 2 from step 1.3

# GitHub
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxxxxxxxx # your PAT with repo + workflow scopes

# Healing behavior
HEAL_MODE=safe                              # safe is recommended for getting started
```

> **That's it for getting started.** Everything else in `.env` has sensible defaults. You can tune optional settings later — see the full list in `backend/.env.example`.

---

## Step 3 — Start the Backend

You have two options. Pick whichever suits you:

### Option A: Host-native (no Docker needed)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8000
```

### Option B: Docker Compose

```bash
docker compose --env-file backend/.env build backend frontend
docker compose --env-file backend/.env up -d backend frontend
```

> **Podman users:** Replace `docker compose` with `podman compose`. Everything else is the same.

### Verify the backend is running

```bash
curl -sS http://127.0.0.1:8000/health
```

You should see `{"status":"healthy"}`. If you don't, check that port 8000 isn't already in use.

---

## Step 4 — Start the Frontend

> **Skip this step** if you used Docker Compose in Step 3 — the frontend is already running at `http://127.0.0.1:3000`.

For host-native setup:

```bash
cd frontend
bun install
bun run dev
```

Open the URL printed by Vite (usually `http://127.0.0.1:5173`). You should see an empty PipelineHealer dashboard.

---

## Step 5 — Verify Azure OpenAI Connection (Recommended)

Before triggering failures, confirm your Azure OpenAI credentials work:

```bash
cd backend
source .venv/bin/activate
python3 scripts/aoai_smoke.py
```

**What success looks like:** Output ends with `model connectivity OK.`

**If it fails:** Double-check `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY` in your `backend/.env`. The endpoint should be the base URL only (no extra path segments).

---

## Step 6 — Set Up Webhook Forwarding

PipelineHealer listens for GitHub webhook events to know when a workflow fails. Since your backend is running on `localhost`, GitHub can't reach it directly. You need a tunnel.

**[smee.io](https://smee.io/)** is a free webhook proxy that forwards GitHub events to your local machine:

1. Go to [https://smee.io/](https://smee.io/) and click **Start a new channel**. Copy the URL it gives you.
2. In a **new terminal**, run:

```bash
bunx smee-client --url https://smee.io/<your-channel> --target http://127.0.0.1:8000/webhook/github
```

**What success looks like:** It prints `Connected` and stays running.

3. Now configure a webhook on your demo GitHub repo:
   - Go to your repo → **Settings** → **Webhooks** → **Add webhook**
   - **Payload URL**: paste your smee.io channel URL
   - **Content type**: `application/json`
   - **Secret**: the value of `GITHUB_WEBHOOK_SECRET` in your `backend/.env` (or leave both empty for local dev)
   - **Events**: select **Let me select individual events** → check only **Workflow runs**
   - Click **Add webhook**

> **Tip:** You can use the included demo repo at `Canepro/pipelinehealer-demo`, or set up your own repo using the fixtures in the `demo-repo/` folder.

---

## Step 7 — Trigger Failures and Watch PipelineHealer Work

Now trigger some CI failures to give PipelineHealer something to analyze:

```bash
gh workflow run CI -R <owner>/<repo> -f failure_type=dependency
gh workflow run CI -R <owner>/<repo> -f failure_type=lint
```

Replace `<owner>/<repo>` with your demo repo (for example `Canepro/pipelinehealer-demo`).

**Wait about 30-60 seconds** for the workflow to run and fail. You should see webhook events arriving in the smee terminal.

### What to expect

| Failure type | What PipelineHealer does |
|-------------|-------------------------|
| `dependency` | Creates a **PR** that adds the missing dependency |
| `lint` | Creates a **PR** with the lint fix |
| `test` | Creates an **Issue** with diagnosis and rerun guidance |
| `build_config` | Creates an **Issue** with diagnosis |
| `timeout` | Creates an **Issue** with diagnosis |

### Check the results

**Dashboard** — open your frontend URL and you should see activities appearing with status badges.

**API** — or check via the command line:

```bash
curl -sS "http://127.0.0.1:8000/api/activities?limit=20"
```

**GitHub** — check for new PRs and issues:

```bash
gh pr list -R <owner>/<repo>
gh issue list -R <owner>/<repo> --state open
```

---

## Using `ph.sh` Commands Locally

The `ph.sh` CLI defaults to targeting Azure, but you can use it locally by setting `PH_BACKEND_URL`:

```bash
export PH_BACKEND_URL=http://127.0.0.1:8000

bash scripts/ph.sh settings:check            # check current settings
bash scripts/ph.sh settings:audit --limit 10  # view audit trail
bash scripts/ph.sh logs --tail 100            # view backend logs (docker compose)
bash scripts/ph.sh backfill                   # trigger diagnostics backfill
```

**Works locally:** `settings:check`, `settings:audit`, `audit:proof`, `backfill`, `logs`, `logs:raw`, `logs:grep`, `demo:proof`, `demo:reset`.

**Azure-only** (prints a clear error in local mode): `deploy`, `warm`, `lowcost`, `status`, `urls`, `webhook:*`, `rollout:canary`, `demo:e2e`.

To switch back to Azure mode:

```bash
unset PH_BACKEND_URL
```

---

## Quality Gates

Before opening a PR, make sure tests and linting pass:

```bash
cd backend
source .venv/bin/activate
ruff check src
mypy src
pytest
```

```bash
cd frontend
bun run lint
bun run build
```

---

## Azure Deployment

The sections below are for deploying to Azure. **You do not need Azure to run PipelineHealer locally** — the steps above are sufficient.

### Quick Status Check

If your Azure environment is already provisioned:

```bash
bash scripts/ph.sh status
bash scripts/ph.sh urls
```

### Redeploy After Code Changes

```bash
bash scripts/ph.sh deploy
```

This builds and pushes images, updates both Container Apps, syncs env vars, and verifies health.

Sync env vars only (no image rebuild):

```bash
bash scripts/ph.sh deploy:env
```

### Scale To Zero

Azure Container Apps can scale down to 0 instances when idle to save cost. This means the first request after a period of inactivity may be slow (cold start).

```bash
bash scripts/ph.sh warm     # keep apps running (before demos)
bash scripts/ph.sh lowcost  # re-enable scale-to-zero (after demos)
```

### Azure E2E Demo (One Command)

If you have Azure set up, this command runs the full demo automatically:

```bash
bash scripts/ph.sh demo:e2e
```

What it does: syncs webhooks, resets fixtures, triggers all failure types, and verifies results.

---

## Troubleshooting

### Backend won't start

- **`AZURE_OPENAI_ENDPOINT` error**: Make sure the endpoint is just the base URL (for example `https://your-resource.openai.azure.com/`), not a full path with `/openai/deployments/...`.
- **Port already in use**: Check if something else is running on port 8000 with `lsof -i :8000`.

### Webhook events aren't arriving

- **smee-client not running**: Make sure the smee terminal is open and shows `Connected`.
- **Wrong webhook URL**: In your GitHub repo's webhook settings, the Payload URL should be your smee.io channel URL (not `localhost`).
- **Wrong event type**: The webhook must be set to **Workflow runs** only.

Check webhook delivery history:

```bash
REPO="<owner>/<repo>"
gh api repos/$REPO/hooks --jq '.[] | {id,active,url:.config.url,events,last_response:.last_response.code}'
```

### Activities stay empty after triggering failures

- **Webhook not reaching backend**: Check the smee terminal for `POST` events arriving.
- **Signature mismatch**: If `GITHUB_WEBHOOK_SECRET` is set in `backend/.env`, it must match the secret configured in the GitHub webhook. For local dev, you can leave both empty.

### Azure OpenAI errors

- **`404 Resource not found`**: The `AZURE_OPENAI_ENDPOINT` is probably malformed. It should be just `https://<resource>.openai.azure.com/` — no extra path.
- **`API version not supported`**: PipelineHealer automatically falls back to the Chat Completions client. If both fail, check the API version in your Azure deployment's Target URI and update `AZURE_OPENAI_API_VERSION` in `.env`.

### `Max remediation attempts reached`

The safety guard limits how many times PipelineHealer will remediate the same workflow. If you're testing repeatedly:

- Restart the backend to clear in-memory state: `docker compose --env-file backend/.env restart backend`
- Or raise the limit in `backend/.env`: `MAX_REMEDIATION_ATTEMPTS=10`

### Activities stuck in `pending` / `analyzing` / `diagnosing`

If the backend was restarted while processing an activity, it can get stuck. This is handled automatically — on startup, the backend marks interrupted activities as `failed` with a clear message. If you see stuck activities from before this fix, restart the backend.

### PR creation fails with `422 Unprocessable Entity`

This usually means the fix branch already exists from a previous run. Merge or delete the old PR first, or re-run the failing workflow to create a new activity.

### Remediation shows `410 Gone` or `403 Forbidden`

The target repository has issues or PRs disabled, or is archived. PipelineHealer handles this gracefully — the activity completes as `completed` with a reason code like `OUTPUT_ISSUES_DISABLED` visible in the Activity Detail page.

### **(WSL only)** Azure CLI errors: `UtilAcceptVsock... accept4 failed 110`

This is a known WSL2 issue with Azure CLI. Workaround — query the backend directly:

```bash
FQDN="<backend-fqdn>.azurecontainerapps.io"
API_KEY=$(grep -E '^API_AUTH_KEY=' backend/.env | tail -n1 | cut -d= -f2-)
ADMIN_KEY=$(grep -E '^ADMIN_API_KEY=' backend/.env | tail -n1 | cut -d= -f2-)

curl -fsS "https://$FQDN/api/settings" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Admin-Key: $ADMIN_KEY" | jq .
```
