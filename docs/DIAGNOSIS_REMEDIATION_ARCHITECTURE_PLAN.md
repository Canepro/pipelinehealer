<!-- LAST_VERIFIED: aec8f84 -->

# Diagnosis and Remediation Architecture Plan

This document defines the architecture direction for the next improvement pass on PipelineHealer's diagnosis and remediation pipeline.

Tracking:

- Target version: `v0.6.0`
- Change type: `minor`
- Changelog section: `Changed`
- Status: in progress

It exists to keep the implementation:

- OSS-first and deployment-portable
- schema-driven instead of prompt-driven
- deterministic-first where evidence is specific
- LLM-assisted where bounded reasoning or patch drafting adds value
- auditable and eval-gated before rollout

## Why This Plan Exists

Current behavior is directionally correct, but the contract between diagnosis, remediation planning, and generated artifacts is too loose.

Observed gaps:

- diagnosis often produces high-level prose where remediation needs typed fields
- deterministic generators already expect structured values that diagnosis does not always populate
- some auto-generated issues and PRs are therefore generic even when the failure class is known
- model strength alone will not fix that contract gap

The fix is architectural: tighten structured interfaces first, then use stronger models only for bounded work.

## Product Alignment

This plan follows the standing product contract in:

- `README.md`
- `docs/OPERATOR_CONTROL_PLANE.md`
- `docs/LLM_AND_AGENT_RUNTIME.md`
- `docs/LEARNING_SYSTEM_PLAN.md`

Key alignment rules:

- Azure Container Apps remains a reference deployment, not the product boundary
- provider-specific runtime choices must adapt into one shared diagnosis/remediation contract
- configured vs effective behavior must remain explicit
- policy and auditability must remain first-class

## Design Goals

1. Improve diagnosis quality without overfitting to one deployment.
2. Improve deterministic suggestion quality for all supported failure types.
3. Improve PR usefulness by generating code-focused edits only when the scope is bounded and validated.
4. Preserve issue-first behavior for ambiguous, risky, or weakly grounded cases.
5. Add an eval-backed rollout path so model or prompt changes do not silently degrade quality.

## Non-Goals

- no provider lock-in in core contracts
- no deployment-specific logic in the diagnosis or remediation core
- no hidden autonomous policy changes
- no model swap as the primary solution
- no unbounded AI-generated patches outside explicit scope and validation rules

## Recommended Architecture

The pipeline should move toward this shape:

1. Evidence normalization
   - log analyzer extracts relevant log lines, failing step, command context, and provider metadata

2. Deterministic structured extraction
   - failure-class-specific extractors produce typed evidence fields before any LLM call

3. Diagnosis contract assembly
   - common diagnosis fields plus failure-type-specific `error_details`

4. LLM refinement
   - the LLM fills only missing structured fields, resolves ambiguity, or drafts bounded explanations

5. Remediation planning
   - remediation generators consume typed fields, not freeform prose

6. Patch drafting
   - a stronger coding model may be used only for bounded file edits after target files and intended edit class are known

7. Validation
   - repo-local or provider-specific checks confirm that the proposed patch or issue is grounded

8. Artifact creation
   - PR, issue, retry, or skip, with explicit reason codes and evidence links

## Diagnosis Contract

Common diagnosis fields should remain:

- `failure_type`
- `confidence`
- `root_cause`
- `affected_files`
- `is_auto_fixable`
- `suggested_fix`
- `diagnosis_source`
- `error_details`

The contract change is that `error_details` must become failure-type-specific and typed.

### Dependency

Required when available:

- `package_name`
- `package_manager`
- `manifest_file`
- `current_version`
- `required_version`
- `resolution_kind` (`missing`, `version_conflict`, `registry_access`, `image_pull`)

### Lint

Required when available:

- `linter`
- `missing_file`
- `violations`
- `autofix_command`
- `config_file`
- `rule_ids`

### Test

Required when available:

- `test_framework`
- `failed_tests`
- `test_errors`
- `is_flaky`
- `failure_scope` (`test_case`, `suite`, `workflow_step`)
- `suspected_files`

### Timeout

Required when available:

- `timed_out_step`
- `timed_out_job`
- `timeout_minutes`
- `suggested_timeout`
- `resource_signal` (`cpu`, `memory`, `disk`, `network`, `unknown`)
- `likely_fix_kind` (`increase_timeout`, `optimize_step`, `split_job`, `runner_capacity`)

### Build Config

Required when available:

- `config_file`
- `config_error`
- `missing_env_vars`
- `workflow_permissions_fix`
- `permissions`
- `misconfiguration_kind` (`secret`, `env_var`, `workflow_permission`, `file_path`, `rate_limit`, `runner_env`)

## Deterministic vs LLM Responsibilities

Recommended split:

### Deterministic-first

Use deterministic extractors for:

- package/module names
- manifest/config file names
- missing env vars or secrets
- workflow permissions failures
- failing test names when explicitly present
- timeout step/job names
- linter/config signatures

### LLM-assisted

Use the LLM for:

- ambiguity resolution when multiple patterns match
- mapping raw evidence into the typed schema when deterministic parsing is incomplete
- short operator-facing reasoning summaries
- bounded patch drafting once scope is already constrained

### Do Not Ask the LLM To Do

- guess file edits without known target files
- produce unstructured remediation prose in the critical path
- override deterministic evidence without explicit trace markers
- decide policy applicability implicitly

## Model Role Matrix

Model choice should be role-based, not deployment-based.

Recommended roles:

- `analysis`
  - cheaper/faster general model
  - summarize logs and extract candidates

- `diagnosis_refinement`
  - stronger reasoning model
  - fill typed diagnosis fields when deterministic extraction is incomplete

- `patch_drafting`
  - strongest coding-capable model available for the active provider
  - only used after target files, edit kind, and validation plan are known

- `operator_summary`
  - lower-cost model or template path
  - rewrite structured evidence into concise issue/PR text

Important:

- these are internal roles, not provider names
- Azure, OpenAI-compatible, or future providers can map different deployments to the same roles
- this keeps ACA useful without baking ACA assumptions into the product

## Remediation Planning Contract

Remediation generators must consume structured evidence and produce one of:

- `CREATE_PR`
- `CREATE_ISSUE`
- `RETRY_WORKFLOW`
- `SKIP`

They should no longer depend on `suggested_fix` prose for core logic.

### Create PR

Allowed only when:

- target files are known or bounded by allowlist
- intended edit type is known
- validation commands are known
- confidence and policy gates pass

Generated PR plans should contain:

- target files
- edit type (`json_update`, `line_update`, `new_file`, `bounded_patch`)
- validation commands
- fallback behavior if validation fails

### Create Issue

Use when:

- ambiguity remains after structured extraction and LLM refinement
- required context is missing
- patch scope exceeds allowlist or policy
- remediation requires operator-owned secrets or environment knowledge

Issue bodies should be structured from typed fields, not generic templates.

### Retry Workflow

Use only for:

- clearly transient failures
- demo-mode flaky patterns
- policy-allowed transient remediation paths

## PR Patch Drafting Standard

If an LLM is used for code edits, the system should pass:

- the typed diagnosis
- the constrained file set
- the edit intent
- repository-local style or rule constraints
- required validation commands

The LLM output should be treated as a draft patch, not as a decision.

Required safety checks:

- patch stays inside allowed files
- patch matches intended edit class
- validation passes before artifact creation
- trace records show that bounded patch drafting was used

## Evaluation Standard

No rollout should rely on anecdotal improvement.

Build an eval corpus from real PipelineHealer incidents:

- dependency: missing package, version conflict, Docker image pull
- lint: missing config, auto-fixable violations, non-auto-fixable violations
- test: explicit failing test, flaky test, workflow-step failure misclassified as test
- timeout: true timeout, disk exhaustion, OOM-like signal
- build_config: missing secret, workflow permissions, missing file, rate limit, runner issue

Required metrics:

- failure type accuracy
- structured field completeness
- remediation action correctness
- PR usefulness
- issue usefulness
- false-confidence rate
- validation pass rate for bounded patches

Release gate principle:

- model or prompt changes do not ship unless eval results are neutral or improved on the tracked fixture set

## Learning-System Integration

Active learning artifacts should inject structured context before diagnosis or remediation, not freeform prose.

Recommended integration:

1. retrieve matching approved or active playbooks
2. map them into structured context fields
3. allow diagnosis/remediation to reference them explicitly
4. record whether the playbook improved or degraded the outcome

This keeps learning as governed remediation memory instead of ad hoc prompt stuffing.

## OSS and Deployment Portability

This plan must work for:

- local development
- Docker or Podman
- Helm or Kubernetes
- Azure Container Apps
- future provider gateways

Portable rules:

- internal model roles are provider-neutral
- provider adapters translate runtime capabilities into shared role assignments
- capability states remain explicit: configured, provider-ready, operation-compatible, full-capability
- no deployment adapter is allowed to redefine diagnosis or remediation semantics

## Implementation Phases

### Phase 1: Contract Hardening

- define typed `error_details` schema per failure type
- update deterministic extractors to populate those fields
- update API and activity serialization if new fields are surfaced
- add fixture-based tests for structured completeness

### Phase 2: Remediation Generator Alignment

- remove generator dependence on generic prose
- improve issue templates to consume typed evidence
- tighten deterministic PR planning around known edit classes
- replace weak generic auto-fix paths with code-focused bounded edits where safe

### Phase 3: Bounded Patch Drafting

- introduce `patch_drafting` role
- allow stronger coding model use only on bounded edit plans
- add validation and fallback-to-issue behavior
- record trace markers showing when bounded drafting ran

### Phase 4: Eval-Gated Rollout

- build and maintain the incident fixture set
- publish success criteria for role/model changes
- gate rollout on eval performance plus real canary evidence

## Implementation Checklist

Use this checklist for the `v0.6.0` workstream.

### Docs and contract

- [ ] API and activity payload contract updated for new typed diagnosis fields
- [x] runtime docs updated to explain deterministic-first extraction plus bounded patch drafting
- [ ] learning-system docs updated to describe structured retrieval injection

### Diagnosis layer

- [ ] dependency extractor fills manifest, package, and resolution fields
- [ ] lint extractor fills linter, config, rule, and autofix fields
- [ ] test extractor fills framework, failed test names, and error snippets
- [ ] timeout extractor fills job, step, timeout, and resource-signal fields
- [ ] build-config extractor fills missing vars, permissions, file, and config-error fields

### LLM layer

- [ ] diagnosis prompt updated to require failure-type-specific structured JSON
- [ ] parser rejects incomplete or malformed structured payloads cleanly
- [x] role mapping documented for `analysis`, `diagnosis_refinement`, `patch_drafting`, and `operator_summary`

### Remediation layer

- [ ] generators consume typed fields instead of generic `suggested_fix` prose
- [ ] issue templates render typed evidence blocks
- [x] bounded patch drafting path introduced only for safe, known edit classes
- [x] validation and fallback-to-issue behavior implemented for bounded patches

### Evaluation and rollout

- [x] incident fixture set created for dependency, lint, test, timeout, and build-config cases
- [x] eval metrics recorded for classification accuracy, field completeness, action correctness, and validation pass rate
- [x] rollout gates defined for schema changes and model-role changes

## Suggested PR Slices

Recommended PR order for `v0.6.0`:

1. docs + schema contract only
2. deterministic extraction and serialization
3. remediation generator alignment
4. bounded patch drafting path
5. eval harness and rollout gate wiring

## Recommended Immediate Next Step

Before implementation:

1. update the diagnosis prompt and parser contract to require typed fields by failure class
2. align deterministic generators with those fields
3. add eval fixtures for current generic failure paths

This is the smallest path that improves output quality while preserving the existing OSS-first control-plane model.
