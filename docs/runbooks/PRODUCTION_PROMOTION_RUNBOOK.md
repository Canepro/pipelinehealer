# Production Promotion Runbook

<!-- LAST_VERIFIED: 50ba6f3 -->

This runbook promotes a reviewed PipelineHealer release to the production Azure Container Apps lane for `pipelinehealer.canepro.me` and `api.pipelinehealer.canepro.me`.

Production is not a rename of the current dev deployment. It needs its own resource group, Container Apps, runtime configuration, secret injection, domain bindings, and smoke proof.

## Promotion Rules

1. Do not tag from an unreviewed branch.
2. Do not copy, print, commit, or paste secret values.
3. Use Infisical as the source for runtime/API/CI/service secrets, then inject values into deploy commands with `infisical run`.
4. Use release images by digest through `deploy:release`; do not build production from a local working tree.
5. Run Azure `what-if` before provisioning or changing production resources.
6. Keep production storage durable. `STORAGE_MODE=memory` is stop-ship outside explicit demos.
7. Keep `HEAL_MODE=safe`, repo allowlists explicit, and webhook signature verification enabled.

## Target Shape

Recommended initial production lane:

| Resource | Value |
| --- | --- |
| Resource group | `rg-canepro-ph-prod-eus2` |
| Bicep parameters | `infra/main.prod.bicepparam` |
| Container Apps environment | `cae-canepro-ph-prod-eus2` |
| Backend app | `ca-canepro-ph-prod-backend` |
| Frontend app | `ca-canepro-ph-prod-frontend` |
| ACR | `caneprophacrprod01` |
| Backend domain | `api.pipelinehealer.canepro.me` |
| Frontend domain | `pipelinehealer.canepro.me` |
| Secret source | Infisical `prod` environment |

The first prod lane uses a separate production ACR. The release workflow still publishes public images to GHCR, so production promotion imports the reviewed GHCR release images into the prod ACR before running `deploy:release`.

## Data Continuity

Existing production history is in the current Cosmos DB lane:

| Resource | Value |
| --- | --- |
| Resource group | `rg-canepro-ph-dev-eus` |
| Cosmos account | `pipelinehealerdev-cosmos-zarrajklt3i5u` |
| Database | `pipelinehealer` |
| Containers | `activities`, `workflow_runs` |
| Partition key | `/repositoryId` |

Do not treat the new production lane as a clean database unless you explicitly want to discard the previous operational history. The safe default for `v0.8.2` is continuity:

1. Keep the existing Cosmos account as the source of record during the first production cutover.
2. Grant the new production backend managed identity Cosmos DB data-plane access to that existing account.
3. Override the production backend runtime env to use the existing Cosmos endpoint and `COSMOS_DB_DATABASE=pipelinehealer`.
4. Only move data into a new prod Cosmos account after a separate export/import plan, count comparison, and rollback checkpoint.

`infra/main.prod.bicepparam` sets `createCosmosDb=false`, so the production infrastructure deployment does not create a replacement Cosmos account during this cutover.

After the production backend app exists, grant its identity access to the existing Cosmos account:

```bash
PROD_BACKEND_PRINCIPAL_ID="$(az containerapp show \
  --resource-group rg-canepro-ph-prod-eus2 \
  --name ca-canepro-ph-prod-backend \
  --query identity.principalId \
  --output tsv)"

COSMOS_CONTRIBUTOR_ROLE_ID="$(az cosmosdb sql role definition list \
  --resource-group rg-canepro-ph-dev-eus \
  --account-name pipelinehealerdev-cosmos-zarrajklt3i5u \
  --query "[?roleName=='Cosmos DB Built-in Data Contributor'].id | [0]" \
  --output tsv)"

az cosmosdb sql role assignment create \
  --resource-group rg-canepro-ph-dev-eus \
  --account-name pipelinehealerdev-cosmos-zarrajklt3i5u \
  --role-definition-id "$COSMOS_CONTRIBUTOR_ROLE_ID" \
  --scope "/" \
  --principal-id "$PROD_BACKEND_PRINCIPAL_ID"
```

Set these values in the production Infisical environment before `deploy:release`:

```env
STORAGE_MODE=cosmos
COSMOS_DB_ENDPOINT=https://pipelinehealerdev-cosmos-zarrajklt3i5u.documents.azure.com:443/
COSMOS_DB_DATABASE=pipelinehealer
```

Then `deploy:release --secure-secrets` will sync the runtime env from the Infisical-injected process and keep the production app pointed at the existing data.

Before pointing Cloudflare DNS at the new frontend/backend, verify the backend is using the intended Cosmos endpoint:

```bash
az containerapp show \
  --resource-group rg-canepro-ph-prod-eus2 \
  --name ca-canepro-ph-prod-backend \
  --query "properties.template.containers[0].env[?name=='COSMOS_DB_ENDPOINT' || name=='COSMOS_DB_DATABASE' || name=='STORAGE_MODE']"
```

Do not delete, reinitialize, or rename the existing Cosmos account during this release. If a later release migrates data into `rg-canepro-ph-prod-eus2`, use a separate migration PR/runbook and capture pre/post counts for both containers.

## Model Runtime

Production uses Codex App Server as the first LLM route for cost control:

```env
LLM_PROVIDER=codex_app_server
CODEX_APP_SERVER_TRANSPORT=websocket
CODEX_APP_SERVER_MODEL=gpt-5.4
CODEX_APP_SERVER_WS_URL=<wss-url>
CODEX_APP_SERVER_WS_ALLOW_REMOTE=true
CODEX_APP_SERVER_WS_BEARER_TOKEN=<secret-if-required>
```

`infra/main.prod.bicepparam` disables managed Azure AI/OpenAI creation for production. This avoids provisioning a billable Azure model deployment when the app should call a Codex App Server bridge instead.

Azure Container Apps cannot rely on the local `codex app-server` stdio path unless the production image includes the Codex binary and has a production-safe auth bootstrap. Use WebSocket transport for ACA production and keep the bridge URL and bearer token in Infisical. The backend refuses non-loopback WebSocket URLs unless `CODEX_APP_SERVER_WS_ALLOW_REMOTE=true`, so that production opt-in is intentional and visible.

If Codex App Server is unavailable, rollback is a configuration action: set `LLM_PROVIDER=azure_openai` or `LLM_PROVIDER=openai_compatible` with the matching provider secrets and redeploy the same release image.

## Infisical Boundary

Use metadata in Git and secret values in Infisical.

Recommended metadata:

```env
SETTINGS_SECRET_BACKEND=infisical
INFISICAL_ENVIRONMENT=prod
INFISICAL_SECRET_PATH=/pipelinehealer/prod
INFISICAL_PROJECT_ID=<infisical-project-id>
```

Required production secret names include:

```text
API_AUTH_KEY
ADMIN_API_KEY
GITHUB_WEBHOOK_SECRET
AUDIT_SALT
SETTINGS_DB_ENCRYPTION_KEY
AGENT_HANDOFF_CALLBACK_SECRET
CODEX_APP_SERVER_WS_BEARER_TOKEN
```

Optional names depend on enabled providers:

```text
AZURE_OPENAI_API_KEY
GITHUB_PERSONAL_ACCESS_TOKEN
GITHUB_APP_PRIVATE_KEY
OPENAI_COMPATIBLE_API_KEY
CODEX_APP_SERVER_HANDOFF_URL
OPENCLAW_HANDOFF_URL
HERMES_HANDOFF_URL
POSTGRES_DSN
INFISICAL_TOKEN
```

Do not run `infisical secrets get`, `infisical export`, or value-copy commands unless the current operator explicitly approves value handling for that task.

## Release Sequence

Prepare and review:

```bash
git switch -c release/v0.8.2
bash scripts/release.sh 0.8.2
bash scripts/check_version_sync.sh
cd frontend && bun install --frozen-lockfile && bun run lint && bun run test && bun run build
cd ../backend && pytest -q
git push origin release/v0.8.2
gh pr create --base main --head release/v0.8.2 --title "chore(release): v0.8.2"
```

Wait for attached review agents and CI. Address comments, resolve review threads, and rerun checks. Tag only the reviewed branch commit:

```bash
git tag -a v0.8.2 -m "Release v0.8.2"
git push origin v0.8.2
bash scripts/release_verify.sh v0.8.2
```

## Provision Or Update Production

Create the resource group if it does not exist:

```bash
az group create --name rg-canepro-ph-prod-eus2 --location eastus2
```

Preview the Azure changes first:

```bash
az deployment group what-if \
  --resource-group rg-canepro-ph-prod-eus2 \
  --template-file infra/acr.bicep \
  --parameters acrName=caneprophacrprod01
```

Create or update the production ACR:

```bash
az deployment group create \
  --resource-group rg-canepro-ph-prod-eus2 \
  --template-file infra/acr.bicep \
  --parameters acrName=caneprophacrprod01
```

Import the reviewed release images from public GHCR into the prod ACR:

```bash
az acr import \
  --name caneprophacrprod01 \
  --source ghcr.io/canepro/pipelinehealer-backend:v0.8.2 \
  --image pipelinehealer-backend:v0.8.2 \
  --force

az acr import \
  --name caneprophacrprod01 \
  --source ghcr.io/canepro/pipelinehealer-frontend:v0.8.2 \
  --image pipelinehealer-frontend:v0.8.2 \
  --force
```

Preview the application infrastructure changes:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  bash -c 'for key in API_AUTH_KEY ADMIN_API_KEY GITHUB_WEBHOOK_SECRET STORAGE_MODE COSMOS_DB_ENDPOINT COSMOS_DB_DATABASE LLM_PROVIDER CODEX_APP_SERVER_TRANSPORT CODEX_APP_SERVER_WS_URL; do test -n "${!key:-}" || { echo "missing $key" >&2; exit 1; }; done'

infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  az deployment group what-if \
    --resource-group rg-canepro-ph-prod-eus2 \
    --template-file infra/main.bicep \
    --parameters infra/main.prod.bicepparam
```

Apply only after the `what-if` output is expected:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  bash -c 'for key in API_AUTH_KEY ADMIN_API_KEY GITHUB_WEBHOOK_SECRET STORAGE_MODE COSMOS_DB_ENDPOINT COSMOS_DB_DATABASE LLM_PROVIDER CODEX_APP_SERVER_TRANSPORT CODEX_APP_SERVER_WS_URL; do test -n "${!key:-}" || { echo "missing $key" >&2; exit 1; }; done'

infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  az deployment group create \
    --resource-group rg-canepro-ph-prod-eus2 \
    --template-file infra/main.bicep \
    --parameters infra/main.prod.bicepparam
```

Promote the reviewed release images. `deploy:release` reads secret values from
an env file (`--secure-secrets` then binds them as Container App secrets), so on
an Infisical-only host the snippet below materializes a short-lived env file from
the injected process env and removes it on exit. The whole command is wrapped in
`bash -c` so `infisical run -- ...` invokes an executable rather than a leading
env assignment:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- bash -c '
  set -euo pipefail
  umask 077
  release_env="$(mktemp)"
  trap "rm -f \"$release_env\"" EXIT
  for key in API_AUTH_KEY ADMIN_API_KEY GITHUB_WEBHOOK_SECRET GITHUB_PERSONAL_ACCESS_TOKEN CODEX_APP_SERVER_WS_BEARER_TOKEN; do
    if [ -n "${!key:-}" ]; then printf "%s=%s\n" "$key" "${!key}" >>"$release_env"; fi
  done
  PH_RG=rg-canepro-ph-prod-eus2 \
  PH_BACKEND_APP=ca-canepro-ph-prod-backend \
  PH_FRONTEND_APP=ca-canepro-ph-prod-frontend \
  bash scripts/ph.sh deploy:release \
    --resource-group rg-canepro-ph-prod-eus2 \
    --acr-name caneprophacrprod01 \
    --backend-app ca-canepro-ph-prod-backend \
    --frontend-app ca-canepro-ph-prod-frontend \
    --release-version v0.8.2 \
    --env-file "$release_env" \
    --secure-secrets
'
```

## Domain And Smoke Proof

After Container Apps have stable FQDNs, bind Cloudflare-backed custom domains through Azure Container Apps managed certificates or uploaded certificates.

Minimum smoke proof:

```bash
curl -fsS https://api.pipelinehealer.canepro.me/health
curl -fsS https://pipelinehealer.canepro.me/runtime-config.js
PH_RG=rg-canepro-ph-prod-eus2 PH_BACKEND_APP=ca-canepro-ph-prod-backend PH_FRONTEND_APP=ca-canepro-ph-prod-frontend bash scripts/ph.sh status
```

Expected:

- `/health` reports `version: "0.8.1"`
- `/health` reports `environment: "production"`
- storage is `cosmos_db` or `postgres`, not `in_memory`
- frontend runtime config points at the production API
- settings auth requires admin authorization
- webhook signature verification is enabled
- external-agent handoff targets are disabled or explicitly allowlisted

## Rollback

Rollback by redeploying the last known good release image:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- bash -c '
  set -euo pipefail
  umask 077
  release_env="$(mktemp)"
  trap "rm -f \"$release_env\"" EXIT
  for key in API_AUTH_KEY ADMIN_API_KEY GITHUB_WEBHOOK_SECRET GITHUB_PERSONAL_ACCESS_TOKEN; do
    if [ -n "${!key:-}" ]; then printf "%s=%s\n" "$key" "${!key}" >>"$release_env"; fi
  done
  PH_RG=rg-canepro-ph-prod-eus2 \
  PH_BACKEND_APP=ca-canepro-ph-prod-backend \
  PH_FRONTEND_APP=ca-canepro-ph-prod-frontend \
  bash scripts/ph.sh deploy:release \
    --resource-group rg-canepro-ph-prod-eus2 \
    --acr-name caneprophacrprod01 \
    --backend-app ca-canepro-ph-prod-backend \
    --frontend-app ca-canepro-ph-prod-frontend \
    --release-version v0.7.2 \
    --env-file "$release_env" \
    --secure-secrets
'
```

Record the rollback reason, release tag, backend revision, frontend revision, and health response in the release PR or incident record.
