# PipelineHealer Hackathon Log

**Last updated:** February 13, 2026

This is the long-form project tracker for hackathon execution status, submission readiness, and milestone history.

## Current Snapshot

- Repo visibility: **Public** (`https://github.com/Canepro/pipelinehealer`)
- Azure deployment: **Live** on Container Apps (backend + frontend)
- Project positioning: **Azure-first** for hackathon compliance, local mode as evaluation fallback
- Runtime security: `X-API-Key` for `/api/*`, `X-Admin-Key` for `/api/settings`
- Demo operations: consolidated to one-command runner `bash scripts/ph.sh ...`
- Recording script: single-source runbook in `docs/DEMO_SCRIPT.md`
- Repo policy docs: `CONTRIBUTING.md` and `SECURITY.md` added

## Phase Overview

| Phase | Goal | Status |
|------:|------|--------|
| 0 | Hygiene baseline (lint/typecheck/tests) | Completed |
| 1 | Correctness (activity IDs, PR fixes, retry behavior) | Completed |
| 1.5 | Safe/demo mode behavior | Completed |
| 2 | Security hardening | Completed |
| 3 | Reliability (timeouts/retries/log handling) | Completed |
| 4 | Azure deployment alignment | Completed |
| 5 | Demo + submission polish | In progress |

## Submission Checklist

- [x] Working project deployed to Azure (`azd up` equivalent infra + app deployment validated)
- [x] Public GitHub repository
- [x] Project description (features/problem/technologies) in `README.md`
- [ ] Demo video (2 min max)
- [x] Architecture diagram (Mermaid in `README.md`)
- [x] Microsoft Learn username(s) for participant(s):
  - `https://learn.microsoft.com/en-us/users/canepro0084/`

## Current Working Defaults

- Recommended healing mode: `HEAL_MODE=safe`
- Demo trigger command:
  - `bash scripts/ph.sh demo:e2e --triggers dependency,lint,prettier,permissions,test,build_config,timeout --wait-seconds 40`
- Demo scale toggle:
  - pre-demo: `bash scripts/ph.sh warm`
  - post-demo: `bash scripts/ph.sh lowcost`

## Key Decisions

- Retry behavior: rerun failed GitHub jobs from dashboard, then process follow-up webhook event.
- Auth model: API key for user routes and admin key for runtime settings routes.
- Hosting target: Azure Container Apps only (for demo reliability and operational simplicity).
- Submission framing: Azure-hosted runtime is primary; local mode is retained for reproducible evaluation and fallback troubleshooting.
- Operator UX: prefer script-first workflows (`scripts/ph.sh`) over manual multi-command runbooks.

## Milestone Log

### Feb 10, 2026

- Created phased execution plan and baseline checklists.
- Fixed backend lint issues and wired observability startup.
- Fixed activity ID persistence mismatch across workflow/orchestrator.
- Implemented retry endpoint behavior using GitHub rerun-failed-jobs.
- Implemented deterministic file patch rendering for dependency/lint PR creation.
- Added core correctness tests.
- Added packaging fixes for backend editable install.
- Validated local E2E flow with webhook forwarding and dashboard activity rendering.

### Feb 11, 2026

- Added `HEAL_MODE` (`safe` and `demo`) and demo-mode behavior wiring.
- Expanded reliability layer: retry/backoff for GitHub API, step timeouts, timed-out log handling, prompt truncation strategy.
- Implemented API auth for `/api/*`, webhook verification policy controls, and improved CORS handling.
- Added runtime settings foundation (`GET /api/settings`, later extended to admin write path).
- Stabilized frontend toolchain (`eslint` flat config + Vite typing support).
- Added `docs/PREDEPLOY_PLACEHOLDER_AUDIT.md` and deployment alignment updates.
- Removed stale Azure Functions mapping and aligned infra to Container Apps.

### Feb 12, 2026

- Provisioned and validated Azure dev stack in `rg-canepro-ph-dev-eus`.
- Stabilized frontend-to-backend proxy behavior in Azure (host/SNI/key forwarding fixes).
- Added production runtime env hardening and validated protected settings endpoint.
- Fixed dashboard stats/failure endpoints by removing unsupported async Cosmos query kwargs and stabilizing aggregation path.
- Added admin settings controls and frontend settings UX polish.
- Added deploy/demo script automation and unified one-command runner `scripts/ph.sh`.
- Fixed script behavior for terminal sourcing pitfalls and WSL/Podman env-file path normalization.
- Validated one-command deploy and one-command E2E demo flows.
- Revalidated end-to-end outcomes: dependency/lint remediation PR path + issue path for non-auto-fixable failures.
- Published project docs updates and synchronized portfolio blog progress.
- Consolidated recording workflow into `docs/DEMO_SCRIPT.md`.
- Slimmed `AGENTS.md` into a concise operator/agent contract and moved long-form tracking here.
- Added `docs/README.md` as a docs index and aligned README/runbook wording with current runtime behavior.

### Feb 13, 2026

- Updated docs framing to explicitly Azure-first (hackathon compliance) with local fallback for evaluator convenience.
- Expanded README with deterministic fix matrix and explicit safety model.
- Added `CONTRIBUTING.md` and `SECURITY.md` and linked them from `docs/README.md`.

## Known Risks / Follow-Ups

- Demo video is still open.
- Auto-fix branch collisions can still produce GitHub `422` in repeated reruns if prior fix branches already exist.
- Dependency remediations currently focus on manifest changes and may not update lockfiles in all package-manager variants.

## File Map for Ongoing Work

- Product overview: `README.md`
- Demo recording (single file): `docs/DEMO_SCRIPT.md`
- Full operator runbook: `docs/LOCAL_DEMO_RUNBOOK.md`
- Agent/repo operating rules: `AGENTS.md`
