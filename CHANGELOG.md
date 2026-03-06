# Changelog

<!-- LAST_VERIFIED: 6793d7f -->

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this repo uses Semantic Versioning.

## [Unreleased]

### Added

- `b5d6a5b` Added the reference Azure Function receiver for Assign-to-Agent webhook delivery, with authenticated handoff ingress, structured logging, and a low-cost deployment-managed gateway boundary.
- `4048c03`, `c73337d`, `a01bc4f` Added first-wave outbound notification adapters (`webhook`, `rocketchat_webhook`, `slack_webhook`, `teams_webhook`) plus operator-facing receiver/integration health visibility in Settings and Control Center.
- `bb2c6e6` Added session-first admin loading for Settings and Control Center so signed-in operators do not have to re-trigger login intent on each admin surface.
- `6793d7f` Added notification target setup guidance in Settings, generating valid `NOTIFY_TARGETS_JSON` examples without persisting downstream sink secrets into generic runtime settings.
- Current working tree: added SMTP-backed `email` notification delivery for the reference receiver, with transport health validation, deployment-managed SMTP settings, and setup guidance aligned across Settings, API docs, and operator runbooks.

### Changed

- `4048c03`, `a01bc4f` Extended the operator-control UI and docs around startup-managed outbound integration boundaries, keeping secret-bearing receiver and notification endpoints deployment-managed while surfacing their readiness in product surfaces.
- `d295b29` Carried forward the `v0.4.0` release sync commit onto `main` after the protected-branch release cut so tag/release lineage stayed reproducible.
- `718d86a` Updated the README media set, demo screenshots, architecture diagram, roadmap status, and deployment examples to match the current outbound integration gateway model and live operator UI.
- Current working tree: clarified CLI/API/runtime guidance so deployment-managed SMTP and receiver-backed notification routing stay explicit rather than leaking into generic runtime settings.

## [v0.4.0] - 2026-03-06

### Added

- `f25afaa`, `628457f`, `7ecdf8a`, `9477f08` Expanded the operator control plane with settings provenance metadata, Assign-to-Agent setup/test flows, and Jenkins bridge setup/test guidance.
- `39aec90` Settings and Control Center now expose stronger provenance for startup-managed fields, including sensitive presence-only signals and derived startup dependency status for Assign-to-Agent webhook, GitHub auth wiring, and OpenAI-compatible API key configuration.

### Changed

- `70a30ef`, `acf955f`, `a9488fb`, `41575cf` Established the `v0.4.0` control-plane baseline and aligned the release planning/docs lineage from the `v0.3.3` baseline.
- `39aec90` Normalized operator-facing provenance language around `GET /api/settings`: `env` now represents portable startup-managed config rather than implying a specific deployment adapter such as ACA `secretref`.
- `e0e9903` Reframed the landing page, app shell, Settings copy, README, demo script, and architecture diagrams around PipelineHealer as an OSS-first pipeline remediation control plane rather than a hackathon-only CI demo.

### Fixed

- `db215f0` Fixed the workflow shutdown task-map mutation race during close/shutdown handling.
- `6b9d82e` Added deterministic diagnosis for GitHub-hosted runner acquisition failures so those activities no longer collapse to `failure_type: not determined`.

## [v0.3.3] - 2026-03-05

- `1a0e13a` Landing page polish: scroll entrance animations (framer-motion), animated capability counters strip, multi-agent pipeline architecture diagram, and mobile-responsive layout improvements.
- Release-lineage reference for `v0.3.3` scope continuity: `0bbfec5`.

## [v0.3.2] - 2026-03-05

### Fixed

- `8ca4b99` Prevented `deploy:env` from clearing existing frontend runtime config when newer `VITE_*` keys are omitted from `backend/.env` during Azure env sync (issue [#55](https://github.com/Canepro/pipelinehealer/issues/55)).
- Added Entra runtime guardrail for Azure deploy env sync: when frontend auth resolves to `VITE_AUTH_MODE=entra`, deployment now fails fast if required `VITE_ENTRA_*` keys are missing from both env input and existing frontend app config.

### Changed

- Release-scope commit references for `v0.3.2` prep and post-`v0.3.1` lineage: `1c1f8fc`, `2064b04`, `f73987f`, `f361493`.
- Stabilized release guardrails for this cut: improved baseline-tag selection and fixed release-workflow verification pagination handling (`e6d76cc`, `0bb6f99`).

## [v0.3.1] - 2026-03-03

### Added

- Added frontend runtime config bootstrap (`/runtime-config.js`) so container deployments can change `VITE_*` values without rebuilding frontend images.
- Added runtime config env sync for Azure deploy automation (`scripts/deploy/redeploy_azure_containerapps.sh`) covering frontend auth/API `VITE_*` keys.

### Changed

- Switched frontend auth/API client config resolution to runtime-first (`window.__PH_RUNTIME_CONFIG__`) with build-time fallback for non-container static builds.
- Updated Helm defaults to expose frontend `VITE_*` runtime env values via chart values/configmaps.
- Updated release workflow to stop enforcing frontend auth build args at image build time.
- Updated operator docs/runbooks/README/CLI to reflect runtime config behavior and runtime verification via `runtime-config.js`.
- Core implementation commit reference: `ef93651`.
- Changelog guardrail alignment commit reference: `d120386`.
- Additional guardrail alignment commit reference: `2d75f85`.
- Release-scope carry-forward commit references (post-`v0.2.11` lineage guardrail): `eaa47f7`, `44effc3`, `5afcdf6`, `9daf25e`, `c6e47b9`, `30d0daf`, `78822fc`, `4ec8637`, `1f53853`.

## [v0.3.0] - 2026-03-02

### Added

- Added `scripts/release/check_ghcr_pullability.sh` to validate anonymous GHCR pullability for backend/frontend release tags and digests, plus Helm OCI chart tags.
- Added `scripts/release_preflight.sh` to enforce release preflight guardrails (clean tree/main branch/version sync/release scope/changelog readiness) with explicit override flags.
- Added `scripts/release_verify.sh` to automate post-tag release verification (remote tag, release metadata/assets, release workflow success, and GHCR pullability gate replay).
- Added Activity Detail `Copy Context` action that generates an AI-ready handoff bundle with deterministic section ordering, redaction, and a 16KB payload cap.
- Added a visible disabled `Assign to Agent` action in Activity Detail with `Coming Soon` labeling for `v0.3.0` discoverability without backend coupling.

### Changed

- `eaa47f7`, `44effc3`, `a437be5` Aligned roadmap/log verification markers and `v0.3.0`/`v0.3.1` tracking scopes across release planning docs.
- Hardened `.github/workflows/release.yml` to block GitHub release creation when anonymous GHCR pullability fails.
- Updated release documentation/checklist surfaces (`README.md`, `docs/CLI.md`, `docs/RELEASE_RUNBOOK.md`, `scripts/release_checklist.sh`) to use the new preflight and post-release verification automation paths.
- Qualified frontend Docker base images (`docker.io/oven/bun:1`, `docker.io/library/nginx:alpine`) to avoid short-name resolution failures in mixed Docker/Podman/WSL deploy environments.
- Hardened Azure full deploy image retagging to auto-detect local compose build image names across dash/underscore and optional `localhost/` prefixes before pushing to ACR, and sanitized ACR prune digest parsing to avoid malformed delete refs.

## [v0.2.11] - 2026-02-23

### Changed

- `9f93ad4` Synced roadmap/log tracking docs to mark `v0.2.10` as released baseline and close `BL-037` tracking.
- Separated runtime execution controls so `AUTO_APPLY_REMEDIATION` gates dry-run vs execution while `AUTO_CREATE_PR`, `AUTO_CREATE_ISSUE`, and `AUTO_RETRY_WORKFLOW` independently gate output actions.
- Extended Settings + Control Center runtime policy surfaces to expose and persist the new action toggles and `heal_mode=freestyle`.
- Updated `scripts/ph.sh rollout:canary` to enforce explicit conservative canary defaults (issue-first, no retry) under the new control model.
- Updated operator docs (`README`, `API`, `CLI`, `LOCAL_DEMO_RUNBOOK`, Kubernetes runbook, settings feature guide, future plan) for the `v0.2.11` control-surface and portability clarifications.

### Fixed

- Stabilized `backend/tests/test_agent_factory.py` compatibility tests by stubbing `agent_framework` through `sys.modules`, avoiding CI-only import failures caused by upstream observability dependency mismatch during monkeypatch resolution.
- Added regression coverage for settings persistence of new runtime action toggles and orchestrator dry-run gating driven by `AUTO_APPLY_REMEDIATION`.

## [v0.2.10] - 2026-02-23

### Changed

- Documented Kubernetes distribution risk for open-source adopters: Helm success alone is not sufficient when image pullability fails (`ErrImagePull` / `ImagePullBackOff`, registry token `401`/`403`).
- Added explicit random-user pullability gate language to `README.md` and `docs/KUBERNETES_HELM_RUNBOOK.md`.
- Added release verification guidance in `docs/RELEASE_RUNBOOK.md` to block portability claims when clean-cluster image pulls fail.
- Hardened `settings:persist` repo-scope behavior: `--repos` now aliases safe additive mode (`--repos-add`), with explicit `--repos-remove` and destructive `--repos-replace` modes.
- Added backend URL validation in `scripts/ph.sh` settings persistence paths to avoid malformed API targets (for example `https:///api/...`) when Azure FQDN resolution fails.

### Fixed

- Closed documentation ambiguity where Kubernetes/Helm could appear generally ready despite registry access constraints; now tracked via issue [#37](https://github.com/Canepro/pipelinehealer/issues/37).
- Prevented accidental `PH_ALLOWED_REPOS` truncation during partial settings updates by introducing merge/remove semantics and explicit replace mode.

## [v0.2.9] - 2026-02-20

### Added

- `8aa5d91` Added secure Azure deployment mode (`deploy:env --secure-secrets`) that maps sensitive runtime settings to Container Apps `secretRef` values instead of plaintext environment values.
- `4387443` Added hybrid external-diagnostics ingestion mode (`GH_AW_INGESTION_MODE=hybrid`) so the same activity can include both passive GH-AW findings and GitHub MCP context.

### Changed

- `4387443` Expanded runtime validation and settings surfaces to support `gh_aw_ingestion_mode=hybrid` across backend API/config validation, `scripts/ph.sh`, and Settings UI.
- `4387443` Updated operator docs, API docs, CLI docs, and feature guides to explain passive vs direct MCP vs hybrid source-selection behavior.
- `f9eb981` Aligned roadmap baseline/tracking docs to the `v0.2.8` submission baseline prior to `v0.2.9` cut.

### Fixed

- `dd885d8` Fixed GH-AW passive backfill matching when CI Doctor issues use unexpected labels by adding bounded unlabeled-issue fallback scanning and regression coverage.
- `ec6dd9d` Fixed CI shellcheck false-positive handling around secret-ref mapping in deploy scripts.

## [v0.2.8] - 2026-02-20

### Changed

- `2882470` Clarified `docs/LEARNING_SYSTEM_PLAN.md` with plain-language behavior, explicit non-goals, and a quick verification checklist for first-time operators.
- `5ef9d80` Clarified learning-system behavior to explicitly note that GitHub issue comments are evidence but are not auto-ingested into feedback.
- `f1bce38` Refreshed `docs/LEARNING_SYSTEM_PLAN.md` verification marker after learning-plan clarity update.
- `b5cbb7e` Re-evaluated `v0.3.0` roadmap scope to add `BL-025` (structured GitHub issue accuracy comment ingestion into `learning/feedback`) and aligned learning plan immediate-next scope.
- `8980118` Updated `demo-repo/README.md` for current demo timings/strict mode, clearer ci-doctor/MCP interpretation, and practical demo-artifact housekeeping commands.
- `b715e90` Added beginner-friendly onboarding clarity and explicit platform support guidance in `README.md`, `docs/CLI.md`, and `docs/LOCAL_DEMO_RUNBOOK.md`.
- `75ebffd` Tightened first-time operator onboarding flow with concrete verification steps and reduced command ambiguity.
- `ca5b69c` Reordered README information architecture and expanded hackathon status/collaboration guidance for submission-phase readability.
- `c07f9c3` Fixed Entra auth release drift by validating/injecting frontend `VITE_*` build args in release workflow, plus clearer UI/runbook guidance.
- `a18e44e` Clarified required-vs-optional auth setup paths for repo adopters and added explicit "Do I Need Entra?" guidance.
- `ac2b1d4` Clarified that `AUTH_MODE=hybrid` supports both key and Entra session auth simultaneously and is the recommended testing/migration posture.
- `6da0e29` Hardened AKS/Kubernetes auth runbooks with build-vs-runtime guardrails and post-deploy auth verification.
- `facb20d` Removed stale hardcoded release-version examples in docs and normalized release commands to `vX.Y.Z` where appropriate.

## [v0.2.7] - 2026-02-19

### Added

- `75c3871` Added `deploy:release` Azure deployment path to promote existing ACR release images by immutable digest (no local build/push required).

### Changed

- `75c3871` Updated operator docs/runbooks to recommend release-driven Azure deploys (`deploy:release --release-version vX.Y.Z`) as the default production path.
- `4d801e0` Refreshed submission freeze tracking and the video demo runbook (`docs/HACKATHON_LOG.md`, `docs/DEMO_SCRIPT.md`) for the `v0.2.6` baseline, including release-driven pre-record deploy guidance.
- `a80c271` Refreshed `docs/DEMO_SCRIPT.md` verification marker after submission-runbook updates.
- `308b862` Polished README submission-phase positioning, clarified remediation language, and added an explicit `v0.2.6` baseline section.
- `9e74863` Updated README architecture Mermaid diagram to match current runtime behavior (background diagnostics backfill, GH-AW sources, optional MCP enrichment).
- `695834f` Hardened `demo:e2e` verification with configurable CI-signal waits, optional strict gating, on-demand diagnostics backfill, and clearer passive-vs-direct MCP summary output.
- `695834f` Clarified Activity Detail MCP observability copy so passive GH-AW attribution and direct MCP tool-call telemetry are clearly differentiated.
- `6608f3a` Reworked Activity Detail information hierarchy with a top-level `PipelineHealer Decision` summary that combines diagnosis and remediation outcome, and moved deep model/evidence panels under a dedicated technical enrichment section.
- `d13bd12` Promoted `v0.2.7` submission baseline references across `README`, `CLI`, demo/runbook docs, and `ph.sh` operator help examples.
- `d13bd12` Added explicit MCP interpretation guidance for non-expert operators (enabled vs selected path vs direct tool invocation) across README, feature docs, and runbooks.
- `d13bd12` Updated roadmap/index tracking to close `v0.2.7` as submission-readiness/operator-clarity scope and return active planning to `v0.3.0`.

## [v0.2.6] - 2026-02-19

### Added

- `d3cbf8a` Added verification feedback capture API (`POST /api/settings/learning/feedback`) with durable per-activity verification metadata/history and audit entries.
- `d3cbf8a` Added verification-aware learning readiness gates (minimum verified sample + verification pass-rate) and surfaced verification metrics in learning queue payloads.
- `d3cbf8a` Added diagnostics source-selection transparency metadata (`source_selection_path`, `source_selection_reason`) and surfaced this in Activity Detail.

### Changed

- `534c216` Added operator-focused inline comments across Helm values/templates to improve first-time deploy clarity without changing chart behavior.
- `157ef45` Added operator-focused inline comments to `docker-compose.yml`, `azure.yaml`, and CI workflow YAML for clearer local/ops intent.
- `7206832` Synced `v0.2.6` roadmap/backlog tracking status, linked/closed BL issues (`#25`-`#28`), and refreshed stale `LAST_VERIFIED` markers in edited docs.
- `29261de` Backfilled `Unreleased` changelog coverage for in-progress `v0.2.6` work so release-scope tracking remains complete.
- `2356c0c` Reworked Activities desktop table layout to remove horizontal rail/slide dependency so row actions remain reachable while scanning long activity histories.

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
- `8b082a1` Aligned release docs and roadmap to an explicit `v0.2.3` QA freeze (no new feature scope; warning-debt closure + QA gates only).
- `8b082a1` Added release warning-triage guidance to runbooks and improved Control Center/Settings readability with structured summary rows and workflow-oriented UI cues.
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
