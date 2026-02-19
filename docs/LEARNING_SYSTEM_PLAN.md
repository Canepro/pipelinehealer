# Learning System Plan

<!-- LAST_VERIFIED: d13bd12 -->

This document explains the learning/governance subsystem, how to use it today, and what is planned next.

## Purpose

The learning system captures recurring remediation outcomes and turns them into operator-governed playbook candidates.

Goals:
- reduce repeated triage decisions
- keep automation policy-safe and auditable
- promote only patterns with clear evidence

## In Plain Language

- PipelineHealer watches for repeated successful remediation patterns.
- It proposes those patterns as **candidates** in the learning queue.
- A human operator still decides whether to approve/activate; activation is not automatic.
- If you use force activation, it is explicitly recorded in audit history.

## Current Scope (Implemented)

Data model:
- durable learning queue records in storage
- candidate fingerprinting from recurring successful activities
- lifecycle states: `candidate`, `approved`, `active`, `rejected`, `retired`

Operator controls:
- refresh candidates in Control Center
- decision actions: approve/reject/activate/retire/reset
- guarded activation with readiness gates
- optional forced activation (`force_activate=true`) with explicit audit trail

Readiness gates for activation:
- approval/status gate
- occurrence count gate (default >= 2)
- success-rate gate (default >= 80%)
- sample-size gate (default >= 2)
- verification-sample gate (default >= 1)
- verification-pass-rate gate (default >= 80%)

Verification feedback loop:
- operator feedback API (`identification`, `diagnosis`, `remediation` outcomes)
- per-activity durable verification payload + history
- candidate verification counters (`pass|partial|fail`) + pass rate

Observability and audit:
- per-candidate `promotion_readiness` payload
- decision audit metadata includes readiness before/after
- forced activation metadata includes actor, reasons, and request id

## What Learning Does Not Do (Yet)

- It does not auto-edit candidate text fields from the UI.
- It does not auto-activate candidates without a governance decision.
- It does not bypass readiness gates unless `force_activate=true` is explicitly chosen and audited.

## How To Use (Today)

UI:
1. Open `/app/control-center`.
2. Authenticate (`X-Admin-Key` or Entra admin session).
3. Click `Refresh Candidates`.
4. Review candidate status + readiness.
5. Use action buttons:
   - `Approve`
   - `Activate` (when ready)
   - `Force Activate` (with confirmation; audited)
   - `Reject`
   - `Retire`

API:
- `GET /api/settings/learning/queue`
- `POST /api/settings/learning/queue/refresh`
- `POST /api/settings/learning/queue/{candidate_id}/decision`
- `POST /api/settings/learning/feedback`

Quick verification checklist:
1. Run refresh and confirm candidate rows appear with `promotion_readiness`.
2. Submit at least one verification payload (`pass|partial|fail`) for a related activity.
3. Re-open the queue and confirm verification counters/pass-rate changed.
4. Confirm audit includes the matching learning action (`learning_queue_refresh`, `learning_queue_decision`, or `learning_verification_feedback`).

## Current Constraints

- Candidate text fields (`suggested_playbook`, `reason_code`, `title`) are generated from observed incidents.
- Inline operator editing of candidate fields is not implemented yet.
- Active playbooks are governed artifacts today; full retrieval/applicator loop is the next phase.

## Immediate Next (Planned)

1. Retrieval-before-diagnosis/remediation:
   - fetch matching active candidates and inject as structured context.
2. Operator field editing:
   - safe `PATCH` endpoint + audited edits for candidate text fields.
3. Promotion execution preview:
   - show what an active playbook would change before action.
4. Evaluation:
   - track learning impact metrics (reuse rate, false-positive rate, manual override rate).

## Safety Rules

- no autonomous policy mutation
- no hidden state transitions
- all force paths must be explicit, deliberate, and audited
- keep deterministic fallback path available when learning context is unavailable
