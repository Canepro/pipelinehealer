# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this repo uses Semantic Versioning.

## [Unreleased]

- _No unreleased entries yet._

## [v0.2.2] - 2026-02-19

### Added

- Case study lifecycle completion details for run `#22163136636`, including final issue state and linked PR artifact.
- Docs index now directly references the release-tag mismatch case study under `docs/case-studies/`.

### Changed

- README "Why this project" section now includes a production-like incident proof block (activity, run, issue, PR, release links).
- Refreshed `LAST_VERIFIED` markers for edited docs to the post-merge baseline commit.

## [v0.2.1] - 2026-02-19

### Added

- Release runbook (`docs/RELEASE_RUNBOOK.md`) with end-to-end prep, publish verification, and rollback guidance.
- Release checklist helper (`scripts/release_checklist.sh`) for copy-paste, ordered release execution.

### Changed

- README and CLI release sections now point to the dedicated release runbook/checklist flow.

### Fixed

- Release process guidance now explicitly prevents repeating tag/version mismatch incidents like run `#22163136636`.

## [v0.2.0] - 2026-02-19

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

### Added

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

## [v0.1.0] - 2026-02-18

### Added

- Initial public hackathon release baseline.
- Multi-agent CI/CD diagnosis and policy-aware remediation flow.
- Admin settings, control center, explainability, and MCP governance foundations.
