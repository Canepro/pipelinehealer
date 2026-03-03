# Feature: Diagnosis And Remediation

<!-- LAST_VERIFIED: c6e47b9 -->

This guide explains how PipelineHealer moves from failed workflow logs to safe remediation artifacts.

## What This Feature Covers

- Failure ingestion and workflow selection
- Pattern diagnosis vs LLM diagnosis
- Safe remediation action selection
- Idempotent find-or-create artifact behavior

## Quick Start

1. Trigger a failure in an allowlisted repo.
2. Open Dashboard -> activity row -> `View`.
3. Confirm:
   - `Failure Type`
   - `Diagnosis Source` (`Pattern` or `LLM`)
   - `Proposed Action`
   - `Reason Code`

## Processing Stages

1. Detect: webhook receives failed `workflow_run.completed`.
2. Analyze: log analyzer extracts useful signal.
3. Diagnose:
   - tries deterministic patterns first.
   - falls back to LLM if needed.
4. Remediate:
   - creates PR for high-confidence deterministic fixes.
   - creates issue for low-confidence, ambiguous, or policy-blocked cases.

## Why Action Might Be `SKIP`

Common reason codes:
- `LOW_CONFIDENCE`
- `AMBIGUOUS_RESOLUTION`
- `OUTSIDE_ALLOWED_FILES`
- `REQUIRES_ENV_CONTEXT`
- `OUTPUT_ISSUES_DISABLED`
- `OUTPUT_PERMISSION_DENIED`

A `SKIP` result can still be successful processing if diagnosis completed correctly.

## Idempotency (Duplicate Prevention)

PipelineHealer uses find-or-create behavior for remediation artifacts.

Expected behavior:
- first matching failure: create PR/issue.
- repeated matching failure: reuse existing artifact when valid.

How to validate:
1. Trigger the same deterministic failure twice.
2. Confirm second activity does not create duplicate PR/issue.
3. Check remediation metadata for reused-existing indicators.

## Safe vs Demo Mode

- `safe` (recommended): conservative changes only.
- `demo`: allows more aggressive demo actions.
- `debug`: same behavior as `safe`, with verbose logs.

## Common Mistakes

- Repo not in scope:
  - ensure repo appears in `ph_allowed_repos`.
- No fix artifact produced:
  - check reason code and repo permissions.
- 403 on issue/PR creation:
  - PAT/app lacks required GitHub permissions.

## Related Docs

- `../API.md` (`/webhook/github`, `/api/activities`, reason codes)
- `../LOCAL_DEMO_RUNBOOK.md` (trigger patterns and proof flow)
