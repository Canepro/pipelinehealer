# Feature: Explainability And Observability

<!-- LAST_VERIFIED: c78ae9b -->

This guide explains where to see evidence, model path telemetry, and confidence attribution for each activity.

## What This Feature Covers

- Explainability snapshot on Dashboard
- Activities table status tagging with row actions reachable without horizontal-rail dependency
- Activity Detail incident-record hierarchy (`what happened`, `what PipelineHealer concluded`, `what it did`, `what still needs review`)
- Activity Detail evidence layers
- Activity Detail verification state and operator feedback history
- Failure context (`failing_job`, `failing_step`, `failing_command`, `signal`)
- LLM model-path telemetry
- MCP observability and action audit
- Control Center `Trust Ops` queue and compact trust metrics

## Quick Start

1. Open Dashboard -> `Explainability Snapshot`.
2. Pick a recent activity.
3. Confirm:
   - incident-record summary (what happened + diagnosis + remediation + verification state)
   - failure type
   - failure context
   - confidence
   - diagnosis source
    - model path
    - proposed action + reason code
4. Click `View activity` for full detail.

Trust-ops tip:
- Open Control Center -> `Trust Ops` to review recent items that still need human follow-up, especially harmful guidance, low-confidence review-only runs, and incidents that used promoted guidance without operator verification.

Activities list tip:
- Desktop layout keeps row actions reachable while scanning long activity histories, so you can review older rows without horizontal-rail juggling.

## Diagnosis Source

- `pattern`: deterministic rule match
- `llm`: model-assisted diagnosis path

This helps operators understand when AI inference was used.

## Model Path (LLM)

Per activity, the UI can show:
- provider
- model/deployment
- call count
- fallback used
- total latency
- error count

Use this to answer:
- which model path handled this run?
- did fallback occur?
- was there latency/error pressure?
- if task overrides are configured, did the expected task model/deployment execute?

## MCP Observability

When MCP is enabled, Activity Detail includes:
- provider and readiness
- read-only mode status
- configured tools
- source attribution
- tool usage counters
- action audit entries (`actor`, `tool`, `payload hash`, `result`, `request id`)

## Evidence Layers

PipelineHealer shows summary-first evidence with optional deep extracts.

Recommended operator flow:
1. start with confidence and reason code.
2. review incident-record status, including whether operator verification already exists.
3. review structured context.
4. expand raw extracts only if needed.

## Common Mistakes

- Treating `Diagnosis: LLM` as low trust by default:
  - combine with confidence, reason code, and evidence context.
- Ignoring fallback indicators:
  - repeated fallback may signal provider/version tuning need.

## Related Docs

- `../reference/API.md` (`LLMModelPath`, `MCPModelPath`, activity schemas)
- `../runbooks/LOCAL_DEMO_RUNBOOK.md` (demo validation with screenshots)
