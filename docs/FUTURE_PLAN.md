# Future Plan (Versioned Roadmap)

<!-- LAST_VERIFIED: 8980118 -->

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

## Definition of Done (Per Version)

1. Code + tests + docs land together for behavior changes.
2. Release notes are prepared before tagging.
3. Upgrade/rollback path is documented for operational changes.
4. No open P0/P1 regressions for the release scope.

## Notes

- Detailed historical implementation evidence remains in `docs/HACKATHON_LOG.md`.
- This file is the planning source of truth for future release targeting.
