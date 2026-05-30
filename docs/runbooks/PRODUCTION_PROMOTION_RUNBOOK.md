# Production Promotion Runbook

<!-- LAST_VERIFIED: 2c862a3 -->

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
AZURE_OPENAI_API_KEY
AGENT_HANDOFF_CALLBACK_SECRET
```

Optional names depend on enabled providers:

```text
GITHUB_PERSONAL_ACCESS_TOKEN
GITHUB_APP_PRIVATE_KEY
OPENAI_COMPATIBLE_API_KEY
CODEX_APP_SERVER_WS_BEARER_TOKEN
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
git switch -c release/v0.8.0
bash scripts/release.sh 0.8.0
bash scripts/check_version_sync.sh
cd frontend && bun install --frozen-lockfile && bun run lint && bun run test && bun run build
cd ../backend && pytest -q
git push origin release/v0.8.0
gh pr create --base main --head release/v0.8.0 --title "chore(release): v0.8.0"
```

Wait for attached review agents and CI. Address comments, resolve review threads, and rerun checks. Tag only the reviewed branch commit:

```bash
git tag -a v0.8.0 -m "Release v0.8.0"
git push origin v0.8.0
bash scripts/release_verify.sh v0.8.0
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
  --source ghcr.io/canepro/pipelinehealer-backend:v0.8.0 \
  --image pipelinehealer-backend:v0.8.0 \
  --force

az acr import \
  --name caneprophacrprod01 \
  --source ghcr.io/canepro/pipelinehealer-frontend:v0.8.0 \
  --image pipelinehealer-frontend:v0.8.0 \
  --force
```

Preview the application infrastructure changes:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  az deployment group what-if \
    --resource-group rg-canepro-ph-prod-eus2 \
    --template-file infra/main.bicep \
    --parameters infra/main.prod.bicepparam
```

Apply only after the `what-if` output is expected:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  az deployment group create \
    --resource-group rg-canepro-ph-prod-eus2 \
    --template-file infra/main.bicep \
    --parameters infra/main.prod.bicepparam
```

Promote the reviewed release images:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  PH_RG=rg-canepro-ph-prod-eus2 \
  PH_BACKEND_APP=ca-canepro-ph-prod-backend \
  PH_FRONTEND_APP=ca-canepro-ph-prod-frontend \
  bash scripts/ph.sh deploy:release \
    --resource-group rg-canepro-ph-prod-eus2 \
    --acr-name caneprophacrprod01 \
    --backend-app ca-canepro-ph-prod-backend \
    --frontend-app ca-canepro-ph-prod-frontend \
    --release-version v0.8.0 \
    --secure-secrets
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

- `/health` reports `version: "0.8.0"`
- `/health` reports `environment: "production"`
- storage is `cosmos_db` or `postgres`, not `in_memory`
- frontend runtime config points at the production API
- settings auth requires admin authorization
- webhook signature verification is enabled
- external-agent handoff targets are disabled or explicitly allowlisted

## Rollback

Rollback by redeploying the last known good release image:

```bash
infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  PH_RG=rg-canepro-ph-prod-eus2 \
  PH_BACKEND_APP=ca-canepro-ph-prod-backend \
  PH_FRONTEND_APP=ca-canepro-ph-prod-frontend \
  bash scripts/ph.sh deploy:release \
    --resource-group rg-canepro-ph-prod-eus2 \
    --acr-name caneprophacrprod01 \
    --backend-app ca-canepro-ph-prod-backend \
    --frontend-app ca-canepro-ph-prod-frontend \
    --release-version v0.7.2 \
    --secure-secrets
```

Record the rollback reason, release tag, backend revision, frontend revision, and health response in the release PR or incident record.
