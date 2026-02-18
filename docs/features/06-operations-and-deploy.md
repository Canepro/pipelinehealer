# Feature: Operations And Deployment

<!-- LAST_VERIFIED: 4b606f9 -->

This guide explains day-to-day operations: local bring-up, Azure deploy, verification, and safe rollout.

## What This Feature Covers

- local run path
- Azure deploy path
- one-command operations via `scripts/ph.sh`
- post-deploy verification and rollback-safe habits

## Quick Start

1. Configure `backend/.env` from `backend/.env.example`.
2. Local verify:
   - `bash scripts/ph.sh aoai:check`
   - `bash scripts/ph.sh settings:check`
3. Deploy to Azure:
   - full deploy: `bash scripts/ph.sh deploy`
   - env-only changes: `bash scripts/ph.sh deploy:env`
4. Verify:
   - `bash scripts/ph.sh status`
   - `bash scripts/ph.sh settings:check`

## Command Groups

Deploy:
- `deploy`, `deploy:env`, `deploy:bg`, `deploy:logs`, `deploy:status`

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

## Portability and Customization

PipelineHealer is Azure-first for hackathon delivery, but not Azure-locked.

- LLM provider:
  - Azure: `LLM_PROVIDER=azure_openai`
  - OpenAI-compatible: `LLM_PROVIDER=openai_compatible`
- Storage:
  - local/dev fallback: in-memory
  - cloud durability: Cosmos DB when configured
- Auth:
  - `api_key`, `entra`, or `hybrid`

See:

- `../LOCAL_DEMO_RUNBOOK.md` for profile setup
- `../MODEL_PROVIDER_STRATEGY.md` for provider roadmap

## Choosing `deploy` vs `deploy:env`

Use `deploy:env` when only backend runtime env changed:
- auth mode and Entra backend vars
- policy values
- MCP/backend controls

Use full `deploy` when frontend build-time vars changed:
- any `VITE_*` auth/config values

## Safe Rollout Tips

- Prefer `AUTH_MODE=hybrid` before hard cutover to `entra`.
- Keep `HEAL_MODE=safe` in shared environments.
- Keep repo allowlists explicit.
- Record admin changes with `X-Request-Id`.

## Common Mistakes

- Running Azure-only CLI commands while in local mode (`PH_BACKEND_URL` set).
- Expecting frontend changes after `deploy:env` only.
- Running long test commands without timeout wrappers.

## Related Docs

- `../CLI.md` (canonical command/flag reference)
- `../LOCAL_DEMO_RUNBOOK.md` (deep step-by-step)
