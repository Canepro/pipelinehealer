# LLM and Agent Runtime

<!-- LAST_VERIFIED: 747334d -->

This document is the operator-facing contract for how PipelineHealer uses LLMs and agents at runtime.

Use it when you need to answer:
- what "healthy" actually means for the LLM path
- which Azure endpoint/model combinations were validated
- what happens when the LLM path degrades
- what is and is not supported in model routing today
- how learning ops should evolve instead of staying a thin recurring-pattern queue

## Current Runtime Model

PipelineHealer has multiple agent responsibilities:
- log analysis
- diagnosis
- remediation
- orchestration

Today, one LLM provider is active per runtime:
- `azure_openai`
- `openai_compatible`
- `custom` (scaffold only; not production-capable)

Task-level routing is supported inside that active provider:
- `LLM_MODEL_ANALYSIS`
- `LLM_MODEL_DIAGNOSIS`
- `LLM_MODEL_REMEDIATION`

Current limitation:
- you cannot use Azure for analysis and `openai_compatible` for diagnosis/remediation in the same run
- provider selection is global for the runtime, not per task

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
- `llm_model_path.error_count` stays at `0` for a healthy canary

Important:
- `provider-health` proves `2`, not `3` or `4`

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

## Validated Azure Behavior

Validated on `v0.5.7`:

1. `https://<resource>.cognitiveservices.azure.com/`
- `gpt-5.1-codex-mini`
- Responses-first runtime path
- validated on Helm and ACA with successful diagnosis and PR remediation

2. `https://<resource>.openai.azure.com/`
- `gpt-5-mini`
- validated as the stable default path

Observed caution:
- routing diagnosis/remediation to `gpt-5.1-codex-mini` while ACA still pointed at the older `openai.azure.com` endpoint produced degraded behavior in production validation
- switching ACA to the `cognitiveservices.azure.com` base endpoint resolved that gap

Operator rule:
- if you want `gpt-5.1-codex-mini` for diagnosis/remediation on Azure, use the validated `cognitiveservices.azure.com` base endpoint and verify with a live canary

## Recommended Azure Routing

Current recommended Azure setup:
- default deployment: `gpt-5-mini`
- analysis: `gpt-5-mini`
- diagnosis: `gpt-5.1-codex-mini`
- remediation: `gpt-5.1-codex-mini`

Reasoning:
- analysis is the best place to save latency/cost
- diagnosis and remediation benefit most from the stronger reasoning/coding model

## Capability Verification Checklist

Before a demo or production promotion:

1. Verify config shape
- `bash scripts/ph.sh settings:check`
- `GET /api/settings/llm/provider-health`

2. Verify live model compatibility
- `bash scripts/ph.sh aoai:check` for Azure
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
- [docs/LOCAL_DEMO_RUNBOOK.md](/mnt/d/repos/pipelinehealer/docs/LOCAL_DEMO_RUNBOOK.md)
- [docs/API.md](/mnt/d/repos/pipelinehealer/docs/API.md)
- [docs/MODEL_PROVIDER_STRATEGY.md](/mnt/d/repos/pipelinehealer/docs/MODEL_PROVIDER_STRATEGY.md)
- [docs/LEARNING_SYSTEM_PLAN.md](/mnt/d/repos/pipelinehealer/docs/LEARNING_SYSTEM_PLAN.md)
