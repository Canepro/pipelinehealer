# GitHub Agentic Workflows Implementation Tracker

**Last updated:** February 14, 2026

This tracker is the execution source of truth for GitHub Agentic Workflows adoption in PipelineHealer.

## Scope

- **Layer 1 (Repo hygiene):** valid `gh aw` setup in this repository.
- **Layer 2 (Product feature):** PipelineHealer invokes `gh aw` workflows as tools for monitored repos.

## Status Summary

| Workstream | Status | Notes |
|---|---|---|
| Layer 1: baseline repo hygiene | In progress | `gh aw init/add/compile` completed; next step is PR creation and review |
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

## Execution Commands (Layer 1)

```bash
gh extension install github/gh-aw
gh aw init
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/ci-doctor.md
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/schema-consistency-checker.md
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.42.13/.github/workflows/breaking-change-checker.md
gh aw compile
```
