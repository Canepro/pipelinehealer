# Feature: Diagnosis And Remediation

<!-- LAST_VERIFIED: d417254 -->

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
- cross-run dedup: open review issues with the same failure signature are reused instead of recreated.
- workflow success: open review issues for the same workflow and branch are auto-closed when `auto_close_on_workflow_success=true`.
- human/PH PR link: active PRs associated with a failing run can be linked to generated issues for auto-close on merge.

How to validate:
1. Trigger the same deterministic failure twice.
2. Confirm second activity does not create duplicate PR/issue.
3. Check remediation metadata for `reused_existing_issue`, `reused_existing_pr`, `linked_pull_request_numbers`, or `closed_superseded_issue_numbers`.
4. Re-run the workflow to green and confirm matching review issues close with an audit comment.

Legacy issues (created before the lifecycle-marker rollout) lack workflow/branch markers and are not managed by green-close or cross-run dedup until upgraded. Run `POST /api/settings/lifecycle/backfill-markers?repository=owner/repo` once per repo to backfill markers on open generated issues.

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

- `../reference/API.md` (`/webhook/github`, `/api/activities`, reason codes)
- `../runbooks/LOCAL_DEMO_RUNBOOK.md` (trigger patterns and proof flow)
