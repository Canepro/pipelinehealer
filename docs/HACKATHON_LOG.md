# PipelineHealer Hackathon Log

**Last updated:** February 13, 2026

This is the long-form project tracker for hackathon execution status, submission readiness, and milestone history.

## Current Snapshot

- Repo visibility: **Public** (`https://github.com/Canepro/pipelinehealer`)
- Azure deployment: **Live** on Container Apps (backend + frontend)
- Project positioning: **Azure-first** for hackathon compliance, local mode as evaluation fallback
- Runtime security: `X-API-Key` for `/api/*`; admin settings routes (`/api/settings*`) use `X-API-Key` + `X-Admin-Key` in non-development
- Admin governance visibility: lightweight in-memory audit trail for settings changes (`GET /api/settings/audit`) with request IDs and actor fingerprints
- Demo operations: consolidated to one-command runner `bash scripts/ph.sh ...`
- Real-repo rollout ops: `rollout:canary`, `webhook:add`, `webhook:disable` added for issue-first canary onboarding
- Frontend design system: shadcn-style primitive layer introduced (button/card/input/badge/switch/table/skeleton/toast)
- Settings admin UX: explicit-load audit panel with copyable request IDs and old/new diff rendering
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
| 6 | UI maturity and design-system consolidation | In progress |

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
  - `bash scripts/ph.sh demo:e2e --triggers dependency,lint,test,build_config,timeout --wait-seconds 120`
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
- Added repo allowlist gate (`PH_ALLOWED_REPOS`) so webhook processing can be scoped to selected repos.
- Added one-command canary rollout + webhook management paths in `scripts/ph.sh`.
- Added minimal admin settings audit trail endpoint (`/api/settings/audit`) for change visibility.
- Added request ID middleware (`X-Request-Id`) and salted admin actor fingerprints for traceability.
- Added frontend outcome breakdown metrics (`Auto PR Rate`, `Issue Rate`, `Safety-Blocked`) and activities refresh stabilization.
- Added proposed-fix governance metadata surfacing in UI (`Includes Proposed Fix`, reason code badges).
- Started shadcn-style frontend migration with reusable primitives and page migrations:
  - settings controls and cards
  - dashboard/activity cards and buttons
  - activities table migrated to reusable table primitives
  - skeleton loading states and toast feedback
- Added explicit-load admin audit panel in Settings with request ID copy action.
- Synced frontend/backend contracts for admin settings and audit types (including `ph_allowed_repos` and `AdminSettingsAuditEntry`).
- Established Week 1 UI token baseline (surface tiers, calmer signature blue palette, sidebar de-emphasis, and spacing normalization in app layout).
- Verified Azure live proof with dual-key admin audit commands:
  - `PATCH /api/settings` with `X-Request-Id`
  - `GET /api/settings/audit?limit=...`
  - response contains `request_id`, actor fingerprint, and old/new change values.

## Project Tracking Plan (Now -> Mar 15)

This plan is the source of truth for controlled polish work without drift.

### Week 1: Visual Foundation + Tracking Discipline (Current)

- [x] Create explicit doc-sync baseline after each behavior change (`README` -> `DEMO_SCRIPT` -> `LOCAL_DEMO_RUNBOOK` -> `HACKATHON_LOG`).
- [x] Establish shadcn primitive base (`button`, `card`, `input`, `badge`, `switch`, `table`, `skeleton`, `toast`).
- [x] Migrate Dashboard + Activities + Settings core surfaces to primitive layer.
- [x] Finalize Week 1 design tokens:
  - one signature primary blue
  - semantic status accents (green/amber/red) only where meaning exists
  - calibrated background/card/border contrast tiers
- [x] Add `docs/UI_PLAN.md` with:
  - visual principles
  - token map
  - component usage rules
  - acceptance checklist per page.

### Week 2: Information Hierarchy + Narrative Flow

- [ ] Dashboard narrative layout pass (processed -> actioned -> blocked -> why).
- [ ] Outcome/safety visual prioritization pass with minimal color noise.
- [ ] Table density and typography calibration for scanability.

### Week 3: Admin and Governance UX Refinement

- [ ] Polish Settings and Audit panel micro-interactions (copy confirmations, empty/error states, spacing).
- [ ] Add lightweight judge-mode walkthrough notes tied to UI states.
- [ ] Confirm all governance claims are visible in both docs and UI.

### Week 4: Submission Freeze and Evidence Pack

- [ ] Freeze feature changes; only bugfix/doc updates.
- [ ] Refresh proof artifacts and links in `README`.
- [ ] Final demo rehearsal using `docs/DEMO_SCRIPT.md`.
- [ ] Produce final 2-minute video and submission package.

## Known Risks / Follow-Ups

- Demo video is still open.
- Auto-fix branch collision risk is mitigated by per-run branch naming (`...-run-<workflow_run_id>`); monitor for edge-case Git ref conflicts.
- Dependency remediations currently focus on manifest changes and may not update lockfiles in all package-manager variants.

## File Map for Ongoing Work

- Product overview: `README.md`
- Demo recording (single file): `docs/DEMO_SCRIPT.md`
- Full operator runbook: `docs/LOCAL_DEMO_RUNBOOK.md`
- UI maturity tracker: `docs/UI_PLAN.md`
- Agent/repo operating rules: `AGENTS.md`
