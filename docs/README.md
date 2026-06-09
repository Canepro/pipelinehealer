# Docs Index

<!-- LAST_VERIFIED: bd24039 -->

Use this index to find the canonical doc quickly. If a topic appears in both an active doc and `docs/archive/`, the active doc wins.

## Start Here

- `../README.md` - product north star, current scope, healing contract, quick start, and deployment overview
- `features/README.md` - feature-by-feature operator walkthroughs
- `runbooks/LOCAL_DEMO_RUNBOOK.md` - full local and Azure evaluation path
- `../integrations/jenkins-bridge/README.md` - Jenkins bridge install kit and supported rollout pattern

If you are validating the runtime configuration model specifically, start with:
- `architecture/OPERATOR_CONTROL_PLANE.md` - configured vs effective runtime behavior, provenance, and startup override boundaries
- `features/03-settings-and-policy-controls.md` - Settings UI workflow, setup checklist, secret handling, and compatibility notes

## Reference

- `reference/API.md` - backend API contracts, auth, data models, runtime settings, and write-only secrets endpoints
- `reference/CLI.md` - canonical `bash scripts/ph.sh` reference, including env-sync compatibility flows around deprecated `settings:persist`

## Runbooks

- `runbooks/DEMO_SCRIPT.md` - concise recording and narration guide
- `runbooks/LIFECYCLE_E2E_VERIFICATION.md` - artifact lifecycle loop verification (markers, dedup, green-close)
- `runbooks/LOCAL_DEMO_RUNBOOK.md` - end-to-end local and Azure operator runbook
- `runbooks/LOGS_AND_INVESTIGATION.md` - troubleshooting and evidence collection guide
- `runbooks/KUBERNETES_HELM_RUNBOOK.md` - secondary Helm/Kubernetes deployment path
- `runbooks/RELEASE_RUNBOOK.md` - release prep, publish, verify, and rollback
- `runbooks/PRODUCTION_PROMOTION_RUNBOOK.md` - reviewed release promotion to the production Azure Container Apps lane
- `runbooks/MODEL_PROVIDER_SWITCH_RUNBOOK.md` - auditable provider switch and rollback flow
- `runbooks/PREDEPLOY_PLACEHOLDER_AUDIT.md` - pre-deploy stop-ship checklist

## Architecture

- `architecture/OPERATOR_CONTROL_PLANE.md` - north star product contract for configuration, provenance, runtime-save semantics, and startup override boundaries
- `architecture/MODEL_PROVIDER_STRATEGY.md` - provider-portable model backend posture
- `architecture/LLM_AND_AGENT_RUNTIME.md` - validated runtime and degraded-mode behavior
- `architecture/LEARNING_SYSTEM_PLAN.md` - learning queue lifecycle and activation rules

## Story And Evidence

- `case-studies/release-tag-mismatch-22163136636.md` - concrete incident write-up
- `screens/` - current hosted UI screenshots and architecture assets
- `../CHANGELOG.md` - shipped release history

Local closeout reports and deployment evidence belong in untracked `reports/`.
Only promote a report into `docs/` after removing machine paths, personal
accounts, tenant identifiers, secret metadata, private registry names, and
operator-only deployment details.

## Project Tracking

- `HACKATHON_LOG.md` - active hackathon planning and execution log
- `FUTURE_PLAN.md` - version-tracked roadmap and forward-looking work
- `archive/README.md` - historical design notes and superseded implementation trackers

## Repo Guidance

- `../CONTRIBUTING.md` - contributor workflow and quality bar
- `../AGENTS.md` - repo-specific operating rules for maintainers and agents
- `../SECURITY.md` - vulnerability reporting and secret hygiene policy
