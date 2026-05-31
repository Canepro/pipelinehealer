# Model Provider Switch Runbook

<!-- LAST_VERIFIED: 3d754c5 -->

This runbook covers safe switching between model providers and fast rollback.

## Supported Runtime Providers

- `codex_app_server` (default)
- `azure_openai`
- `openai_compatible`
- `custom` (scaffold/no-op path)

## Safety First

Before switching:

1. Keep `HEAL_MODE=safe`.
2. Ensure repo allowlists are set (`PH_ALLOWED_REPOS`, optional `MCP_REPO_ALLOWLIST`).
3. Verify current state:

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.codex_app_server_model,.codex_app_server_transport,.azure_openai_deployment_name,.openai_compatible_base_url,.openai_compatible_model'
```

## Switch via Settings API (Recommended for auditable runtime change)

Use an explicit request ID so the change is traceable in audit logs.

### 1) Switch to Codex App Server

```bash
curl -sS -X PATCH "$PH_BACKEND_URL/api/settings" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: provider-switch-codex-app-server-$(date +%s)" \
  -d '{
    "llm_provider": "codex_app_server",
    "codex_app_server_transport": "stdio",
    "codex_app_server_model": "gpt-5.4",
    "llm_model_analysis": "",
    "llm_model_diagnosis": "",
    "llm_model_remediation": ""
  }'
```

### 2) Switch to OpenAI-compatible

```bash
curl -sS -X PATCH "$PH_BACKEND_URL/api/settings" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: provider-switch-openai-compatible-$(date +%s)" \
  -d '{
    "llm_provider": "openai_compatible",
    "openai_compatible_base_url": "https://api.openai.com/v1",
    "openai_compatible_model": "provider-model-name"
  }'
```

### 3) Optional: sync to startup env if you want the provider choice to survive as an env override

```bash
bash scripts/ph.sh settings:persist --from-settings
```

Notes:
- the `PATCH /api/settings` call above already applied the runtime change and persisted it durably
- run `settings:persist --from-settings` only if you intentionally want local `backend/.env` sync and the deprecated compatibility audit/redeploy flow

### 4) Verify health + runtime

```bash
bash scripts/ph.sh settings:check | jq '.llm_provider,.codex_app_server_model,.openai_compatible_base_url,.openai_compatible_model'
curl -sS "$PH_BACKEND_URL/api/settings/llm/provider-health" \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" | jq
```

## Rollback (Codex/OpenAI-compatible -> Azure)

```bash
curl -sS -X PATCH "$PH_BACKEND_URL/api/settings" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: provider-rollback-azure-$(date +%s)" \
  -d '{
    "llm_provider": "azure_openai",
    "azure_openai_deployment_name": "my-azure-deployment"
  }'

bash scripts/ph.sh settings:persist --from-settings
bash scripts/ph.sh settings:check | jq '.llm_provider,.azure_openai_deployment_name'
```

Rollback note:
- the rollback `PATCH` is already the real durable runtime change
- re-running `settings:persist --from-settings` is optional and only needed when you also want startup env sync

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
