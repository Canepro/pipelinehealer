# Pre-Deploy Placeholder Audit

<!-- LAST_VERIFIED: a2adcec -->

Use this checklist before `azd up`, before major public demos, and before final submission recording.

If any stop-ship check fails, do not deploy.

## 1) Stop-Ship Checks

1. No placeholder container images in infra.
2. No service mapping mismatches in `azure.yaml`.
3. No placeholder secrets/keys in deployed environment values.
4. Webhook signature verification is enabled for deployed environments.
5. API auth key is configured for `/api/*` in non-development environments.
6. Storage is not silently falling back to in-memory in deployed environments.

## 2) Infra and Deployment Mapping

Run:

```bash
rg -n "containerapps-helloworld|placeholder|TODO" infra/main.bicep azure.yaml
```

Expected:

- `infra/main.bicep` references your real backend/frontend images.
- `azure.yaml` service `host` and `project` values match actual deployable code.

## 3) Environment Placeholder Audit

Run:

```bash
rg -n "YOUR_|CHANGE_ME|example.com|TODO|placeholder" backend/.env.example backend/.env
```

Expected:

- `backend/.env.example` may contain placeholders.
- `backend/.env` must not contain unresolved placeholder values for active settings.

Minimum deployed values to verify:

- `ENVIRONMENT=production` (or your non-dev target)
- `API_AUTH_KEY=<non-empty>`
- `VERIFY_WEBHOOK_SIGNATURE=true`
- `GITHUB_WEBHOOK_SECRET=<non-empty>`
- `AZURE_OPENAI_ENDPOINT=<real endpoint>`
- `AZURE_OPENAI_DEPLOYMENT_NAME=<real deployment>`
- `COSMOS_DB_ENDPOINT=<real endpoint>`

## 4) Runtime Safety Mode Audit

Run (against the active backend URL):

```bash
BACKEND_URL="https://<backend-fqdn>"
curl -sS \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  "$BACKEND_URL/api/settings"
```

Expected for non-dev:

- `api_auth_enabled=true`
- `admin_api_auth_enabled=true`
- `verify_webhook_signature=true`
- `environment` is not `development` for deployed env
- `heal_mode=safe` unless you explicitly want demo behavior

## 5) Dummy Data and Demo-Only Logic Audit

Confirm these are intentional for demo only and not accidentally copied to production repos:

- Simulated failure workflow steps in `demo-repo/.github/workflows/ci.yml`
- Demo-mode auto-remediation behavior (`HEAL_MODE=demo`)
- Any hardcoded placeholder values in generated fixes (for example default env var injection behavior in demo flow)

## 6) Known Hotspots to Recheck Before Final Deploy

1. `infra/main.bicep`: placeholder image references must be removed.
2. `azure.yaml`: container app vs function mapping must be intentional and valid.
3. `backend/src/workflows/pipeline_healer.py`: ensure Cosmos-backed storage is used in deployed envs.
4. `backend/src/agents/log_analyzer.py`: `job_id=0` is currently a synthetic value; fix if real job-level traceability is required.
5. GitHub webhook mode: ensure only one active `workflow_run` hook for the target env (disable stale `smee.io` when using Azure direct webhook).
6. Demo reruns: dependency/lint fix branch names can collide on repeated runs, causing `422` on `POST /git/refs` until old fix branches are merged/cleaned.

## 7) Quick Verification Commands

```bash
# Backend health
curl -sS http://127.0.0.1:8000/health

# Latest activities
curl -sS -H "X-API-Key: $API_AUTH_KEY" "http://127.0.0.1:8000/api/activities?limit=20"

# Open remediation outputs in demo repo
gh pr list -R Canepro/pipelinehealer-demo
gh issue list -R Canepro/pipelinehealer-demo --state open
```

## 8) Sign-Off

Mark this audit complete when all stop-ship checks pass:

- [ ] Infra images are real
- [ ] Service mapping is correct
- [ ] No placeholder secrets in active env
- [ ] Webhook signature verification enforced
- [ ] API auth enforced for `/api/*` in non-dev
- [ ] Storage and remediation behavior verified in target environment

## 9) Latest Dev Sign-Off Snapshot (Feb 14, 2026)

Applied environment:

- Resource group: `rg-canepro-ph-dev-eus`
- Backend app: `ca-canepro-ph-backend`
- Frontend app: `ca-canepro-ph-frontend`
- Azure OpenAI deployment: `gpt-5-mini`
- Backend mode: `ENVIRONMENT=production`
- Heal mode: `safe`
- Log noise: Azure Cosmos/Identity/Core SDK loggers suppressed to WARNING

Verified:

- [x] Infra images are real (ACR-backed backend/frontend images in Container Apps)
- [x] Service mapping is correct (Container Apps only, no placeholder Functions service)
- [x] No placeholder secrets in active env values
- [x] Webhook signature verification enforced (`VERIFY_WEBHOOK_SIGNATURE=true`)
- [x] API auth enforced for `/api/*` in non-dev (`401` without key, `200` with key)
- [x] Storage and remediation behavior verified in deployed environment
- [x] Logs clean: `bash scripts/ph.sh logs` shows pipeline entries without Cosmos SDK noise
- [x] API doc exists (`docs/API.md`) and matches runtime endpoint contracts
