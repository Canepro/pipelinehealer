# Future Plan (Versioned Roadmap)

<!-- LAST_VERIFIED: 9169bf3 -->

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
| `v0.2.3` | Candidate in `main` | Release QA freeze scope implemented; release tag validation pending |

## Active Target: `v0.2.4` (Release Artifact Immutability + Cost Guardrails)

Theme: ensure versioned installs are reproducible and affordable by publishing immutable release images and enforcing retention guardrails.

### Must-Have Scope

1. Immutable release image publishing
   - On each `vX.Y.Z` tag, build and push backend/frontend images to ACR.
   - Publish both tag forms (`vX.Y.Z` and `X.Y.Z`) and record digests in release output.
2. Helm reproducibility controls
   - Add digest-based image pinning support (`repository@sha256:...`) with tag fallback.
   - Keep Helm chart versions synced with repository versioning during release prep.
3. Retention and cost controls
   - Prune old local ACR-tagged images after full deploy.
   - Prune old ACR tags/manifests with semver-tag preservation to avoid breaking versioned installs.
4. Operator docs and runbook sync
   - Document OIDC + ACR release requirements.
   - Document digest-first Helm install guidance and release verification steps.
5. Workflow compatibility hardening
   - Ensure release build paths work with current lockfile format and existing CI/runtime constraints.

### Exit Criteria

1. `vX.Y.Z` GitHub release publishes immutable ACR references for backend/frontend (tags + digests).
2. Helm chart supports both semver tag pinning and digest pinning without template changes.
3. Full deploy includes retention controls; semver-like tags are preserved from ACR prune.
4. Release docs and runbooks describe required GitHub/Azure OIDC configuration and verification commands.
5. `bash scripts/check_version_sync.sh` validates `VERSION`, backend/frontend package versions, and Helm chart version/appVersion.

### Initial `v0.2.4` Implementation Snapshot

- Release workflow publishes ACR release images + `release_images.md` digest artifact.
- Helm chart supports `digest` fields for backend/frontend images.
- Deploy path includes local + ACR retention pruning controls with semver preservation.
- Release helpers now synchronize `charts/pipelinehealer/Chart.yaml`.
- GitHub OIDC release environment wiring documented and configured.

## Next Target: `v0.3.0` (Minor)

Theme: complete learning-system operator workflow from candidate signal to safe activation.

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
4. Documentation and runbook sync
   - Update feature docs and operator runbooks for new learning workflow.

### Exit Criteria

1. Contract tests for retrieval + fallback path pass.
2. Audit coverage for learning edits/actions is visible in UI and API.
3. Control Center can run simulation without changing live policy.
4. Docs updated:
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

## Definition of Done (Per Version)

1. Code + tests + docs land together for behavior changes.
2. Release notes are prepared before tagging.
3. Upgrade/rollback path is documented for operational changes.
4. No open P0/P1 regressions for the release scope.

## Notes

- Detailed historical implementation evidence remains in `docs/HACKATHON_LOG.md`.
- This file is the planning source of truth for future release targeting.
