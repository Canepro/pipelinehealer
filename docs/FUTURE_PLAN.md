# Future Plan (PipelineHealer)

This document captures planned improvements after the current demo-ready baseline.

## 1) Make “Healing” More Real (Beyond PRs For Lint/Deps)

- Test failures:
  - Detect flakiness via `GITHUB_RUN_ATTEMPT`, retry signals, and “intermittent” heuristics.
  - Add safe auto-rerun once (already supported in demo mode).
  - Add quarantine options for known-flaky tests (issue + label + optional skip list).
- Timeouts:
  - Patch `timeout-minutes` deterministically (demo mode supports this for known workflow paths).
  - Add “optimize” hints (caching, split jobs) when patching is unsafe.
- Build config:
  - Only auto-fix non-secret variables, never secrets.
  - Prefer PRs that add placeholder `env:` blocks rather than trying to guess YAML structure.

## 2) Safer Patch Engine

- Add a YAML-aware patch mode for GitHub Actions workflows:
  - Parse YAML, apply minimal edits, re-serialize while preserving formatting as much as possible.
  - Avoid regex-only edits for structural changes (env blocks, step insertion).
- Improve `line_update`:
  - Support “insert after match” and “insert under key” operations.
  - Track and report “why a patch was not applied” back to the issue body.

## 3) Observability And Guardrails

- Add per-step timeouts for agent actions (log fetch, diagnosis, PR creation).
- Add retry/backoff on GitHub API 429/5xx.
- Add “cost guardrails” in demo mode (max tokens, max calls per workflow run).

## 4) Security (Phase 2)

- Add `X-API-Key` protection for `/api/*` in non-development environments.
- Hard-fail webhooks without signature in production.
- Tighten CORS for deployed origins.

## 4.1) Settings UI (Admin)

Future UX feature (requires auth):

- Add a Settings page in the dashboard to control runtime behavior:
  - `HEAL_MODE` (safe vs demo)
  - Auto PR toggle (`AUTO_CREATE_PR`)
  - Tracking issues toggle (`AUTO_CREATE_TRACKING_ISSUE_FOR_PRS`)
  - Allowed repos / org allowlist
  - Cost limits (max runs per hour, max model calls per activity)

Implementation notes:

- Require login (recommended: GitHub OAuth for demo simplicity or Entra ID for Azure alignment).
- Treat Settings as admin-only:
  - Either add an `is_admin` claim/allowlist
  - Or run behind an auth proxy (simplest for Container Apps)
- Store settings in Cosmos DB (or Key Vault for secrets).

## 5) CI Platform Adapter (Extensibility)

- Implement a `CIPlatformAdapter` interface:
  - GitHub Actions (current)
  - Jenkins / GitLab (future)
- Keep webhook handlers thin:
  - `/webhook/github`, `/webhook/jenkins`, `/webhook/gitlab`

## 6) AI Responsibilities (What To Give The Model Next)

Today the model is used mainly for:

- Summarizing job logs (LogAnalyzer agent)
- Diagnosing when patterns don’t match (Diagnosis agent)
- Writing human-readable remediation descriptions (Remediation agent prompts)

Next safe expansions:

- File selection: given repo tree + diagnosis, pick the most likely workflow/config file to patch.
- Patch suggestion: propose a structured patch plan (`json_update`, `yaml_update`, etc.), not raw diffs.
- Validation: after generating a patch plan, run consistency checks (schema, “does this key exist?”) before creating PRs.

## 7) Model Selection And Cost Control

PipelineHealer does not require a "frontier" model for most of its work today:

- Pattern matching and remediation execution are deterministic.
- LLM usage is mostly summarization, classification fallback, and writing PR/issue narratives.

Recommended approach:

- Keep the code provider-aligned (Azure OpenAI via `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT_NAME`).
- Use a cheaper deployment for local dev and routine runs (for example a mini model), and reserve a larger model only when needed.

Future enhancements:

- Per-task model routing:
  - Log summarization uses a low-cost model.
  - Diagnosis fallback uses a stronger model only when confidence is low.
  - Remediation narrative uses low-cost by default.
- First-class config for multiple deployments:
  - `AZURE_OPENAI_DEPLOYMENT_NAME_SUMMARY`
  - `AZURE_OPENAI_DEPLOYMENT_NAME_DIAGNOSIS`
  - `AZURE_OPENAI_DEPLOYMENT_NAME_REMEDIATION`
- Provider abstraction:
  - Keep Azure OpenAI as the default provider for hackathon alignment.
  - Optionally support OpenAI direct API as a secondary provider behind the same agent interfaces.
