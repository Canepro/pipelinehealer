# Learning System Plan

<!-- LAST_VERIFIED: 51d0763 -->

This document explains the learning/governance subsystem, how to use it today, and what is planned next.

Honest status:
- the current learning system is useful, but it is not yet the final shape we want
- today it behaves more like a governed recurring-pattern queue than a strong LLM-assisted learning layer
- the next phase should rework it around evidence quality, retrieval value, and operator trust
- this direction is now also supported by external provider guidance collected in `docs/LLM_PROVIDER_RESEARCH_AND_PLAN.md`

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
- activity-level learning context trace showing which active artifacts were injected into diagnosis/remediation
- remediation results can now record when one strong active playbook was promoted into explicit applied guidance

## What Learning Does Not Do (Yet)

- It does not auto-edit candidate text fields from the UI.
- It does not auto-activate candidates without a governance decision.
- It does not bypass readiness gates unless `force_activate=true` is explicitly chosen and audited.
- It does not auto-parse GitHub issue comments into verification feedback; comments are evidence, but feedback must be submitted via the learning feedback API/UI flow.

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
- Active playbooks are governed artifacts today; bounded runtime influence is now implemented as guidance, not as silent action selection.

## Immediate Next (Planned)

1. Retrieval-before-diagnosis/remediation:
   - initial runtime retrieval trace is now implemented for active artifacts.
   - a strong top match can now be promoted into an explicit remediation guidance section when it agrees with current evidence.
   - next step is to deepen scoring, evaluation, and operator feedback on whether the applied guidance actually helped.
2. Operator field editing:
   - safe `PATCH` endpoint + audited edits for candidate text fields.
3. Promotion execution preview:
   - show what an active playbook would change before action.
4. Verification capture bridge:
   - add a structured parser path for "PipelineHealer Accuracy Assessment" issue comments.
   - map parsed values into `POST /api/settings/learning/feedback` payload shape with audit metadata.
   - keep manual API/UI submission as fallback.
5. Evaluation:
   - track learning impact metrics (reuse rate, false-positive rate, manual override rate).

## Structured Retrieval Injection Contract

The next learning step is not "let the queue influence the model somehow." It is a
bounded retrieval contract.

When active learning artifacts are injected into diagnosis/remediation, the runtime
should pass structured records, not freeform prompt stuffing.

Recommended injected fields per matched artifact:
- `id` (matching `LearningQueueItem.id`; a runtime adapter may alias this as `candidate_id` externally)
- `title`
- `reason_code`
- `suggested_playbook`
- `applicability_notes` (planned governed or derived notes about when the playbook applies)
- `risk_notes` (planned governed or derived notes about residual or introduced risk)
- `evidence_summary` (planned derived summary of the key evidence that led to this candidate)
- `verification_summary` (planned derived summary of verification outcomes and operator feedback)
- `match_basis`
- `match_rank`
- `match_score`

Recommended runtime rules:
- inject only `active` artifacts
- `approved` artifacts remain pre-activation governance records and are not injected into live diagnosis/remediation
- keep retrieval read-only; no activation or mutation in the diagnosis/remediation path
- inject a bounded number of matches with explicit ranking metadata (`match_rank`, `match_score`, and `match_basis`)
- preserve deterministic evidence as the primary source of truth
- treat learning context as advisory by default; only a strong top match may be promoted into explicit guidance, and that promotion must be recorded

Recommended operator-facing behavior:
- activities should be able to show when learning context was injected
- operators should be able to see which artifact matched and why
- learning context should never silently override explicit failure evidence from logs, MCP, or deterministic extractors

Recommended failure behavior:
- if retrieval is unavailable, diagnosis/remediation continues without learning context
- if retrieved artifacts are stale, low-confidence, or in conflict with current evidence, the runtime should ignore them and record why in trace metadata

This keeps the learning system aligned with the rest of `v0.6.0`:
- deterministic-first
- schema-driven
- operator-auditable
- provider-agnostic

## Rework Direction

The learning system should evolve from "repeat incidents become candidates" into an LLM-assisted, operator-governed remediation memory.

Target improvements:

1. Evidence-first candidate generation
   - build candidates from repeated incidents plus verification outcomes, not recurrence alone
2. LLM-assisted candidate drafting
   - generate a first-pass title, playbook summary, applicability notes, and risk notes from the underlying incident evidence
3. Retrieval quality before action
   - use active candidates as structured context for diagnosis/remediation rather than as passive queue records only
   - keep the injected context typed, bounded, and traceable at the activity level
4. Evaluation and retirement loop
   - measure whether learned guidance improved remediation quality, and retire candidates that create noise or drift
5. Stronger operator trust model
   - show why a candidate matched, what evidence it was built from, and where operator feedback changed its readiness

Non-goals for the rework:
- no silent policy mutation
- no automatic activation without explicit operator approval
- no hiding LLM-authored candidate text from audit history

## Safety Rules

- no autonomous policy mutation
- no hidden state transitions
- all force paths must be explicit, deliberate, and audited
- keep deterministic fallback path available when learning context is unavailable
