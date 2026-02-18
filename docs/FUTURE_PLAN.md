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

## Next Priorities

## 0) Platform Extension Track (MCP + Learning + Admin UX)

### 0.1 MCP Foundation (Recommended first)

- ~~Add an MCP provider abstraction in backend tools layer:~~ (Done: foundation scaffold)
  - ~~`MCPToolProvider` interface (connect, list tools, invoke, health check)~~
  - ~~provider registry and per-provider feature flags~~
- ~~Add policy controls for MCP in admin settings:~~ (Done: initial controls)
  - ~~provider enabled/disabled~~
  - ~~read vs write mode~~ (read-only toggle)
  - timeout/retry budget per provider
- ~~Add MCP provider health endpoint for operator visibility.~~ (Done: `GET /api/settings/mcp/provider-health`)
- Start with read-only MCP actions before write actions:
  - ~~diagnostics/context retrieval~~ (Done: GitHub MCP read-only run-context evidence path, decoupled from gh-aw toggles)
  - ~~incident metadata lookup~~ (Done: failing job/timed-out counts + related PR metadata + optional changed-file correlation in `github-mcp` evidence)
  - knowledge/runbook retrieval
- Add full audit attributes for MCP calls:
  - provider, tool name, latency, success/failure, error class, request ID
  - (In progress) per-activity MCP explainability now captures tool usage, source attribution, and confidence rationale

Initial MCP providers to prioritize:

- GitHub MCP (context enrichment and artifact lookup)
- Azure Monitor/Application Insights MCP (trace/log diagnostics correlation)
- Ticketing MCP (Jira/ServiceNow/Linear) for enterprise escalation path
- Knowledge MCP (Confluence/internal docs) for remediation context

### 0.2 Learning System (Policy-safe, human-in-the-loop)

- Add a durable "remediation memory" store:
  - incident fingerprint
  - diagnosis + action taken
  - outcome (success/failure/rollback)
  - human feedback signal
- Add a retrieval layer before diagnosis/remediation:
  - fetch similar historical incidents and inject evidence into agent context
- Add controlled "playbook promotion":
  - promote repeated successful patterns to deterministic remediation templates
  - require thresholds (for example N successful outcomes) before promotion
- Add explicit approval mode:
  - operator approves/rejects learned playbooks
  - rejected candidates recorded with reason for model feedback
- Preserve trust controls:
  - no autonomous policy mutation without human approval
  - all learned behavior remains explainable and auditable

### 0.3 Admin UX: Settings + Control Center

- Keep **Settings** focused on static/runtime configuration.
- Add a new **Control Center** page for operational governance:
  - MCP provider health and permissions
  - learning queue (candidates, approvals, rejects)
  - remediation replay/simulation controls
  - policy impact preview (what would happen under current settings)
- Improve professional IA and visual hierarchy:
  - grouped sections: Access, Policy, Integrations, Learning, Persistence
  - sticky change summary panel with unsaved + effective values
  - environment scope chips (`runtime`, `persisted`, `redeploy pending`)
  - explicit "safe defaults" and risk labels for advanced toggles

### 0.4 Model Platform Portability (Azure-first, not Azure-locked)

Keep Azure OpenAI as the default path now, but design for pluggable model providers early.

- Add provider abstraction:
  - `LLMProvider` interface (`analyze`, `diagnose`, `remediate`, `health_check`)
  - concrete adapters: `azure_openai` (current), `openai_compatible`, `custom_gateway`
- Separate provider selection from model routing:
  - task-level model choices (`analysis`, `diagnosis`, `remediation`)
  - fallback chains per task (primary -> cheaper fallback -> deterministic fallback)
- Add runtime config surface:
  - `LLM_PROVIDER=azure_openai|openai_compatible|custom`
  - provider-specific env groups (endpoint/base_url, auth key, api version/model/deployment)
  - optional task overrides for model names
- Keep prompts portable:
  - normalize provider responses into one internal schema
  - keep provider translation logic inside adapters only
- Add portability quality gates:
  - provider contract tests (same prompts, consistent structured output)
  - outage/fallback tests (timeouts, 429, 5xx)
  - regression checks for diagnosis/remediation behavior parity

## ~~0) Layer 2 Foundations (GitHub Agentic Workflows + UX Reliability)~~ — COMPLETE

All Layer 2 delivery phases (PR 0 through PR G) are implemented and deployed:

- ~~Implement Layer 2 via API-first integration for external diagnostics signals (no production subprocess dependency).~~ (Done)
- ~~Keep PipelineHealer as native-first remediation control plane; use `gh aw` as optional supplemental diagnostics.~~ (Done)
- ~~Sequence delivery explicitly (PR 0 → PR A → PR B → PR C → PR D → PR E → PR F → PR G).~~ (Done: all merged to `main`)
- ~~Resolve settings/allowlist reliability before enabling Layer 2 for demo-critical paths.~~ (Done)
- ~~Add explicit UX semantics for runtime settings (draft vs saved, effective scope, persistence behavior).~~ (Done: Cosmos DB durable persistence with in-memory fallback, runtime-only warning banner, "Persist Settings" action)
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
  - ~~explicit runtime-vs-durable status label on mutable settings~~ (Done: "Persist Settings" button with durable storage feedback)

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
- Add `docs/LEARNING_SYSTEM_PLAN.md`:
  - learning lifecycle (observe -> candidate -> approve -> active -> retire)
  - safety and governance rules
  - rollback path for promoted playbooks
- Add architecture update in `README.md` and `docs/API.md` once contracts are implemented.

### Model Portability Docs Additions

- Add `docs/MODEL_PROVIDER_STRATEGY.md`:
  - provider adapter contract
  - routing and fallback policy
  - migration plan from Azure-only to multi-provider
  - cost/latency tradeoff guidance

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
