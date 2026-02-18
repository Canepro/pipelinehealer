# Feature: Operations And Deployment

<!-- LAST_VERIFIED: a95ed82 -->

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
