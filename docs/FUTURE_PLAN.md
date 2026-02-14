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
