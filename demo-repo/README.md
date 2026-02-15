# PipelineHealer Demo Repository

This repository is used to demonstrate and test [PipelineHealer](https://github.com/Canepro/pipelinehealer)'s self-healing capabilities.

## Quick Start

### Run all default failure types (full E2E demo)

If this repo is checked out under `pipelinehealer/demo-repo`, run:

```bash
cd <repo-root>/pipelinehealer
bash scripts/ph.sh demo:e2e --wait-seconds 40
```

This handles webhook sync, fixture reset, workflow dispatch (for the default set: `dependency,lint,test,build_config,timeout`), and verification output.

### Run a single failure type

To trigger just one scenario, use `--triggers` with a single value:

```bash
bash scripts/ph.sh demo:e2e --triggers dependency --wait-seconds 40
bash scripts/ph.sh demo:e2e --triggers lint --wait-seconds 40
bash scripts/ph.sh demo:e2e --triggers prettier --wait-seconds 40
bash scripts/ph.sh demo:e2e --triggers permissions --wait-seconds 40
bash scripts/ph.sh demo:e2e --triggers test --wait-seconds 40
bash scripts/ph.sh demo:e2e --triggers build_config --wait-seconds 40
bash scripts/ph.sh demo:e2e --triggers timeout --wait-seconds 60
```

### Run a custom subset

Combine any failure types as a comma-separated list:

```bash
bash scripts/ph.sh demo:e2e --triggers dependency,lint,prettier --wait-seconds 40
```

### Trigger via GitHub UI (no CLI)

1. Go to **Actions** > **CI** > **Run workflow**
2. Select a `failure_type` from the dropdown
3. Click **Run workflow**

## Failure Types

| Type | What it simulates | PipelineHealer response |
|------|-------------------|------------------------|
| `none` | Normal successful build | No action (healthy run) |
| `dependency` | Missing npm module (`left-pad`) | **PR** — adds the missing dependency to `package.json` |
| `lint` | ESLint v9 missing flat config | **PR** — adds `eslint.config.js` |
| `prettier` | Prettier formatting violation | **Issue** — formatting diagnostics and fix suggestions |
| `permissions` | `403 Resource not accessible by integration` | **Issue** — recommends adding a `permissions` block |
| `test` | Intermittent test failure (passes on rerun) | **Issue** — structured failure analysis; may trigger rerun |
| `build_config` | Missing `REQUIRED_CONFIG` env var | **Issue** — missing environment variable diagnostics |
| `timeout` | `sleep 120` with `timeout-minutes: 1` | **Issue** — timeout analysis and recommendations |

## How PipelineHealer Responds

When a failure occurs, PipelineHealer will:

1. **Detect** the failed workflow run via webhook
2. **Analyze** the failure logs using an AI log-analysis agent
3. **Diagnose** the root cause with pattern matching + LLM reasoning
4. **Remediate** by creating a PR (for fixable issues) or an issue (for advisory)

## CI Doctor (GitHub Agentic Workflows)

This repo also includes a **ci-doctor** agentic workflow (`.github/workflows/ci-doctor.md`) that runs independently via GitHub's Agentic Workflows platform. When the CI workflow fails, ci-doctor performs its own investigation and opens a `[CI Failure Doctor]` issue. PipelineHealer can passively ingest these findings for richer diagnostics.

## Tooling Note

This demo repo's CI uses **Bun** (`oven-sh/setup-bun`) to align with PipelineHealer's frontend stack.
