# Docs Index

<!-- LAST_VERIFIED: 3116334 -->

Use this index to find the right doc quickly.

### Tier 1 — User-Facing (update every feature PR)

- `../README.md` — public-facing project overview, features, env vars, setup
- `features/README.md` — dedicated feature-by-feature operator/user guides
- `API.md` — full API reference: endpoints, authentication, data models, best practices
- `../CONTRIBUTING.md` — contributor workflow, quality gates, and docs update policy
- `../SECURITY.md` — vulnerability reporting and secret hygiene policy

### Tier 2 — Operator (update on infra/config changes)

- `CLI.md` — canonical `scripts/ph.sh` CLI reference: all commands, flags, error handling, env overrides
- `LOGS_AND_INVESTIGATION.md` — dedicated troubleshooting guide for logs, activity correlation, and incident playbooks
- `DEMO_SCRIPT.md` — single-file recording checklist and 2-minute narration script
- `LOCAL_DEMO_RUNBOOK.md` — full local and Azure E2E operator runbook
- `MODEL_PROVIDER_STRATEGY.md` — Azure-first but provider-portable model backend strategy
- `MODEL_PROVIDER_SWITCH_RUNBOOK.md` — auditable provider switching and rollback playbook
- `LEARNING_SYSTEM_PLAN.md` — learning queue lifecycle, governance model, and activation safety rules
- `KUBERNETES_HELM_RUNBOOK.md` — Helm-based Kubernetes deployment target (secondary to Azure)
- `RELEASE_RUNBOOK.md` — release prep, semver bump, tag/publish verification, and rollback guidance
- `PREDEPLOY_PLACEHOLDER_AUDIT.md` — pre-deploy stop-ship checklist

### Tier 3 — Internal/Transient (author discretion; archive post-submission)

- `HACKATHON_LOG.md` — current phase status, submission checklist, and milestone history
- `FUTURE_PLAN.md` — version-targeted roadmap (current active target: `v0.3.2`; latest released baseline: `v0.3.1`)
- `UI_PLAN.md` — UI maturity plan, principles, and weekly tracking through submission
- `AGENT_HANDOFF_CONTEXT_MINISPEC.md` — draft design for Activity Detail `Copy Context` + optional `Assign to Agent` handoff integration
- `GH_AW_IMPLEMENTATION_TRACKER.md` — gh-aw research summary, Layer 1/2 checklists, decision log, and evidence
- `JENKINS_BRIDGE_TECHNICAL_DESIGN.md` — design draft for `BL-034` Jenkins bridge ingestion (payload/auth/replay/API/tests)
- `case-studies/` — real incident writeups showing detection, classification, and remediation outcomes
  - `case-studies/release-tag-mismatch-22163136636.md` — release tag/version mismatch incident handled by PipelineHealer
- `screens/` — versioned UI proof screenshots used by Week 2 and Week 3 evidence checkpoints

### Repo-Level

- `../AGENTS.md` — concise repo operating rules for agents and maintainers (includes doc update checklist)
