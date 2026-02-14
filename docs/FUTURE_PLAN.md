# Future Plan (PipelineHealer)

This document tracks post-demo improvements beyond the current stable baseline.

## Baseline Already Completed

The following are already implemented in the current project state:

- API and admin auth (`X-API-Key` for `/api/*`; `/api/settings*` uses `X-API-Key` + `X-Admin-Key` outside development)
- GitHub API retry/backoff and orchestrator step timeouts
- Timed-out workflow log handling and prompt truncation safeguards
- Safe/demo/debug healing mode split (debug adds verbose pipeline logging without behavior change)
- Script-first operator workflow (`bash scripts/ph.sh ...`)
- One-command log inspection (`logs`, `logs:raw`, `logs:grep`)
- Docker base image failure pattern matching in diagnosis agent
- Cosmos SDK log noise suppression for clean Azure Container Apps logs
- API reference documentation (`docs/API.md`)
- Chart dark-theme legibility (axis ticks, pie labels)

## Next Priorities

## 0) Layer 2 Foundations (GitHub Agentic Workflows + UX Reliability)

- Implement Layer 2 via API-first integration for external diagnostics signals (no production subprocess dependency).
- Keep PipelineHealer as native-first remediation control plane; use `gh aw` as optional supplemental diagnostics.
- Sequence delivery explicitly:
  - **PR 0**: settings reliability + allowlist UX fixes
  - **PR A**: config/contracts
  - **PR B**: universal diagnosis upgrades (history + PR-file correlation + richer patterns)
  - **PR C**: passive ingestion MVP (optional external diagnostics, no mandatory dispatch)
  - **PR D**: UI/operator surface + hardening + demo reliability
- Resolve settings/allowlist reliability before enabling Layer 2 for demo-critical paths.
- Add explicit UX semantics for runtime settings:
  - draft vs saved state
  - effective scope confirmation
  - persistence behavior across restart/redeploy
- Prioritize universal diagnosis gains before optional external integrations:
  - improve native diagnosis quality for every monitored repo
  - keep external diagnostics strictly additive
- Handle `ci-doctor` timing and repo capability gaps in MVP:
  - bounded wait/poll before fallback to native diagnosis
  - explicit "workflow not installed/capability unavailable" handling with non-blocking native fallback
- Add regression tests for:
  - settings update path (`PATCH /api/settings`)
  - webhook allowlist enforcement (`PH_ALLOWED_REPOS`)
  - frontend add/remove/save/reload allowlist flow

Acceptance target:

- No known reproductions for "repo add looks saved but not effective" and "list does not persist without clear UI messaging."
- Operators can reliably determine whether a setting is draft-only, runtime-active, or durable.

## 1) Higher-Confidence Auto-Remediation

- Add lockfile-aware dependency fixes (`package-lock.json`, `pnpm-lock.yaml`, `bun.lockb` where applicable).
- Expand deterministic lint fix coverage beyond missing ESLint flat config.
- Add safer fallback behavior: if patch rendering fails, auto-open issue with explicit patch failure reason.

## 2) Patch Engine Improvements

- Add structured workflow/YAML patch operations (beyond regex line updates).
- Add insert operations (`insert_after`, `insert_under_key`) with validation.
- Produce patch-application diagnostics in remediation output for easier debugging.

## 3) GitHub App First-Class Path

- Complete GitHub App authentication path for production use.
- Keep PAT path as local/dev fallback.
- Add clear runtime indicator and docs for active auth mode.

## 4) Settings and Policy Controls

- Add optional persistence for runtime setting overrides (currently in-memory; resets on restart).
- ~~Add repo/org allowlist controls for remediation scope.~~ (Done: `PH_ALLOWED_REPOS`)
- ~~Add configurable governance limits (max remediations per repo/time window).~~ (Done: `max_remediation_attempts`)
- Add lightweight admin session auth for settings operations (post-submission):
  - Replace direct admin-key-only UX with short-lived, password-backed admin sessions.
  - Keep `X-Admin-Key` as emergency fallback via feature flag.
- Add settings state UX hardening:
  - persistent "unsaved changes" indicator
  - post-save "effective policy" confirmation panel
  - explicit runtime-vs-durable status label on mutable settings

## 5) CI Platform Extensibility

- Introduce adapter interface implementation for non-GitHub CI providers.
- Keep webhook handlers thin and source-specific (`/webhook/github`, future `/webhook/gitlab`, `/webhook/jenkins`).
- Preserve deterministic remediation boundaries across providers.

## 6) Observability and Reporting

- ~~Add dashboard views for remediation trend lines and outcome ratios over time.~~ (Done: bar chart + pie chart + stats cards)
- Add exportable run summary for demos and incident review.
- ~~Add structured audit trail fields for policy decisions (why PR vs issue).~~ (Done: reason codes + explainability snapshot in UI)
- Move admin settings audit trail from in-memory runtime storage to durable storage (Cosmos DB or Log Analytics).
- Add log retention and search improvements beyond `logs:grep`.
- Add Layer 2 diagnostics observability:
  - external-tool invocation success/failure counters
  - latency metrics for dispatch -> findings ingestion
  - fallback reason-code distribution for unavailable optional external diagnostics paths

## Documentation Improvement Plan (Professional Standard)

- Keep architecture and execution docs synchronized with code in each Layer 2 PR:
  - `docs/GH_AW_IMPLEMENTATION_TRACKER.md` (status and checklists)
  - `docs/GH_AW_WORKFLOWS_QUALITY_HYGIENE_REVIEW.md` (strategy and decisions)
  - `docs/API.md` (new endpoints/fields/contracts)
  - `docs/DEMO_SCRIPT.md` + `docs/LOCAL_DEMO_RUNBOOK.md` (operator flow and troubleshooting)
- Add a release-quality "What changed / Why / Rollback" section to major doc updates.
- Require every new runtime setting to document:
  - default value
  - persistence model
  - failure mode and fallback behavior
- Require Layer 2 docs to preserve the contract:
  - PipelineHealer native diagnosis/remediation is always primary
  - `gh aw`/`ci-doctor` integration is additive and never a hard dependency
- Add known-issues section with explicit reproduction and mitigation for active bugs until closed.

## 7) Demo Experience Hardening

- Add a `demo:prep` command to combine `warm`, `settings:check`, and baseline validation.
- Add a `demo:cleanup` command to merge/close demo artifacts and return to low-cost mode.
- ~~Add optional "recording-safe" mode that suppresses noisy logs during video capture.~~ (Done: Cosmos SDK noise suppression + `logs` command with built-in noise filtering)
- Expand demo-repo workflow fixtures with additional deterministic trigger types (`prettier`, `permissions`, `docker`) once the fixture workflow and backend routing are re-aligned.

## Guiding Principles

- Keep deterministic fixes default-first.
- Keep risky or speculative edits out of auto-PR paths.
- Keep operator workflow one-command where possible.
- Keep docs synchronized with runtime behavior.
