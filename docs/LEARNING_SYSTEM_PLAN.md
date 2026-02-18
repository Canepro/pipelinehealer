# Learning System Plan

<!-- LAST_VERIFIED: c8a1c8d -->

This document explains the learning/governance subsystem, how to use it today, and what is planned next.

## Purpose

The learning system captures recurring remediation outcomes and turns them into operator-governed playbook candidates.

Goals:
- reduce repeated triage decisions
- keep automation policy-safe and auditable
- promote only patterns with clear evidence

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

Observability and audit:
- per-candidate `promotion_readiness` payload
- decision audit metadata includes readiness before/after
- forced activation metadata includes actor, reasons, and request id

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

