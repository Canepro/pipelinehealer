# Local Demo Runbook (PipelineHealer)

<!-- LAST_VERIFIED: 74e2d09 -->

This guide walks you through setting up PipelineHealer locally, triggering CI failures in a demo repo, and verifying the results on the dashboard.

For dedicated feature-by-feature docs, see `docs/features/README.md`.

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
- **An LLM provider credential** (Azure OpenAI or OpenAI-compatible) — see Step 1 below
- **A GitHub Personal Access Token** with `repo` and `workflow` scopes — [create one here](https://github.com/settings/tokens)

---

## Choose Your Operating Profile

Pick one profile before running commands:

| Profile | Best for | Key commands |
|--------|----------|--------------|
| Local-only dev (no Azure infra) | fast iteration, local testing | host-native/Docker steps + `PH_BACKEND_URL=http://127.0.0.1:8000` API commands |
| Azure managed (hackathon default) | demo + managed deployment | `bash scripts/ph.sh deploy:release --release-version vX.Y.Z`, `status`, `warm`, `lowcost` |
| Other cloud backend (AWS/GCP/DO/K8s/etc.) | non-Azure production path | deploy containers with your platform, then use `PH_BACKEND_URL=https://<your-backend>` for API commands |

Important command scope rule:

- `deploy*`, `status`, `urls`, `warm`, `lowcost`, `webhook:*`, `rollout:canary`, `demo:e2e` are Azure-infra commands.
- `settings:check`, `settings:audit`, `settings:persist`, `settings:persist:verify`, `audit:proof`, `backfill` work with any reachable backend URL via `PH_BACKEND_URL`.
- `demo:proof` and `demo:reset` are GitHub-only (`gh`), backend independent.
- For Kubernetes, use the Helm guide: `docs/KUBERNETES_HELM_RUNBOOK.md`.

---

## Step 1 — Configure an LLM Provider

PipelineHealer needs one working LLM provider for log analysis/diagnosis/remediation.

### Option A (Hackathon default): Azure OpenAI

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

### Option B: OpenAI-compatible provider (portable path)

If you are not using Azure OpenAI, configure:

```dotenv
LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
OPENAI_COMPATIBLE_MODEL=gpt-5-mini
OPENAI_COMPATIBLE_API_KEY=sk-...
```

For this path, Azure-specific smoke command `aoai:check` does not apply.
Use:

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.openai_compatible_base_url,.openai_compatible_model'
```

---

## Step 2 — Configure Environment

From the repo root:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` in your editor and fill in these values:

```dotenv
# LLM provider (pick one path from Step 1)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o       # the name you chose in step 1.2
AZURE_OPENAI_API_KEY=your-key-here         # Key 1 or Key 2 from step 1.3
# OR
# LLM_PROVIDER=openai_compatible
# OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
# OPENAI_COMPATIBLE_MODEL=gpt-5-mini
# OPENAI_COMPATIBLE_API_KEY=sk-...
# Optional per-task model overrides (empty => provider default):
# LLM_MODEL_ANALYSIS=gpt-5-mini-fast
# LLM_MODEL_DIAGNOSIS=gpt-5-mini-reasoner
# LLM_MODEL_REMEDIATION=gpt-5-mini

# GitHub
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxxxxxxxx # your PAT with repo + workflow scopes

# Healing behavior
HEAL_MODE=safe                              # safe is recommended for getting started
```

> **That's it for getting started.** Everything else in `.env` has sensible defaults. You can tune optional settings later — see the full list in `backend/.env.example`.

Optional external diagnostics fast-path tuning:

```dotenv
# Keep this short so the main pipeline completes quickly.
EXTERNAL_DIAGNOSTICS_WAIT_SECONDS=60
# Poll cadence while within the wait budget.
EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS=15
```

- Set `EXTERNAL_DIAGNOSTICS_WAIT_SECONDS=0` to skip waiting entirely and rely on async backfill.

### Optional: Enable Entra login (frontend + backend)

Add these values in `backend/.env` when enabling token auth:

```dotenv
AUTH_MODE=hybrid
ENTRA_TENANT_ID=<tenant-id>
ENTRA_CLIENT_ID=<api-app-id>
ENTRA_ALLOWED_AUDIENCES=api://<api-app-id>,<api-app-id>
ENTRA_ADMIN_ROLES=PipelineHealer.Admin

VITE_AUTH_MODE=entra
VITE_ENTRA_CLIENT_ID=<spa-app-id>
VITE_ENTRA_API_SCOPE=api://<api-app-id>/PipelineHealer.Access
# Prefer explicit authority when tenant GUID issues are suspected:
VITE_ENTRA_AUTHORITY=https://login.microsoftonline.com/<tenant-or-primary-domain>
```

For Entra config changes:

- backend-only auth changes: `bash scripts/ph.sh deploy:env`
- frontend `VITE_*` changes: publish a new release, then run `bash scripts/ph.sh deploy:release --release-version vX.Y.Z`

#### Beginner-friendly Entra portal checklist

1. Create `PipelineHealer API` app registration:
   - copy `Application (client) ID` (this is `ENTRA_CLIENT_ID`)
   - copy `Directory (tenant) ID` (this is `ENTRA_TENANT_ID`)
2. In `PipelineHealer API` -> `Expose an API`:
   - set Application ID URI to `api://<api-app-id>`
   - add scope `PipelineHealer.Access`
3. In `PipelineHealer API` -> `App roles`:
   - add role value `PipelineHealer.Admin` (Users/Groups)
4. In `PipelineHealer API` -> `Manifest`:
   - set `"requestedAccessTokenVersion": 2` inside `"api"`
5. Create `PipelineHealer SPA` app registration:
   - copy SPA `Application (client) ID` (this is `VITE_ENTRA_CLIENT_ID`)
6. In `PipelineHealer SPA` -> `Authentication` -> SPA:
   - add redirect URIs:
     - `https://<frontend-fqdn>`
     - `https://<frontend-fqdn>/app`
     - `http://localhost:5173` (optional local)
7. In `PipelineHealer SPA` -> `API permissions`:
   - add delegated permission `PipelineHealer.Access` from `PipelineHealer API`
   - click `Grant admin consent`
8. In `Enterprise applications` -> `PipelineHealer API` -> `Users and groups`:
   - assign your user/group to role `PipelineHealer Admin`

Troubleshooting quick map:

- `AADSTS50011`: add exact redirect URI shown in error details.
- `AADSTS90002`: tenant identifier mismatch; verify tenant and use explicit authority with primary domain.
- `401 Invalid bearer token` after login: sync backend `ENTRA_*` via `deploy:env`; if `VITE_*` changed, publish and deploy a new release image.

### Optional: Enable MCP diagnostics path

Use this for GitHub MCP observability during activity analysis:

```dotenv
MCP_ENABLED=true
MCP_PROVIDER=github
MCP_READ_ONLY=true
MCP_TIMEOUT_SECONDS=15
MCP_MAX_RETRIES=1
MCP_TOOL_POLICIES=fetch_failure_context=read_only,publish_artifact=write_with_approval,rerun_pipeline=write_with_approval
MCP_REPO_ALLOWLIST=<owner/repo>
```

Verify runtime values:

```bash
bash scripts/ph.sh settings:check | jq '.mcp_enabled,.mcp_provider,.mcp_read_only,.mcp_tool_policies,.mcp_repo_allowlist'
```

#### Issues encountered in this repo rollout (and fixes)

- Wrong tenant GUID copy/paste (`04f...` vs `040f...`):
  - Symptom: `AADSTS90002`
  - Fix: use the exact `Directory (tenant) ID` from Entra and prefer explicit `VITE_ENTRA_AUTHORITY`.
- Missing SPA redirect URI with `/app` path:
  - Symptom: `AADSTS50011` mismatch for `https://<frontend-fqdn>/app`
  - Fix: add both `https://<frontend-fqdn>` and `https://<frontend-fqdn>/app` in SPA redirect URIs.
- Frontend `VITE_*` values changed but only env-sync deploy was used:
  - Symptom: old login behavior/config remains in browser app
  - Fix: publish a new release, then run `bash scripts/ph.sh deploy:release --release-version vX.Y.Z`.
- Backend still on key mode during migration:
  - Symptom: bearer login succeeds but API acts like key-only
  - Fix: set `AUTH_MODE=hybrid` (or `entra`) and run `bash scripts/ph.sh deploy:env`.
- Token issuer format differences from Microsoft:
  - Symptom: `401 Invalid bearer token` despite successful sign-in
  - Fix: ensure backend accepts both tenant issuer formats and set API app `requestedAccessTokenVersion` to `2`.
- Admin user not assigned to Entra admin role:
  - Symptom: settings endpoints denied after sign-in
  - Fix: assign `PipelineHealer Admin` in Enterprise Applications -> `PipelineHealer API` -> Users and groups.

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

## Step 5 — Verify Model Connection (Recommended)

If you are using `LLM_PROVIDER=openai_compatible`, verify provider values through `settings:check`:

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.openai_compatible_base_url,.openai_compatible_model,.llm_model_analysis,.llm_model_diagnosis,.llm_model_remediation'
```

If you are using Azure OpenAI, run the connectivity checks below.

Before triggering failures, confirm your Azure OpenAI credentials work:

```bash
cd backend
source .venv/bin/activate
python3 scripts/aoai_smoke.py
```

If you are using Docker Compose (no local venv), run:

```bash
bash scripts/ph.sh aoai:check
```

If `aoai:check` cannot run in your environment, use this direct container check:

```bash
docker compose --env-file backend/.env exec backend python3 -c "import os; from openai import AzureOpenAI; c=AzureOpenAI(api_key=os.environ['AZURE_OPENAI_API_KEY'], api_version=os.environ.get('AZURE_OPENAI_CHAT_API_VERSION','2024-12-01-preview'), azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT']); r=c.chat.completions.create(model=os.environ['AZURE_OPENAI_DEPLOYMENT_NAME'], messages=[{'role':'user','content':'Reply with OK'}], max_tokens=8); print('model connectivity OK.'); print(r.choices[0].message.content)"
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

Top-level KPI chips now also include:

- `MCP Runs (30d)` — activities processed with MCP enabled
- `LLM Fallback (30d)` — percentage of LLM-observed runs that used fallback path

**API** — or check via the command line:

```bash
curl -sS "http://127.0.0.1:8000/api/activities?limit=20"
```

**GitHub** — check for new PRs and issues:

```bash
gh pr list -R <owner>/<repo>
gh issue list -R <owner>/<repo> --state open
```

To confirm whether AI inference was used for a specific activity, open Activity Detail and check `Diagnosis Source`:

- `pattern` = deterministic rule-based diagnosis
- `llm` = LLM-assisted diagnosis path

If MCP is enabled, the same Activity Detail now includes `MCP Observability`:

- summary: `Provider`, `Status`, `Read Only`, `Reason` (friendly label + raw code)
- expandable details: `Configured Tools`, `Source Attribution`, `Tool Usage`
- action audit rows now show both friendly result (`Allowed` / `Blocked` / `Error` / `Timeout`) and raw result codes for audit trust.

### Idempotency Validation (Recommended for demos/reviews)

Validate remediation deduplication with a repeated trigger:

1. Trigger a deterministic failure type twice (for example `dependency`) against the same repo/workflow.
2. Confirm the second activity does **not** create a duplicate PR/issue.
3. In Activity Detail, confirm Result Metadata includes `Reused Existing PR`.
4. Save evidence for your review/demo notes:
   - two run IDs
   - one activity screenshot showing the reuse badge
   - one PR URL showing a single reused artifact

---

## Using `ph.sh` Commands Locally

The `ph.sh` CLI defaults to targeting Azure, but you can use it locally by setting `PH_BACKEND_URL`:

```bash
export PH_BACKEND_URL=http://127.0.0.1:8000

bash scripts/ph.sh settings:check            # check current settings
bash scripts/ph.sh settings:audit --limit 10  # view audit trail
bash scripts/ph.sh settings:persist:verify --from-settings --skip-redeploy
bash scripts/ph.sh logs --tail 100            # view backend logs (docker compose)
bash scripts/ph.sh backfill                   # trigger diagnostics backfill
```

**Works locally:** `settings:check`, `settings:audit`, `settings:persist` (`--skip-redeploy`), `settings:persist:verify` (`--skip-redeploy`), `audit:proof`, `backfill`, `logs`, `logs:raw`, `logs:grep`, `demo:proof`, `demo:reset`.

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

### Deploy Published Release (Recommended)

```bash
bash scripts/ph.sh deploy:release --release-version v0.2.6
```

This promotes already-published release images from ACR by digest, updates both Container Apps, syncs env vars, and verifies health.

### Full Redeploy From Local Build (Development/Hotfix Path)

```bash
bash scripts/ph.sh deploy
```

This path builds and pushes from your local machine before updating Container Apps.
It also prunes old local ACR-tagged images and old ACR tags/manifests by default.
Protected from pruning: `latest`, current deploy tag, and semver-like tags (for example `v0.2.3`).

Tune retention or disable pruning for the full deploy path:

```bash
bash scripts/ph.sh deploy --acr-retain-tags 50
bash scripts/ph.sh deploy --skip-acr-prune
bash scripts/ph.sh deploy --skip-local-image-prune
```

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

PipelineHealer now uses a find-or-create flow for remediation artifacts:

- If a matching open remediation PR already exists, it is reused (no duplicate PR).
- If a branch ref collision occurs on `POST /git/refs`, PipelineHealer checks for an existing PR on that branch first.
- If no reusable PR is found, PipelineHealer retries with a suffixed branch name.

If you still see persistent `422` failures, inspect the activity error and verify the token can read/write refs and PRs in the target repo.

### Remediation shows `410 Gone` or `403 Forbidden`

The target repository has issues or PRs disabled, or is archived. PipelineHealer handles this gracefully — the activity completes as `completed` with a reason code like `OUTPUT_ISSUES_DISABLED` visible in the Activity Detail page.

### Remediation shows `403 Forbidden` for `/repos/<owner>/<repo>/issues` or pull request APIs

This usually means an auth/permission mismatch for GitHub write actions.

Common causes:

- PAT lacks required write scopes/permissions for the repo.
- Fine-grained token is not granted access to the target repository.
- Fine-grained token permissions for Issues/Pull requests are read-only or unset (must allow write).
- Repository has Issues disabled (for issue fallback) or is read-only/archived.
- Runtime token in `backend/.env` differs from the one you tested locally.

Quick checks:

```bash
gh auth status
gh issue create -R <owner>/<repo> -t "PipelineHealer auth test" -b "test"
gh pr list -R <owner>/<repo>
```

If needed, update `GITHUB_PERSONAL_ACCESS_TOKEN` in `backend/.env` and resync runtime env:

```bash
bash scripts/ph.sh deploy:env
```

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
