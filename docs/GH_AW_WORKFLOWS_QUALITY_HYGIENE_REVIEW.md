# GitHub Agentic Workflows Quality/Hygiene Review for PipelineHealer

This note reviews PipelineHealer against GitHub's **Agentic Workflows "hygiene"** guidance and outlines how to leverage those workflows in this repo.

Reference blog/tooling entry points:

- `gh aw add-wizard .../.github/workflows/ci-doctor.md`
- `gh aw add-wizard .../.github/workflows/schema-consistency-checker.md`
- `gh aw add-wizard .../.github/workflows/breaking-change-checker.md`

## Executive Summary

PipelineHealer already has strong runtime safety controls and local quality gates (auth boundaries, allowlists, deterministic remediation policy, and backend/frontend test/lint/build commands). The main gap is that this repo currently does **not** have a root `.github/workflows/` CI pipeline that continuously enforces those checks in GitHub Actions.

The best leverage is to add GitHub Agentic Workflows as an **outer quality layer** that continuously audits this repo itself, while PipelineHealer remains the **runtime remediation product** for downstream repositories.

## What You Already Have (Strong Baseline)

- Clear backend and frontend quality commands (`pytest`, `mypy`, `bun run lint`, `bun run build`) documented for contributors.
- Security defaults and auth boundaries documented for API and admin settings routes.
- Runtime safety model (allowlist + safe/demo/debug modes) and deterministic-vs-manual remediation policy.
- Demo repository workflow fixture used to generate representative CI failures (`dependency`, `lint`, `test`, `build_config`, `timeout`, etc.).

## Gap vs "Quality Hygiene" Workflows

### 1) Missing repository-level CI automation

There is no top-level `.github/workflows/` pipeline in this repository to automatically run backend/frontend quality gates on PRs and pushes.

Impact:

- Quality checks rely on manual execution before merge.
- No branch-protection-friendly status checks.
- No machine-readable trend/history in Actions for this repo's own reliability.

### 2) No automated contract-change and schema drift checks

You expose a documented API surface and response shapes, but there is no automated workflow comparing API/docs/schema drift over time.

Impact:

- Risk of docs/API mismatch in rapid iteration.
- Harder to spot backward-incompatible changes early.

### 3) No autonomous CI failure investigation loop in-repo

PipelineHealer does remediation for monitored repos, but this repo itself does not yet run an agentic "CI Doctor" style workflow for its own failing jobs.

Impact:

- Meta-dogfooding opportunity is underused.
- Investigation burden remains human-first for this repo.

## Recommended Adoption Plan

## Phase 1 (Immediate, low risk)

1. Install and compile GitHub Agentic Workflows in a dedicated branch:
   - Add `ci-doctor`
   - Add `schema-consistency-checker`
   - Add `breaking-change-checker`
2. Configure them in **advisory mode** first (issue/comment outputs; no auto-merge behavior).
3. Add a standard root CI workflow (`ci.yml`) that runs:
   - backend: `pytest -q`, `mypy src`
   - frontend: `bun run lint`, `bun run build`

Success criteria:

- Every PR has required status checks.
- Hygiene workflows create actionable diagnostics without blocking velocity.

## Phase 2 (Dogfooding + policy hardening)

1. Point PipelineHealer at this repository in allowlist-safe mode to observe/fix deterministic failures in a canary branch strategy.
2. Use CI Doctor outputs to seed remediation pattern improvements in your diagnosis/remediation agents.
3. Require explicit CODEOWNERS review for breaking-change workflow alerts.

Success criteria:

- Reduced mean-time-to-diagnose for failed CI runs.
- Fewer doc/API drift regressions.

## Phase 3 (Advanced integration)

1. Feed hygiene workflow outcomes into your dashboard/metrics (for example, by ingesting issue labels or workflow run summaries).
2. Add periodic workflow that audits "docs vs implementation" targets from `docs/API.md` and enforcement checks.
3. Optionally create a dedicated "platform-hygiene" dashboard view.

Success criteria:

- Unified view of runtime remediation outcomes + repository quality posture.
- Evidence-driven updates to deterministic fix policy.

## Practical Leveraging Patterns

- **CI Doctor as triage accelerator**: Use it to classify flaky/dependency/permissions classes quickly, then route deterministic classes to existing remediation logic.
- **Breaking Change Checker as safety gate**: Tie alerts to manual approval policy before release/deploy commands.
- **Schema Consistency Checker as docs guardrail**: Keep `docs/API.md` and runtime behavior aligned as endpoints evolve.
- **Feedback loop into PipelineHealer**: Convert repeated hygiene findings into new deterministic templates and test fixtures.

## Suggested First PR Sequence

1. PR 1: Add baseline root CI workflow (tests, types, lint, build).
2. PR 2: Add GitHub Agentic Workflows in advisory mode.
3. PR 3: Tune rules and branch protections based on two weeks of signal.
4. PR 4: Integrate hygiene outputs into PipelineHealer activity/metrics views.

## Bottom Line

You should adopt GitHub's workflow hygiene tooling as an **internal quality control plane** for PipelineHealer itself. It complements your product's core mission and creates a strong dogfooding loop: better repo hygiene improves PipelineHealer, and PipelineHealer insights improve hygiene automation.
