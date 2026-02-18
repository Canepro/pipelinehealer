# Feature: External Diagnostics And MCP

<!-- LAST_VERIFIED: a95ed82 -->

This guide explains how PipelineHealer ingests external findings and how GitHub MCP is used safely.

## What This Feature Covers

- `ci-doctor` passive diagnostics ingestion
- async backfill behavior
- GitHub MCP integration path
- MCP safety boundaries and policy checks

## Quick Start

1. Keep external diagnostics enabled:
   - `GH_AW_TOOLS_ENABLED=true`
   - `GH_AW_INGESTION_MODE=passive`
2. Enable MCP (optional):
   - `MCP_ENABLED=true`
   - `MCP_PROVIDER=github`
3. Verify health:
   - `GET /api/settings/mcp/provider-health`
4. Check Activity Detail:
   - `MCP Observability`
   - external findings panel

## External Diagnostics Flow

1. Activity starts with native diagnosis pipeline.
2. Passive collector checks for external findings.
3. If findings are not ready in the bounded wait window, activity completes without blocking.
4. Background backfill later enriches activity when findings appear.

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

## Common Mistakes

- Enabling MCP without GitHub token:
  - provider health reports unavailable.
- Expecting MCP write behavior while `MCP_READ_ONLY=true`.
- Assuming missing external findings means failure:
  - could be pending/backfill timing.

## Related Docs

- `../API.md` (`ExternalDiagnostic`, `MCPModelPath`, provider health)
- `../LOCAL_DEMO_RUNBOOK.md` (backfill and validation workflow)
