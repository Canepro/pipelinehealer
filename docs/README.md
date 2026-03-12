# Docs Index

<!-- LAST_VERIFIED: d555eef -->

Use this index to find the right doc quickly.

## Current UI Surfaces

These stable screenshots reflect the current hosted operator experience and are safe to reuse in docs and demo prep:

![Dashboard — KPIs, safety framing, and explainability snapshot](screens/dashboard-current.png)
![Activity Detail — incident record, verification workspace, and remediation evidence](screens/activity-detail-current.png)
![Control Center — governance posture, learning explainability, trust ops, and investigation shortcuts](screens/control-center-current.png)
![Settings — runtime policy, provider wiring, and Assign-to-Agent status](screens/settings-current.png)

### Tier 1 — User-Facing (update every feature PR)

- `../README.md` — public-facing project overview, features, env vars, setup
- `OPERATOR_CONTROL_PLANE.md` — product-level contract for configuration, provenance, and operator-surface design
- `features/README.md` — dedicated feature-by-feature operator/user guides
- `API.md` — full API reference: endpoints, authentication, data models, best practices
- `../CONTRIBUTING.md` — contributor workflow, quality gates, and docs update policy
- `../SECURITY.md` — vulnerability reporting and secret hygiene policy

### Tier 2 — Operator (update on infra/config changes)

- `CLI.md` — canonical `scripts/ph.sh` CLI reference: all commands, flags, error handling, env overrides
- `LOGS_AND_INVESTIGATION.md` — dedicated troubleshooting guide for logs, activity correlation, and incident playbooks
- `DEMO_SCRIPT.md` — single-file recording checklist and 2-minute narration script
- `LOCAL_DEMO_RUNBOOK.md` — full local and Azure E2E operator runbook
- `MODEL_PROVIDER_STRATEGY.md` — reference Azure path plus provider-portable model backend strategy
- `LLM_AND_AGENT_RUNTIME.md` — validated LLM runtime behavior, degraded-mode contract, and Azure endpoint/model guidance
- `LLM_PROVIDER_RESEARCH_AND_PLAN.md` — source-backed provider research and the resulting PipelineHealer implementation direction
- `MODEL_PROVIDER_SWITCH_RUNBOOK.md` — auditable provider switching and rollback playbook
- `LEARNING_SYSTEM_PLAN.md` — learning queue lifecycle, governance model, and activation safety rules
- `KUBERNETES_HELM_RUNBOOK.md` — Helm-based Kubernetes deployment target (secondary to Azure)
- `RELEASE_RUNBOOK.md` — release prep, semver bump, tag/publish verification, and rollback guidance
- `PREDEPLOY_PLACEHOLDER_AUDIT.md` — pre-deploy stop-ship checklist
- `../infra/terraform/README.md` — manual Terraform equivalent of the Azure reference Bicep stack
- `../integrations/jenkins-bridge/README.md` — reusable Jenkins bridge install kit, supported rollout patterns, and failure-capture guidance

### Tier 3 — Internal/Transient (author discretion; archive post-submission)

- `HACKATHON_LOG.md` — current phase status, submission checklist, milestone history, and freeze tracking notes
- `FUTURE_PLAN.md` — version-targeted roadmap and release archaeology
- `DIAGNOSIS_REMEDIATION_ARCHITECTURE_PLAN.md` — implementation contract for schema-first diagnosis/remediation hardening and bounded patch drafting
- `UI_PLAN.md` — UI maturity plan, principles, and weekly tracking through submission
- `AGENT_HANDOFF_CONTEXT_MINISPEC.md` — draft design for Activity Detail `Copy Context` + optional `Assign to Agent` handoff integration
- `GH_AW_IMPLEMENTATION_TRACKER.md` — gh-aw research summary, Layer 1/2 checklists, decision log, and evidence
- `JENKINS_BRIDGE_TECHNICAL_DESIGN.md` — Jenkins bridge design and implementation-reference notes (`BL-034`)
- `case-studies/` — real incident writeups showing detection, classification, and remediation outcomes
  - `case-studies/release-tag-mismatch-22163136636.md` — release tag/version mismatch incident handled by PipelineHealer
- `screens/` — versioned UI proof screenshots used by Week 2 and Week 3 evidence checkpoints

### Repo-Level

- `../AGENTS.md` — concise repo operating rules for agents and maintainers (includes doc update checklist)
