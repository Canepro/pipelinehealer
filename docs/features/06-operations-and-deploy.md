# Feature: Operations And Deployment

<!-- LAST_VERIFIED: c78ae9b -->

This guide explains day-to-day operations: local bring-up, Azure deploy, verification, and safe rollout.

## What This Feature Covers

- local run path
- Azure deploy path
- Kubernetes Helm deploy path (secondary target)
- one-command operations via `scripts/ph.sh`
- post-deploy verification and rollback-safe habits

## Quick Start

1. Configure `backend/.env` from `backend/.env.example`.
2. Local verify:
   - `bash scripts/ph.sh aoai:check`
   - `bash scripts/ph.sh settings:check`
3. Deploy to Azure:
   - recommended release deploy: `bash scripts/ph.sh deploy:release --release-version vX.Y.Z`
   - production hardening: `bash scripts/ph.sh deploy:release --release-version vX.Y.Z --secure-secrets`
   - env-only changes: `bash scripts/ph.sh deploy:env`
4. Verify:
   - `bash scripts/ph.sh status`
   - `bash scripts/ph.sh settings:check`

## Command Groups

Deploy:
- `deploy:release`, `deploy`, `deploy:env`, `deploy:bg`, `deploy:logs`, `deploy:status`

Runtime/admin:
- `settings:check`, `settings:audit`, `settings:persist`, `audit:proof`

Diagnostics:
- `logs`, `logs:raw`, `logs:grep`, `backfill`

Demo:
- `demo:e2e`, `demo:proof`, `demo:reset`, `warm`, `lowcost`

## Command Scope (Important)

- Azure-only infra commands:
  - `deploy*`, `status`, `urls`, `warm`, `lowcost`, `webhook:*`, `rollout:canary`, `demo:e2e`
- Backend API commands (portable; use `PH_BACKEND_URL`):
  - `settings:check`, `settings:audit`, `audit:proof`, `backfill`
- GitHub-only commands:
  - `demo:proof`, `demo:reset`
- Local container commands:
  - `logs*`, `aoai:check` (require local Docker/Podman compose stack)

If you run backend outside Azure (AWS/GCP/DO/Kubernetes), set:

```bash
export PH_BACKEND_URL=https://your-backend.example.com
```

Then use backend API commands from `scripts/ph.sh` for day-to-day operations.

Kubernetes target:
- chart path: `charts/pipelinehealer`
- runbook: `../runbooks/KUBERNETES_HELM_RUNBOOK.md`
- install pattern:
  - `helm upgrade --install pipelinehealer ./charts/pipelinehealer -n pipelinehealer --create-namespace -f values.production.yaml`

## Portability and Customization

PipelineHealer uses Azure as the current reference managed deployment, but it is not Azure-locked.

- LLM provider:
  - Azure: `LLM_PROVIDER=azure_openai`
  - OpenAI-compatible: `LLM_PROVIDER=openai_compatible`
- Storage:
  - local/dev fallback: in-memory
  - durable backends: Cosmos DB (`STORAGE_MODE=cosmos`) or PostgreSQL (`STORAGE_MODE=postgres`)
- Auth:
  - `api_key`, `entra`, or `hybrid`

See:

- `../runbooks/LOCAL_DEMO_RUNBOOK.md` for profile setup
- `../architecture/MODEL_PROVIDER_STRATEGY.md` for provider roadmap

## Choosing `deploy` vs `deploy:env`

Use `deploy:release` for Azure production/staging promotion:
- deploys already-published ACR release images by digest
- no local container build dependency
- best match for release-driven operations
- add `--secure-secrets` to store sensitive runtime values as Container App secrets + `secretref` mappings

Use `deploy:env` when runtime env changed:
- auth mode and Entra backend vars
- frontend runtime vars (`VITE_*`)
- policy values
- MCP/backend controls
- use `deploy:env --secure-secrets` when rotating or hardening secrets

Use full `deploy` for development/hotfix iterations when image contents changed:
- frontend/backend source changes
- dependency or Dockerfile changes

## Safe Rollout Tips

- Prefer `AUTH_MODE=hybrid` before hard cutover to `entra`.
- Keep `HEAL_MODE=safe` in shared environments.
- Keep repo allowlists explicit.
- Record admin changes with `X-Request-Id`.

## Common Mistakes

- Running Azure-only CLI commands while in local mode (`PH_BACKEND_URL` set).
- Expecting code changes after `deploy:env` only.
- Running long test commands without timeout wrappers.

## Related Docs

- `../reference/CLI.md` (canonical command/flag reference)
- `../runbooks/LOCAL_DEMO_RUNBOOK.md` (deep step-by-step)
- `../runbooks/MODEL_PROVIDER_SWITCH_RUNBOOK.md` (provider switch + rollback)
- `../runbooks/KUBERNETES_HELM_RUNBOOK.md` (Helm deployment)
