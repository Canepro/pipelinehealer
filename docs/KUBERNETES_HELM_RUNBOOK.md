# Kubernetes Helm Runbook

<!-- LAST_VERIFIED: ac2b1d4 -->

This runbook adds Kubernetes as a secondary deployment target while keeping Azure Container Apps as the default path.

## Scope

- Primary production/demo path remains: Azure Container Apps (`bash scripts/ph.sh deploy`)
- Secondary portability path: Helm chart at `charts/pipelinehealer`

## Required vs Optional (AKS Adopters)

| Goal | Required | Optional |
|---|---|---|
| Baseline AKS install (key auth) | Helm chart + cluster + registry access, backend secrets (`API_AUTH_KEY`, `ADMIN_API_KEY`, PAT, LLM key), image refs (tag or digest) | Entra config (`ENTRA_*`), frontend `VITE_ENTRA_*` |
| Entra login session in UI | Backend auth mode/config (`AUTH_MODE=hybrid` or `entra` + `ENTRA_*`) and frontend image built with `VITE_AUTH_MODE=entra` | Key headers for runtime API access when using strict `entra` |
| Migration/testing posture (recommended) | `AUTH_MODE=hybrid` so both key and Entra session auth are valid | Move later to strict `AUTH_MODE=entra` after client rollout |

Important:
- Backend auth config is runtime (`values.yaml`/Secret/ConfigMap).
- Frontend `VITE_*` auth config is build-time image input, not runtime.

## Prerequisites

- Kubernetes cluster (any CNCF-conformant distro)
- `kubectl` + `helm` installed
- Registry access to backend/frontend images
- A populated `values` override file with real secrets

## Chart Location

- Chart: `charts/pipelinehealer`
- Defaults: `charts/pipelinehealer/values.yaml`

## Quick Start

1. Select image source.
   - Recommended: immutable release digests from GitHub Release asset `release_images.md`.
   - Alternative: your own custom-built images.
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

5. Verify backend health:

```bash
kubectl -n pipelinehealer port-forward svc/pipelinehealer-backend 8000:8000
curl -sS http://127.0.0.1:8000/health
```

## Minimal Production Override Example

```yaml
backend:
  image:
    repository: caneprophacr01.azurecr.io/pipelinehealer-backend
    tag: "vX.Y.Z"
    digest: ""
  env:
    ENVIRONMENT: production
    HEAL_MODE: safe
    AUTH_MODE: hybrid
    # Optional for Entra session auth:
    # ENTRA_TENANT_ID: "<tenant-id>"
    # ENTRA_CLIENT_ID: "<api-app-id>"
    # ENTRA_ALLOWED_AUDIENCES: "api://<api-app-id>,<api-app-id>"
    # ENTRA_ADMIN_ROLES: "PipelineHealer.Admin"
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
    tag: "vX.Y.Z"
    digest: ""

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: pipelinehealer.example.com
      paths:
        - path: /
          pathType: Prefix
```

If `digest` is set, the chart uses `repository@digest` and ignores `tag`.

## Entra on AKS (Important)

To make `Use Login Session` work on AKS:

1. Backend runtime must allow bearer auth:
   - `AUTH_MODE=hybrid` (recommended rollout/testing) or `AUTH_MODE=entra`
   - correct `ENTRA_*` values in backend environment
2. Frontend image must be built with Entra enabled:
   - `VITE_AUTH_MODE=entra`
   - `VITE_ENTRA_CLIENT_ID`
   - `VITE_ENTRA_API_SCOPE`
   - `VITE_ENTRA_AUTHORITY` or `VITE_ENTRA_TENANT_ID`

If frontend image was built with `VITE_AUTH_MODE=none`, session login will not work even when backend Entra runtime is correct.

### Verify frontend auth mode from deployed image

```bash
kubectl -n pipelinehealer port-forward svc/pipelinehealer-frontend 3000:3000
JS_PATH="$(curl -fsSL http://127.0.0.1:3000/ | sed -n 's/.*src=\"\\(\\/assets\\/index-[^\"]*\\.js\\)\".*/\\1/p' | head -n1)"
curl -fsSL "http://127.0.0.1:3000${JS_PATH}" | rg 'const dd=' | head -n1
```

Expected for Entra-enabled image: `const dd="entra"...`

## Version Pinning (Recommended)

Use release digests for reproducible installs:

```yaml
backend:
  image:
    repository: caneprophacr01.azurecr.io/pipelinehealer-backend
    digest: "sha256:<backend-digest-from-release_images.md>"

frontend:
  image:
    repository: caneprophacr01.azurecr.io/pipelinehealer-frontend
    digest: "sha256:<frontend-digest-from-release_images.md>"
```

Or pin by semver tag:

```bash
helm upgrade --install pipelinehealer ./charts/pipelinehealer \
  --namespace pipelinehealer \
  --create-namespace \
  --set backend.image.tag=vX.Y.Z \
  --set frontend.image.tag=vX.Y.Z \
  -f values.prod.yaml
```

## Port-Forward Validation (No Ingress)

```bash
kubectl -n pipelinehealer port-forward svc/pipelinehealer-frontend 3000:3000
kubectl -n pipelinehealer port-forward svc/pipelinehealer-backend 8000:8000
curl http://127.0.0.1:8000/health
```

## Operational Notes

- Frontend still proxies `/api` to backend via `BACKEND_UPSTREAM`.
- For Entra session auth, image build-time `VITE_*` values must already be present in the frontend image.
- Keep `MCP_ENABLED=false` and `MCP_READ_ONLY=true` by default for first rollout.
- Use repo allowlists (`PH_ALLOWED_REPOS`, `MCP_REPO_ALLOWLIST`) before enabling wider automation.
- Use `docs/MODEL_PROVIDER_SWITCH_RUNBOOK.md` for provider migration/rollback steps.

## Common AKS Auth Pitfall

Symptom:
- UI sign-in succeeds, but `/settings` or `/control-center` shows `401 Invalid or missing admin API key` when using session login.

Root cause:
- Frontend image built with `VITE_AUTH_MODE=none` while backend is configured for Entra/hybrid.

Fix:
1. Rebuild/publish frontend image with `VITE_AUTH_MODE=entra` and required `VITE_ENTRA_*`.
2. Update Helm values to that new frontend image tag/digest.
3. `helm upgrade --install ...` and re-verify with bundle check above.

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
