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
- Chart dark-theme legibility (axis ticks, pie labels, tooltip text)
- Stale activity recovery on startup (transient-state sweep marks interrupted activities as failed)
- Capability-aware remediation (graceful `SKIP` when target repo has issues/PRs disabled or is read-only)
- Smart external diagnostics polling (skips ci-doctor polling for failures in known gh-aw workflows)
- Retry endpoint no longer resets original activity state (triggers GitHub re-run only; new webhook creates fresh record)
- MCP safety guardrails:
  - default-safe posture (`mcp_enabled=false`, `mcp_read_only=true`)
  - repo/tool allowlist enforcement and timeout/retry budgets
  - per-tool policy model (`disabled|read_only|write_with_approval|auto`)
  - per-activity MCP action audit (`actor`, `tool`, `payload_hash`, `result`, `request_id`)
- Dedicated feature documentation set under `docs/features/` for beginner/operator/expert workflows
- Ambiguous failure-type trust hardening:
  - generic `N failing` signatures now require test context before mapping to `test`
  - pattern-based diagnoses now persist classification transparency metadata (`classification_signal`, `classification_family`, `classification_pattern`)

## Current Roadmap Status (Feb 18, 2026)

| Track | Status | Notes |
|---|---|---|
| 0.1 MCP Foundation | Completed | Guardrails, health endpoints, per-tool policy, audit fields, runbook context path |
| 0.3 Admin UX | Mostly completed | Control Center + audit consolidation shipped; replay/simulation controls still pending |
| 0.4 Model Portability | Completed (core) | Provider abstraction, fallback/retry tests, parity tests, switch runbook, Helm target |
| 0.2 Learning System | In progress | Queue + governance + activation gates shipped; retrieval + editable candidates pending |

## Immediate Next (Active Execution Track)

1. **Learning retrieval context (0.2)**  
Add retrieval-before-diagnosis/remediation so active candidates can provide structured context.
2. **Learning candidate editing (0.2)**  
Add safe operator edits for candidate fields with full audit metadata.
3. **Control Center learning UX finish (0.3)**  
Add clearer edit/review flow and simulation-style preview for promoted playbooks.
4. **Docs and runbook sync**  
Keep README/API/feature docs aligned on the same commit.

## Execution Rules (Locked)

- Only one active implementation track at a time.
- New requests are queued in backlog unless they are:
  - production break/fix
  - security risk
  - data-loss risk
  - explicit user-prioritized blocker
- Definition of done for behavior changes:
  - feature/tests/docs updated together
  - runtime verification command documented
  - rollback path documented

## Engineering Clarity Standards (Always-On)

- Add brief, professional comments for non-obvious logic in code and workflow YAML.
- Prefer intent-focused comments ("why this exists"), not line-by-line narration.
- Keep comments minimal and current; remove stale comments during edits.
- When adding a new feature flag/policy, include:
  - one inline comment at decision boundary
  - one docs entry describing default, effect, and safety fallback

## 0) Platform Extension Track (MCP + Learning + Admin UX)

### 0.1 MCP Foundation (Completed)

- Provider abstraction scaffold implemented.
- Policy controls implemented (`enabled`, `provider`, `read_only`, timeout/retry, per-tool policy, repo allowlist).
- Provider health endpoint implemented (`GET /api/settings/mcp/provider-health`).
- Read-only enrichment paths implemented (`fetch_failure_context`, `fetch_runbook_context`).
- MCP action audit and explainability metadata implemented.

### 0.2 Learning System (In Progress)

Completed:
- durable learning queue storage + model
- Control Center queue with decision actions
- audited learning queue refresh/decision trail
- promotion-readiness gating + audited forced activation

Remaining:
- retrieval layer before diagnosis/remediation (active candidates as context)
- safe operator edit API/UI for candidate fields
- promoted playbook simulation/preview surface

### 0.3 Admin UX (Mostly Completed)

Completed:
- read-only Control Center governance route
- runtime/auth/provider posture cards
- MCP policy effect matrix
- logs/investigation quick-actions
- centralized audit timeline with JSON diffs
- badge density and readability hardening

Remaining:
- remediation replay/simulation controls
- deeper IA polish for large datasets

### 0.4 Model Platform Portability (Completed Core)

Completed:
- pluggable provider model (`azure_openai`, `openai_compatible`, `custom`)
- task-level routing and runtime config
- fallback/outage contract tests and parity regression tests
- switching/rollback runbook
- Kubernetes Helm deployment target

Remaining:
- token/cost telemetry per activity
- degradation alerting thresholds (fallback spikes, provider timeout/error spikes)

### Backlog Intake Queue (Non-Active)

Use this section to capture new requests without breaking the execution lock.

| ID | Item | Impact | Risk | Estimate | Recommended phase | Status |
|---|---|---|---|---|---|---|
| BI-001 | Release/tag workflow and release notes template | Operator confidence and repeatable deploys | Medium | M | Post 0.4 | Completed |
| BI-002 | Additional activity classification context labels for ambiguous CI failures | Better failure-type trust for operators | Low | S | 0.3 | Completed |
| BI-003 | In-app live log tail/search UX (backend-safe streaming + RBAC) | Faster investigations without switching to CLI | Medium | M | Post 0.4 | Queued |

## ~~0) Layer 2 Foundations (GitHub Agentic Workflows + UX Reliability)~~ — COMPLETE

All Layer 2 delivery phases (PR 0 through PR G) are implemented and deployed:

- ~~Implement Layer 2 via API-first integration for external diagnostics signals (no production subprocess dependency).~~ (Done)
- ~~Keep PipelineHealer as native-first remediation control plane; use `gh aw` as optional supplemental diagnostics.~~ (Done)
- ~~Sequence delivery explicitly (PR 0 → PR A → PR B → PR C → PR D → PR E → PR F → PR G).~~ (Done: all merged to `main`)
- ~~Resolve settings/allowlist reliability before enabling Layer 2 for demo-critical paths.~~ (Done)
- ~~Add explicit UX semantics for runtime settings (draft vs saved, effective scope, persistence behavior).~~ (Done: Cosmos DB durable persistence with in-memory fallback and one-step "Save & Persist" UX)
- ~~Prioritize universal diagnosis gains before optional external integrations.~~ (Done: PR B universal diagnosis upgrades)
- ~~Handle `ci-doctor` timing and repo capability gaps in MVP:~~ (Done)
  - ~~bounded wait/poll before fallback to native diagnosis~~ (Done: 480s polling window)
  - ~~explicit "workflow not installed/capability unavailable" handling with non-blocking native fallback~~ (Done: reason codes)
  - ~~async backfill pass for `poll_window_exhausted` activities so late-arriving ci-doctor findings can enrich existing records~~ (Done: background sweep every 10 min + manual `POST /api/backfill-diagnostics` + CLI `bash scripts/ph.sh backfill` + UI button)
- ~~Deep content enrichment for external diagnostics~~ (Done: structured `details` extraction from ci-doctor issue bodies — summary, root cause, recommended actions, historical context — with boilerplate sanitization)
- ~~External Findings panel in Activity Detail UI~~ (Done: collapsible panel with inline markdown rendering, truncation, auto-expand for available findings)
- ~~Add regression tests for settings update path, webhook allowlist enforcement, and frontend allowlist flow.~~ (Done)

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

- ~~Add optional persistence for runtime setting overrides (currently in-memory; resets on restart).~~ (Done: Cosmos DB durable persistence with in-memory fallback; auto-restored on startup)
- ~~Add repo/org allowlist controls for remediation scope.~~ (Done: `PH_ALLOWED_REPOS`)
- ~~Add configurable governance limits (max remediations per workflow/time window).~~ (Done: `max_remediation_attempts`, scoped per-workflow within each repository)
- Add lightweight admin session auth for settings operations (post-submission):
  - Replace direct admin-key-only UX with short-lived, password-backed admin sessions.
  - Keep `X-Admin-Key` as emergency fallback via feature flag.
- Add settings state UX hardening:
  - ~~persistent "unsaved changes" indicator~~ (Done: draft vs saved state tracking)
  - post-save "effective policy" confirmation panel
  - ~~explicit runtime-vs-durable status label on mutable settings~~ (Done: one-step "Save & Persist" with durable storage feedback)

## 5) CI Platform Extensibility

- Introduce adapter interface implementation for non-GitHub CI providers.
- Keep webhook handlers thin and source-specific (`/webhook/github`, future `/webhook/gitlab`, `/webhook/jenkins`).
- Preserve deterministic remediation boundaries across providers.

### 5.1 Multi-provider Readiness via MCP

- Route provider-specific calls through adapter/MCP boundaries.
- Keep orchestrator contracts provider-agnostic (`fetch_failure_context`, `publish_artifact`, `rerun_pipeline`).
- Add compatibility matrix in docs for supported provider capabilities.

## 6) Observability and Reporting

- ~~Add dashboard views for remediation trend lines and outcome ratios over time.~~ (Done: bar chart + pie chart + stats cards)
- Add exportable run summary for demos and incident review.
- ~~Add structured audit trail fields for policy decisions (why PR vs issue).~~ (Done: reason codes + explainability snapshot in UI)
- ~~Move admin settings audit trail from in-memory runtime storage to durable storage (Cosmos DB or Log Analytics).~~ (Done: Cosmos DB with in-memory fallback)
- Add log retention and search improvements beyond `logs:grep`.
- ~~Add Layer 2 diagnostics observability (basic):~~ (Partial — reason-code tracking, status badges, and findings links are live in UI)
  - Add external-tool invocation success/failure counters (not yet — requires metrics backend)
  - Add latency metrics for dispatch -> findings ingestion (not yet)
  - ~~Fallback reason-code distribution for unavailable optional external diagnostics paths~~ (Done: reason codes stored and visible in activity records)

### 6.1 Multi-model Observability

- ~~Track model path per activity:~~ (Done: baseline telemetry)
  - ~~provider, model/deployment, fallback-used flag, latency~~
  - token/cost estimate (pending)
- ~~Add UI explainability fields:~~ (Done)
  - ~~"Model Path" summary in activity details and dashboard drilldown~~
- Alert on degradation:
  - sustained fallback rate increase
  - timeout/error spikes by provider

## Documentation Improvement Plan (Professional Standard)

- ~~Keep architecture and execution docs synchronized with code in each Layer 2 PR.~~ (Done: `API.md`, `DEMO_SCRIPT.md`, `LOCAL_DEMO_RUNBOOK.md`, `CLI.md`, `README.md`, `HACKATHON_LOG.md` all updated through PR G)
- ~~Add dedicated CLI reference.~~ (Done: `docs/CLI.md`)
- ~~Make demo script presentation-ready (no placeholders, concrete commands).~~ (Done: `docs/DEMO_SCRIPT.md`)
- Add a release-quality "What changed / Why / Rollback" section to major doc updates.
- Require every new runtime setting to document:
  - default value
  - persistence model
  - failure mode and fallback behavior
- ~~Require Layer 2 docs to preserve the contract (native-first, gh-aw additive).~~ (Done: contract enforced throughout implementation)
- Add known-issues section with explicit reproduction and mitigation for active bugs until closed.

### MCP + Learning Docs Additions

- Add `docs/MCP_INTEGRATION_PLAN.md`:
  - provider onboarding checklist
  - auth model
  - timeout/retry and blast-radius policy
- ~~Add `docs/LEARNING_SYSTEM_PLAN.md`:~~ (Done)
  - ~~learning lifecycle (observe -> candidate -> approve -> active -> retire)~~
  - ~~safety and governance rules~~
  - ~~rollback path for promoted playbooks~~
- ~~Add architecture update in `README.md` and `docs/API.md` once contracts are implemented.~~ (Done)

### Model Portability Docs Additions

- ~~Add `docs/MODEL_PROVIDER_STRATEGY.md`:~~ (Done)
  - ~~provider adapter contract~~
  - ~~routing and fallback policy~~
  - ~~migration plan from Azure-only to multi-provider~~
  - ~~cost/latency tradeoff guidance~~

## 7) Demo Experience Hardening

- Add a `demo:prep` command to combine `warm`, `settings:check`, and baseline validation.
- Add a `demo:cleanup` command to merge/close demo artifacts and return to low-cost mode.
- ~~Add optional "recording-safe" mode that suppresses noisy logs during video capture.~~ (Done: Cosmos SDK noise suppression + `logs` command with built-in noise filtering)
- ~~Expand demo-repo workflow fixtures with additional deterministic trigger types.~~ (Done: demo repo now has 7 failure types — `dependency`, `lint`, `test`, `build_config`, `timeout`, `prettier`, `docker` — with single-type and custom-subset CLI triggers)

## Guiding Principles

- Keep deterministic fixes default-first.
- Keep risky or speculative edits out of auto-PR paths.
- Keep operator workflow one-command where possible.
- Keep docs synchronized with runtime behavior.
