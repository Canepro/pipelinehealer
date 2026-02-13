# Agent Instructions (Repo-Specific)

This repository contains **PipelineHealer** — a multi-agent CI/CD self-healing system for the AI Dev Days Hackathon.

This file is intentionally concise. Detailed phase/checklist/history tracking lives in:

- `docs/HACKATHON_LOG.md`

## Primary Docs (Use These)

- `docs/README.md` — docs index
- `README.md` — public-facing project overview and setup
- `docs/DEMO_SCRIPT.md` — single-file recording/demo runbook
- `docs/LOCAL_DEMO_RUNBOOK.md` — detailed local/Azure E2E operations
- `docs/HACKATHON_LOG.md` — phased plan, submission checklist, execution history

## One-Command Ops (Recommended)

From repo root:

```bash
bash scripts/ph.sh help
bash scripts/ph.sh deploy
bash scripts/ph.sh deploy:env
bash scripts/ph.sh demo:e2e
bash scripts/ph.sh demo:reset
bash scripts/ph.sh warm
bash scripts/ph.sh lowcost
bash scripts/ph.sh status
bash scripts/ph.sh settings:check
```

Important:

- Execute scripts with `bash scripts/...`
- Do **not** use `source` or `. scripts/...`

## Dev Commands

Backend:

```bash
cd backend
uv pip install -e ".[dev]"
pytest -q
mypy src
```

Frontend:

```bash
cd frontend
bun install
bun run lint
bun run build
```

## Engineering Guardrails

- Do not commit secrets; use `.env` locally and Key Vault/GitHub Secrets in cloud paths.
- Keep configuration env-driven via `backend/src/config.py`.
- Keep agents single-responsibility (log analysis, diagnosis, remediation, orchestration).
- Preserve in-memory fallback (`InMemoryStorage`) for local development.
- Keep backend lint/type/test healthy (`ruff`, `mypy`, `pytest`).
- Keep frontend lint/build healthy (`eslint`, `tsc`/`vite build`).

## Security and Runtime Defaults

- API routes (`/api/*`) are protected by `X-API-Key` in non-development.
- Admin settings routes (`/api/settings`) require `X-Admin-Key`.
- Recommended demo mode: `HEAL_MODE=safe`.
- Current demo fixture trigger set: `dependency,lint,test,build_config,timeout`.
- For demo reliability: `bash scripts/ph.sh warm` before recording; `lowcost` afterward.

## Public Repo Hygiene

The repo is public. Treat any committed secret as compromised and rotate immediately.

Before major pushes:

- verify `.env`/keys are not tracked
- sanity-check docs for accuracy vs current runtime
- avoid placeholder commit messages

## Update Policy

When behavior changes, update docs in this order:

1. `README.md` (user-facing behavior)
2. `docs/DEMO_SCRIPT.md` (recording/demo steps)
3. `docs/LOCAL_DEMO_RUNBOOK.md` (operator detail)
4. `docs/HACKATHON_LOG.md` (status, checklist, execution history)
