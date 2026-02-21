# Future Plan (Versioned Roadmap)

<!-- LAST_VERIFIED: e5242d1 -->

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
   - Document release-environment prerequisites for deterministic frontend auth behavior.
2. AKS/operator runbook hardening
   - Clarify required vs optional settings for Kubernetes deployments.
   - Clarify Entra build-time vs runtime settings and post-deploy verification checks.
3. Version drift cleanup
   - Remove stale hardcoded release examples from user-facing docs where they could be misread as current baseline.
   - Keep historical version references only in changelog/case-study/roadmap history context.

### Exit Criteria

1. Tagged release publishes successfully and appears on GitHub release page.
2. Release workflow fails early when required Entra frontend build variables are missing.
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

## Active Target: `v0.3.0` (Minor)

Theme: complete learning-system operator workflow from candidate signal to safe activation, including lower-friction verification capture.

### Must-Have Scope

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

## Planned Target: `v0.3.1` (Minor)

Theme: Jenkins-first repo onboarding bridge so non-GitHub-primary CI repos can still feed actionable failures into PipelineHealer safely.

### Planned Scope

1. Jenkins bridge ingestion path (recommended first)
   - Add signed ingestion path for external CI failures (Jenkins) into PipelineHealer activity pipeline.
   - Normalize payload shape (`repo`, `sha`, `branch`, `job_url`, `failed_stage`, compact logs, timestamp).
2. Synthetic activity + diagnosis flow
   - Create auditable synthetic activity records for Jenkins failures with explicit `source_selection_path=jenkins_bridge`.
   - Run existing diagnosis/remediation logic in conservative mode (issue-first by default).
3. Governance and safety controls
   - Require repo allowlist checks (`PH_ALLOWED_REPOS` + optional provider-specific allowlist).
   - Add signing secret validation + replay protection for bridge payloads.
4. Operator verification path
   - Add CLI/runbook checks for bridge health, recent bridge ingestions, and failed payload diagnostics.

### Exit Criteria

1. Jenkins failure payloads can create PipelineHealer activities without GitHub `workflow_run`.
2. Bridge path is auditable with request IDs and source attribution.
3. Repo/policy guardrails enforce least privilege by default.
4. Docs include setup for Jenkins operators and rollback path.

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

## Decision Parking Lot (Researched, Not Committed)

These items are researched and tracked, but not approved for build scope yet.

### DP-001: GitHub Copilot SDK / Agent Integration Fit

- Status: `Undecided` (`nice-to-have`, not in active release scope)
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

- Status: `Planned` (recommended to start in `v0.3.1`)
- Problem statement:
  - Some onboarded repos are Jenkins-primary and may not emit GitHub `workflow_run` failures, so PipelineHealer receives no trigger despite webhook allowlisting.
- Recommended option:
  - Build a signed Jenkins bridge ingestion path into PipelineHealer first (`v0.3.1`) before full native Jenkins adapter work.
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
| `BL-001` | Learning retrieval-before-diagnosis/remediation | `v0.3.0` | minor | High | Planned |
| `BL-002` | Learning candidate edit API/UI + audit metadata | `v0.3.0` | minor | High | Planned |
| `BL-003` | Learning simulation/preview controls in Control Center | `v0.3.0` | minor | High | Planned |
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
| `BL-025` | Accuracy-assessment bridge: ingest structured GitHub issue verification comments into `learning/feedback` with audit traceability | `v0.3.0` | minor | High | Planned |
| `BL-026` | Cross-platform operator support: PowerShell wrapper + non-Azure deploy wrapper strategy for `ph` commands | `v0.5.0` | minor | Medium | Planned |
| `BL-027` | AKS/Helm onboarding hardening: explicit required-vs-optional auth paths, Entra build-time vs runtime guardrails, and post-deploy auth verification checklist ([#32](https://github.com/Canepro/pipelinehealer/issues/32)) | `v0.3.0` | patch | Medium | Completed (in `main`) |
| `BL-028` | Submission-baseline drift control (`v0.2.8`): release auth build-var gating + docs version alignment pass | `v0.2.8` | patch | High | Completed (in `main`) |
| `BL-029` | Azure deploy hardening option: `--secure-secrets` path in deploy tooling (`ph.sh` + redeploy script) with operator docs for secretref-backed runtime env | `v0.2.9` | patch | High | Completed (released in `v0.2.9`) |
| `BL-030` | GH-AW + GitHub MCP hybrid diagnostics ingestion mode (`GH_AW_INGESTION_MODE=hybrid`) across backend/UI/CLI/docs | `v0.2.9` | patch | High | Completed (released in `v0.2.9`) |
| `BL-031` | Passive backfill label-mismatch reliability fix (unlabeled fallback matching for ci-doctor findings) ([#35](https://github.com/Canepro/pipelinehealer/issues/35)) | `v0.2.9` | patch | High | Completed (released in `v0.2.9`) |
| `BL-032` | Copilot integration research track: evaluate coding-agent + MCP coexistence model without bypassing PipelineHealer governance | `TBD (post-submission)` | minor | Low | Research / Undecided |
| `BL-033` | Multi-platform notifications research track: Slack/Teams/Rocket.Chat delivery model for non-admin stakeholders with auditable outbound events | `TBD (post-submission)` | minor | Medium | Research / Undecided |
| `BL-034` | Jenkins bridge ingestion path: signed external CI failure payload -> synthetic PipelineHealer activity (`source_selection_path=jenkins_bridge`) with issue-first defaults | `v0.3.1` | minor | High | Planned |
| `BL-035` | Native Jenkins provider adapter: deeper job metadata/log/artifact retrieval + rerun/governance parity with existing provider model | `v0.5.x` | minor | Medium | Queued |

## Definition of Done (Per Version)

1. Code + tests + docs land together for behavior changes.
2. Release notes are prepared before tagging.
3. Upgrade/rollback path is documented for operational changes.
4. No open P0/P1 regressions for the release scope.

## Notes

- Detailed historical implementation evidence remains in `docs/HACKATHON_LOG.md`.
- This file is the planning source of truth for future release targeting.
