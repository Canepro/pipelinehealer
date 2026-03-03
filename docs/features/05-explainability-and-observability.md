# Feature: Explainability And Observability

<!-- LAST_VERIFIED: c6e47b9 -->

This guide explains where to see evidence, model path telemetry, and confidence attribution for each activity.

## What This Feature Covers

- Explainability snapshot on Dashboard
- Activities table status tagging with row actions reachable without horizontal-rail dependency
- Activity Detail information hierarchy (`PipelineHealer Decision` first, deep technical panels second)
- Activity Detail evidence layers
- Failure context (`failing_job`, `failing_step`, `failing_command`, `signal`)
- LLM model-path telemetry
- MCP observability and action audit

## Quick Start

1. Open Dashboard -> `Explainability Snapshot`.
2. Pick a recent activity.
3. Confirm:
   - `PipelineHealer Decision` summary (root cause + remediation result)
   - failure type
   - failure context
   - confidence
   - diagnosis source
   - model path
   - proposed action + reason code
4. Click `View activity` for full detail.

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
2. review structured context.
3. expand raw extracts only if needed.

## Common Mistakes

- Treating `Diagnosis: LLM` as low trust by default:
  - combine with confidence, reason code, and evidence context.
- Ignoring fallback indicators:
  - repeated fallback may signal provider/version tuning need.

## Related Docs

- `../API.md` (`LLMModelPath`, `MCPModelPath`, activity schemas)
- `../LOCAL_DEMO_RUNBOOK.md` (demo validation with screenshots)
