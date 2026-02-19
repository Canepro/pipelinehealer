# Future Plan (Versioned Roadmap)

<!-- LAST_VERIFIED: 69331ac -->

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

## Active Target: `v0.3.0` (Next Minor)

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

## Fast-Follow Patch Target: `v0.2.3` (Quality/Build Warning Debt)

Theme: remove known non-breaking deployment/build warnings before continuing deeper feature work.

### Must-Have Scope

1. Frontend bundle warning reduction
   - Address Vite `chunk size > 500kB` warnings with targeted route/component splitting.
   - Review heavy dependencies in dashboard/control-center paths and defer non-critical imports.
2. Frontend dependency warning hygiene
   - Resolve Bun peer dependency warning (`incorrect peer dependency react@18.3.1`) by aligning package peer matrix.
   - Keep runtime stack stable (no breaking React major jump in patch release).
3. Python package warning hygiene
   - Investigate `agent-framework-core ... does not have an extra named all` warning during backend image build.
   - Pin/upgrade dependency chain or document upstream limitation with explicit guardrails.
4. Deploy log quality gate
   - Add lightweight deploy-warning check/runbook note so warnings are visible and triaged each deploy.

### Exit Criteria

1. `bash scripts/ph.sh deploy` emits no untracked known-warning classes.
2. Frontend production build warnings are reduced to zero or formally documented as upstream/transient.
3. Warning triage policy is documented in ops docs (`docs/LOCAL_DEMO_RUNBOOK.md` and/or release checklist docs).

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
| `BL-009` | Vite chunk-size warning reduction (`>500kB`) | `v0.2.3` | patch | High | Planned |
| `BL-010` | Bun peer-dependency warning cleanup (`react@18.3.1`) | `v0.2.3` | patch | High | Planned |
| `BL-011` | Backend build warning cleanup (`agent-framework-core[all]`) | `v0.2.3` | patch | Medium | Planned |
| `BL-012` | Deploy warning gate + triage runbook updates | `v0.2.3` | patch | Medium | Planned |

## Definition of Done (Per Version)

1. Code + tests + docs land together for behavior changes.
2. Release notes are prepared before tagging.
3. Upgrade/rollback path is documented for operational changes.
4. No open P0/P1 regressions for the release scope.

## Notes

- Detailed historical implementation evidence remains in `docs/HACKATHON_LOG.md`.
- This file is the planning source of truth for future release targeting.
