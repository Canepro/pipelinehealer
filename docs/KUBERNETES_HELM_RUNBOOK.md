# Kubernetes Helm Runbook

<!-- LAST_VERIFIED: 1f53853 -->

This runbook adds Kubernetes as a secondary deployment target while keeping Azure Container Apps as the default path.

## Stop: Read This First

This project is open source, and release portability is validated via anonymous-pullability gates at release time.

Do not treat Helm success output by itself as deployment success. `helm upgrade --install` can return `deployed` while workloads fail to pull images.

Known failure signatures:
- Pod status: `ErrImagePull` / `ImagePullBackOff`
- Pod events with registry token failures (`401 Unauthorized`, `403 Forbidden`)

Portability hardening tracker [#37](https://github.com/Canepro/pipelinehealer/issues/37) is closed in `v0.3.0`.

## Scope

- Primary production/demo path remains: Azure Container Apps (`bash scripts/ph.sh deploy`)
- Secondary portability path: Helm chart at `charts/pipelinehealer`

## Required vs Optional (Cluster Adopters)

| Goal | Required | Optional |
|---|---|---|
| Baseline cluster install (key auth) | Helm chart + cluster, backend secrets (`API_AUTH_KEY`, `ADMIN_API_KEY`, PAT, LLM key), image refs (tag or digest) reachable by nodes | Entra config (`ENTRA_*`), frontend `VITE_*` runtime env |
| Entra login session in UI | Backend auth mode/config (`AUTH_MODE=hybrid` or `entra` + `ENTRA_*`) and frontend runtime env `VITE_AUTH_MODE=entra` + required `VITE_ENTRA_*` | Key headers for runtime API access when using strict `entra` |
| Migration/testing posture (recommended) | `AUTH_MODE=hybrid` so both key and Entra session auth are valid | Move later to strict `AUTH_MODE=entra` after client rollout |

Important:
- Backend auth config is runtime (`values.yaml`/Secret/ConfigMap).
- Frontend `VITE_*` auth/api config is runtime (`values.yaml` -> ConfigMap/Secret -> container env).

## Prerequisites

- Kubernetes cluster (any CNCF-conformant distro)
- `kubectl` + `helm` installed
- Node egress to GHCR (default) or credentials for your private registry override
- A populated `values` override file with real secrets

Important for open-source adopters:
- Default chart images are GHCR-hosted. If anonymous pull is blocked for your selected tag/package visibility, pods fail with token `401/403` even when Helm reports `deployed`.
- In that case, either use pullable public release images or configure `imagePullSecrets`/private registry mirroring before calling the setup random-user-ready.

## Chart Location

- Chart: `charts/pipelinehealer`
- Defaults: `charts/pipelinehealer/values.yaml`

## Deployment Profile Naming (Platform-Neutral)

Use profile names that describe intent, not cluster distro/tooling:

- `values.quickstart.yaml`: fast local/lab onboarding profile (non-production)
- `values.production.yaml`: hardened production profile
- optional overlays: `values.<env>.yaml` for team/environment-specific deltas

Avoid naming that implies single-platform support (for example `values.kind.*.yaml`).
PipelineHealer supports Kubernetes generally; profile names should communicate posture, not vendor/runtime.

## Public OCI Chart (Recommended)

When chart artifacts are available in GHCR, install directly from OCI:

```bash
helm upgrade --install pipelinehealer oci://ghcr.io/canepro/charts/pipelinehealer \
  --version X.Y.Z \
  --namespace pipelinehealer \
  --create-namespace \
  -f values.production.yaml
```

If you are iterating locally from source, install from `./charts/pipelinehealer` as shown below.

## Quick Start

Important:
- A successful Helm release creation is necessary but not sufficient.
- Rollout and image-pull verification are mandatory acceptance checks.

1. Select image source.
   - Recommended: immutable GHCR release digests from GitHub Release asset `release_images.md`.
   - Alternative: your own custom-built images.
2. Create a values override file (example below).
3. Install/upgrade:

```bash
helm upgrade --install pipelinehealer ./charts/pipelinehealer \
  --namespace pipelinehealer \
  --create-namespace \
  -f values.production.yaml
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
    repository: ghcr.io/canepro/pipelinehealer-backend
    tag: "vX.Y.Z"
    digest: ""
  env:
    ENVIRONMENT: production
    HEAL_MODE: safe
    AUTO_APPLY_REMEDIATION: "true"
    AUTO_CREATE_PR: "false"
    AUTO_CREATE_ISSUE: "true"
    AUTO_RETRY_WORKFLOW: "false"
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
    repository: ghcr.io/canepro/pipelinehealer-frontend
    tag: "vX.Y.Z"
    digest: ""
  env:
    VITE_AUTH_MODE: none
    # Optional for Entra session auth:
    # VITE_AUTH_MODE: entra
    # VITE_ENTRA_CLIENT_ID: "<spa-app-id>"
    # VITE_ENTRA_API_SCOPE: "api://<api-app-id>/PipelineHealer.Access"
    # VITE_ENTRA_AUTHORITY: "https://login.microsoftonline.com/<tenant-or-domain>"

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

## Entra on Kubernetes (Important)

To make `Use Login Session` work on AKS:

1. Backend runtime must allow bearer auth:
   - `AUTH_MODE=hybrid` (recommended rollout/testing) or `AUTH_MODE=entra`
   - correct `ENTRA_*` values in backend environment
2. Frontend runtime env must enable Entra:
   - `VITE_AUTH_MODE=entra`
   - `VITE_ENTRA_CLIENT_ID`
   - `VITE_ENTRA_API_SCOPE`
   - `VITE_ENTRA_AUTHORITY` or `VITE_ENTRA_TENANT_ID`

If runtime env keeps `VITE_AUTH_MODE=none`, session login will not work even when backend Entra runtime is correct.

### Verify frontend runtime auth mode from deployed app

```bash
kubectl -n pipelinehealer port-forward svc/pipelinehealer-frontend 3000:3000
curl -fsSL http://127.0.0.1:3000/runtime-config.js | rg 'VITE_AUTH_MODE|VITE_ENTRA_CLIENT_ID|VITE_ENTRA_API_SCOPE'
```

Expected for Entra-enabled runtime config: `VITE_AUTH_MODE: "entra"` with matching Entra keys.

## Version Pinning (Recommended)

Use release digests for reproducible installs:

```yaml
backend:
  image:
    repository: ghcr.io/canepro/pipelinehealer-backend
    digest: "sha256:<backend-digest-from-release_images.md>"

frontend:
  image:
    repository: ghcr.io/canepro/pipelinehealer-frontend
    digest: "sha256:<frontend-digest-from-release_images.md>"
```

## Private Registry Override (Optional)

If your cluster must pull from a private registry (for example ACR/ECR/GCR), override both image repositories and configure `imagePullSecrets`:

```yaml
imagePullSecrets:
  - name: regcred

backend:
  image:
    repository: <private-registry>/pipelinehealer-backend

frontend:
  image:
    repository: <private-registry>/pipelinehealer-frontend
```

## Random-User Pullability Gate (Required)

Before claiming "any user can set this up on Kubernetes", validate from a clean cluster:

1. `kubectl -n pipelinehealer get pods` shows backend/frontend `Running` (no `ErrImagePull` / `ImagePullBackOff`).
2. `kubectl -n pipelinehealer describe pod <pod>` has no token-fetch failures (`401 Unauthorized`, `403 Forbidden`).
3. `kubectl -n pipelinehealer rollout status` succeeds for both deployments.

If any gate fails, the setup is not random-user-ready and docs/release notes must state required registry access explicitly.

Or pin by semver tag:

```bash
helm upgrade --install pipelinehealer ./charts/pipelinehealer \
  --namespace pipelinehealer \
  --create-namespace \
  --set backend.image.tag=vX.Y.Z \
  --set frontend.image.tag=vX.Y.Z \
  -f values.production.yaml
```

## Port-Forward Validation (No Ingress)

```bash
kubectl -n pipelinehealer port-forward svc/pipelinehealer-frontend 3000:3000
kubectl -n pipelinehealer port-forward svc/pipelinehealer-backend 8000:8000
curl http://127.0.0.1:8000/health
```

## Operational Notes

- Frontend still proxies `/api` to backend via `BACKEND_UPSTREAM`.
- For Entra session auth, set frontend runtime `VITE_*` values in Helm overrides; no image rebuild is required.
- Keep `MCP_ENABLED=false` and `MCP_READ_ONLY=true` by default for first rollout.
- Use repo allowlists (`PH_ALLOWED_REPOS`, `MCP_REPO_ALLOWLIST`) before enabling wider automation.
- Use `docs/MODEL_PROVIDER_SWITCH_RUNBOOK.md` for provider migration/rollback steps.

## Common Auth Pitfall

Symptom:
- UI sign-in succeeds, but `/settings` or `/control-center` shows `401 Invalid or missing admin API key` when using session login.

Root cause:
- Frontend runtime env still has `VITE_AUTH_MODE=none` while backend is configured for Entra/hybrid.

Fix:
1. Set frontend runtime env in values:
   - `VITE_AUTH_MODE=entra`
   - required `VITE_ENTRA_*`
2. `helm upgrade --install ...` with updated values.
3. Re-verify with `runtime-config.js` check above.

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
