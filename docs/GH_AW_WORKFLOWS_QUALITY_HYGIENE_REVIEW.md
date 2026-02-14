# GitHub Agentic Workflows Hygiene Review for PipelineHealer

This note captures a practical, correct adoption path for GitHub Agentic Workflows (`gh aw`) in PipelineHealer.

Execution status is tracked in `docs/GH_AW_IMPLEMENTATION_TRACKER.md`.

Primary source:

- `https://github.github.com/gh-aw/blog/2026-01-13-meet-the-workflows-quality-hygiene/` (Jan 13, 2026, "Meet the Workflows: Fault Investigation")

## Critical Implementation Rule

Workflow specs must be created from `gh aw` templates and compiled. Do not hand-write freeform markdown files under `.github/workflows/` and treat them as executable workflows.

Required flow:

1. `gh extension install github/gh-aw`
2. `gh aw init`
3. `gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/ci-doctor.md`
4. `gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/schema-consistency-checker.md`
5. `gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/breaking-change-checker.md`
6. Customize to advisory mode.
7. `gh aw compile`

## Executive Summary

PipelineHealer should use a two-layer strategy:

1. **Layer 1 (Repo hygiene)**: enforce quality in this repository with baseline CI and valid `gh aw` workflows.
2. **Layer 2 (Product capability)**: let PipelineHealer invoke `gh aw` workflows as tools for monitored repos, then ingest findings into diagnosis/remediation.

## Current State

- Local quality commands are well-defined (`pytest`, `mypy`, `bun run lint`, `bun run build`).
- Runtime safety controls are strong (allowlists, heal modes, auth boundaries).
- Baseline GitHub Actions CI should exist as `.github/workflows/ci.yml`.
- `gh aw` workflow specs are not yet correctly generated/compiled in this repo.

## Recommended PR Sequence

1. **PR 1 (Recommended)**: add baseline `.github/workflows/ci.yml` only.
2. **PR 2**: add real `gh aw` workflows via `init` + `add-wizard` + `compile` in advisory mode.
3. **PR 3**: wire Layer 2 integration into PipelineHealer (tool invocation + output ingestion + dashboard visibility).

## Layer 2 Integration Blueprint (Product Feature)

1. Add a `gh_aw_tools` config surface (enabled workflows, advisory/active mode, allowlisted repos).
2. Add a `gh-aw` tool adapter in orchestration that can trigger selected workflows and collect structured outcomes.
3. Map workflow outputs to existing diagnosis/remediation confidence/risk fields.
4. Show last `gh aw` run and findings in activity views for operator traceability.

## Practical Leverage Patterns

- Use CI Doctor outputs as high-signal triage input before remediation planning.
- Use Breaking Change Checker alerts as explicit human sign-off gates.
- Use Schema Consistency Checker to keep `docs/API.md` and runtime behavior aligned.
- Convert repeated findings into deterministic remediation templates and new fixtures.

## Bottom Line

The strategy is correct, but execution must use the real `gh aw` toolchain. Keep baseline CI and agentic workflows in separate PRs, then build PipelineHealer's Layer 2 orchestration on top.
