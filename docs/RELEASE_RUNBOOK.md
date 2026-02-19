# Release Runbook

<!-- LAST_VERIFIED: 1ad62ce -->

End-to-end release procedure for PipelineHealer using the repo release helpers.

This runbook covers:
- release prep
- semver bump
- release commit + tag
- publish and verification
- rollback/correction paths

## Scope

Use this runbook when you want to publish a new version tag (`vX.Y.Z`) and trigger the release workflow.

Current release automation:
- version source of truth: `VERSION`
- synced manifests: `backend/pyproject.toml`, `frontend/package.json`
- changelog source: `CHANGELOG.md`
- release workflow trigger: git tag `vX.Y.Z`

## Choose Release Type

| Type | When to use |
|------|-------------|
| `patch` | bug fixes, docs-only updates, no meaningful feature expansion |
| `minor` | new features/capabilities, backward-compatible behavior additions |
| `major` | breaking changes, removed/changed contracts |

## 1) Preflight (Required)

Run from repo root:

```bash
git status --short
bash scripts/check_version_sync.sh
bash scripts/release_scope_check.sh
```

Requirements:
- working tree is clean
- version sync passes
- release scope check passes (all commits since last tag are referenced in `CHANGELOG.md` `## [Unreleased]`)
- you are on the intended branch (usually `main`)

If there are pending commits for release notes, finish and push them first.

Optional helper (prints the exact ordered commands used in this runbook):

```bash
bash scripts/release_checklist.sh minor
```

This is a dry-run checklist generator; it does not modify files.

## 2) Prepare Changelog Notes

Before bumping, add concise release notes under `## [Unreleased]` in `CHANGELOG.md`:
- `### Added`
- `### Changed`
- `### Fixed`

Tip:
- summarize user-facing outcomes (not internal implementation details only)
- keep bullets short and audit-friendly

## 3) Generate Release Version

Run one command:

```bash
bash scripts/release.sh <patch|minor|major|x.y.z>
```

Examples:

```bash
bash scripts/release.sh patch
bash scripts/release.sh minor
bash scripts/release.sh 0.2.3
```

This updates:
- `VERSION`
- `backend/pyproject.toml`
- `frontend/package.json`
- `CHANGELOG.md` (moves Unreleased notes into new `## [vX.Y.Z] - YYYY-MM-DD` section)

## 4) Validate Generated State

```bash
bash scripts/check_version_sync.sh
```

Recommended sanity checks:

```bash
python3 -m pytest backend/tests/test_phase2_security.py::test_api_routes_allow_development_without_key -q
cd frontend && bun run build && cd ..
```

## 5) Commit, Tag, Push

```bash
git add VERSION backend/pyproject.toml frontend/package.json CHANGELOG.md
git commit -m "chore(release): vX.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main --follow-tags
```

Replace `X.Y.Z` with the generated version.

## 6) Verify Published Release

1. Confirm tag exists remotely:

```bash
git ls-remote --tags origin | grep "refs/tags/vX.Y.Z"
```

2. Confirm GitHub Actions release workflow succeeded for that tag.
3. Confirm GitHub Release notes match `CHANGELOG.md` release section.

## 7) Post-Release

Keep `## [Unreleased]` ready for next cycle:
- add new entries as work lands
- avoid batching massive undocumented changes

## Rollback / Correction

### A) Release commit is wrong but not pushed

- fix files
- recommit (or amend locally if policy allows)
- recreate tag if needed

### B) Tag pushed with bad notes/version

Preferred safe path:
1. create a follow-up release (`patch`) with corrected content
2. document correction in changelog

Avoid force-rewriting published tags unless absolutely necessary and team-approved.

## Minimal Operator Checklist

1. `git status --short` clean
2. update `CHANGELOG.md` Unreleased
3. `bash scripts/release.sh minor` (or patch/major)
4. `bash scripts/check_version_sync.sh`
5. sanity test/build
6. commit + tag + push `--follow-tags`
7. verify release workflow + GitHub release page
