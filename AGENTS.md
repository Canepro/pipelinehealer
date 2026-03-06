# Agent Instructions (Repo-Specific)

This repository contains **PipelineHealer** — an OSS-first, policy-aware pipeline remediation platform. Current shipped provider paths focus on GitHub Actions plus a Jenkins bridge, and the reference managed deployment is Azure Container Apps.

This file is intentionally concise. Detailed phase/checklist/history tracking lives in:

- `docs/HACKATHON_LOG.md`

## Primary Docs (Use These)

- `docs/README.md` — docs index
- `docs/API.md` — full API reference (endpoints, auth, data models, best practices)
- `docs/CLI.md` — canonical CLI reference (all commands, flags, error handling, env overrides)
- `README.md` — public-facing project overview and setup
- `docs/DEMO_SCRIPT.md` — single-file recording/demo runbook
- `docs/LOCAL_DEMO_RUNBOOK.md` — detailed local/Azure E2E operations
- `docs/HACKATHON_LOG.md` — phased plan, submission checklist, execution history

## One-Command Ops (Recommended)

Full CLI reference: `docs/CLI.md`

Quick examples from repo root:

```bash
bash scripts/ph.sh help
bash scripts/ph.sh deploy
bash scripts/ph.sh status
bash scripts/ph.sh settings:check
bash scripts/ph.sh demo:e2e
bash scripts/ph.sh logs
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
- Keep configuration modeled centrally via `backend/src/config.py`, with deployment-specific injection layers around that model.
- Preserve OSS-first product framing: Azure is a supported reference deployment, not the product boundary.
- Prefer deterministic settings surfaces over hidden deployment-specific toggles. When a capability is intended to be operator-managed, the UI/API/docs should expose it coherently.
- Separate configured policy from effective runtime behavior in operator-facing surfaces.
- Keep agents single-responsibility (log analysis, diagnosis, remediation, orchestration).
- Preserve in-memory fallback (`InMemoryStorage`) for local development.
- Keep backend lint/type/test healthy (`ruff`, `mypy`, `pytest`).
- Keep frontend lint/build healthy (`eslint`, `tsc`/`vite build`).
- Add brief, intent-focused comments for non-obvious logic in code and workflow YAML.
- Keep comments minimal and current; update or remove stale comments during edits.
- When presenting options, always include a clearly labeled recommended option based on current best practices.

## Security and Runtime Defaults

- API routes (`/api/*`) are protected by `X-API-Key` in non-development.
- Admin settings routes (`/api/settings*`) use dual-key auth in non-development: `X-API-Key` + `X-Admin-Key`.
- Recommended demo mode: `HEAL_MODE=safe`.
- Real-repo canary mode: `PH_ALLOWED_REPOS` + `HEAL_MODE=safe` with `AUTO_CREATE_PR=false` for issue-only observation.
- Current demo fixture trigger set: `dependency,lint,test,build_config,timeout,prettier,docker`.
- For demo reliability: `bash scripts/ph.sh warm` before recording; `lowcost` afterward.

## Public Repo Hygiene

The repo is public. Treat any committed secret as compromised and rotate immediately.

Before major pushes:

- verify `.env`/keys are not tracked
- sanity-check docs for accuracy vs current runtime
- avoid placeholder commit messages

## Update Policy

Before major implementation work, ensure the governing docs describe the intended product model clearly enough that code is forced into the right shape. For control-plane/configuration work, update:

1. `README.md` — product framing and deployment posture
2. `CONTRIBUTING.md` — contributor rules and quality bar
3. `docs/README.md` — docs index / where the design contract lives
4. `docs/OPERATOR_CONTROL_PLANE.md` — settings/configuration/provenance contract

Serious product changes should be version-tracked first in `docs/FUTURE_PLAN.md` before implementation proceeds.

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

**After any commit that edits a user-facing doc**, update the `<!-- LAST_VERIFIED: ... -->` marker in that file to the short SHA you are certifying against (typically the latest stable baseline commit you validated for that doc), and keep it current whenever that doc is edited again.

Internal/transient docs (`docs/HACKATHON_LOG.md`, `docs/FUTURE_PLAN.md`, `docs/GH_AW_IMPLEMENTATION_TRACKER.md`) are updated at author discretion — they are not user-facing.
