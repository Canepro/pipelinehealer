# Future Plan (Versioned Roadmap)

<!-- LAST_VERIFIED: 8ca4b99 -->

This roadmap is version-driven. Backlog work is planned against target releases, not ad-hoc phases.

## Planning Model (SemVer)

- `patch` (`vX.Y.Z+1`): bug fixes, reliability hardening, docs/ops updates, no contract break.
- `minor` (`vX.Y+1.0`): new backward-compatible capabilities.
- `major` (`vX+1.0.0`): breaking API/config/runtime behavior changes.

### Execution Rules

1. Only one active target release at a time.
2. Every implementation PR must declare:
   - target version
   - change type (`patch|minor|major`)
   - changelog section (`Added|Changed|Fixed`)
3. Unfinished items are explicitly moved to the next target version before closing a milestone.

## Released Baseline

| Version | Status | Notes |
|---|---|---|
| `v0.1.1` | Released | Version sync + release automation baseline |
| `v0.2.0` | Released | Learning governance, portability core, Helm target |
| `v0.2.1` | Released | Release-process corrective hardening |
| `v0.2.2` | Released | Case-study/readme/docs consistency + release cleanup |
| `v0.2.3` | Released | Release QA freeze scope completed and tagged |
| `v0.2.4` | Released | Immutable release images + retention guardrails |
| `v0.2.5` | Released | Release publish/RBAC hardening follow-up |
| `v0.2.6` | Released | Verification-learning loop + diagnostics source-selection transparency |
| `v0.2.7` | Released | Submission-readiness/operator-clarity pass (MCP explanation, demo/runbook clarity, docs alignment) |
| `v0.2.8` | Released | Release integrity hardening + docs/version drift cleanup for submission baseline |
| `v0.2.9` | Released | GH-AW/MCP hybrid diagnostics mode + passive backfill matching reliability hardening |
| `v0.2.10` | Released | Settings persistence safety hardening (`PH_ALLOWED_REPOS` mutation safety + URL guardrails) |
| `v0.2.11` | Released | Runtime control-surface separation + canary policy hardening + Kubernetes pullability docs clarity |
| `v0.3.0` | Released | Activity Detail AI handoff UX baseline (`Copy Context` + disabled `Assign to Agent`) + anonymous GHCR pullability gate hardening |
| `v0.3.1` | Released | Frontend runtime-config decoupling for containerized `VITE_*` settings + deploy/workflow/docs alignment |

## Released Target: `v0.2.6` (Verification Learning + Diagnostics Signal Clarity)

Theme: close the loop between operator verification and PipelineHealer learning, and make diagnostics source behavior explicit (especially MCP vs `gh_aw` passive mode).

### Must-Have Scope

1. Verification feedback capture for learning
   - Add explicit verification payload for `identification`, `diagnosis`, `remediation` outcomes (`pass|partial|fail`).
   - Persist verification metadata alongside activity/learning records with audit trail.
2. Learning-queue quality gates using verification outcomes
   - Weight candidate readiness by verified pass rate and verified sample size.
   - Prevent activation when verification quality gates fail (unless force path).
3. Diagnostics source-selection transparency
   - Expose why direct GitHub MCP was/was not used for an activity (policy/gating/source mode).
   - Make `gh_aw` passive vs MCP direct-path selection visible in issue/activity metadata.
4. Operator docs and triage workflow sync
   - Standardize issue-close quality gate requiring PipelineHealer accuracy assessment + target version assignment.
   - Update API/operator docs for verification feedback and readiness impact.

### Exit Criteria

1. Verification outcomes are captured through a supported API path and stored durably.
2. Learning queue readiness reflects verification quality gates (and remains auditable).
3. Activity/issue evidence clearly explains diagnostics source path (`gh_aw` passive vs GitHub MCP direct vs blocked).
4. Docs cover verification workflow and target-version tracking standards.
5. Existing remediation/learning tests remain green with new verification logic.

### Prior `v0.2.4/v0.2.5` Implementation Snapshot

- Release workflow publishes ACR release images + `release_images.md` digest artifact.
- Helm chart supports `digest` fields for backend/frontend images.
- Deploy path includes local + ACR retention pruning controls with semver preservation.
- Release helpers now synchronize `charts/pipelinehealer/Chart.yaml`.
- GitHub OIDC release environment wiring documented and configured.
- Release publish path validated for `v0.2.4` and `v0.2.5` after subscription/RBAC hardening.

Known portability gap observed in local Kind validation (2026-02-23):
- random-user-style Helm install can fail with `ErrImagePull`/`ImagePullBackOff` when default registry images are not anonymously pullable.
- this is a distribution/release gate issue (image visibility + pullability), not a Helm templating issue.

## Released Target: `v0.2.7` (Submission Readiness + Operator Clarity)

Theme: remove operator ambiguity before submission by clarifying diagnostics-source behavior (passive `gh_aw` vs direct MCP), tightening demo verification signals, and aligning runbooks/CLI/docs to release-first Azure operations.

### Must-Have Scope

1. Submission-phase docs clarity
   - Update README/runbooks/CLI with release-first deploy guidance and current baseline references.
   - Add beginner-readable MCP interpretation rules so "enabled" vs "used" is explicit.
2. Demo verification hardening
   - Ensure demo flow checks CI doctor signal and prints source clarity counters.
   - Keep strict-mode path for rehearsal/submission gates.
3. Activity UX/readability alignment
   - Keep decision summary (`PipelineHealer Decision`) first.
   - Keep deep enrichment panels secondary (`Technical Analysis & Enrichment`).

### Exit Criteria

1. Operator can determine diagnostics path from one activity without log digging.
2. Demo CLI output explicitly distinguishes passive-only signal runs from direct MCP tool calls.
3. Core docs (`README`, `CLI`, `DEMO_SCRIPT`, `LOCAL_DEMO_RUNBOOK`, feature guides) are version-aligned and non-contradictory.

## Released Target: `v0.2.8` (Release Integrity + Drift Control)

Theme: lock submission baseline integrity by ensuring release/auth wiring matches runtime expectations and removing stale version guidance from operator docs.

### Must-Have Scope

1. Release auth/build guardrails
   - Validate required frontend auth build variables in release workflow for Entra-mode releases.
   - Historical implementation note: superseded by runtime-first frontend config in `BL-043` (`v0.3.1`).
   - Document release-environment prerequisites for deterministic frontend auth behavior.
2. AKS/operator runbook hardening
   - Clarify required vs optional settings for Kubernetes deployments.
   - Clarify Entra build-time vs runtime settings and post-deploy verification checks.
3. Version drift cleanup
   - Remove stale hardcoded release examples from user-facing docs where they could be misread as current baseline.
   - Keep historical version references only in changelog/case-study/roadmap history context.

### Exit Criteria

1. Tagged release publishes successfully and appears on GitHub release page.
2. Release workflow fails early when required Entra frontend build variables are missing (historical `v0.2.8` criterion; superseded by runtime config in `BL-043`).
3. Core operator docs and README consistently point to `v0.2.8` as submission baseline (or use `vX.Y.Z` placeholders where appropriate).
4. No contradictory release-version statements in user-facing docs.

## Released Target: `v0.2.9` (Hybrid Diagnostics + Backfill Reliability)

Theme: remove MCP vs GH-AW ingestion ambiguity by enabling combined evidence collection while improving passive matching reliability.

### Must-Have Scope

1. Hybrid diagnostics mode
   - Support `GH_AW_INGESTION_MODE=hybrid` so GH-AW passive findings and GitHub MCP context can appear in one activity.
2. Backfill reliability hardening
   - Fix ci-doctor matching gaps when expected labels are missing/mismatched.
3. Ops/docs alignment
   - Sync API/CLI/settings UI/runbooks with hybrid-mode behavior and per-finding source-selection metadata.

### Exit Criteria

1. Hybrid mode is configurable through runtime settings + CLI + UI.
2. Activity diagnostics can include both `gh_aw_passive` and `github_mcp_direct` path metadata in one run.
3. Passive backfill regression coverage confirms late ci-doctor issue matching when labels drift.
4. Release notes and changelog capture real Added/Changed/Fixed entries for `v0.2.9`.

## Released Target: `v0.2.10` (Patch Safety Hardening)

Theme: operator safety hardening for settings persistence and repo allowlist management.

### Delivered Scope

1. Allowlist mutation safety in `scripts/ph.sh`
   - default repo mutations to additive/remove semantics (`--repos-add`, `--repos-remove`)
   - keep destructive replacement as explicit mode (`--repos-replace`)
2. Runtime URL guardrails for settings persistence
   - reject malformed backend URLs early
   - avoid accidental `curl https:///api/...` fallback behavior
3. Docs/changelog/release notes sync
   - update operator-facing examples and warnings in `README.md`, `docs/CLI.md`, and `docs/LOCAL_DEMO_RUNBOOK.md`
   - implementation tracked in `BL-037` / [#38](https://github.com/Canepro/pipelinehealer/issues/38) (closed)

### Exit Criteria

1. Partial repo updates no longer truncate `PH_ALLOWED_REPOS` by default.
2. Destructive replace remains available but explicit.
3. Command output shows effective allowlist action (`merge`, `remove`, `replace`, `clear`).
4. Release notes call out behavior change for operators.

## Released Target: `v0.2.11` (Patch Control-Surface Hardening)

Theme: separate runtime execution controls cleanly for operators and close remaining portability/documentation gaps for random-user Kubernetes installs.

### Delivered Scope

1. Runtime policy control separation
   - decouple global execution gate from PR toggle:
     - `AUTO_APPLY_REMEDIATION` controls dry-run vs execution
     - `AUTO_CREATE_PR`, `AUTO_CREATE_ISSUE`, `AUTO_RETRY_WORKFLOW` control per-action outputs
   - expose/update controls consistently across backend API, Settings UI, and Control Center summaries
2. Canary behavior stabilization
   - keep `rollout:canary` deterministic with explicit action toggles (issue-only default without retries)
3. Kubernetes operator clarity
   - highlight GHCR token/visibility failure mode (`ErrImagePull` `401/403`) and required pullability gate before portability claims
   - portability risk tracked in issue [#37](https://github.com/Canepro/pipelinehealer/issues/37) (closed in `v0.3.0`)
4. Regression protection + docs sync
   - add/update tests around settings persistence and orchestration dry-run gating
   - update `README.md`, `docs/API.md`, `docs/CLI.md`, `docs/KUBERNETES_HELM_RUNBOOK.md`, and `docs/features/03-settings-and-policy-controls.md`

### Exit Criteria

1. Operators can set independent execution/output controls from Settings and see the same posture in Control Center.
2. `rollout:canary` behavior remains conservative and explicit after control decoupling.
3. Kubernetes portability docs clearly block false "Helm deployed = working" conclusions.
4. Updated tests pass for settings persistence and remediation dry-run behavior.

## Released Target: `v0.3.0` (Minor)

Theme: operator handoff UX baseline + Kubernetes portability release hardening.

### Delivered Scope

1. Activity Detail copy-handoff baseline (`BL-038`)
   - Add `Copy Context` action with bounded, redacted payload output.
   - Add visible disabled `Assign to Agent` affordance with `Coming Soon` messaging.
2. Kubernetes portability hardening (`BL-036`)
   - Add release/distribution pullability gate to prevent false random-user readiness claims.
   - Keep private-registry paths optional and explicit (`imagePullSecrets`) without owner-only assumptions.
3. Release tracking + docs sync (`BL-040`)
   - Keep `v0.3.0` scope tied to issue [#43](https://github.com/Canepro/pipelinehealer/issues/43).
   - Align runbooks/readme/changelog wording with the actual shipped scope.

### Exit Criteria

1. `Copy Context` ships with payload size caps and redaction safeguards.
2. `Assign to Agent` is visible but non-functional, clearly labeled `Coming Soon`.
3. Kubernetes portability claims are gated by pullability verification, not Helm `deployed` output alone.
4. No regressions in existing Activity Detail actions (`Retry`, `Backfill Diagnostics`).
5. Release docs and changelog match shipped behavior.

## Active Target: `v0.3.2` (Minor)

Theme: integration activation for non-GitHub CI ingestion and agent handoff.

### Must-Have Scope

1. Jenkins bridge ingestion (`BL-034`)
   - Add signed ingestion path for external CI failures (Jenkins) into PipelineHealer activity pipeline.
   - Normalize payload shape (`repo`, `sha`, `branch`, `job_url`, `failed_stage`, compact logs, timestamp).
2. `Assign to Agent` functional handoff (`BL-039`)
   - Activate the `Coming Soon` control with configured handoff modes (`copy_only`/`webhook`).
   - Keep disabled-by-default runtime behavior and auditable request correlation.
3. Storage posture hardening (`BL-045`)
   - Enforce explicit storage mode contract and non-development durability guardrails.
   - Fail fast in non-development when durable storage is required but not configured.
   - Preserve explicit local/demo in-memory opt-in with operator-visible active backend surface.
4. Governance and operator verification
   - Require allowlist, signing, and replay guardrails for bridge/handoff paths.
   - Add CLI/runbook checks for integration health and failure diagnostics.

### Stretch Scope (Only After Must-Have Scope Is Green)

1. OSS-friendly PostgreSQL durable adapter (`BL-046`)
   - Add `PostgresStorage` as an adapter-only implementation path.
   - Keep orchestration and core workflow logic backend-agnostic.
   - Require parity tests across active adapters before any release inclusion.
2. Freeze risk control
   - If parity/migration/CI confidence is not strong, defer `BL-046` to `v0.3.3` with no partial rollout.

### Exit Criteria

1. Jenkins payloads can create auditable activities without GitHub `workflow_run`.
2. Assign-to-Agent handoff is functional when configured and safe when not configured.
3. Non-development deploys cannot run accidentally on ephemeral in-memory storage.
4. Integration failures are non-blocking for core activity workflows.
5. API/docs/runbooks are aligned with shipped integration behavior.

## Planned Target: `v0.3.3` (Minor)

Theme: complete learning-system operator workflow from candidate signal to safe activation, including lower-friction verification capture.

### Planned Scope

1. Learning retrieval context in runtime path
   - Retrieve active learning candidates before diagnosis/remediation.
   - Add bounded retrieval timeout and safe fallback to normal path.
2. Candidate editing workflow
   - Add API + UI to edit candidate fields safely.
   - Preserve audit trail (`actor`, `request_id`, changed fields, timestamp).
3. Learning simulation/preview
   - Add "simulate before activate" operator flow in Control Center.
   - Show predicted policy impact and safety gates before activation.
4. Verification capture bridge (GitHub issue comment -> feedback payload)
   - Define a safe parser for structured "PipelineHealer Accuracy Assessment" comment blocks.
   - Add explicit API/CLI path to ingest parsed outcomes as `learning/feedback` with traceability metadata.
   - Keep manual feedback path as fallback when comments are missing or malformed.
5. Documentation and runbook sync
   - Update feature docs and operator runbooks for new learning workflow.

### Exit Criteria

1. Contract tests for retrieval + fallback path pass.
2. Audit coverage for learning edits/actions is visible in UI and API.
3. Control Center can run simulation without changing live policy.
4. Structured issue-comment verification can be ingested with clear success/fallback behavior.
5. Docs updated:
   - `README.md` (concise user-facing summary)
   - `docs/API.md`
   - `docs/LOCAL_DEMO_RUNBOOK.md`
   - `docs/features/04-learning-system.md`

## Planned Target: `v0.4.0` (Minor)

Theme: MCP operational maturity + observability depth.

### Planned Scope

1. MCP write-path governance completion
   - Enforce per-tool policy outcomes (`disabled|read_only|write_with_approval|auto`) with explicit operator UX.
2. Observability expansion
   - Token/cost telemetry by activity/model path.
   - Provider degradation thresholds (fallback spikes, timeout/error spikes).
3. Investigation UX polish
   - Better large-dataset ergonomics in Control Center and Activity Detail.
   - Optional in-app logs viewer (safe, bounded, RBAC-aware).

## Planned Target: `v0.5.0` (Minor)

Theme: provider and platform extensibility.

### Planned Scope

1. Provider portability hardening
   - Stronger parity contract coverage across providers.
   - Rollback/runbook automation for provider switching.
2. CI platform extensibility
   - Adapter contracts for non-GitHub providers.
   - Preserve policy and remediation guardrails across providers.
3. Operator packaging
   - Kubernetes deployment polish and environment profiles.
   - Cross-platform operator wrapper support (PowerShell-first path on Windows).

## Decision Parking Lot (Researched Items)

These items are researched and tracked; some have scoped phased rollout while others remain undecided.

### DP-001: GitHub Copilot SDK / Agent Integration Fit

- Status: `Phased rollout`:
  - `v0.3.0`: discoverability UI (`Assign to Agent` shown as disabled `Coming Soon`)
  - `v0.3.2`: functional handoff integration (`copy_only`/`webhook`)
- Draft mini-spec for scoped, non-breaking handoff UX:
  - `docs/AGENT_HANDOFF_CONTEXT_MINISPEC.md`
- Why parked:
  - We need to preserve PipelineHealer as the policy/audit control plane.
  - Current MCP + GH-AW hybrid path already covers core diagnostics needs for submission.
- Research summary:
  - Legacy GitHub Copilot Extensions path is deprecated.
  - Viable modern path is Copilot coding-agent task execution, optionally paired with MCP context.
- Guardrails if adopted later:
  - No bypass of PipelineHealer policy gates.
  - All Copilot-assisted remediation actions must remain traceable in activity/issue evidence.
  - Keep GitHub provider coupling optional (do not regress non-GitHub portability goals).

### DP-002: Multi-Platform Notification Delivery (Slack / Teams / Rocket.Chat)

- Status: `Undecided` (`nice-to-have`, not in active release scope)
- Problem statement:
  - Non-admin developers and stakeholders need actionable PipelineHealer updates in chat tools without depending on dashboard access.
- Research summary:
  - Slack supports app-based incoming webhooks and OAuth-based installation, with upgrade path to `chat.postMessage` for richer lifecycle operations.
  - Microsoft Teams is migrating connector-based webhooks toward Workflows/Power Automate and bot-based proactive messaging patterns.
  - Rocket.Chat supports incoming/outgoing webhooks and Integration API endpoints for managed integration provisioning.
- Candidate architecture:
  - Add a provider-agnostic `NotificationSink` interface (`send`, `update`, `health`) with adapters for Slack, Teams, Rocket.Chat.
  - Emit notification events from activity lifecycle transitions (`created`, `diagnosed`, `remediation_opened`, `resolved`, `failed`).
  - Keep dashboard as source of truth; notifications carry summary + deep links to activity details.
- Recommended rollout (if approved):
  - Phase 1: Slack webhook adapter + audit trail + rate-limit/retry policy.
  - Phase 2: Teams Workflows webhook adapter with card templates aligned to Teams connector retirement path.
  - Phase 3: Rocket.Chat incoming webhook/API adapter for self-hosted teams.
  - Phase 4: Optional message update/ack actions (`chat.postMessage`/provider equivalent) with approval gates for write actions.
- Guardrails if adopted later:
  - Respect repo allowlist and role-based audience mapping.
  - Redact secrets/tokens from payloads by policy before send.
  - Rate-limit and retry with provider-specific backoff/429 handling.
  - Preserve audit trail for every outbound notification attempt/result.

### DP-003: Jenkins Bridge Strategy for GitHub-Adjacent Repos

- Status: `Planned` (recommended to start in `v0.3.2`)
- Problem statement:
  - Some onboarded repos are Jenkins-primary and may not emit GitHub `workflow_run` failures, so PipelineHealer receives no trigger despite webhook allowlisting.
- Recommended option:
  - Build a signed Jenkins bridge ingestion path into PipelineHealer first (`v0.3.2`) before full native Jenkins adapter work.
- Why this option:
  - Reuses existing diagnosis/remediation pipeline quickly.
  - Preserves current policy/audit model.
  - Avoids blocking on full provider abstraction before demo/operator value is realized.
- Follow-on option (later):
  - Native Jenkins provider adapter (`v0.5.x`) for richer capabilities (job replay, artifact retrieval, deeper stage metadata).
- Guardrails:
  - Signed payload verification + replay protection.
  - Explicit source attribution (`jenkins_bridge`) in activity evidence.
  - Issue-first default until confidence and idempotency behavior are validated.

## Backlog Queue (Version-Mapped)

| ID | Item | Recommended Target | Type | Priority | Status |
|---|---|---|---|---|---|
| `BL-001` | Learning retrieval-before-diagnosis/remediation | `v0.3.3` | minor | High | Planned |
| `BL-002` | Learning candidate edit API/UI + audit metadata | `v0.3.3` | minor | High | Planned |
| `BL-003` | Learning simulation/preview controls in Control Center | `v0.3.3` | minor | High | Planned |
| `BL-004` | MCP policy visualization + approval UX completion | `v0.4.0` | minor | Medium | Planned |
| `BL-005` | Token/cost telemetry and degradation alerts | `v0.4.0` | minor | Medium | Planned |
| `BL-006` | In-app investigation/log viewer (bounded) | `v0.4.x` | patch/minor | Medium | Queued |
| `BL-007` | Multi-provider parity hardening and rollback automation | `v0.5.0` | minor | Medium | Queued |
| `BL-008` | Non-GitHub CI adapter readiness | `v0.5.x` | minor | Medium | Queued |
| `BL-009` | Vite chunk-size warning reduction (`>500kB`) | `v0.2.3` | patch | High | Completed |
| `BL-010` | Bun peer-dependency warning cleanup (`react@18.3.1`) | `v0.2.3` | patch | High | Completed |
| `BL-011` | Backend build warning cleanup (`agent-framework-core[all]`) ([#17](https://github.com/Canepro/pipelinehealer/issues/17)) | `v0.2.3` | patch | Medium | Blocked (upstream/index) |
| `BL-012` | Deploy warning gate + triage runbook updates | `v0.2.3` | patch | Medium | Completed |
| `BL-013` | Immutable ACR release image publish + digest artifact | `v0.2.4` | patch | High | Completed (in `main`) |
| `BL-014` | Helm digest pinning + chart version sync in release tooling | `v0.2.4` | patch | High | Completed (in `main`) |
| `BL-015` | Deploy retention controls (local + ACR) with semver preservation | `v0.2.4` | patch | Medium | Completed (in `main`) |
| `BL-016` | Verification feedback API + durable storage (`identification/diagnosis/remediation`) ([#25](https://github.com/Canepro/pipelinehealer/issues/25)) | `v0.2.6` | patch | High | Completed (in `main`) |
| `BL-017` | Verification-aware learning readiness gates + metrics ([#26](https://github.com/Canepro/pipelinehealer/issues/26)) | `v0.2.6` | patch | High | Completed (in `main`) |
| `BL-018` | Diagnostics source transparency (`gh_aw` passive vs MCP direct path reasons) ([#27](https://github.com/Canepro/pipelinehealer/issues/27)) | `v0.2.6` | patch | Medium | Completed (in `main`) |
| `BL-019` | Operator-oriented inline comments for Helm/compose/workflows ([#28](https://github.com/Canepro/pipelinehealer/issues/28)) | `v0.2.6` | patch | Low | Completed (in `main`) |
| `BL-020` | Activities desktop UX: remove horizontal rail dependency and keep actions reachable ([#29](https://github.com/Canepro/pipelinehealer/issues/29)) | `v0.2.6` | patch | High | Completed (in `main`) |
| `BL-021` | Azure deploy from immutable ACR release images (no local build) ([#30](https://github.com/Canepro/pipelinehealer/issues/30)) | `v0.2.6` | patch | High | Completed (in `main`) |
| `BL-022` | Demo verification output clarity (`mcp_tool_calls_total` vs passive-only counters) | `v0.2.7` | patch | High | Completed (in `main`) |
| `BL-023` | Docs/runbook MCP interpretation hardening for non-expert operators | `v0.2.7` | patch | High | Completed (in `main`) |
| `BL-024` | Release baseline alignment (`v0.2.7`) across README/CLI/runbooks | `v0.2.7` | patch | Medium | Completed (in `main`) |
| `BL-025` | Accuracy-assessment bridge: ingest structured GitHub issue verification comments into `learning/feedback` with audit traceability | `v0.3.3` | minor | High | Planned |
| `BL-026` | Cross-platform operator support: PowerShell wrapper + non-Azure deploy wrapper strategy for `ph` commands | `v0.5.0` | minor | Medium | Planned |
| `BL-027` | AKS/Helm onboarding hardening: explicit required-vs-optional auth paths, Entra build-time vs runtime guardrails, and post-deploy auth verification checklist ([#32](https://github.com/Canepro/pipelinehealer/issues/32)) | `v0.3.0` | patch | Medium | Completed (in `main`) |
| `BL-028` | Submission-baseline drift control (`v0.2.8`): release auth build-var gating + docs version alignment pass | `v0.2.8` | patch | High | Completed (in `main`) |
| `BL-029` | Azure deploy hardening option: `--secure-secrets` path in deploy tooling (`ph.sh` + redeploy script) with operator docs for secretref-backed runtime env | `v0.2.9` | patch | High | Completed (released in `v0.2.9`) |
| `BL-030` | GH-AW + GitHub MCP hybrid diagnostics ingestion mode (`GH_AW_INGESTION_MODE=hybrid`) across backend/UI/CLI/docs | `v0.2.9` | patch | High | Completed (released in `v0.2.9`) |
| `BL-031` | Passive backfill label-mismatch reliability fix (unlabeled fallback matching for ci-doctor findings) ([#35](https://github.com/Canepro/pipelinehealer/issues/35)) | `v0.2.9` | patch | High | Completed (released in `v0.2.9`) |
| `BL-032` | Copilot integration research track: evaluate coding-agent + MCP coexistence model without bypassing PipelineHealer governance | `v0.3.2` | minor | Medium | Planned (phased via `BL-038`/`BL-039`) |
| `BL-033` | Multi-platform notifications research track: Slack/Teams/Rocket.Chat delivery model for non-admin stakeholders with auditable outbound events | `TBD (post-submission)` | minor | Medium | Research / Undecided |
| `BL-034` | Jenkins bridge ingestion path: signed external CI failure payload -> synthetic PipelineHealer activity (`source_selection_path=jenkins_bridge`) with issue-first defaults ([#36](https://github.com/Canepro/pipelinehealer/issues/36)) | `v0.3.2` | minor | High | Planned |
| `BL-035` | Native Jenkins provider adapter: deeper job metadata/log/artifact retrieval + rerun/governance parity with existing provider model | `v0.5.x` | minor | Medium | Queued |
| `BL-036` | Public distribution hardening for Kubernetes portability: publish anonymous-pull image path and add clean-cluster pullability gate in release verification to block `ErrImagePull` (`401`/`403`) regressions ([#37](https://github.com/Canepro/pipelinehealer/issues/37)) | `v0.3.0` | patch | High | Completed (released in `v0.3.0`) |
| `BL-037` | Settings persistence safety hardening: prevent accidental `PH_ALLOWED_REPOS` truncation via additive/remove semantics in `scripts/ph.sh` with explicit replace mode, plus backend URL resolution guardrails ([#38](https://github.com/Canepro/pipelinehealer/issues/38)) | `v0.2.10` | patch | High | Completed (released in `v0.2.10`) |
| `BL-038` | Activity Detail one-click `Copy Context` for AI-ready handoff payloads with bounded size + redaction, plus disabled `Assign to Agent` `Coming Soon` affordance ([#41](https://github.com/Canepro/pipelinehealer/issues/41)) | `v0.3.0` | patch | High | Completed (released in `v0.3.0`) |
| `BL-039` | Activity Detail `Assign to Agent` integration (`copy_only` + optional `webhook`) with audit-safe handoff controls ([#42](https://github.com/Canepro/pipelinehealer/issues/42)) | `v0.3.2` | minor | Medium | Planned |
| `BL-040` | Release umbrella tracking for bundled `v0.3.0` scope (`BL-036`, `BL-038`) ([#43](https://github.com/Canepro/pipelinehealer/issues/43)) | `v0.3.0` | patch | High | Completed (released in `v0.3.0`) |
| `BL-041` | Release umbrella tracking for `v0.3.2` freeze scope (`BL-034`, `BL-039`, `BL-045`) and guarded stretch tracking (`BL-046`) ([#44](https://github.com/Canepro/pipelinehealer/issues/44)) | `v0.3.2` | patch | High | Tracking (active) |
| `BL-042` | Platform-neutral Kubernetes deployment profiles + docs guidance (`values.quickstart.yaml`, `values.production.yaml`) with optional installer automation follow-up ([#51](https://github.com/Canepro/pipelinehealer/issues/51)) | `TBD (post-submission, no release cut required)` | patch | High | Completed (in `main`) |
| `BL-043` | Frontend runtime-config decoupling: make containerized `VITE_*` settings runtime-first across frontend/Helm/Azure deploy tooling and remove build-arg coupling in release path ([#54](https://github.com/Canepro/pipelinehealer/issues/54)) | `v0.3.1` | patch | High | Completed (released in `v0.3.1`) |
| `BL-044` | Azure env-sync regression fix: keep existing frontend runtime config when `VITE_*` keys are omitted from env input during `deploy:env` ([#55](https://github.com/Canepro/pipelinehealer/issues/55)) | `v0.3.2` | patch | High | Planned |
| `BL-045` | Storage posture hardening: explicit storage mode + non-development durability guardrail with fail-fast misconfiguration behavior ([#57](https://github.com/Canepro/pipelinehealer/issues/57)) | `v0.3.2` | patch | High | Planned |
| `BL-046` | PostgreSQL durable storage adapter (OSS-friendly persistence path) with adapter-contract parity requirements ([#58](https://github.com/Canepro/pipelinehealer/issues/58)) | `v0.3.2` (stretch) / `v0.3.3` (fallback) | minor | Medium | Planned (stretch-gated) |

## Definition of Done (Per Version)

1. Code + tests + docs land together for behavior changes.
2. Release notes are prepared before tagging.
3. Upgrade/rollback path is documented for operational changes.
4. No open P0/P1 regressions for the release scope.

## Notes

- Detailed historical implementation evidence remains in `docs/HACKATHON_LOG.md`.
- This file is the planning source of truth for future release targeting.
