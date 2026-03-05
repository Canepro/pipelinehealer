# PipelineHealer

<!-- LAST_VERIFIED: 310d40e -->

> Policy-aware CI/CD remediation platform for GitHub Actions failures.

[![Live Demo](https://img.shields.io/badge/Live_Demo-Try_It-brightgreen)](https://ca-canepro-ph-frontend.kinddune-53ac219d.eastus2.azurecontainerapps.io)
[![Azure](https://img.shields.io/badge/Azure-Deployed-blue)](https://azure.microsoft.com)
[![Release](https://img.shields.io/badge/Release-v0.3.1-blue)](https://github.com/Canepro/pipelinehealer/releases/tag/v0.3.1)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

PipelineHealer ingests failed workflow runs, diagnoses root causes, and applies controlled remediation:
- deterministic fixes open or reuse pull requests
- ambiguous or risky cases open structured issues instead of unsafe edits
- all actions are auditable, explainable, and tied to concrete run evidence

![Dashboard — processed count, safety gating ratios, failure type breakdown, and explainability snapshot](docs/screens/dashboard.png)
![Landing page — policy-aware remediation overview and operational snapshot](docs/screens/Pipelinehealer-Landing_Page.png)

## Hackathon Snapshot

- Public repository: `https://github.com/Canepro/pipelinehealer`
- Live deployment: Azure Container Apps (backend + frontend)
- Current release baseline: [`v0.3.1`](https://github.com/Canepro/pipelinehealer/releases/tag/v0.3.1)
- Next scoped target: `v0.3.2` ([#44](https://github.com/Canepro/pipelinehealer/issues/44))
- `v0.3.2` freeze-required scope: `#36` (Jenkins bridge), `#42` (Assign-to-Agent), `#57` (storage posture hardening)
- OSS-friendly durable storage path: PostgreSQL adapter (`#58`) is now available as an alternative durable backend
- Demo runbook: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)

## Example Remediation Stories

| Path | Evidence |
|------|----------|
| Cross-repo operator-reviewed path (production-style) | Issue: [rocketchat-app-logs-viewer#16](https://github.com/Canepro/rocketchat-app-logs-viewer/issues/16) -> Fix PR: [rocketchat-app-logs-viewer#17](https://github.com/Canepro/rocketchat-app-logs-viewer/pull/17) |
| Deterministic auto-fix path (demo fixture) | Diagnostics: [pipelinehealer-demo#122](https://github.com/Canepro/pipelinehealer-demo/issues/122) -> Tracking issue: [pipelinehealer-demo#120](https://github.com/Canepro/pipelinehealer-demo/issues/120) -> Auto-generated fix PR: [pipelinehealer-demo#121](https://github.com/Canepro/pipelinehealer-demo/pull/121) |

Story flow: PipelineHealer captures failure evidence, opens a traceable issue, and then drives either human-reviewed remediation or deterministic fix PR generation.

## Beginner Path (First 10 Minutes)

For first-time evaluation, start local with default key authentication and no Entra setup.

1. Create env file:

```bash
cp backend/.env.example backend/.env
```

2. In `backend/.env`, set only:
- one LLM path (`AZURE_OPENAI_*` or `OPENAI_COMPATIBLE_*`)
- `GITHUB_PERSONAL_ACCESS_TOKEN`

3. Start backend (Terminal A):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8000
```

4. Start frontend (Terminal B):

```bash
cd frontend
bun install
bun run dev
```

5. Verify:
- `curl -sS http://127.0.0.1:8000/health` returns `{\"status\":\"healthy\"}`
- open `http://127.0.0.1:5173`

Defaults are already beginner-safe in `.env.example`:
- `HEAL_MODE=safe`
- `AUTH_MODE=api_key`
- `VITE_AUTH_MODE=none`
- `STORAGE_MODE=memory` (development default)

For managed deployment and full demo ops, use [docs/LOCAL_DEMO_RUNBOOK.md](docs/LOCAL_DEMO_RUNBOOK.md).

## Deployment Command Cheat Sheet

Pick the path that matches your environment:

1. Azure Container Apps (recommended managed path)

```bash
# Runtime/env-only update (no image rebuild)
bash scripts/ph.sh deploy:env

# Promote a published release by tag
bash scripts/ph.sh deploy:release --release-version vX.Y.Z

# Full rebuild + redeploy from local source
bash scripts/ph.sh deploy
```

2. Kubernetes (Helm)

```bash
# Install or update from chart source
helm upgrade --install pipelinehealer ./charts/pipelinehealer \
  --namespace pipelinehealer \
  --create-namespace \
  -f values.production.yaml

# Verify rollout
kubectl -n pipelinehealer rollout status deploy/pipelinehealer-backend
kubectl -n pipelinehealer rollout status deploy/pipelinehealer-frontend
```

3. Local containers (Docker/Podman)

```bash
docker compose --env-file backend/.env build backend frontend
docker compose --env-file backend/.env up -d backend frontend
# Podman: replace `docker compose` with `podman compose`
```

Detailed docs:
- Azure + local operations: [docs/LOCAL_DEMO_RUNBOOK.md](docs/LOCAL_DEMO_RUNBOOK.md)
- Kubernetes/Helm: [docs/KUBERNETES_HELM_RUNBOOK.md](docs/KUBERNETES_HELM_RUNBOOK.md)
- Full CLI command reference: [docs/CLI.md](docs/CLI.md)

Persistence guardrail for non-development deployments:
- Use a durable backend: `STORAGE_MODE=cosmos` (`COSMOS_DB_ENDPOINT`) or `STORAGE_MODE=postgres` (`POSTGRES_DSN`).
- Non-development startup now fails fast when durable storage is required but missing.
- Explicit non-development in-memory mode is blocked unless you set `ALLOW_IN_MEMORY_STORAGE_IN_NON_DEVELOPMENT=true` for demo/evaluation.

## Why PipelineHealer

CI failures create repetitive triage work and slow delivery. PipelineHealer reduces mean time to understanding and remediation with a safety-first flow:
- Analyze -> Diagnose -> Remediate
- policy gates (`HEAL_MODE`, per-action toggles, repo allowlists)
- explainability fields (`diagnosis_source`, reason codes, source attribution)
- universal failure context (`failing_job`, `failing_step`, `failing_command`, `signal`)
- idempotent artifacts (find-or-create PR/issue reuse)

## Professional Value

- Faster triage: failure context is normalized into consistent signals and evidence.
- Safer automation: deterministic fixes can be auto-proposed while risky paths stay review-first.
- Operational traceability: every action links to run evidence, reason codes, and policy state.
- Deployment flexibility: same control model across Azure, Kubernetes, and local container paths.

## v0.3.2 Freeze Guardrails (Applied)

- Required scope is locked to `#36/#42/#57` to protect submission reliability.
- `#58` (PostgreSQL adapter) was implemented adapter-first after required scope completion.
- Storage extensibility work must remain adapter-scoped and additive (no core workflow rewrites).

## v0.3.2 Integration Scope (Current)

- Signed Jenkins bridge ingestion endpoint for Jenkins-primary CI paths: `POST /webhook/jenkins`
- Jenkins bridge replay protection hardened for concurrent ingress (atomic nonce/delivery reservation path).
- Assign-to-Agent handoff integration with runtime-safe modes:
  - `copy_only` (audited, no network delivery)
  - `webhook` (bounded timeout/retry + destination allowlist)
- Explicit storage posture guardrails:
  - non-development fail-fast when durable storage is required but missing
  - explicit non-development in-memory mode requires opt-in
- OSS-friendly durable storage path:
  - `STORAGE_MODE=postgres` with `POSTGRES_DSN`

## What Shipped In v0.3.1

- frontend runtime-first config for containerized deployments (`VITE_*` via `/runtime-config.js`)
- no-rebuild config updates through runtime env sync paths (ACA/Helm/compose)
- release workflow/frontend image decoupled from auth build-arg coupling

## Previously Shipped In v0.3.0

- Activity Detail `Copy Context` for one-click AI-ready handoff payloads (bounded + redacted)
- visible disabled `Assign to Agent` affordance (`Coming Soon`) for discoverability
- release hardening with anonymous GHCR pullability gating for:
  - backend/frontend tags (`vX.Y.Z` and `X.Y.Z`)
  - backend/frontend digests
  - Helm chart OCI tag (`X.Y.Z`)

Release notes: [CHANGELOG.md](CHANGELOG.md), [v0.3.1 release](https://github.com/Canepro/pipelinehealer/releases/tag/v0.3.1), and [v0.3.0 release](https://github.com/Canepro/pipelinehealer/releases/tag/v0.3.0)

## Kubernetes Portability Status

As of March 3, 2026 (`v0.3.1`), random-user image pullability regressions are gated in release automation.

- previous portability gap issue [#37](https://github.com/Canepro/pipelinehealer/issues/37) is closed
- Helm success output alone is still not sufficient proof; verify rollout and image pulls on clean clusters
- recommended operator path: use published release images and run release verification gates

Operational runbook: [docs/KUBERNETES_HELM_RUNBOOK.md](docs/KUBERNETES_HELM_RUNBOOK.md)

## Architecture

The diagrams below show system boundaries and runtime decision flow.

```mermaid
flowchart TB
  subgraph EXT["External Systems"]
    GH["GitHub Actions"]
    GHAW["GH-AW findings<br/>ci-doctor / breaking-change"]
    MCP["GitHub MCP provider<br/>optional, read-only default"]
  end

  subgraph CTRL["PipelineHealer Control Plane"]
    WH["Webhook Ingress<br/>/webhook/github"]
    ORCH["Orchestrator"]
    ANA["Log Analyzer"]
    DIA["Diagnosis Engine<br/>rules first, LLM fallback"]
    REM["Remediation Engine<br/>policy-gated"]
    BF["Backfill Worker<br/>eventual diagnostics sync"]
  end

  subgraph GOV["Policy and Operator Surface"]
    UI["Dashboard / Activities / Settings"]
    API["Settings API<br/>/api/settings*"]
    AUD["Audit Trail"]
    LRN["Learning Queue + Promotion Gates"]
  end

  subgraph DATA["State and Evidence"]
    DB[("Cosmos DB / PostgreSQL / InMemory")]
    EXP["Explainability Metadata<br/>source path, reason codes"]
  end

  subgraph OUT["GitHub Outcomes"]
    PR["Create or Reuse PR"]
    IS["Create or Reuse Issue"]
    RR["Retry Failed Jobs"]
  end

  GH --> WH --> ORCH
  ORCH --> ANA --> DIA --> REM
  REM --> PR
  REM --> IS
  REM --> RR

  ORCH -. enrich .-> GHAW
  GHAW -. findings .-> DIA
  ORCH -. tool calls .-> MCP
  MCP -. context .-> DIA

  UI --> API --> ORCH
  API --> AUD
  ORCH --> LRN
  BF --> ORCH
  BF --> DB
  ORCH --> DB
  ORCH --> EXP
```

### Failure Processing Flow

```mermaid
sequenceDiagram
  participant GH as GitHub Actions
  participant WH as Webhook API
  participant OR as Orchestrator
  participant DI as Diagnosis
  participant RM as Remediation
  participant DB as Storage
  participant OUT as GitHub Artifacts

  GH->>WH: workflow_run.completed (failure)
  WH->>OR: normalized event
  OR->>DI: logs + context + policy snapshot
  DI-->>OR: diagnosis + confidence + evidence
  OR->>RM: remediation request (policy-gated)
  alt deterministic and allowed
    RM->>OUT: create or reuse PR
  else ambiguous, low confidence, or restricted
    RM->>OUT: create or reuse issue (review-first)
  end
  OR->>DB: persist activity, diagnostics, decisions
  OR-->>WH: accepted and tracked
```

## Developer Setup (uv Variant)

If you already completed the **Beginner Path**, this is the equivalent backend startup using `uv`:

```bash
cd backend
uv pip install --system -e ".[dev]"
uvicorn src.main:app --reload
```

For full local/Azure/Kubernetes run paths, use [docs/LOCAL_DEMO_RUNBOOK.md](docs/LOCAL_DEMO_RUNBOOK.md).

## One-Command Operations

From repo root:

```bash
bash scripts/ph.sh help
bash scripts/ph.sh status
bash scripts/ph.sh settings:check
bash scripts/ph.sh deploy:release --release-version vX.Y.Z
bash scripts/ph.sh demo:e2e
bash scripts/ph.sh logs
```

Full CLI reference: [docs/CLI.md](docs/CLI.md)

Runtime config notes:
- containerized frontend config (`VITE_*`, including Entra settings) is runtime-driven
- use `bash scripts/ph.sh deploy:env` to apply backend/frontend env changes without rebuilding images
- full `deploy` is only needed when code/image contents changed

## Two-Minute Demo Path

- Recording script: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
- On-camera E2E command:

```bash
bash scripts/ph.sh demo:e2e --triggers dependency,lint,test,build_config,timeout --wait-seconds 180 --ci-signal-wait-seconds 180
```

- Proof command:

```bash
bash scripts/ph.sh demo:proof --repo <owner>/<repo> --limit 5
```

## Security and Governance Defaults

- `HEAL_MODE=safe`
- independent execution/action toggles:
  - `AUTO_APPLY_REMEDIATION` (global execution gate)
  - `AUTO_CREATE_PR`, `AUTO_CREATE_ISSUE`, `AUTO_RETRY_WORKFLOW` (per-action outputs)
- Jenkins bridge output policy:
  - `JENKINS_BRIDGE_ALLOW_PR=false` keeps signed Jenkins bridge events issue-first by default
  - set `JENKINS_BRIDGE_ALLOW_PR=true` only when you explicitly want bridge-triggered PR output (and `AUTO_CREATE_PR=true`)
- protected settings APIs (`X-API-Key`; admin routes require `X-Admin-Key` in non-development)
- auditable settings changes and remediation traces
- MCP defaults: `MCP_ENABLED=false`, `MCP_READ_ONLY=true`

Security policy: [SECURITY.md](SECURITY.md)

## Versioning and Release

Version sources are synchronized across:
- `VERSION`
- `backend/pyproject.toml`
- `frontend/package.json`
- `charts/pipelinehealer/Chart.yaml` (`version`, `appVersion`)

Release helpers:

```bash
bash scripts/release_preflight.sh
bash scripts/release_checklist.sh minor
bash scripts/release.sh minor
bash scripts/release_verify.sh vX.Y.Z
```

Release runbook: [docs/RELEASE_RUNBOOK.md](docs/RELEASE_RUNBOOK.md)

## Documentation Map

- [Docs Index](docs/README.md)
- [Feature Guides](docs/features/README.md)
- [API Reference](docs/API.md)
- [CLI Reference](docs/CLI.md)
- [Local + Azure Runbook](docs/LOCAL_DEMO_RUNBOOK.md)
- [Kubernetes Helm Runbook](docs/KUBERNETES_HELM_RUNBOOK.md)
- [Logs & Investigation](docs/LOGS_AND_INVESTIGATION.md)
- [Future Plan](docs/FUTURE_PLAN.md)
- [Changelog](CHANGELOG.md)

## Contributing

Contributions are welcome. For workflow, quality gates, and docs policy:
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [AGENTS.md](AGENTS.md)

When proposing changes, include target version alignment (`docs/FUTURE_PLAN.md`) and release-note intent (`Added`, `Changed`, or `Fixed`).
