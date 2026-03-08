# LLM Provider Research and Plan

<!-- LAST_VERIFIED: 747334d -->

This document captures what the major LLM and agent-platform providers are recommending now, and how those recommendations should shape PipelineHealer.

It exists to prevent us from designing the next phase in isolation.

## Why This Matters

PipelineHealer is now clearly dependent on a healthy LLM runtime for its primary value:
- high-confidence diagnosis
- safe remediation planning
- deterministic PR generation for known patterns

That means our runtime, tracing, routing, and learning-system design should follow external best practice where the guidance is converging instead of treating our current implementation as self-validating.

## Research Summary

## OpenAI

Key themes from OpenAI's current guidance:
- optimize for accuracy first, then cost/latency
- use eval-driven development continuously, not only before release
- use structured tool calling rather than loose freeform prompting when actions/data access matter
- treat tracing as a first-class runtime capability for agents

Relevant guidance:
- [Model selection principles](https://platform.openai.com/docs/guides/model-selection/principles)
- [Evaluation best practices](https://platform.openai.com/docs/guides/evaluation-best-practices)
- [Function calling](https://platform.openai.com/docs/guides/function-calling/how-do-i-ensure-the-model-calls-the-correct-function)
- [Prompting guide](https://platform.openai.com/docs/guides/prompting)
- [Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/)

What matters for PipelineHealer:
- releases should be gated by canary/eval quality, not just config readiness
- tool contracts should stay strongly typed and tightly described
- traces should capture end-to-end remediation workflows, not just coarse activity summaries

## Azure

Key themes from Azure guidance:
- the Responses API is the unified direction
- remote MCP/tool use and approvals should be explicit and auditable
- multi-model or multi-instance deployments should be abstracted behind a gateway when client-side routing becomes brittle

Relevant guidance:
- [Azure OpenAI Responses API](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/responses)
- [Gateway in front of multiple Azure OpenAI deployments](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/azure-openai-gateway-multi-backend)

What matters for PipelineHealer:
- `Responses` should remain the primary Azure runtime surface
- model-routing rules should be verifiable before release/demo promotion
- the ACA issue we hit is exactly the kind of client-side brittleness Azure's gateway guidance is trying to avoid

## Anthropic

Key themes from Anthropic guidance:
- detailed tool descriptions matter more than examples
- MCP should be treated as a real protocol boundary, not just a custom integration detail
- prompt structure should be explicit and parseable

Relevant guidance:
- [How to implement tool use](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use)
- [MCP](https://docs.anthropic.com/en/docs/mcp)
- [Use XML tags to structure prompts](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags)

What matters for PipelineHealer:
- MCP/tool boundaries should stay explicit in both policy and telemetry
- our tool descriptions, handoff payloads, and structured context blocks should be treated as product assets, not incidental strings
- prompt structure should become more deliberate where the agent pipeline is doing classification and remediation planning

## Google

Key themes from Google guidance:
- function calling should use strongly typed, well-described schemas
- explicit tool modes (`AUTO`, `ANY`, `NONE`) reduce ambiguity
- MCP/tool integration can be built into SDK/runtime flows rather than bolted on at the edge

Relevant guidance:
- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)

What matters for PipelineHealer:
- provider portability should preserve strong tool contracts
- tool mode and approval semantics should remain explicit
- our routing and tool policy system should stay more schema-driven than prompt-driven

## Cross-Provider Convergence

The major providers are not saying wildly different things. The strongest common signals are:

1. Use structured tools, not vague freeform action prompts.
2. Validate live capability with evals/canaries, not config checks alone.
3. Add tracing and observability as core runtime features.
4. Keep model selection empirical and task-specific.
5. Treat routing and approvals as explicit policy, not hidden logic.

This is directionally consistent with the issues we already encountered:
- provider-health is necessary but insufficient
- endpoint/model compatibility must be proven live
- task-level routing is valuable, but only if backed by verified runtime compatibility

## What PipelineHealer Should Do Next

## 1. Capability States Must Become a First-Class Contract

We should keep using these four states everywhere:
- configured
- provider-ready
- operation-compatible
- full-capability

This distinction should appear in:
- docs
- API semantics
- UI summaries
- release gates

## 2. Canary-Backed Release Gates

We should require at least one real canary activity for any release/demo that changes:
- LLM provider
- endpoint family
- default deployment/model
- task-level routing

Passing criteria should include:
- non-null `failure_type`
- high confidence
- `llm_model_path.error_count = 0`
- successful PR/issue result consistent with policy

## 3. Stronger Tracing

We already have useful activity telemetry, but the research points to a more trace-native direction.

We should move toward:
- trace/span views per activity
- agent-stage timing (`analysis`, `diagnosis`, `remediation`)
- tool-call traceability
- redaction-aware payload capture
- clearer fallback-path trace markers

## 4. Azure Routing Hardening

We should stop assuming that a single endpoint family is interchangeable for every model.

Near-term:
- keep validated endpoint/model combinations documented
- add a release/canary check for endpoint-family compatibility

Mid-term:
- evaluate a gateway or routing abstraction for Azure deployments so model changes do not require brittle client assumptions

## 5. Learning Ops Rework

The current learning system is not wrong, but it is too shallow.

The research supports moving toward:
- evidence-first candidate generation
- LLM-assisted candidate drafting
- retrieval of active learning artifacts before diagnosis/remediation
- explicit evaluation of whether learned guidance improved outcomes

In other words:
- learning should become an operator-governed remediation memory
- not just a queue of recurring patterns

## Proposed Implementation Order

Recommended:

1. `v0.6.0`
- capability-state surfacing
- canary release gates
- Azure endpoint/model validation hardening
- learning-system design cleanup in docs and API contracts

2. `v0.6.x`
- richer runtime tracing
- retrieval-backed learning injection
- candidate editing/drafting improvements

3. `v0.7.0`
- gateway/routing abstraction if the Azure model matrix keeps growing
- stronger provider-portable agent runtime

## Non-Goals

These research findings do not mean we should:
- add multiple providers in one activity run immediately
- overbuild a generic agent framework before we harden our current control plane
- hide provider-specific differences behind vague abstractions

The goal is not maximal abstraction. The goal is reliable, auditable runtime behavior.
