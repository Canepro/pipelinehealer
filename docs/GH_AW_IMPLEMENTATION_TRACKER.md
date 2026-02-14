# GitHub Agentic Workflows Implementation Tracker

**Last updated:** February 14, 2026

This tracker is the execution source of truth for GitHub Agentic Workflows adoption in PipelineHealer.

## Scope

- **Layer 1 (Repo hygiene):** valid `gh aw` setup in this repository.
- **Layer 2 (Product feature):** PipelineHealer invokes `gh aw` workflows as tools for monitored repos.

## Status Summary

| Workstream | Status | Notes |
|---|---|---|
| Layer 1: baseline repo hygiene | Completed | merged in PR #3 with passing CI checks |
| Layer 2: PipelineHealer orchestration integration | Planned | Design direction agreed; implementation not started |

## Layer 1 Checklist (Repo Hygiene)

- [x] Remove non-compilable hand-written workflow markdown files from `.github/workflows/`.
- [x] Keep baseline CI workflow in `.github/workflows/ci.yml`.
- [x] Install `gh aw` CLI extension.
- [x] Run `gh aw init` in repo root.
- [x] Add workflows via wizard:
  - [x] `ci-doctor`
  - [x] `schema-consistency-checker`
  - [x] `breaking-change-checker`
- [x] Configure all 3 workflows to advisory mode (no auto-remediation or auto-merge behavior).
- [x] Run `gh aw compile` and verify generated lock outputs.
- [x] Open separate PR for `gh aw` workflow setup (do not mix with docs-only PRs).
- [x] Merge Layer 1 PR to `main` after CI is green.

## Layer 2 Checklist (PipelineHealer Product Integration)

- [ ] Add `gh_aw_tools` configuration model (enabled workflows, mode, repo scope).
- [ ] Implement backend tool adapter to trigger selected `gh aw` workflows.
- [ ] Ingest `gh aw` outputs (issues/comments/discussions) into diagnosis/remediation signals.
- [ ] Surface `gh aw` run status and findings in dashboard activity views.
- [ ] Add demo flow narrative:
  - failure detected
  - `gh aw` workflow invoked
  - findings consumed
  - fix recommendation produced

## Layer 2 Execution Plan (Kickoff)

## Layer 2 Preflight Decisions (Before PR A)

These decisions should be finalized before implementing Layer 2 runtime wiring.

### D1: Invocation backend for `gh aw`

Options:

- `subprocess` (`gh aw run ...`) first (Recommended for hackathon speed)
- GitHub Actions API first (workflow dispatch / direct trigger path)

Decision impact:

- This choice defines the initial adapter contract and test strategy in PR A.

### D2: Runtime settings durability model

Current behavior:

- Admin settings updates (including `ph_allowed_repos`) are in-memory runtime mutations only.
- Changes are not durable across backend restart/redeploy.

Options:

- Keep in-memory for now and document operational constraints (single-replica consistency + explicit save semantics).
- Add durable shared persistence for settings before/with PR A.

Decision impact:

- Layer 2 config (`gh_aw_tools`) should follow the same durability model to avoid mixed runtime behavior.

### D3: Known preflight risks (from current behavior)

- Risk A: Add-to-allowlist can appear successful in UI but not become effective in practice unless settings are saved and consumed in the same runtime path.
- Risk B: Allowlist does not persist across backend restart/redeploy by design (in-memory only).

Recommendation:

- Track these as explicit gating risks for Layer 2 rollout and demo reliability.
- Do not mark Layer 2 "demo-ready" until these runtime-settings semantics are accepted (or fixed).

### PR A: Config + Interface (Recommended first)

Scope:

- Add `gh_aw_tools` runtime config shape in backend settings.
- Define a backend adapter interface for `gh aw` operations (trigger, status, findings).
- Add no-risk plumbing in orchestrator to accept external diagnostics input without behavior changes.

Acceptance:

- Config loads from env/settings without breaking existing startup.
- New adapter paths are feature-flagged off by default.
- Existing tests pass unchanged.

### PR B: Invocation + Ingestion

Scope:

- Implement workflow invocation for selected repos/workflows.
- Ingest `gh aw` outputs (issue/comment/discussion references + summary) into diagnosis context.
- Add structured metadata fields to activity records for external-tool evidence.

Acceptance:

- For a target failure, PipelineHealer can attach `gh aw` findings to diagnosis output.
- Failures in `gh aw` invocation degrade gracefully (no orchestration crash).
- API responses remain backward compatible.

### PR C: Dashboard + Operator Visibility

Scope:

- Show `gh aw` status/findings in activity details (last run, workflow id, summary, links).
- Add minimal policy visibility in settings for enabled workflows and mode.
- Add demo-ready evidence path in docs (`DEMO_SCRIPT`, `LOCAL_DEMO_RUNBOOK`).

Acceptance:

- Operators can see whether `gh aw` was invoked and what it contributed.
- UI remains responsive and type-safe with/without `gh aw` metadata.

### PR D: Demo Hardening (Optional but recommended)

Scope:

- Add deterministic fallback behavior for missing tokens/permissions.
- Add integration tests for one successful and one degraded `gh aw` path.
- Finalize 2-minute demo script wording for "PipelineHealer + gh-aw" loop.

Acceptance:

- Demo flow is reliable under safe-mode defaults.
- Logs and UI clearly show tool outcome and fallback reason when unavailable.

## Evidence Log

### February 14, 2026

- Confirmed baseline repo CI at `.github/workflows/ci.yml`.
- Removed invalid hand-written workflow markdown files from `.github/workflows/`.
- Installed `gh aw` extension (`github/gh-aw v0.43.23`).
- Updated strategy doc: `docs/GH_AW_WORKFLOWS_QUALITY_HYGIENE_REVIEW.md`.
- Ran `gh aw init --no-mcp`.
- Added and compiled:
  - `.github/workflows/ci-doctor.md`
  - `.github/workflows/schema-consistency-checker.md`
  - `.github/workflows/breaking-change-checker.md`
- Kept `engine: copilot` for CI Doctor and removed unsupported `web-search` tool; compile now reports zero warnings.
- Opened dedicated Layer 1 PR: `https://github.com/Canepro/pipelinehealer/pull/3`.
- Closed superseded docs-only PR: `https://github.com/Canepro/pipelinehealer/pull/2`.
- Merged Layer 1 PR #3 to `main` after passing CI checks.
- Updated baseline CI install step to `uv pip install --system -e ".[dev]"` for GitHub Actions compatibility.

## Execution Commands (Layer 1)

```bash
gh extension install github/gh-aw
gh aw init
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/ci-doctor.md
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/schema-consistency-checker.md
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/breaking-change-checker.md
gh aw compile
```
