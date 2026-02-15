# Agent Instructions (Repo-Specific)

This repository contains **PipelineHealer** — a multi-agent CI/CD self-healing system for the AI Dev Days Hackathon.

This file is intentionally concise. Detailed phase/checklist/history tracking lives in:

- `docs/HACKATHON_LOG.md`

## Primary Docs (Use These)

- `docs/README.md` — docs index
- `docs/API.md` — full API reference (endpoints, auth, data models, best practices)
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
bash scripts/ph.sh urls
bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2
bash scripts/ph.sh webhook:add --repo owner/repo1
bash scripts/ph.sh webhook:disable --repo owner/repo1
bash scripts/ph.sh demo:e2e
bash scripts/ph.sh demo:proof
bash scripts/ph.sh demo:reset
bash scripts/ph.sh warm
bash scripts/ph.sh lowcost
bash scripts/ph.sh status
bash scripts/ph.sh settings:check
bash scripts/ph.sh settings:audit --limit 5
bash scripts/ph.sh audit:proof --limit 5
bash scripts/ph.sh logs
bash scripts/ph.sh logs:raw --tail 200
bash scripts/ph.sh logs:grep --pattern "debug-mode"
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
- When presenting options, always include a clearly labeled recommended option based on current best practices.

## Security and Runtime Defaults

- API routes (`/api/*`) are protected by `X-API-Key` in non-development.
- Admin settings routes (`/api/settings*`) use dual-key auth in non-development: `X-API-Key` + `X-Admin-Key`.
- Recommended demo mode: `HEAL_MODE=safe`.
- Real-repo canary mode: `PH_ALLOWED_REPOS` + `HEAL_MODE=safe` with `AUTO_CREATE_PR=false` for issue-only observation.
- Current demo fixture trigger set: `dependency,lint,test,build_config,timeout`.
- For demo reliability: `bash scripts/ph.sh warm` before recording; `lowcost` afterward.

## Public Repo Hygiene

The repo is public. Treat any committed secret as compromised and rotate immediately.

Before major pushes:

- verify `.env`/keys are not tracked
- sanity-check docs for accuracy vs current runtime
- avoid placeholder commit messages

## Update Policy

When behavior changes, update docs using this checklist:

**Feature PR** (new endpoint, UI control, agent behavior):
1. `docs/API.md` — endpoint/model/field changes
2. `README.md` — features list, env vars, commands
3. `docs/DEMO_SCRIPT.md` — if demo flow is affected
4. `docs/LOCAL_DEMO_RUNBOOK.md` — operator steps

**Config/infra change** (env vars, deploy, security):
1. `README.md` — env vars table, security notes
2. `docs/LOCAL_DEMO_RUNBOOK.md` — deploy/verify steps
3. `docs/PREDEPLOY_PLACEHOLDER_AUDIT.md` — if new placeholders introduced

**Bug fix**:
1. Only update docs if the fix changes documented behavior.

**After any commit**, verify the `<!-- LAST_VERIFIED: ... -->` comment near the top of each changed doc still matches HEAD. Update it if you edited the file.

Internal/transient docs (`docs/HACKATHON_LOG.md`, `docs/FUTURE_PLAN.md`, `docs/GH_AW_IMPLEMENTATION_TRACKER.md`) are updated at author discretion — they are not user-facing.
