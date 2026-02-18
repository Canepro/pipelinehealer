# Kubernetes Helm Runbook

<!-- LAST_VERIFIED: 647ddde -->

This runbook adds Kubernetes as a secondary deployment target while keeping Azure Container Apps as the default path.

## Scope

- Primary production/demo path remains: Azure Container Apps (`bash scripts/ph.sh deploy`)
- Secondary portability path: Helm chart at `charts/pipelinehealer`

## Prerequisites

- Kubernetes cluster (any CNCF-conformant distro)
- `kubectl` + `helm` installed
- Registry access to backend/frontend images
- A populated `values` override file with real secrets

## Chart Location

- Chart: `charts/pipelinehealer`
- Defaults: `charts/pipelinehealer/values.yaml`

## Quick Start

1. Build and push images (or reuse existing tagged images).
2. Create a values override file (example below).
3. Install/upgrade:

```bash
helm upgrade --install pipelinehealer ./charts/pipelinehealer \
  --namespace pipelinehealer \
  --create-namespace \
  -f values.prod.yaml
```

4. Verify rollout:

```bash
kubectl -n pipelinehealer get pods,svc,ingress
kubectl -n pipelinehealer rollout status deploy/pipelinehealer-backend
kubectl -n pipelinehealer rollout status deploy/pipelinehealer-frontend
```

## Minimal Production Override Example

```yaml
backend:
  image:
    repository: caneprophacr01.azurecr.io/pipelinehealer-backend
    tag: "0.1.1"
  env:
    ENVIRONMENT: production
    HEAL_MODE: safe
    AUTH_MODE: hybrid
    LLM_PROVIDER: azure_openai
    AZURE_OPENAI_ENDPOINT: https://<resource>.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT_NAME: gpt-5-mini
    PH_ALLOWED_REPOS: owner/repo1,owner/repo2
  secretEnv:
    API_AUTH_KEY: <set-me>
    ADMIN_API_KEY: <set-me>
    AZURE_OPENAI_API_KEY: <set-me>
    GITHUB_PERSONAL_ACCESS_TOKEN: <set-me>
    GITHUB_WEBHOOK_SECRET: <set-me>

frontend:
  image:
    repository: caneprophacr01.azurecr.io/pipelinehealer-frontend
    tag: "0.1.1"

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: pipelinehealer.example.com
      paths:
        - path: /
          pathType: Prefix
```

## Port-Forward Validation (No Ingress)

```bash
kubectl -n pipelinehealer port-forward svc/pipelinehealer-frontend 3000:3000
kubectl -n pipelinehealer port-forward svc/pipelinehealer-backend 8000:8000
curl http://127.0.0.1:8000/health
```

## Operational Notes

- Frontend still proxies `/api` to backend via `BACKEND_UPSTREAM`.
- Keep `MCP_ENABLED=false` and `MCP_READ_ONLY=true` by default for first rollout.
- Use repo allowlists (`PH_ALLOWED_REPOS`, `MCP_REPO_ALLOWLIST`) before enabling wider automation.
- Use `docs/MODEL_PROVIDER_SWITCH_RUNBOOK.md` for provider migration/rollback steps.

## Rollback

Rollback to previous Helm revision:

```bash
helm -n pipelinehealer history pipelinehealer
helm -n pipelinehealer rollback pipelinehealer <REVISION>
```

Then verify:

```bash
kubectl -n pipelinehealer rollout status deploy/pipelinehealer-backend
kubectl -n pipelinehealer rollout status deploy/pipelinehealer-frontend
```
