# Model Provider Switch Runbook

<!-- LAST_VERIFIED: c78ae9b -->

This runbook covers safe switching between model providers and fast rollback.

## Supported Runtime Providers

- `azure_openai` (default)
- `openai_compatible`
- `custom` (scaffold/no-op path)

## Safety First

Before switching:

1. Keep `HEAL_MODE=safe`.
2. Ensure repo allowlists are set (`PH_ALLOWED_REPOS`, optional `MCP_REPO_ALLOWLIST`).
3. Verify current state:

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.azure_openai_deployment_name,.openai_compatible_base_url,.openai_compatible_model'
```

## Switch via Settings API (Recommended for auditable runtime change)

Use an explicit request ID so the change is traceable in audit logs.

### 1) Switch to OpenAI-compatible

```bash
curl -sS -X PATCH "$PH_BACKEND_URL/api/settings" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: provider-switch-openai-compatible-$(date +%s)" \
  -d '{
    "llm_provider": "openai_compatible",
    "openai_compatible_base_url": "https://api.openai.com/v1",
    "openai_compatible_model": "gpt-5-mini"
  }'
```

### 2) Persist to durable config and redeploy env

```bash
bash scripts/ph.sh settings:persist --from-settings
```

### 3) Verify health + runtime

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.openai_compatible_base_url,.openai_compatible_model'
curl -sS "$PH_BACKEND_URL/api/settings/llm/provider-health" \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" | jq
```

## Rollback (OpenAI-compatible -> Azure)

```bash
curl -sS -X PATCH "$PH_BACKEND_URL/api/settings" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: provider-rollback-azure-$(date +%s)" \
  -d '{
    "llm_provider": "azure_openai",
    "azure_openai_deployment_name": "gpt-5-mini"
  }'

bash scripts/ph.sh settings:persist --from-settings
bash scripts/ph.sh settings:check | jq '.llm_provider,.azure_openai_deployment_name'
```

## Failure Handling Playbook

If provider switch degrades diagnosis/remediation quality or reliability:

1. Roll back provider immediately (commands above).
2. Check recent activity model path telemetry in UI (`Model Path`, `Fallback Used`, `LLM Errors`).
3. Review logs:

```bash
bash scripts/ph.sh logs:grep --pattern "openai|AzureOpenAI|retry|fallback|provider"
```

4. Confirm current settings:

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.openai_compatible_base_url,.openai_compatible_model,.azure_openai_deployment_name'
```

## Validation Checklist

- Provider health endpoint returns `available=true`.
- New activities show expected model path label.
- No sustained spike in `Fallback Used` or `LLM Errors`.
- Audit trail contains your switch request IDs.

## Provider Health Reason Codes

OpenAI-compatible provider health now returns actionable `reason` values:

- `ok`: probe succeeded
- `missing_base_url`, `missing_model`, `missing_api_key`: missing required config
- `probe_timeout`: probe request timed out
- `probe_auth_failed`: API key rejected (`401/403`)
- `probe_rate_limited`: provider rate-limited probe (`429`)
- `probe_provider_error`: upstream provider server error (`5xx`)
- `probe_http_error`: other non-success HTTP status
- `probe_network_error`: DNS/TCP/connectivity failure

Use these reason codes to choose rollback urgency:

- **Immediate rollback:** `probe_auth_failed`, `probe_provider_error` (persistent), repeated `probe_timeout`
- **Monitor + retry:** `probe_rate_limited`, occasional `probe_timeout`
- **Fix config:** `missing_*`
