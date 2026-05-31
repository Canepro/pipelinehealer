# PipelineHealer

<!-- LAST_VERIFIED: 044aa39 -->

> OSS-first, policy-aware remediation for failed CI/CD pipelines.

[![Live Demo](https://img.shields.io/badge/Live_Demo-Try_It-brightgreen)](https://pipelinehealer.canepro.me)
[![Demo Video](https://img.shields.io/badge/Demo_Video-YouTube-red)](https://youtu.be/9iv5ZMKYzts)
[![Azure](https://img.shields.io/badge/Azure-Deployed-blue)](https://azure.microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

PipelineHealer ingests failed pipeline runs, normalizes the evidence, diagnoses likely root causes, and chooses a policy-safe remediation path.

- deterministic fixes can create or reuse pull requests
- ambiguous or risky failures fall back to structured issues
- selected failures can be delegated to external agents while PipelineHealer keeps the audit trail
- every outcome stays tied to run evidence, policy, labels, and operator verification

Native ingress is GitHub Actions. Jenkins is supported through the signed bridge in [integrations/jenkins-bridge](integrations/jenkins-bridge/README.md). Azure Container Apps is the reference managed deployment, but PipelineHealer is not Azure-only.

![Landing page: policy-aware remediation overview](docs/screens/landing-current.png)
![Dashboard: processed count, safety gates, failure mix, and explainability](docs/screens/dashboard-current.png)

## Current Scope

- Providers: GitHub Actions, Jenkins bridge
- Agent handoff targets: Codex App Server, OpenClaw, Hermes, custom webhook
- Model providers: Azure OpenAI, OpenAI-compatible, Codex App Server, custom scaffold
- Storage: PostgreSQL, Cosmos DB, in-memory local mode
- Secret stores: Infisical, encrypted DB, optional Azure Key Vault
- Current production release: `v0.8.3`
- Latest published release: [`v0.8.3`](https://github.com/Canepro/pipelinehealer/releases/tag/v0.8.3)

## Core Workflow

```text
failed run -> normalized evidence -> diagnosis -> policy decision -> remediation or handoff -> verification
```

PipelineHealer remains the system of record. External agents can do the GitHub work, open PRs, comment, apply labels, rerun workflows, and report back through callback events.

Tracked handoff events:

```text
acknowledged, started_work, needs_more_info, pr_opened, issue_commented,
label_applied, workflow_rerun, completed, failed
```

## Quick Start

Prerequisites:

- Python 3.12+
- `uv`
- Bun
- GitHub token or GitHub App wiring
- one model route, such as Azure OpenAI or Codex App Server

Create local env metadata:

```bash
cp backend/.env.example backend/.env
```

For secrets, prefer Infisical. Do not commit secret values.

```bash
bash scripts/ph.sh secrets:infisical:inventory
bash scripts/ph.sh secrets:infisical:migrate --project-id <infisical-project-id>
```

Keep only metadata in `backend/.env` after migration:

```env
SETTINGS_SECRET_BACKEND=infisical
INFISICAL_PROJECT_ID=<infisical-project-id>
INFISICAL_ENVIRONMENT=dev
INFISICAL_SECRET_PATH=/personal/pipelinehealer
```

Start the backend:

```bash
cd backend
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
infisical run --env dev --path /personal/pipelinehealer --projectId <infisical-project-id> -- uvicorn src.main:app --reload --port 8000
```

Start the frontend:

```bash
cd frontend
bun install
bun run dev
```

Verify:

```bash
curl -sS http://127.0.0.1:8000/health
```

Open `http://127.0.0.1:5173`.

## Tell An Agent To Install PipelineHealer

Paste this into Codex, OpenClaw, Hermes, or another coding agent:

```text
Set up PipelineHealer from this repository.

Rules:
- Do not print, commit, or move secret values.
- Use Infisical for runtime/API/CI/service secrets when available.
- Keep backend/.env to non-secret metadata after migration.
- Run backend tests and frontend build before reporting completion.

Steps:
1. Read AGENTS.md, README.md, docs/reference/CLI.md, and docs/runbooks/LOCAL_DEMO_RUNBOOK.md.
2. Install backend deps with: cd backend && uv pip install -e ".[dev]".
3. Install frontend deps with: cd frontend && bun install.
4. Configure backend/.env from backend/.env.example.
5. Migrate or inject secrets with Infisical. Use redacted proof only.
6. Start backend with infisical run and uvicorn.
7. Start frontend with bun run dev.
8. Verify /health, /api/settings, frontend load, and at least one activity or handoff path if test data exists.
9. Report exact commands run, pass/fail status, and any blocked secrets or provider setup.
```

## Azure Container Apps Deploy

The reference deployment uses `scripts/ph.sh`, Azure Container Registry, and Azure Container Apps.

Recommended Infisical-backed deploy:

```bash
infisical run --env dev --path /personal/pipelinehealer --projectId <infisical-project-id> -- \
  bash scripts/ph.sh deploy --secure-secrets
```

If Docker or Podman is not running locally, add `--remote-build` to build the images in Azure Container Registry.

Env-only update:

```bash
infisical run --env dev --path /personal/pipelinehealer --projectId <infisical-project-id> -- \
  bash scripts/ph.sh deploy:env --secure-secrets
```

Release promotion:

```bash
bash scripts/ph.sh deploy:release --release-version vX.Y.Z --secure-secrets
```

Status and logs:

```bash
bash scripts/ph.sh status
bash scripts/ph.sh logs
```

The deploy adapter stores sensitive values as Container App secrets and binds them through `secretref`. It reads process env first, so `infisical run` can inject values without restoring them to `backend/.env`.

For the production lane, follow [docs/runbooks/PRODUCTION_PROMOTION_RUNBOOK.md](docs/runbooks/PRODUCTION_PROMOTION_RUNBOOK.md). Production promotion uses reviewed release images, Infisical-injected secrets, Azure `what-if`, and the `rg-canepro-ph-prod-eus2` Container Apps lane.

## Kubernetes And Local Containers

Helm:

```bash
helm upgrade --install pipelinehealer ./charts/pipelinehealer \
  --namespace pipelinehealer \
  --create-namespace \
  -f values.production.yaml
```

Local containers:

```bash
docker compose --env-file backend/.env build backend frontend
docker compose --env-file backend/.env up -d backend frontend
```

Optional local storage:

- PostgreSQL: `docker compose --profile postgres up -d postgres`
- Cosmos emulator: `docker compose --profile cosmos up -d cosmos-emulator`

## Operator Surface

- Dashboard: safety gates, failure mix, recent activity
- Activities: searchable run history
- Activity Detail: incident record, evidence, remediation, handoff sessions, verification
- Control Center: governance, learning, trust ops, audit
- Settings: runtime controls, model routing, handoff target policy, write-only secrets

![Activity Detail: incident record, verification, and diagnostics](docs/screens/activity-detail-current.png)
![Control Center: governance posture and integration health](docs/screens/control-center-current.png)

## Security Defaults

- `HEAL_MODE=safe`
- API routes use `X-API-Key` in non-development key mode
- admin settings routes use `X-API-Key` plus `X-Admin-Key`
- Jenkins bridge uses signed payloads with replay/skew guards
- MCP is disabled and read-only by default
- secret values stay in Infisical, ACA secret refs, encrypted DB, or Key Vault depending on deployment

Security policy: [SECURITY.md](SECURITY.md)

## One-Command Ops

```bash
bash scripts/ph.sh help
bash scripts/ph.sh status
bash scripts/ph.sh settings:check
bash scripts/ph.sh deploy:release --release-version vX.Y.Z
bash scripts/ph.sh demo:e2e
bash scripts/ph.sh logs
```

Full CLI reference: [docs/reference/CLI.md](docs/reference/CLI.md)

## Documentation Map

- [Docs Index](docs/README.md)
- [API Reference](docs/reference/API.md)
- [CLI Reference](docs/reference/CLI.md)
- [Operator Control Plane](docs/architecture/OPERATOR_CONTROL_PLANE.md)
- [LLM And Agent Runtime](docs/architecture/LLM_AND_AGENT_RUNTIME.md)
- [Local And Azure Runbook](docs/runbooks/LOCAL_DEMO_RUNBOOK.md)
- [Kubernetes Helm Runbook](docs/runbooks/KUBERNETES_HELM_RUNBOOK.md)
- [Jenkins Integration Kit](integrations/jenkins-bridge/README.md)
- [Changelog](CHANGELOG.md)

This README intentionally stays short. Detailed architecture diagrams, Jenkins rollout notes, release mechanics, and long demo histories live in the docs above.

## Contributing

Contributions are welcome.

- workflow and quality gates: [CONTRIBUTING.md](CONTRIBUTING.md)
- repo-specific delivery rules: [AGENTS.md](AGENTS.md)

For product changes, update [docs/FUTURE_PLAN.md](docs/FUTURE_PLAN.md) before implementation and include release-note intent in [CHANGELOG.md](CHANGELOG.md).
