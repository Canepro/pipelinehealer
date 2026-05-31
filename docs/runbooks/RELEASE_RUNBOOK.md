# Release Runbook

<!-- LAST_VERIFIED: caeed6a -->

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
- synced manifests: `backend/pyproject.toml`, `frontend/package.json`, `charts/pipelinehealer/Chart.yaml` (`version` + `appVersion`)
- changelog source: `CHANGELOG.md`
- release workflow trigger: git tag `vX.Y.Z`
- release workflow output: GitHub release + GHCR images for both tags (`vX.Y.Z` and `X.Y.Z`) + digest references (`release_images.md`)
- release workflow gate: validates anonymous GHCR pullability for backend/frontend tags + digests and Helm chart tag before creating the GitHub release
- optional release output (when Azure secrets are configured): mirrored ACR images for Azure promotion flows

## Choose Release Type

| Type | When to use |
|------|-------------|
| `patch` | bug fixes, docs-only updates, no meaningful feature expansion |
| `minor` | new features/capabilities, backward-compatible behavior additions |
| `major` | breaking changes, removed/changed contracts |

## GitHub Prerequisites (Required)

Configure these repository secrets for `.github/workflows/release.yml`:

- none required for GHCR publishing (workflow uses `GITHUB_TOKEN`)

GitHub requirements:

- Environment named `release` (used by `.github/workflows/release.yml`)
- `gh` CLI authenticated for local verification helpers (`gh auth status`)

Optional repository variable:

- `ACR_NAME` (target Azure Container Registry for optional ACR mirroring; no public default)

## Azure Prerequisites (Optional, ACR Mirror + Azure Promotion)

If you want release workflow ACR mirror output and `deploy:release` Azure promotion, configure:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Service principal requirements (optional Azure path):

- Federated credential for this GitHub repo/environment workflow (OIDC)
- `AcrPush` role on your target ACR

Frontend runtime auth variables (set in deploy-time env when Entra login is expected):

- `VITE_AUTH_MODE` (`entra` or `none`; defaults to `none`)
- `VITE_ENTRA_CLIENT_ID`
- `VITE_ENTRA_API_SCOPE`
- `VITE_ENTRA_AUTHORITY` or `VITE_ENTRA_TENANT_ID`
- optional: `VITE_ENTRA_REDIRECT_URI`, `VITE_ENTRA_POST_LOGOUT_REDIRECT_URI`, `VITE_API_URL`, `VITE_API_TIMEOUT_MS`

Important:
- release frontend images are runtime-configurable for `VITE_*` values.
- `deploy:env` only syncs frontend `VITE_*` keys that are explicitly present in your env file; omitted keys keep their existing Container App values.
- when frontend auth resolves to `VITE_AUTH_MODE=entra`, deploy tooling validates required Entra runtime keys and fails fast if they are missing from both env input and current frontend app config.
- when frontend auth resolves to `VITE_AUTH_MODE=entra`, deploy tooling binds a disabled placeholder for the frontend proxy API key. The browser must use the Entra bearer token path; anonymous same-origin `/api/*` calls should return 401.
- if a `VITE_*` key is omitted on first deployment, frontend entrypoint defaults still apply (for example `VITE_AUTH_MODE=none`).

## 1) Preflight (Required)

Run from repo root:

```bash
bash scripts/release_preflight.sh
```

If there are pending commits for release notes, finish and push them first.

Optional helper (prints the full ordered command list used in this runbook):

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
- `charts/pipelinehealer/Chart.yaml` (`version` + `appVersion`)
- `CHANGELOG.md` (moves Unreleased notes into new `## [vX.Y.Z] - YYYY-MM-DD` section)

Important:
- do not push or publish a release tag until this command has created the matching `## [vX.Y.Z] - YYYY-MM-DD` section in `CHANGELOG.md`
- the release workflow extracts notes from that exact section and will fail if the notes still only live under `## [Unreleased]`

## 4) Validate Generated State

```bash
bash scripts/check_version_sync.sh
```

Recommended sanity checks:

```bash
python3 -m pytest backend/tests/test_phase2_security.py::test_api_routes_allow_development_without_key -q
cd frontend && bun run build && cd ..
```

Deploy-warning QA gate (required before tagging):

1. Run full deploy and capture warnings:
```bash
bash scripts/ph.sh deploy
```
2. If warnings appear, classify them as:
   - fixed in-scope (must be resolved before tag), or
   - tracked upstream/transient with explicit backlog/issue linkage.
3. Verify warning debt status is documented in:
   - `docs/FUTURE_PLAN.md` (backlog status)
   - `CHANGELOG.md` (`Unreleased` entry)
4. Historical warning exceptions must remain explicitly documented with linked issue IDs and a target version for closure (example legacy tracker: [#17](https://github.com/Canepro/pipelinehealer/issues/17)).

## 5) Commit, Tag, Push

```bash
git add VERSION backend/pyproject.toml frontend/package.json charts/pipelinehealer/Chart.yaml CHANGELOG.md
git commit -m "chore(release): vX.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main --follow-tags
```

Replace `X.Y.Z` with the generated version.

Before tagging, double-check:
- `CHANGELOG.md` contains `## [vX.Y.Z] - YYYY-MM-DD`
- `## [Unreleased]` has already been reset by `scripts/release.sh`
- the commit you are tagging includes both the version-file bump and the changelog section

### Protected `main` fallback

If `git push origin main --follow-tags` is blocked by branch protection, use a release branch and PR:

```bash
git checkout -b release/vX.Y.Z
git push origin release/vX.Y.Z
gh pr create --base main --head release/vX.Y.Z --title "chore(release): vX.Y.Z"
git push origin vX.Y.Z
```

Recommended sequence when branch protection is active:

1. Push the branch first.
2. Open the PR and wait for the repository's attached review agents/bots to publish their review comments.
3. Do not tag yet. Wait until attached review agents/bots appear to be finished commenting, then address review comments, resolve review threads, and re-run the relevant checks.
4. Confirm the release-branch HEAD is the reviewed commit you actually want to ship. The tag must point at this post-review commit, not at an earlier pre-review candidate.
5. If you need deployment before PR merge, push the release tag from that reviewed release-branch commit to `origin` (for example: `git push origin vX.Y.Z`) and continue with release verification + Azure promotion.
6. Merge the PR after checks are green, then delete the branch and sync local `main`.

Practical note:
- GitHub can briefly report "base branch policy prohibits the merge" or block admin merge while review threads remain unresolved. Treat that as expected policy lag, not as a signal to bypass review discipline.
- If comments land after a tag is already published and they require code changes, do not reuse the existing tag. Cut a new patch release from the corrected commit instead.

## 6) Verify Published Release

Run the automated verifier:

```bash
bash scripts/release_verify.sh vX.Y.Z
```

`scripts/release_verify.sh` checks:
- remote tag exists
- GitHub release exists and includes `release_images.md`
- release notes include `## Container Images`
- release workflow run for the tag commit succeeded (unless `--skip-workflow-check` is provided)
- anonymous GHCR pullability for backend/frontend (`vX.Y.Z`, `X.Y.Z`, and digests) and Helm chart `X.Y.Z`

Optional fallback/manual checks:
- if `gh` API is unavailable in your environment, run `bash scripts/release_verify.sh vX.Y.Z --skip-workflow-check` and manually confirm the release workflow run is green.
- in Actions logs, confirm `Verify GHCR anonymous pullability` is passed.

Optional Azure checks:
1. Confirm ACR has both semver tags for backend/frontend:

```bash
az acr repository show-tags -n <acr-name> --repository pipelinehealer-backend --orderby time_desc -o tsv | head
az acr repository show-tags -n <acr-name> --repository pipelinehealer-frontend --orderby time_desc -o tsv | head
```

2. Deploy released ACR images to Azure Container Apps:

```bash
bash scripts/ph.sh deploy:release --release-version vX.Y.Z
bash scripts/ph.sh status
```

Production hardening option:

```bash
bash scripts/ph.sh deploy:release --release-version vX.Y.Z --secure-secrets
```

3. If Entra auth is expected, verify frontend runtime auth config after deploy:

```bash
FRONTEND_URL="https://<frontend-fqdn>"
curl -fsSL "${FRONTEND_URL}/runtime-config.js" | rg 'VITE_AUTH_MODE|VITE_ENTRA_CLIENT_ID|VITE_ENTRA_API_SCOPE'
```

Expected for Entra-enabled release: `VITE_AUTH_MODE: "entra"` with matching Entra keys.

### Release PR close-out

Before merging the release PR, leave one short PR comment that records:
- the release tag and workflow run used for publish
- whether ACA deploy already happened
- the live backend `/health` version and latest backend/frontend ACA revisions
- whether `main` is merely catching up to an already-live release or introducing new post-tag follow-up commits

## 7) Post-Release

Keep `## [Unreleased]` ready for next cycle:
- add new entries as work lands
- avoid batching massive undocumented changes

Complete the release cleanup:

1. Merge the release PR.
2. Confirm the remote release branch is deleted.
3. Sync local `main` to `origin/main`.
4. Verify `git status --short` is empty.

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

1. `bash scripts/release_preflight.sh`
2. update `CHANGELOG.md` Unreleased
3. `bash scripts/release.sh minor` (or patch/major)
4. `bash scripts/check_version_sync.sh`
5. sanity test/build
6. commit + tag + push `--follow-tags`
7. `bash scripts/release_verify.sh vX.Y.Z`
