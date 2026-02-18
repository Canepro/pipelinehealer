# Feature: Settings And Policy Controls

<!-- LAST_VERIFIED: a95ed82 -->

This guide explains runtime controls, persistence behavior, and governance guardrails.

## What This Feature Covers

- Settings page workflow (`/settings`)
- Runtime vs persisted settings
- Admin audit trail
- Guardrails for repos, retries, and MCP tool policy

## Quick Start

1. Open `/settings`.
2. Authenticate as admin:
   - key mode: enter `X-Admin-Key`
   - Entra mode: use `Use Login Session`
3. Change only one policy group at a time.
4. Save, then optionally persist:
   - runtime update: `PATCH /api/settings`
   - durable save: `POST /api/settings/persist`

## Runtime vs Durable

- Runtime settings apply immediately.
- Persisted settings survive restarts/redeploys.
- In Azure, persistence is Cosmos DB-backed.

CLI equivalents:
```bash
bash scripts/ph.sh settings:check
bash scripts/ph.sh settings:audit --limit 10
bash scripts/ph.sh settings:persist --from-settings
```

## MCP Guardrail Policy Model

Per-tool policy values:
- `disabled`
- `read_only`
- `write_with_approval`
- `auto`

Current tool keys:
- `fetch_failure_context`
- `publish_artifact`
- `rerun_pipeline`

Recommended baseline:
- keep writes blocked by default (`MCP_READ_ONLY=true`)
- explicitly allow repos with `mcp_repo_allowlist`
- use short timeout/retry budgets

## Repo Scope Controls

- `ph_allowed_repos`: webhook processing scope
- `mcp_repo_allowlist`: MCP action scope

Best practice:
- use explicit owner/repo allowlists.
- avoid wildcard/global scope in shared environments.

## Audit Trail

Every settings change logs:
- changed keys and old/new values
- actor fingerprint
- request ID
- client metadata

Use request IDs in admin changes:
```bash
curl -X PATCH \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: policy-update-001" \
  -H "Content-Type: application/json" \
  -d '{"heal_mode":"safe"}' \
  "$BACKEND_URL/api/settings"
```

## Common Mistakes

- Changing `VITE_*` then using only `deploy:env`:
  - frontend config is build-time, use full `deploy`.
- Large multi-setting edits without request ID:
  - harder to trace/rollback.
- Leaving allowlists empty in production:
  - expands blast radius.

## Related Docs

- `../API.md` (`GET/PATCH/POST /api/settings*`)
- `../CLI.md` (`settings:persist` flags)
