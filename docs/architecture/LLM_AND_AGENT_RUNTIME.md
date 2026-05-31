# LLM and Agent Runtime

<!-- LAST_VERIFIED: 044aa39 -->

This document is the operator-facing contract for how PipelineHealer uses LLMs and agents at runtime.

Use it when you need to answer:
- what "healthy" actually means for the LLM path
- which Azure endpoint/model combinations were validated
- what happens when the LLM path degrades
- what is and is not supported in model routing today
- how learning ops should evolve instead of staying a thin recurring-pattern queue
- how external agent handoffs differ from model-runtime routing

## Current Runtime Model

PipelineHealer has multiple agent responsibilities:
- log analysis
- diagnosis
- remediation
- bounded patch drafting
- orchestration

Today, one LLM provider is active per runtime:
- `azure_openai`
- `openai_compatible`
- `codex_app_server`
- `custom` (scaffold only; not production-capable)

Task-level routing is supported inside Azure OpenAI and OpenAI-compatible
providers:
- `LLM_MODEL_ANALYSIS`
- `LLM_MODEL_DIAGNOSIS`
- `LLM_MODEL_REMEDIATION`

Codex App Server intentionally ignores the generic task override fields. It uses
`CODEX_APP_SERVER_MODEL` for all model-backed tasks so stale Azure or
OpenAI-compatible overrides cannot shadow the app-server route in telemetry,
health checks, or Activity records.

Internal role note:
- `patch_drafting` is now a distinct internal role for bounded single-file drafts
- today it reuses the remediation model override/path unless a dedicated override is added later

Current limitation:
- you cannot use Azure for analysis and `openai_compatible` for diagnosis/remediation in the same run
- provider selection is global for the runtime, not per task

## Codex App Server

Codex App Server is supported as a model-backed runtime through `LLM_PROVIDER=codex_app_server`.

Settings:
- `CODEX_APP_SERVER_TRANSPORT=stdio|websocket`
- `CODEX_APP_SERVER_COMMAND=codex app-server` for stdio
- `CODEX_APP_SERVER_MODEL=gpt-5.4` by default
- `CODEX_APP_SERVER_TURN_TIMEOUT_MS=120000`
- `CODEX_APP_SERVER_WS_URL` plus one WebSocket auth input when using WebSocket transport

Runtime behavior:
- PipelineHealer starts an ephemeral Codex App Server thread for model-backed turns.
- The turn uses read-only sandbox settings and `approvalPolicy=never`.
- This provider is for diagnosis/remediation model work. It is separate from external-agent handoff.

Important distinction:
- `LLM_PROVIDER=codex_app_server` means PipelineHealer asks Codex App Server for model output.
- `target=codex_app_server` in a handoff session means PipelineHealer delegates work to an external agent runtime that may have connected tools such as GitHub.
- OpenClaw and Hermes are handoff targets, not LLM providers.

## Diagnosis Contract Enforcement

Diagnosis is now schema-gated, not prose-gated.

Current runtime rule:
- the diagnosis model must return exactly one JSON object
- top-level diagnosis fields must all be present
- `error_details` must include the full typed key set for the chosen `failure_type`
- unknown values should be represented with empty strings, empty arrays/objects, `false`, or `0`, not omitted fields

Fallback behavior:
- malformed JSON is rejected
- incomplete typed payloads are rejected
- when rejection happens, PipelineHealer falls back to deterministic diagnosis when available instead of trusting partial LLM prose
- fallback diagnoses now expose `diagnosis.llm_rejection` for operator-facing auditability
- `diagnosis.llm_rejection.candidate_count` reports diagnosis-shaped JSON candidates, not every brace-balanced substring in the raw model output
- the legacy `error_details` rejection keys remain for backward compatibility and lower-level traces

Operator implication:
- a model that can answer loosely in natural language but cannot satisfy the structured diagnosis contract is not full-capability for diagnosis

## Readiness Levels

There are four different states operators need to distinguish.

1. Configured
- endpoint/base URL, key, and default model/deployment are present

2. Provider-ready
- `GET /api/settings/llm/provider-health` returns `available=true`
- this means PipelineHealer has enough configuration to attempt calls

3. Operation-compatible
- the target model actually supports the API shape PipelineHealer will use
- this is where Azure `Responses` vs `Chat Completions` differences matter

4. Full-capability
- analysis and diagnosis succeed
- remediation can produce a high-confidence PR path
- bounded patch drafting validations pass when that path is invoked
- `llm_model_path.error_count` stays at `0` for a healthy canary

Important:
- `provider-health` proves `2`, not `3` or `4`
- Settings and Control Center now surface these states directly from `GET /api/settings/llm/provider-health` via `capability_state`, `capability_summary`, and `last_validation`

## Degraded Mode

If the LLM path is unhealthy, PipelineHealer does not become completely inoperable, but it does become materially weaker.

Still works:
- webhook/run ingestion
- activity creation
- GitHub/MCP evidence collection
- external diagnostics collection
- low-confidence fallback issue creation

Degraded or lost:
- accurate root-cause diagnosis
- reliable remediation planning
- deterministic PR automation for novel failures

Practical interpretation:
- without a working LLM path, PipelineHealer is still an explainable incident-ingestion control plane
- but it is not meeting its primary diagnosis/remediation promise

## Azure Fallback Behavior

Azure OpenAI remains a supported fallback/reference provider. Production is currently
configured for Codex App Server with `CODEX_APP_SERVER_MODEL=gpt-5.4`.

When using Azure OpenAI:
- use an operator-owned deployment name, not a hardcoded example from this repo
- prefer `https://<resource>.cognitiveservices.azure.com/` for Responses-first validation
- keep per-task overrides empty until the exact deployment has passed a live canary
- validate the selected deployment with `bash scripts/ph.sh aoai:check` and one known canary activity

Observed caution from earlier ACA validation: mixing a newer Responses-only
deployment with an older endpoint shape degraded diagnosis/remediation behavior.
Treat endpoint, API version, and deployment as one tested bundle.

## Recommended Azure Routing

Current recommended Azure setup:
- default deployment: the operator-owned deployment that passed canary validation
- analysis: leave empty unless a cheaper validated deployment is available
- diagnosis: leave empty unless a stronger validated deployment is available
- remediation: leave empty unless a stronger validated deployment is available
- patch_drafting: currently reuses the remediation override/path

Reasoning:
- analysis is the best place to save latency/cost
- diagnosis and remediation benefit most from the stronger reasoning/coding model
- bounded patch drafting is the narrowest place to spend stronger coding-model budget

## Bounded Patch Drafting

PipelineHealer now supports a bounded patch drafting path for safe, known edit classes.

Current rules:
- deterministic extraction and remediation planning still happen first
- bounded drafting is only used for tightly-scoped single-file edits
- draft output is validated before write/apply
- if the draft is invalid, PipelineHealer falls back to deterministic content when available
- if no safe fallback exists, the PR path falls back to issue-only instead of applying a weak patch

Current shipped edit class:
- minimal ESLint flat-config creation for missing `eslint.config.*`

Traceability:
- activities may include `remediation_result.details.patch_drafting_trace`
- this records when bounded drafting ran and whether the final content came from a validated draft or deterministic fallback

## Capability Verification Checklist

Before a demo or production promotion:

1. Verify config shape
- `bash scripts/ph.sh settings:check`
- `GET /api/settings/llm/provider-health`

2. Verify live model compatibility
- `bash scripts/ph.sh aoai:check` for Azure
- Codex App Server: `GET /api/settings/llm/provider-health`, then run one known canary activity with `LLM_PROVIDER=codex_app_server`
- or direct provider smoke test for other providers

3. Verify a real canary
- trigger one known demo-repo failure
- confirm the resulting activity has:
  - non-null `failure_type`
  - high confidence
  - `llm_model_path.error_count = 0`
  - successful PR or issue behavior matching policy

4. Fail the release/demo gate if the activity falls back to:
- `failure_type: unknown`
- low-confidence issue creation caused by LLM incompatibility

## Learning Ops: Why the Current Shape Needs Rework

The current learning system is useful but too shallow for the next phase.

Current weakness:
- it mostly promotes recurring remediation outcomes into governed candidates
- it is not yet strongly LLM-aware in candidate synthesis, retrieval quality, or operator review ergonomics
- it behaves more like a governed queue than a real learning-assisted remediation layer

That is acceptable for the shipped baseline, but not strong enough for the long-term product story.

## Learning Ops Rework Direction

The next evolution should make learning a first-class LLM-assisted subsystem, not just a recurrence tracker.

Target shape:

1. Evidence-first candidate generation
- build candidates from repeated incidents plus operator verification
- include normalized failure evidence, not just recurrence counts

2. LLM-assisted candidate drafting
- use the LLM to draft:
  - candidate title
  - suggested playbook
  - boundary conditions
  - risk notes
- keep activation operator-governed

3. Retrieval before diagnosis/remediation
- fetch matching active playbooks/candidates before the main diagnosis/remediation calls
- inject them as structured context, not freeform prompt stuffing

4. Evaluation loop
- compare learned-playbook suggestions against actual remediation outcomes
- track false positives, overrides, and retirement triggers

5. Governance hardening
- no silent activation
- no hidden policy mutation
- no learned change applied without clear provenance and auditability

## References

- [README.md](/mnt/d/repos/pipelinehealer/README.md)
- [docs/runbooks/LOCAL_DEMO_RUNBOOK.md](/mnt/d/repos/pipelinehealer/docs/runbooks/LOCAL_DEMO_RUNBOOK.md)
- [docs/reference/API.md](/mnt/d/repos/pipelinehealer/docs/reference/API.md)
- [docs/architecture/MODEL_PROVIDER_STRATEGY.md](/mnt/d/repos/pipelinehealer/docs/architecture/MODEL_PROVIDER_STRATEGY.md)
- [docs/architecture/LEARNING_SYSTEM_PLAN.md](/mnt/d/repos/pipelinehealer/docs/architecture/LEARNING_SYSTEM_PLAN.md)
