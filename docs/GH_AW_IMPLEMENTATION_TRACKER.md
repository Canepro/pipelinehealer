# GitHub Agentic Workflows Implementation Tracker

**Last updated:** February 20, 2026

This tracker is the single source of truth for GitHub Agentic Workflows adoption in PipelineHealer, covering both the original research review and execution status.

## Research Summary

Primary source: [`Meet the Workflows: Fault Investigation`](https://github.github.com/gh-aw/blog/2026-01-13-meet-the-workflows-quality-hygiene/) (Jan 13, 2026)

**Critical rule**: Workflow specs must be created from `gh aw` templates and compiled. Do not hand-write freeform markdown files under `.github/workflows/`.

**Two-layer strategy**:

1. **Layer 1 (Repo hygiene)**: enforce quality in this repository with baseline CI and valid `gh aw` workflows.
2. **Layer 2 (Product capability)**: keep PipelineHealer native-first; ingest `gh aw`/`ci-doctor` findings as optional external diagnostics for monitored repos.

**Runtime clarification**: `gh aw` CLI is an authoring-time dependency (init/add/compile), not a runtime dependency. Monitored repos may or may not have `ci-doctor` installed; missing capability must not block healing.

**Practical leverage patterns**:

- Use CI Doctor outputs as high-signal triage input before remediation planning.
- Use Breaking Change Checker alerts as explicit human sign-off gates.
- Use Schema Consistency Checker to keep `docs/API.md` and runtime behavior aligned.
- Convert repeated findings into deterministic remediation templates and new fixtures.

## Scope

- **Layer 1 (Repo hygiene):** valid `gh aw` setup in this repository.
- **Layer 2 (Product feature):** PipelineHealer remains native-first and ingests `gh aw`/`ci-doctor` findings as optional external diagnostics when available.

## Status Summary

| Workstream | Status | Notes |
|---|---|---|
| Layer 1: baseline repo hygiene | Completed | merged in PR #3 with passing CI checks |
| Layer 2: PipelineHealer orchestration integration | **Complete** | PR A through PR G implemented on `main`; backfill + deep enrichment + UI panel shipped |
| Layer 2 runtime mode evolution (MCP + GH-AW) | **Complete** | `v0.2.9` shipped `GH_AW_INGESTION_MODE=hybrid` with per-finding source selection metadata and passive backfill label-mismatch hardening |

## Layer 1 Checklist (Repo Hygiene)

- [x] Remove non-compilable hand-written workflow markdown files from `.github/workflows/`.
- [x] Keep baseline CI workflow in `.github/workflows/ci.yml`.
- [x] Install `gh aw` CLI extension.
- [x] Run `gh aw init` in repo root.
- [x] Add workflows via wizard:
  - [x] `ci-doctor`
  - [x] `schema-consistency-checker`
  - [x] `breaking-change-checker`
- [x] Configure all 3 workflows to advisory mode (no auto-remediation or auto-merge behavior).
- [x] Run `gh aw compile` and verify generated lock outputs.
- [x] Open separate PR for `gh aw` workflow setup (do not mix with docs-only PRs).
- [x] Merge Layer 1 PR to `main` after CI is green.

## Layer 2 Checklist (PipelineHealer Product Integration)

- [x] Resolve settings/allowlist reliability baseline before Layer 2 wiring:
  - [x] Fix "add repo appears to work but not effective" behavior path.
  - [x] Fix/clarify persistence semantics for allowed-repo settings in UI/ops docs.
  - [x] Add regression tests for `ph_allowed_repos` update + webhook enforcement.
- [x] Add `gh_aw_tools` configuration model (enabled workflows, mode, repo scope).
- [x] Implement universal diagnosis upgrades (history signals, PR-file correlation, richer deterministic patterns).
- [x] Implement backend adapter for capability discovery + optional `gh aw` signal ingestion.
- [x] Ingest `gh aw` outputs (issues/comments/discussions) into diagnosis/remediation signals without blocking native diagnosis/remediation.
- [x] Surface `gh aw` run status and findings in dashboard activity views.
- [x] Add demo flow narrative:
  - failure detected
  - `gh aw` workflow invoked
  - findings consumed (with async backfill for late arrivals)
  - fix recommendation produced
  - external findings panel in Activity Detail UI

## Layer 2 Program Plan (Professional Draft)

### Objectives

1. Integrate GitHub Agentic Workflows as first-class diagnostics signals for PipelineHealer.
2. Preserve PipelineHealer as the remediation control plane (policy, PR/issue actions, auditability).
3. Deliver demo reliability without introducing runtime fragility or hidden operational debt.

### Non-Goals (Initial Layer 2 Scope)

- Replacing existing diagnosis/remediation logic end-to-end.
- Introducing auto-merge/autonomous write behavior from `gh aw` workflows.
- Multi-provider CI support in the same milestone.

### Decision Log (Preflight)

#### D1: Invocation model for `gh aw`

Decision: **API-first** (strong recommendation; aligns with existing backend architecture).

Rationale:

- Backend already uses async API tooling (`httpx`) and retry policies via `GitHubTools`.
- Avoids CLI/subprocess operational dependency in Azure/containers.
- Reduces security and portability concerns from shell execution.

Implementation note:

- `ci-doctor` currently triggers on `workflow_run` failures.
- `gh aw` CLI/extension is an authoring-time dependency (init/add/compile), not a runtime dependency for monitored repos.
- For Layer 2, treat `ci-doctor` as passive high-signal ingestion first, then add explicit dispatch only where workflow semantics support it.

#### D2: Runtime settings durability model

Status: **Resolved**

Decision: Cosmos DB durable persistence with in-memory fallback. Settings are auto-restored on startup. UI uses one-step "Save & Persist" behavior for durable updates.

#### D3: Preflight gating risks

Status: **Resolved**

- ~~Risk A: allowlist additions may appear successful in UI but not be effective.~~ Fixed: settings update path and webhook enforcement tested.
- ~~Risk B: allowlist/runtime settings are not durable across restart/redeploy.~~ Fixed: Cosmos DB durable persistence (see D2).

### Delivery Phases and PR Plan

#### PR 0: Settings Reliability and UX Baseline (Required before PR A)

Scope:

- Finalize D2 settings durability decision.
- Fix current allowlist UX/reliability gaps before Layer 2 is enabled.
- Clarify "Save Settings required" behavior in UI copy/runbooks.
- Add explicit operator note on runtime persistence semantics.
- Add backend/frontend regression coverage for settings update and effective webhook scoping.

Exit criteria:

- Agreed operational semantics for mutable settings.
- No ambiguity in docs/operator UX for allowlist behavior.
- Repro for known bugs is closed with automated test coverage.

#### PR A: Config + Contracts (Recommended first implementation PR)

Scope:

- Add `gh_aw_tools` runtime config shape in backend settings/model layer.
- Define adapter contracts for trigger/status/findings retrieval.
- Add orchestration extension points for external diagnostics input (feature-flagged off).

Acceptance:

- Startup remains backward compatible.
- Feature flag defaults off with no behavior regression.
- Existing tests pass unchanged.

#### PR B: Universal Diagnosis Upgrades (Native Path First)

Scope:

- Extend GitHub API tooling for diagnosis context:
  - issue/history search for related failures.
  - PR changed-files retrieval for run-linked correlation.
  - run/commit context helpers required for deterministic correlation.
- Upgrade Diagnosis/Log analysis to use new signals:
  - correlate failing run with `run_id` / `head_sha` / changed files before LLM fallback.
  - enrich deterministic pattern matching for common CI failure modes.
- Keep behavior policy-safe:
  - no new autonomous write behavior.
  - preserve existing remediation controls and feature flags.

Acceptance:

- Diagnosis quality improves for all monitored repos (including repos without `gh aw`).
- Fewer failures require LLM fallback for known patterns.
- API responses and existing webhook/remediation flows remain backward compatible.

#### PR C: Optional External Diagnostics Ingestion (`ci-doctor` passive MVP)

Scope:

- Add capability discovery for monitored repos:
  - detect whether target repo exposes expected external workflow artifacts/signals.
  - record capability status per repo for operator visibility.
- Implement **passive ingestion MVP** for `ci-doctor` findings:
  - ingest issue/comment/discussion evidence when present.
  - correlate by run metadata (`run_id`, `head_sha`, bounded time window) before text heuristics.
- Add controlled timing strategy for `ci-doctor` lag:
  - bounded polling/backoff window for evidence lookup.
  - explicit fallback reason when external findings are unavailable in-window.
- Keep PipelineHealer native diagnosis/remediation as the primary path regardless of external workflow availability.
- Keep dispatch path out of MVP unless workflow semantics explicitly support `workflow_dispatch`.
- Add structured external evidence fields to activity records.

Acceptance:

- Optional external findings enrich diagnosis without blocking primary path.
- `ci-doctor` timing handling is deterministic (bounded wait + explicit fallback reason).
- Missing external workflow capability on target repo is explicit and non-fatal.
- API responses remain backward compatible.

Future enhancement (post-MVP):

- Add API-first dispatch path for workflows that support explicit trigger semantics.

#### PR D: UI Surface + Hardening and Demo Reliability (Recommended)

Scope:

- Show `gh aw` status/findings in activity detail view (run id, workflow id, summary, links).
- Add settings visibility for enabled workflows/mode.
- Add concise operator troubleshooting for `gh aw` failures.
- Add deterministic fallbacks for missing token/permissions/workflow unavailability.
- Add integration tests for success path + degraded path.
- Finalize demo narrative for "PipelineHealer + gh-aw" loop.

Acceptance:

- Operators can reliably answer: "Was `gh aw` used? What did it find? What action followed?"
- UI type safety and empty-state handling verified.
- Reliable demo under safe-mode defaults.
- Clear logs/reason codes when `gh aw` is unavailable.

### Quality and Validation Standards

#### Backend quality gates

- `pytest -q`
- `mypy src`
- No regressions to existing webhook/remediation flows.

#### Frontend quality gates

- `bun run lint`
- `bun run build`
- Validate activity detail rendering with/without `gh aw` metadata.
- Validate settings UX for allowlist add/remove/save/reload paths.

#### Integration validation

- Trigger controlled failure in demo repo.
- Confirm `gh aw` signal captured and linked to activity.
- Confirm remediation decision remains policy-gated (`HEAL_MODE`, allowlist, PR toggle).
- Confirm allowlist changes become effective for webhook processing under documented runtime model.

#### UX acceptance checks (required)

- Adding an allowed repo has clear state transitions: draft -> saved -> effective.
- After save, the visible allowlist source of truth matches backend response.
- On restart/redeploy, UI clearly communicates whether settings are persisted or runtime-only.
- Error states are actionable (invalid format, unauthorized, backend unavailable, not persisted).

### Definition of Done (Layer 2 MVP)

- Known allowlist UI/behavior bugs are resolved or explicitly accepted with documented constraints.
- Universal diagnosis upgrades are live for all monitored repos.
- Optional `gh aw` ingestion is live behind controlled config.
- External diagnostics are visible in backend activity records and UI.
- Degraded/unavailable external diagnostics path is safe, explicit, and non-blocking.
- Native PipelineHealer diagnosis/remediation remains fully functional when no `gh aw` workflows exist on a monitored repo.
- Docs/runbooks clearly describe operator flow, limits, and troubleshooting.

## Evidence Log

### February 14, 2026

- Confirmed baseline repo CI at `.github/workflows/ci.yml`.
- Removed invalid hand-written workflow markdown files from `.github/workflows/`.
- Installed `gh aw` extension (`github/gh-aw v0.43.23`).
- Updated strategy section in `docs/GH_AW_IMPLEMENTATION_TRACKER.md`.
- Ran `gh aw init --no-mcp`.
- Added and compiled:
  - `.github/workflows/ci-doctor.md`
  - `.github/workflows/schema-consistency-checker.md`
  - `.github/workflows/breaking-change-checker.md`
- Kept `engine: copilot` for CI Doctor and removed unsupported `web-search` tool; compile now reports zero warnings.
- Opened dedicated Layer 1 PR: `https://github.com/Canepro/pipelinehealer/pull/3`.

### February 15, 2026

- Implemented **PR A** on `main`:
  - Added `gh_aw_tools` runtime config surface and validation.
  - Added structured `external_diagnostics` schema.
  - Added no-op `gh-aw` adapter contracts + feature-flagged orchestration hooks.
- Implemented **PR B** on `main`:
  - Added GitHubTools helpers for issue history search, PR-file retrieval, and recent commit context.
  - Added workflow context enrichment in orchestrator (changed files + recent commits).
  - Added deterministic diagnosis improvements:
    - changed-file correlation
    - historical issue signal boosting
    - richer failure patterns (flaky/rate-limit/runner resource context)
  - Added regression tests for diagnosis and GitHubTools helpers.
- Implemented **PR C** on `main`:
  - Replaced no-op adapter path with passive capability discovery against repository workflow artifacts.
  - Added bounded ci-doctor polling/backoff with explicit unavailable/error reason codes.
  - Added run/sha-correlated ci-doctor issue ingestion into `external_diagnostics`.
  - Extended passive polling window to 10 minutes with a final immediate fetch to reduce boundary misses.
  - Added adapter/orchestrator coverage tests for capability, ingestion filtering, and polling behavior.
- Added settings UX persistence guardrails:
  - runtime-only warning banner ("lost on redeploy")
  - One-step "Save & Persist" action for durable persistence without manual shell edits
  - helper command `bash scripts/ph.sh settings:persist ...` to persist all mutable runtime settings and optionally trigger env-only redeploy.
- Implemented **PR D** on `main`:
  - Added full settings controls for healing policy and `gh_aw` runtime settings in admin UI.
  - Added browser-only persistence flow (now one-step `Save & Persist`) to write mutable settings without manual shell edits.
  - Updated scripts/docs alignment for mutable settings persistence behavior.
- Implemented **PR E** on `main`:
  - Added patchable `azure_openai_deployment_name` runtime setting.
  - Added runtime agent refresh so model deployment changes take effect immediately.
  - Added backend/frontend coverage for model switch and settings persistence path.
- Implemented **PR F** on `main`:
  - Added activity detail external diagnostics card with status badges, confidence deltas, and findings links.
  - Added activities list/table external diagnostic badges plus findings actions.
  - Added empty-state messaging when external diagnostics are absent.
- Implemented **PR G** on `main`:
  - Added async backfill sweep (background task every 10 min + manual `POST /api/backfill-diagnostics` endpoint).
  - Added `bash scripts/ph.sh backfill [--max-age-hours N]` CLI command and UI "Backfill Diagnostics" button.
  - Added deep content enrichment: structured `details` extraction from ci-doctor issue bodies (summary, root cause, recommended actions, historical context) with boilerplate sanitization.
  - Added collapsible "External Findings Details" panel in Activity Detail UI with inline markdown rendering, truncation, and auto-expand for available findings.
  - Added storage `get_backfill_candidates` method for both Cosmos DB and in-memory backends.
  - Added 8 backfill unit tests + 7 extraction/sanitization unit tests.
  - E2E validated: `dependency` failure → PipelineHealer PR #91 + Issue #90 → ci-doctor Issue #89 → backfill enrichment → UI panel rendering.
- Closed superseded docs-only PR: `https://github.com/Canepro/pipelinehealer/pull/2`.
- Merged Layer 1 PR #3 to `main` after passing CI checks.
- Updated baseline CI install step to `uv pip install --system -e ".[dev]"` for GitHub Actions compatibility.

### February 16, 2026

- Implemented **PR G** (async backfill + deep enrichment):
  - Background sweep task polls every 10 min for `poll_window_exhausted` activities and enriches with late-arriving ci-doctor findings.
  - Manual trigger via `POST /api/backfill-diagnostics` endpoint, `bash scripts/ph.sh backfill` CLI, and UI button.
  - Deep content enrichment parses ci-doctor issue bodies into structured `details` (summary, root cause, recommended actions, historical context, doctor engine/model metadata).
  - Boilerplate sanitization strips HTML comments, AI-generated footers, gh-aw setup hints, expiry markers, and temp-file paths before persistence.
  - Collapsible "External Findings Details" panel in Activity Detail UI with markdown rendering, section truncation, and auto-expand.
- E2E validated full loop: `dependency` failure → PR #91 + Issue #90 → ci-doctor Issue #89 → backfill → enriched UI panel.
- Updated all documentation: `README.md`, `API.md`, `CLI.md`, `DEMO_SCRIPT.md`, `LOCAL_DEMO_RUNBOOK.md`, `HACKATHON_LOG.md`.
- Marked Layer 2 status as **Complete** (PR A through PR G all on `main`).
- Resolved D2 (settings durability: Cosmos DB) and D3 (preflight gating risks: fixed and tested).

## Execution Commands (Layer 1)

```bash
gh extension install github/gh-aw
gh aw init
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/ci-doctor.md
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/schema-consistency-checker.md
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/breaking-change-checker.md
gh aw compile
```
