# Feature: External Diagnostics And MCP

<!-- LAST_VERIFIED: c6e47b9 -->

This guide explains how PipelineHealer ingests external findings and how GitHub MCP is selected, gated, and verified in real runs.

## What This Feature Covers

- `ci-doctor` passive diagnostics ingestion
- async backfill behavior
- GitHub MCP integration path
- source-selection behavior (`gh_aw` passive vs direct MCP)
- MCP safety boundaries and policy checks

## Quick Start

1. Choose your diagnostics path:
   - Passive `gh_aw`: `GH_AW_TOOLS_ENABLED=true` + `GH_AW_INGESTION_MODE=passive`
   - Hybrid (recommended): `GH_AW_TOOLS_ENABLED=true` + `GH_AW_INGESTION_MODE=hybrid`
   - Direct MCP: disable passive mode first (`GH_AW_TOOLS_ENABLED=false` or `GH_AW_INGESTION_MODE=disabled`), then enable MCP.
2. Enable MCP (if you want direct MCP collection):
   - `MCP_ENABLED=true`
   - `MCP_PROVIDER=github`
   - ensure repo allowlist/tool policy allows `fetch_failure_context`
3. Verify provider health:
   - `GET /api/settings/mcp/provider-health`
4. Validate in Activity Detail:
   - `MCP Observability`
   - `Source Attribution`
   - `metadata.source_selection_path` + `metadata.source_selection_reason`

## External Diagnostics Flow

1. Activity starts with native diagnosis pipeline.
2. Passive collector checks for external findings.
3. If findings are not ready in the bounded wait window, activity completes without blocking.
4. Background backfill later enriches activity when findings appear.

Source-selection behavior:
- If `GH_AW_TOOLS_ENABLED=true` and `GH_AW_INGESTION_MODE=passive`, PipelineHealer prioritizes passive `gh_aw` diagnostics collection.
- If `GH_AW_TOOLS_ENABLED=true` and `GH_AW_INGESTION_MODE=hybrid`, PipelineHealer collects passive `gh_aw` findings and GitHub MCP context in the same activity (subject to MCP policy/health guardrails).
- If passive mode is disabled and GitHub MCP is enabled/healthy/policy-allowed, PipelineHealer uses direct GitHub MCP context collection.
- If passive mode is enabled but a repo has no `gh_aw` workflows, PipelineHealer records passive-path unavailability (`capability_unavailable`).
  - In `passive`, that is the final diagnostics path.
  - In `hybrid`, MCP collection still runs and may provide context if allowed.
- Activity metadata now includes:
  - `metadata.source_selection_path`
  - `metadata.source_selection_reason`

Tuning keys:
- `EXTERNAL_DIAGNOSTICS_WAIT_SECONDS` (default `60`)
- `EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS` (default `15`)

## MCP Safety Model

Default-safe baseline:
- `MCP_ENABLED=false`
- `MCP_READ_ONLY=true`
- hard timeout + retry caps

When enabled, MCP calls are still bounded by:
- provider health state
- per-tool policy mode
- repo allowlist checks
- read-only/write restrictions

## How To Verify MCP Is Working (No Guesswork)

Use this interpretation model:
- `source_selection_path=gh_aw_passive`:
  - expected when passive GH-AW collection is enabled (`passive` or `hybrid`).
  - `MCP Tool Calls` can be `0` and still be healthy.
- `source_selection_path=github_mcp_direct`:
  - direct MCP path selected (standalone MCP mode or hybrid mode).
  - `MCP Tool Calls` should be `> 0` for successful context fetches.
- `source_selection_path=github_mcp_blocked`:
  - MCP was configured but blocked by policy/health/provider state.
  - use the reason code to fix config.

Fast proof command:

```bash
bash scripts/ph.sh demo:e2e --triggers dependency,lint,test,build_config,timeout --wait-seconds 180 --ci-signal-wait-seconds 180 --strict
```

Then read the printed counters:
- `mcp_tool_calls_total`
- `passive_only_signal_activities`

## Read-Only vs Write Policy

Read-only mode:
- useful for context enrichment and evidence attribution.
- no mutation actions executed.

Write-capable policies (`write_with_approval` / `auto`):
- require explicit policy decisions.
- should still respect repo protections and branch strategy.

## UI Signals

- Activity chips can show diagnostics and MCP context.
- Activity Detail -> MCP panel shows:
  - provider status
  - configured tools
  - source attribution
  - tool usage counts
  - action audit entries
- Activity Detail starts with `PipelineHealer Decision`; deep MCP/evidence details are under `Technical Analysis & Enrichment`.
- Activity Detail -> External Diagnostics cards show source path selection metadata when available.

## Common Mistakes

- Enabling MCP without GitHub token:
  - provider health reports unavailable.
- Expecting MCP write behavior while `MCP_READ_ONLY=true`.
- Assuming missing external findings means failure:
  - could be pending/backfill timing.

## Related Docs

- `../API.md` (`ExternalDiagnostic`, `MCPModelPath`, provider health)
- `../LOCAL_DEMO_RUNBOOK.md` (backfill and validation workflow)
