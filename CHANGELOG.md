# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this repo uses Semantic Versioning.

## [Unreleased]

- _No unreleased entries yet._

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
