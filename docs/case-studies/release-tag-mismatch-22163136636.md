# Case Study: Release Tag/Version Mismatch (`run #22163136636`)

<!-- LAST_VERIFIED: fadd4cf -->

## Summary

PipelineHealer detected and processed a real CI release failure caused by a version mismatch:

- Activity ID: `f92ee7d9-dd2f-4e32-8edd-c2b44ee0cae3`
- Workflow run: `#22163136636` (`Release`)
- Repository: `Canepro/pipelinehealer`
- Outcome: classified as `build_config`, remediation artifact published as issue `#15`

## What Failed

During GitHub Actions `Release` workflow execution on **February 19, 2026**, the step `Validate tag matches VERSION` failed because:

- tag: `v0.2.0`
- expected from `VERSION`: `v0.1.1`

This is a deterministic release-configuration error, not a test/lint/dependency failure.

## How PipelineHealer Handled It

1. **Detect**  
   Ingested the failing `workflow_run.completed` event and created activity `f92ee7d9-dd2f-4e32-8edd-c2b44ee0cae3`.
2. **Classify**  
   Diagnosis source: `llm`  
   Failure type: `build_config`  
   Confidence: `95%`
3. **Remediate Safely**  
   Proposed fix included changing `VERSION`, but this path is intentionally guarded for automation safety.
   - Auto-PR was blocked by policy (`OUTSIDE_ALLOWED_FILES`)
   - PipelineHealer created a structured issue instead: `https://github.com/Canepro/pipelinehealer/issues/15`
4. **Preserve Auditability**  
   Activity retained diagnosis rationale, evidence snippets, and remediation reason code for operator review.

## Why This Is Useful

This incident shows practical value beyond demo fixtures:

- Correctly avoided misclassifying a release-config failure as a generic test failure.
- Produced a usable remediation issue instead of silently failing.
- Enforced policy boundaries when proposed edits touched guarded files.

## Operator Resolution

To resolve without rewriting published tags:

1. Publish a follow-up patch release from the correct release commit.
2. Keep the original failed run/issue as an auditable trail.

Applied in this repository:

- Release published: `v0.2.1`
- Release commit: `b69a9ec`
- Purpose: supersede the mis-tagged release event with a correct tag/version-aligned publish flow.

## Learning Candidate Follow-up (Self-Learning Path)

This incident is a good candidate for the learning system.

- Candidate type: `build_config` release validation mismatch.
- Candidate signature cues:
  - workflow context includes release/tag validation
  - evidence contains `Validate tag matches VERSION`
  - mismatch pattern between `TAG_NAME` and `VERSION`
- Candidate draft remediation:
  - run `bash scripts/check_version_sync.sh`
  - align `VERSION` with intended tag via release flow
  - publish corrected tag/release (patch follow-up when required)

If a similar incident first appears as `unknown` or low-confidence, it should stay in `candidate` state until recurrence + operator review confirm the pattern. After approval, the playbook can be activated to improve future classification and guidance quality.

Important safety rule: even with an active candidate, guarded-file policies still apply. For this class, remediation should continue to prefer issue-first guidance when proposed edits touch protected release/version paths.

## Related Artifacts

- Activity detail: `f92ee7d9-dd2f-4e32-8edd-c2b44ee0cae3`
- Workflow run: `https://github.com/Canepro/pipelinehealer/actions/runs/22163136636`
- Remediation issue: `https://github.com/Canepro/pipelinehealer/issues/15` (closed after corrective release + case-study merge)
- Corrective release tag: `https://github.com/Canepro/pipelinehealer/releases/tag/v0.2.1`
- Case-study PR: `https://github.com/Canepro/pipelinehealer/pull/16`
