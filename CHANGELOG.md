# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this repo uses Semantic Versioning.

## [Unreleased]

- _No unreleased entries yet._

## [v0.2.5] - 2026-02-19

### Fixed

- `1c6e6d7` Hardened release workflow ACR login to auto-discover the subscription containing the target registry when the configured subscription does not match.

## [v0.2.4] - 2026-02-19

### Added

- `9169bf3` Release workflow now publishes immutable backend/frontend ACR images on `vX.Y.Z` tags, including semver tags and digest references (`release_images.md`) for reproducible installs.
- `9169bf3` Helm chart now supports digest pinning (`repository@sha256:...`) for backend and frontend images, with tag fallback.

### Changed

- `9169bf3` Full deploy now includes local + ACR image retention controls, preserving semver-style tags while pruning older non-release tags.
- `9169bf3` Version sync/release tooling now includes Helm chart version/appVersion synchronization in `charts/pipelinehealer/Chart.yaml`.
- `ed44e99` Initialized `v0.2.4` roadmap target in `docs/FUTURE_PLAN.md` with release-artifact immutability and cost-guardrail scope/exit criteria.

## [v0.2.3] - 2026-02-19

### Changed

- `69c7e51` Linked BL-011 backend warning tracking issue (`#17`) into roadmap/log docs to keep warning-debt traceability release-aligned.
- `1ad62ce` Replaced phase-style future plan with a SemVer-aligned roadmap in `docs/FUTURE_PLAN.md` (`v0.3.0` active target, `v0.4.0+` mapped backlog).
- `1ad62ce` Updated docs index wording to reflect version-targeted planning as the default roadmap model.
- `69331ac` Refined Control Center information architecture with section tabs (`Governance Overview`, `Learning & Ops`, `Audit & Trace`) and improved learning/ops layout density.
- `69331ac` Polished Settings page operator ergonomics with structured key/value summary cards and quick navigation actions to Control Center/Activities.
- `HEAD` Aligned release docs and roadmap to an explicit `v0.2.3` QA freeze (no new feature scope; warning-debt closure + QA gates only).
- `HEAD` Added release warning-triage guidance to runbooks and improved Control Center/Settings readability with structured summary rows and workflow-oriented UI cues.
- `688ae1d` Adopted SemVer-based future roadmap structure and version-targeted backlog model.
- `030fc39` Refreshed documentation `LAST_VERIFIED` markers after roadmap synchronization.
- `a13de38` Added capability highlights across historical changelog versions for clearer release archaeology.
- `2dc9251` Extended case-study documentation with learning-candidate follow-up details.
- `dfc6efc` Added release-scope guardrail tooling so commits since the last tag must be represented in `CHANGELOG` `Unreleased`.
- `6bb19fe` Split frontend chart/auth vendors in Vite build output to remove the chunk-size warning from local production builds.
- `6bb19fe` Pinned MSAL packages to a React 18-compatible line (`@azure/msal-react=3.0.26`, `@azure/msal-browser=4.28.2`) to eliminate Bun peer warning noise.
- `6bb19fe` Hardened release scope guardrail to validate all non-HEAD commits since last tag against `CHANGELOG` `Unreleased` references.

## [v0.2.2] - 2026-02-19

### Capability Highlights

- Documentation and release-history clarity upgrade:
  - incident case study is linked from docs index and README
  - historical release trail is easier to audit and present

### Added

- Case study lifecycle completion details for run `#22163136636`, including final issue state and linked PR artifact.
- Docs index now directly references the release-tag mismatch case study under `docs/case-studies/`.

### Changed

- README "Why this project" section now includes a production-like incident proof block (activity, run, issue, PR, release links).
- Refreshed `LAST_VERIFIED` markers for edited docs to the post-merge baseline commit.

## [v0.2.1] - 2026-02-19

### Capability Highlights

- Production release safety hardening:
  - repeatable release preparation flow
  - explicit verification and rollback guidance
  - safeguards to prevent tag/version mismatch recurrence

### Added

- Release runbook (`docs/RELEASE_RUNBOOK.md`) with end-to-end prep, publish verification, and rollback guidance.
- Release checklist helper (`scripts/release_checklist.sh`) for copy-paste, ordered release execution.

### Changed

- README and CLI release sections now point to the dedicated release runbook/checklist flow.

### Fixed

- Release process guidance now explicitly prevents repeating tag/version mismatch incidents like run `#22163136636`.

## [v0.2.0] - 2026-02-19

### Capability Highlights

- Learning-system governance became operational:
  - candidate lifecycle actions in Control Center
  - promotion-readiness gates and audited force activation
- Platform portability improved:
  - provider portability reliability hardening
  - Kubernetes Helm target for non-ACA deployments

### Added

- Learning queue governance APIs and Control Center actions (`approve`, `reject`, `activate`, `retire`, `reset_candidate`).
- Promotion-readiness gates for playbook activation with explicit audited `force_activate` override.
- Kubernetes Helm deployment target and operator runbook.
- Dedicated learning-system documentation and updated architecture coverage in README.

### Changed

- Control Center learning queue now uses a full-width layout for better operator review workflow.
- Docs and runbooks synchronized to current command/auth/runtime behavior (`API`, `CLI`, `LOCAL_DEMO_RUNBOOK`, `README`).
- Repo standards now require concise intent-focused comments for non-obvious logic.

### Fixed

- Provider portability path hardened with retry/error classification for timeout/429/5xx scenarios.
- Added provider parity regression tests to guard diagnosis/remediation behavior consistency.
- Failure classification trust hardened for ambiguous test signatures.

## [v0.1.1] - 2026-02-18

### Capability Highlights

- First public PipelineHealer release:
  - multi-agent CI failure triage and policy-aware remediation
  - explainability and operator visibility foundations
  - script-first operations and release/version control baseline

### Added

- First public release baseline of PipelineHealer core capabilities:
  - multi-agent CI/CD flow (`analyze -> diagnose -> remediate`) for GitHub Actions failures
  - policy-aware remediation modes with safe-first defaults
  - explainability metadata (diagnosis source, reason codes, evidence)
  - operator surfaces (dashboard/activity views + admin settings)
  - script-first operations via `bash scripts/ph.sh ...`
- Release automation workflow for `vX.Y.Z` tags that validates version sync and publishes GitHub releases from changelog notes.
- Repository `VERSION` file as the semver source of truth across backend and frontend packages.
- Release helper scripts:
  - `scripts/check_version_sync.sh`
  - `scripts/release.sh`

### Changed

- CI now enforces version alignment between `VERSION`, `backend/pyproject.toml`, and `frontend/package.json`.
- ShellCheck coverage extended to include release helper scripts.

### Fixed

- `scripts/release.sh` now preserves existing `Unreleased` notes when generating a new release section.

## [v0.1.0] - 2026-02-18 (internal baseline, not a published GitHub release tag)

### Capability Highlights

- Internal milestone that established initial architecture and demo baseline before public release tagging.

### Added

- Initial public hackathon release baseline.
- Multi-agent CI/CD diagnosis and policy-aware remediation flow.
- Admin settings, control center, explainability, and MCP governance foundations.
