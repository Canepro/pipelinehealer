# Agent Instructions (Repo-Specific)

This repository contains **PipelineHealer** — a multi-agent CI/CD self-healing system built for the [AI Dev Days Hackathon](https://github.com/Azure/AI-Dev-Days-Hackathon).

## Quick Commands

### Backend (Python + UV)

```bash
cd pipelinehealer/backend
cp .env.example .env           # first time only — fill in values
uv pip install -e ".[dev]"     # install with dev dependencies (Recommended)
# If `uv` isn't installed yet:
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -U pip
#   pip install -e ".[dev]"
uvicorn src.main:app --reload  # run API server on :8000
pytest                         # run tests
ruff check src/                # lint
mypy src/                      # typecheck
```

### Frontend (TypeScript + Bun/npm)

```bash
cd pipelinehealer/frontend
bun install                    # or npm install
bun run dev                    # Vite dev server on :5173
bun run build                  # tsc + vite build
bun run lint                   # eslint
bun run format                 # prettier
```

### Docker (local dev)

```bash
cd pipelinehealer
cp backend/.env.example backend/.env   # first time only — fill in values
podman compose --env-file backend/.env build backend frontend
podman compose --env-file backend/.env up -d backend frontend
podman compose --env-file backend/.env ps
curl -sS http://127.0.0.1:8000/health
# docker compose works too if your environment maps Docker CLI to Podman
```

### Azure Deployment

```bash
cd pipelinehealer
# complete docs/PREDEPLOY_PLACEHOLDER_AUDIT.md first
azd up                         # provision infra (Bicep) + deploy services
```

## Phased Execution Plan (Track Here)

**Last updated:** Feb 12, 2026

This section is the working checklist for getting PipelineHealer demo-ready and submission-ready. As we complete work, we:

- Check off items in the current phase
- Update phase status
- Add a short entry to **Execution Log**

### Phase Overview

| Phase | Goal | Status | Primary Files |
|------:|------|--------|---------------|
| 0 | Hygiene baseline (lint/typecheck/tests) | Completed | `backend/pyproject.toml`, `backend/src/*` |
| 1 | Correctness (IDs, auto-fix PRs, retry behavior) | Completed | `backend/src/workflows/pipeline_healer.py`, `backend/src/agents/orchestrator.py`, `backend/src/tools/fix_generators.py`, `backend/src/agents/remediation.py`, `backend/src/api/dashboard.py` |
| 1.5 | Safe+demo mode (more self-healing without breaking safety) | Completed | `backend/src/config.py`, `backend/src/tools/fix_generators.py`, `backend/src/agents/remediation.py`, `demo-repo/.github/workflows/ci.yml` |
| 2 | Security (API auth, webhook hardening) | Completed | `backend/src/main.py`, `backend/src/api/*`, `backend/src/config.py` |
| 3 | Reliability (timeouts, retries/backoff, log handling) | Completed (backend) | `backend/src/tools/github_tools.py`, `backend/src/agents/*` |
| 4 | Deployment alignment (azd/bicep/images/container apps) | Completed (Azure dev environment provisioned and validated) | `azure.yaml`, `infra/main.bicep`, `backend/Dockerfile`, `frontend/Dockerfile` |
| 5 | Demo + submission polish | In progress | `README.md`, `docs/DEMO_SCRIPT.md`, `docs/LOCAL_DEMO_RUNBOOK.md`, `demo-repo/.github/workflows/ci.yml` |

### Phase 0: Hygiene Baseline (lint/typecheck/tests)

Exit criteria:

- `ruff check backend/src` passes
- `mypy backend/src` passes (strict)
- `pytest backend/tests` passes

Work items:

- [x] Fix current ruff errors (unused imports/vars) in backend.
- [x] Wire observability setup (or explicitly remove dead code) so the module is either used or intentionally excluded.
- [x] Ensure local dev path works without Azure storage dependencies (in-memory storage path remains functional).

Notes:

- If this environment doesn’t have `ruff`/`mypy`/`pytest` installed, run Phase 0 validation after `uv pip install -e ".[dev]"` in `backend/`.
- If `pip install -e ".[dev]"` fails due to a missing README, confirm `backend/README.md` exists (packaging metadata requires it).
- Feb 10, 2026 validation (backend venv):
  - `ruff check src`: pass
  - `mypy src` (strict): pass
  - `pytest`: pass (16 tests)
  - Remaining warnings: Pydantic v2 deprecations and `datetime.utcnow()` deprecation (future cleanup).

### Phase 1: Correctness (Core Behavior)

Exit criteria:

- Webhook `activity_id` corresponds to a real persisted activity record.
- Dependency and lint PR creation produces real commits (not empty PR attempts).
- Manual retry endpoint triggers a real action (rerun jobs or restart pipeline) and the UI reflects it.

Work items:

- [x] Fix the **activity ID mismatch** between `PipelineHealerWorkflow.start()` and `OrchestratorAgent.process_workflow_failure()`.
- [x] Make dependency auto-fix actually write file contents (or implement structured patch application) so PRs are not empty.
- [x] Implement `/api/activities/{id}/retry` to re-run failed jobs via GitHub API (minimum viable) or to re-run the internal workflow pipeline (preferred).
- [x] Add/extend tests for the above flows.
- [x] Demo verification: ensure **dependency** and **lint** scenarios open PRs (not issues) in the demo repo.

Known limitations (address in future):

- Dependency PRs currently update source manifests (for example `package.json`) but do not update lockfiles (for example `package-lock.json`, `bun.lockb`, `pnpm-lock.yaml`).
- Structured change rendering supports `json_update` and `line_update` today. `toml_update` is not implemented yet.
- If fix rendering fails, the system returns a failed remediation; future improvement is to fall back to creating an issue automatically.
- Azure OpenAI connectivity can be validated via `backend/scripts/aoai_smoke.py`. This script supports both Azure OpenAI resources (`*.openai.azure.com`) and Foundry/AIServices endpoints (`*.cognitiveservices.azure.com`).
- Demo repo note: `demo-repo/.github/workflows/ci.yml` uses **Bun** (`oven-sh/setup-bun`) to align with the frontend stack, and does not require a committed lockfile.
- Webhook tunneling for local dev: use `ngrok` when available; if you can't install it, use `smee.io` + `bunx smee-client` to forward GitHub webhooks to `http://127.0.0.1:8000/webhook/github`.
- Demo repo note: to demonstrate PR creation reliably, the `dependency` failure should be a missing module (for example `Cannot find module 'left-pad'`) and the `lint` failure should be an ESLint flat config missing case (missing `eslint.config.js`).
- Storage note: `InMemoryStorage` resets on backend restart; if `/api/activities` returns `[]`, confirm you triggered at least one `workflow_run.completed` failure since the last restart.

**Phase 1 E2E verification checklist** (run with backend + smee.io receiving webhooks; repo `Canepro/pipelinehealer-demo`):

| failure_type   | Expected remediation | Trigger |
|----------------|----------------------|--------|
| dependency     | PR created           | `gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=dependency` |
| lint           | PR created           | `gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=lint` |
| test           | Issue created        | `gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=test` |
| build_config   | Issue created        | `gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=build_config` |
| timeout        | Issue created        | `gh workflow run CI -R Canepro/pipelinehealer-demo -f failure_type=timeout` |

Check activities after each run: `curl -sS "http://127.0.0.1:8000/api/activities?limit=20"`.

### Phase 1.5: Safe+Demo Mode (Hackathon-Friendly)

Goal:

- Keep default behavior stable (`HEAL_MODE=safe`)
- Provide an optional mode (`HEAL_MODE=demo`) that demonstrates real self-healing for more scenarios, without adding unsafe "guessy" PRs

Exit criteria:

- `HEAL_MODE=safe` behavior unchanged for the 5 failure types
- `HEAL_MODE=demo` enables at least:
  - Flaky test retry (`retry_workflow`)
  - Timeout PR to bump `timeout-minutes` (when a known workflow file is present)
- Local runbook exists and matches the real commands used during verification

Work items:

- [x] Add `HEAL_MODE` setting and document it in `backend/.env.example`.
- [x] Wire `HEAL_MODE` into remediation planning (`FixGenerators`).
- [x] Upgrade `line_update` to support regex substitutions and multi-file selection.
- [x] Add admin-protected runtime settings surface (`GET/PATCH /api/settings` + frontend `/settings`) for secure ops controls.
- [x] Add unit tests for demo-mode behaviors (retry, timeout PR plan rendering).

Blog note:

- Published: series post #2 covered "AI vs logic" and the safe/demo split.
- Next blog post should focus on log-analysis reliability and webhook hardening tradeoffs (Phase 3 + real Azure delivery behavior).

### Phase 2: Security (Minimum Viable)

Exit criteria:

- Dashboard API requires a secret (API key or bearer token) for all `/api/*` endpoints in non-dev environments.
- Webhook signature verification policy is explicit and safe for demo/prod.
- Admin settings endpoints require dedicated admin auth.

Work items:

- [x] Add `X-API-Key` (or bearer token) auth for `/api/*` endpoints.
- [x] Add `X-Admin-Key` auth for admin settings endpoints (`GET/PATCH /api/settings`).
- [x] Decide and document webhook signature verification behavior for `development` vs `production`.
- [x] Fix CORS configuration for deployed origins (wildcard strings in `allow_origins` won’t match; prefer `allow_origin_regex` or explicit origins).

### Phase 3: Reliability (Demo Safety)

Exit criteria:

- GitHub API calls handle 429/5xx with retry/backoff.
- Agent steps have sane per-step timeouts.
- `timed_out` runs still surface useful logs or a clear reason.

Work items:

- [x] Add retry/backoff for GitHub API calls in `GitHubTools`.
- [x] Add per-step timeouts in orchestrator pipeline steps.
- [x] Adjust log fetching to handle `timed_out` conclusions (not only `failure` jobs).
- [x] Increase or improve log truncation strategy (preserve error tail/sections).

### Phase 4: Deployment Alignment

Exit criteria:

- `azd up` deploys the real backend/frontend images.
- Infra no longer references placeholder hello-world images.
- Service configuration matches real code (Container Apps only for current architecture).

Work items:

- [x] Replace placeholder images in `infra/main.bicep` with ACR-backed backend/frontend image references.
- [x] Align `azure.yaml` services to Container Apps (removed placeholder Functions mapping).
- [x] Provisioned Azure dev environment in `rg-canepro-ph-dev-eus` and verified backend/frontend FQDNs.
- [x] Run and sign off `docs/PREDEPLOY_PLACEHOLDER_AUDIT.md` (dev signoff recorded after provisioning/verification).

### Phase 5: Demo + Submission Polish

Exit criteria:

- End-to-end demo flow works: failing run -> webhook -> dashboard activity -> PR/issue created.
- README contains an architecture diagram and a crisp “how to demo” section.
- Demo video outline exists (2 minutes max).
- Blog series is kept in sync with real progress (at least 1 post/week during the hacking window).

Work items:

- [x] Validate `demo-repo/.github/workflows/ci.yml` triggers all 5 failure types reliably.
- [x] Add Mermaid architecture diagram to `README.md`.
- [x] Write a short demo script and checklist for recording.
- [x] Publish the next blog post in the portfolio repo and update its roadmap:
  - `/mnt/d/repos/portfolio_website-main/content/blog/YYYY-MM-DD-*.mdx`
  - `/mnt/d/repos/portfolio_website-main/content/blog/blog.md`

### Human “Come In Here” Points (Decisions/Inputs Needed)

Decisions made (Recommended defaults for this repo):

- Retry semantics (Recommended): GitHub Actions `rerun-failed-jobs` from the dashboard, then rely on the next webhook to re-process the run.
  - Future: “re-run internal pipeline” requires persisting enough event/run metadata per activity.
- Dashboard auth (Recommended): `X-API-Key` for `/api/*` plus `X-Admin-Key` for admin settings endpoints.
  - Future: bearer/JWT or fronted by an auth proxy.
- Deployment target (Recommended): Container Apps only for demo reliability.
  - Future: add an Azure Functions webhook-forwarder once there is real Functions app code in-repo.

### Execution Log

- Feb 10, 2026: Added phased plan and checklists to `AGENTS.md`.
- Feb 10, 2026: Fixed known ruff `F401/F841` issues (unused imports/vars) in backend modules.
- Feb 10, 2026: Wired `configure_observability(app)` into FastAPI startup.
- Feb 10, 2026: Phase 1 started: persist activity up-front in `start()` and pass `activity_id` through to orchestrator so webhook IDs map to stored records.
- Feb 10, 2026: Implemented `/api/activities/{id}/retry` to request GitHub Actions `rerun-failed-jobs` for the stored run.
- Feb 10, 2026: Implemented structured change application for dependency fixes (render `json_update`/`line_update` into committed file contents before PR creation).
- Feb 10, 2026: Added Phase 1 unit tests for activity ID reuse, retry rerun call, and `json_update` rendering.
- Feb 10, 2026: Added `backend/README.md` to unblock editable installs (`pip install -e` / hatchling metadata).
- Feb 10, 2026: Fixed backend editable install by adding hatch wheel package selection (`[tool.hatch.build.targets.wheel] packages = ["src"]`). Future improvement: rename Python package from `src` to `pipelinehealer`.
- Feb 10, 2026: Repo visibility note: OK to keep private during development; still treat committed secrets as compromised; plan to make repo public before Mar 15, 2026.
- Feb 10, 2026: Azure AI Foundry compatibility: added `AZURE_OPENAI_API_KEY` support for local dev and a clear error if `AZURE_OPENAI_ENDPOINT` is mistakenly set to a Foundry *project* endpoint (`...services.ai.azure.com`) instead of an Azure OpenAI *resource* endpoint (`...openai.azure.com`).
- Feb 10, 2026: Azure OpenAI Responses API version: defaulted `AZURE_OPENAI_API_VERSION` to `2025-03-01-preview`; using an unsupported version can yield `400 API version not supported` on some resources.
- Feb 10, 2026: Foundry/AIServices endpoint support: if `AZURE_OPENAI_ENDPOINT` is `*.cognitiveservices.azure.com`, agents use `AzureOpenAIChatClient` (chat completions). If `*.openai.azure.com`, agents use `AzureOpenAIResponsesClient` (responses).
- Feb 10, 2026: Fixed log analyzer regex bug that could throw `global flags not at the start of the expression` when extracting error/warning lines.
- Feb 10, 2026: E2E verified locally: demo repo failing run delivered via `smee.io` created an activity and a remediation issue in `Canepro/pipelinehealer-demo`.
- Feb 10, 2026: E2E verified locally (frontend): `/api/activities` list + dashboard charts populated for multiple failure types (in-memory storage).
- Feb 10, 2026: E2E verified locally (PR): lint failure produced PR `Canepro/pipelinehealer-demo#10` (adds `eslint.config.js`).
- Feb 10, 2026: Demo repo workflow improvements: opened PR `Canepro/pipelinehealer-demo#12` to make dependency + lint failures deterministic and PR-fixable.
- Feb 11, 2026: E2E verified locally (PR): dependency failure produced PR `Canepro/pipelinehealer-demo#13` (adds missing dependency to `package.json`).
- Feb 11, 2026: Phase 1.5 started: added `HEAL_MODE` (`safe` vs `demo`) to support demo-friendly self-healing while keeping safe defaults stable.
- Feb 11, 2026: Phase 1.5: demo mode supports retrying flaky test runs (`retry_workflow`) and opening PRs to bump `timeout-minutes` when a known workflow file can be patched deterministically.
- Feb 11, 2026: Docs: added `docs/LOCAL_DEMO_RUNBOOK.md` (exact demo commands) and `docs/FUTURE_PLAN.md` (roadmap), plus README section clarifying AI vs logic.
- Feb 10, 2026: Portfolio blog Series 1 updated: drafted Post 2 (multi-agent pipeline design) and updated roadmap in `/mnt/d/repos/portfolio_website-main/content/blog/blog.md`.
- Feb 11, 2026: Containerized local backend flow verified with Podman using `--env-file backend/.env` (build/up/ps/health) and documented in runbook + README.
- Feb 11, 2026: Fixed Agent Framework compatibility for Foundry/AIServices endpoints: if a client lacks `as_agent()` (seen in older containerized builds), fallback wraps it via `ChatAgent`, preventing `'AzureOpenAIChatClient' object has no attribute 'as_agent'` runtime failures.
- Feb 11, 2026: Phase 2 started: `/api/*` now requires `X-API-Key` outside development, webhook signature verification policy is explicit (`VERIFY_WEBHOOK_SIGNATURE`, `VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT`), and CORS now uses env-driven `cors_allowed_origins` plus `allow_origin_regex` for deploy hosts.
- Feb 11, 2026: Phase 2 validated locally (`ruff`, `mypy`, `pytest` all pass) and PR #1 review follow-up comment posted summarizing resolved suggestions and security updates.
- Feb 11, 2026: Resolved current backend deprecation warnings by switching to timezone-aware UTC timestamps (`datetime.now(UTC)`), normalizing naive/aware datetime comparisons in storage, and migrating Pydantic model config to `ConfigDict`.
- Feb 11, 2026: Refined `backend/.env.example` to a clearer, sectioned template (local E2E-first), keeping variable names unchanged while clarifying endpoint/API-version guidance and security defaults.
- Feb 11, 2026: Updated `docker-compose.yml` backend env passthrough to include Phase 2 security/agent vars (`VERIFY_WEBHOOK_SIGNATURE*`, `API_AUTH_KEY`, CORS, heal mode, remediation limits). Note: env changes require `podman compose ... up -d --force-recreate backend`.
- Feb 11, 2026: Added settings foundation: backend `GET /api/settings` and frontend `/settings` baseline.
- Feb 11, 2026: Frontend tooling baseline fixed for local validation: added `frontend/src/vite-env.d.ts` (`import.meta.env` typing) and `frontend/eslint.config.js` (ESLint v9 flat config), so `bun run build` and `bun run lint` run cleanly.
- Feb 11, 2026: Frontend API client now supports optional `VITE_API_AUTH_KEY`, sending `X-API-Key` automatically for secured `/api/*` routes in non-development environments.
- Feb 11, 2026: Phase 3 implemented in backend core: GitHub API retries/backoff for 429/5xx + network errors, per-step orchestrator timeouts, timed_out job log collection, and head+tail log truncation for prompts.
- Feb 11, 2026: Added Phase 3 tests in `backend/tests/test_phase3_reliability.py` for retry behavior, timed_out job inclusion, orchestrator timeout failure handling, and prompt truncation tail preservation.
- Feb 11, 2026: Phase 3 validation passed: `ruff check src`, `mypy src`, and `pytest` (35 tests passing).
- Feb 11, 2026: Added `docs/PREDEPLOY_PLACEHOLDER_AUDIT.md` and wired it into README/AGENTS as a required pre-deploy gate.
- Feb 11, 2026: Phase 4 deployment alignment started: removed `functions` service from `azure.yaml`, switched post-provision outputs to backend/frontend URLs, replaced placeholder Container App images in `infra/main.bicep` with ACR-backed backend/frontend image references, and added Canepro naming defaults in `infra/main.bicepparam`.
- Feb 11, 2026: Fixed frontend Azure crash-loop by making Nginx backend proxy runtime-configurable (`BACKEND_UPSTREAM`), wiring local compose to `http://backend:8000` and Bicep frontend env to backend Container App FQDN.
- Feb 11, 2026: Fixed Azure frontend `/api/*` proxy loop/auth behavior by forwarding `Host: $proxy_host`, enabling SNI (`proxy_ssl_server_name on`), and adding server-side `X-API-Key` injection from frontend `API_AUTH_KEY`.
- Feb 12, 2026: Provisioned Azure dev stack successfully in `rg-canepro-ph-dev-eus` (ACR, Container Apps env, backend/frontend apps, OpenAI, Cosmos, Key Vault, App Insights) and verified backend health + frontend reachability.
- Feb 12, 2026: Set production backend runtime env on Azure Container Apps (`ENVIRONMENT=production`, API auth enabled, webhook signature verification enabled) and validated protected settings access.
- Feb 12, 2026: Azure OpenAI deployment switched to `gpt-5-mini` on backend runtime config; settings endpoint now reports `AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5-mini`.
- Feb 12, 2026: Phase 4 completed: frontend runtime proxy and API key forwarding are now stable on Azure Container Apps; backend/frontend FQDNs and auth behavior verified end-to-end.
- Feb 12, 2026: Added recommended warm/low-cost copy-paste toggle block in README + runbook to switch `min-replicas` between demo reliability (`1`) and cost-saving idle mode (`0`).
- Feb 12, 2026: Phase 5 started: submission checklist updated with Azure deployment complete; remaining focus is demo polish, architecture diagram, and final video/script assets.
- Feb 12, 2026: Phase 5 docs pass: added Mermaid architecture diagram in `README.md` and created `docs/DEMO_SCRIPT.md` with a time-boxed 2-minute runbook/checklist.
- Feb 12, 2026: Azure webhook mode stabilized: disabled legacy `smee.io` repo hook, activated direct webhook to backend Container App, and verified `ping` deliveries return `200`.
- Feb 12, 2026: Azure runtime updated to include `GITHUB_PERSONAL_ACCESS_TOKEN` for GitHub REST calls from Container Apps (temporary path until full GitHub App auth wiring is completed).
- Feb 12, 2026: Documented and validated expected duplicate-run behavior: remediation PR creation can return `422` when target fix branches already exist (for example `fix/update-left-pad`, `fix/lint-eslint-config`).
- Feb 12, 2026: Fixed Azure dashboard metrics endpoints by removing unsupported async Cosmos query kwargs and switching stats/failure-breakdown aggregation to storage-backed activity paging.
- Feb 12, 2026: Portfolio blog roadmap synced and Post 3 published in `/mnt/d/repos/portfolio_website-main/content/blog/2026-02-12-pipelinehealer-azure-deployment-lessons.mdx`.
- Feb 12, 2026: Removed stale `PROJECT_STATUS.md` and `REVIEW.md`; consolidated active tracking/design notes into `AGENTS.md` and `README.md`.
- Feb 12, 2026: Added scripted Azure redeploy flow `scripts/deploy/redeploy_azure_containerapps.sh` and updated docs to use script-first instructions (including `ADMIN_API_KEY` runtime setup).

## Project Layout

```
pipelinehealer/
├── azure.yaml                 # Azure Developer CLI config
├── docker-compose.yml         # Local dev stack
├── README.md                  # Project README (public-facing)
├── LICENSE                    # MIT
├── backend/                   # Python FastAPI backend
│   ├── pyproject.toml         # Dependencies (UV/hatch)
│   ├── .env.example           # Required env vars
│   ├── Dockerfile
│   ├── src/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── config.py          # Pydantic settings (env-driven)
│   │   ├── models.py          # Data models
│   │   ├── storage.py         # Cosmos DB + in-memory storage
│   │   ├── observability.py   # OpenTelemetry / App Insights
│   │   ├── agents/            # AI agents (one per file)
│   │   │   ├── base.py        # Base agent class
│   │   │   ├── log_analyzer.py
│   │   │   ├── diagnosis.py
│   │   │   ├── remediation.py
│   │   │   └── orchestrator.py
│   │   ├── api/               # FastAPI routers
│   │   │   ├── webhook.py     # GitHub webhook handler
│   │   │   └── dashboard.py   # Dashboard API endpoints
│   │   ├── tools/             # Agent tools
│   │   │   ├── github_tools.py    # GitHub REST API wrapper
│   │   │   └── fix_generators.py  # Fix generation for 5 failure types
│   │   └── workflows/
│   │       └── pipeline_healer.py # Orchestration pipeline
│   └── tests/
│       ├── test_diagnosis.py
│       └── test_webhook.py
├── frontend/                  # React dashboard
│   ├── package.json
│   ├── Dockerfile
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/               # API client (TanStack Query)
│       ├── components/        # UI components
│       └── pages/
│           ├── Dashboard.tsx   # Stats cards, charts
│           ├── Activities.tsx  # Filterable activity table
│           └── ActivityDetail.tsx
├── infra/                     # Azure Bicep templates
│   ├── main.bicep
│   └── main.bicepparam
├── scripts/
│   ├── demo/                  # Demo automation scripts
│   └── deploy/                # Azure redeploy helper scripts
└── demo-repo/                 # Demo repo for triggering test failures
    ├── .github/               # GitHub Actions workflow with failure triggers
    ├── index.js
    ├── test.js
    └── package.json
```

## Architecture

Four agents form a sequential pipeline triggered by GitHub webhooks:

1. **Log Analyzer** (`agents/log_analyzer.py`) — Parses raw CI logs, extracts structured error patterns. Does not diagnose.
2. **Diagnosis Agent** (`agents/diagnosis.py`) — Maps patterns to failure categories. Does not fix.
3. **Remediation Agent** (`agents/remediation.py`) — Generates targeted fixes based on confirmed diagnosis. Does not guess from raw logs.
4. **Orchestrator** (`agents/orchestrator.py`) — Coordinates the pipeline, manages state, opens PR or issue.

Agents communicate through typed Pydantic models, not free-form text.

### Supported Failure Types

| Type | Auto-Fix |
|------|----------|
| Dependency issues | PR |
| Lint/format errors | PR |
| Test failures | Issue |
| Build config errors | Issue |
| Timeouts | Issue |

### CI Platform Extensibility

Currently GitHub Actions only. The architecture should support pluggable CI platforms via an adapter interface:

```python
class CIPlatformAdapter(ABC):
    async def get_run_info(self, event_data: dict) -> WorkflowRunInfo: ...
    async def get_logs(self, run_id: str) -> dict[str, str]: ...
    async def create_fix(self, repo: str, files: dict, message: str) -> str: ...
    async def create_issue(self, repo: str, title: str, body: str) -> str: ...
    async def retry_run(self, run_id: str) -> bool: ...
```

- `GitHubAdapter` wraps existing `GitHubTools` methods
- Webhook routes: `/webhook/github`, `/webhook/jenkins`, `/webhook/gitlab`
- Factory selects adapter based on incoming webhook source
- CI extensibility plan is documented in this section and tracked directly in `AGENTS.md`.

### Data Flow

```
GitHub workflow_run.completed webhook
  → api/webhook.py (signature verification, event routing)
  → workflows/pipeline_healer.py (orchestration)
  → agents/log_analyzer.py → agents/diagnosis.py → agents/remediation.py
  → tools/github_tools.py (create PR or issue)
  → storage.py (persist activity to Cosmos DB)
```

## Engineering Rules

- Do not commit secrets. Use `.env` locally (see `.env.example`), Azure Key Vault in production.
- All configuration is env-driven via Pydantic `Settings` in `config.py`. Do not hardcode endpoints, keys, or deployment names.
- Agents must remain single-responsibility. If an agent is doing two jobs, split it.
- Agent inputs and outputs must use typed Pydantic models defined in `models.py`.
- Backend code must pass `ruff check` and `mypy --strict`.
- Frontend code must pass `eslint` and `tsc`.
- Keep the in-memory storage path (`InMemoryStorage`) working for local dev without Azure dependencies.

## Repo Visibility & Secret Hygiene

- Keeping the repo **private during active development** is reasonable to reduce accidental disclosure.
- A private repo does **not** make committed secrets safe. If a secret is ever committed (even briefly), assume it is compromised:
  - remove it from git history (or invalidate the repo),
  - rotate/revoke the secret (preferred),
  - re-issue credentials using Key Vault / GitHub Secrets.
- Hackathon requirement reminder: the repository must be **public** before submission (target: before **Mar 15, 2026, 11:59 PM PT**).

Recommended before switching public:

- Run a secret scan (gitleaks/trufflehog) and review git history for tokens/keys.
- Ensure `.env`, private keys (`*.pem`, `*.key`), and local credentials remain untracked (see `.gitignore`).

## Hackathon Context

### Target Categories

- **Grand Prize: Agentic DevOps** (primary) — Automating CI/CD incident response
- **Best Multi-Agent System** — Four-agent orchestration pipeline
- **Best Azure Integration** — Cosmos DB, OpenAI, Container Apps, Key Vault, App Insights

### Required Technologies (must use at least one)

- Microsoft Agent Framework ✅ (agent orchestration)
- Azure OpenAI ✅ (model deployment configurable; current dev uses `gpt-5-mini`)
- Azure services ✅ (Cosmos DB, Container Apps, Key Vault, App Insights, ACR)
- GitHub ✅ (public repo, webhooks, PR/issue creation)

### Submission Checklist

- [x] Working project deployed to Azure (`azd up`)
- [ ] Public GitHub repository
- [ ] Project description (features, problem solved, technologies)
- [ ] Demo video (2 min max, YouTube/Vimeo, shows the product working)
- [ ] Architecture diagram (Mermaid or draw.io)
- [ ] Microsoft Learn usernames for all participants
- [ ] Microsoft Learn Skilling Plan completed

### Judging Criteria (20% each)

1. **Technological Implementation** — Code quality, effective use of hero technologies, documentation
2. **Agentic Design & Innovation** — Creative AI patterns, agent orchestration sophistication
3. **Real-World Impact** — Problem significance, production readiness, potential impact
4. **User Experience & Presentation** — Intuitive UX, clear demo video, balanced frontend/backend
5. **Adherence to Category** — Matches the Agentic DevOps category description

### Key Deadlines

| Phase | Dates |
|-------|-------|
| Registration | Jan 20 – Feb 22, 2026 |
| Hacking | Feb 10 – Mar 15, 2026 (11:59 PM PT) |
| Judging | Mar 16 – Mar 22, 2026 |
| Winners | Mar 25, 2026 |

### Official Rules Summary

- Project must be **newly created** after Feb 10, 2026 (start of hacking period).
- Open-source dependencies are allowed; the project itself must be the entrant's original work.
- Demo video must be under 2 minutes. Judges are not required to watch beyond that.
- Repository must be public.
- Up to 4 team members. Currently solo.
- Can win one Grand Prize + one Category Prize.
- Judges may reassign projects to a different category if it fits better.
- Stage 1 judging is pass/fail (does it fit the theme and use required tech). Stage 2 is scored.

## Azure Services Reference

| Service | Purpose | Config |
|---------|---------|--------|
| Azure OpenAI | Model inference for agent reasoning (`gpt-5-mini` in current dev env) | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME` |
| Cosmos DB | Activity/healing record storage | `COSMOS_DB_ENDPOINT`, serverless tier |
| Container Apps | Backend + frontend hosting | Defined in `azure.yaml` |
| Key Vault | Secrets (GitHub App key, etc.) | `KEY_VAULT_URL` |
| Application Insights | Observability, tracing | `APPLICATIONINSIGHTS_CONNECTION_STRING` |

## Environment Variables

All variables are documented in `backend/.env.example`. Required for production:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI service endpoint |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Yes | Azure OpenAI deployment name (for example `gpt-5-mini` or `gpt-4o`) |
| `COSMOS_DB_ENDPOINT` | Yes | Cosmos DB endpoint |
| `GITHUB_WEBHOOK_SECRET` | Prod | Webhook HMAC secret |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Dev | PAT for local development |
| `GITHUB_APP_ID` | Prod | GitHub App ID |
| `KEY_VAULT_URL` | Prod | Azure Key Vault for secrets |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional | App Insights telemetry |

For local dev, only `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, and `GITHUB_PERSONAL_ACCESS_TOKEN` are needed. Storage falls back to in-memory.

## Testing

```bash
# Unit tests
cd pipelinehealer/backend
pytest

# With coverage
pytest --cov=src --cov-report=term-missing

# Run specific test
pytest tests/test_diagnosis.py -v
```

Integration and E2E tests require deployed Azure resources and a configured GitHub App.

## Demo Repo

`demo-repo/` contains a small Node.js project with a GitHub Actions workflow that can trigger various failure types via workflow dispatch. Use this to test PipelineHealer end-to-end:

1. Push `demo-repo/` to a new GitHub repository
2. Configure the webhook to point to PipelineHealer's deployed URL
3. Trigger workflow dispatch with different failure scenarios
4. Observe PipelineHealer's response in the dashboard

## Tracking & Continuity

- **Execution tracker**: `AGENTS.md` (phases, status, execution log).
- **Public-facing status**: `README.md`.
- **Blog series**: portfolio repo `content/blog/blog.md`.
