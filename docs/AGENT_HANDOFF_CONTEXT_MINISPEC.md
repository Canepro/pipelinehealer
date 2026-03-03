# Agent Handoff + Copy Context Mini-Spec

<!-- LAST_VERIFIED: c6e47b9 -->

Status: Phase 0/1 released in `v0.3.0` (`Copy Context` + disabled `Assign to Agent`), Phase 2 pending (`v0.3.1`)
Owner: PipelineHealer maintainers
Scope target:
- `v0.3.0`: `Copy Context` + disabled `Assign to Agent` `Coming Soon` affordance
- `v0.3.1`: functional agent handoff integration (`copy_only`/`webhook`)

## Problem

Activity Detail has deep diagnosis/remediation evidence, but operators who use AI coding assistants still copy fragments manually. This creates slow and inconsistent handoff quality.

## Goal

Add two operator actions to Activity Detail:

1. `Copy Context`:
   - one-click copy of an AI-ready activity context bundle.
2. `Assign to Agent`:
   - optional handoff to a configured external coding-agent bridge.

Both must preserve PipelineHealer as the policy/audit control plane.

## Non-Goals

- No direct IDE-specific hard dependency (Cursor/Copilot extensions are optional adapters, not required runtime dependencies).
- No bypass of existing remediation policy gates.
- No automatic write-back into repositories from this feature without existing policy enforcement.

## Recommended Rollout (Non-Breaking)

### Phase 0: Discoverability UI (`v0.3.0`)

Add a visible but disabled `Assign to Agent` button with a `Coming Soon` label/badge.

Why:
- sets operator expectation early
- avoids fake/incomplete handoff behavior
- creates stable placement before enabling integration

### Phase 1: `Copy Context` (`v0.3.0`, frontend-only)

Add a button in Activity Detail that builds and copies a deterministic context payload from existing activity data already loaded in the UI.

Why first:
- no backend/API changes
- low regression risk
- immediate user value

### Phase 2: `Assign to Agent` (`v0.3.1`, configurable integration)

Add a pluggable handoff path with disabled-by-default behavior.

Recommended first integration mode:
- `webhook` connector (POST payload to configured endpoint)

Fallback mode:
- `copy_only` (copies handoff payload, no network call)

## UX Contract

Placement:
- Activity Detail header actions area (near existing `Retry` action).

Controls:
- `Copy Context` button: always available when activity is loaded.
- `Assign to Agent` button:
  - `v0.3.0`: visible, disabled, marked `Coming Soon`
  - `v0.3.1`: enabled only when connector mode is configured

Feedback:
- success/failure toast for each action.
- no blocking spinner beyond action-level pending state.

## Context Payload Contract (for `Copy Context`)

Format:
- plain text (markdown-friendly)

Sections (in order):
1. Activity identity (`activity_id`, repository, workflow, run ID, status, timestamps)
2. Diagnosis summary (failure type, source, confidence, root cause, suggested fix)
3. Remediation outcome (action taken, success, artifact URLs, reason codes)
4. Failure context (`failing_job`, `failing_step`, `failing_command`, `signal`)
5. External diagnostics summary (source, status, confidence deltas, top findings URL)
6. MCP/LLM observability summary (provider/model/path health fields)
7. Operator ask template:
   - "Propose minimal safe fix"
   - "List verification steps"
   - "Provide rollback plan"

Limits:
- cap payload size to avoid runaway clipboard blobs (target <= 16 KB text)
- truncate long lists/sections with explicit `...truncated...` marker

Redaction safety:
- never include API keys, tokens, Authorization headers, or raw secret-looking strings
- keep only already-rendered activity data fields and curated summaries

## Optional Backend Contract (for `Assign to Agent`)

If backend handoff is approved, add:

- `POST /api/activities/{activity_id}/agent-handoff`

Request:
- `connector_id` (string)
- `mode` (`webhook` | `copy_only`)
- `context_format` (`plain_text` | `markdown`)
- `include_sections` (optional allowlist)

Response:
- `status` (`queued` | `copied` | `disabled` | `failed`)
- `delivery_id` (optional)
- `message`

Auth:
- same `/api/*` auth model as existing activity actions

Audit:
- record handoff attempts/results with request correlation ID

## Configuration Model (Proposed)

New runtime settings (disabled by default):
- `AGENT_HANDOFF_ENABLED=false`
- `AGENT_HANDOFF_MODE=copy_only|webhook`
- `AGENT_HANDOFF_WEBHOOK_URL=...` (required for `webhook`)
- `AGENT_HANDOFF_TIMEOUT_SECONDS` (bounded, small default)

Guardrails:
- allowlist destination domain(s) for webhook mode
- bounded retry policy; no infinite retries
- structured error reporting without leaking sensitive payloads

## Compatibility and Risk

Compatibility:
- no change to existing remediation pipeline semantics
- no schema breaks to existing activity endpoints for Phase 1

Primary risks:
- oversized context payloads
- accidental leakage of sensitive strings
- over-promising IDE-native execution semantics

Mitigations:
- hard payload cap + deterministic truncation
- explicit redaction pass
- position as "handoff helper", not "direct IDE automation"

## Test Plan (Implementation Gate)

Phase 1 tests:
- unit: context builder includes required sections and truncation markers
- unit: redaction removes secret-like content
- UI: copy button success/error toast behavior

Phase 2 tests:
- API: auth, validation, timeout/error handling
- integration: webhook connector success/failure paths
- audit visibility: handoff event traceability

## Acceptance Criteria

1. Operator can copy one coherent, AI-ready context bundle from Activity Detail in one click.
2. Payload is bounded and redacted.
3. Existing `Retry` and `Backfill Diagnostics` workflows are unaffected.
4. If enabled, agent handoff attempts are traceable and failure-safe.
