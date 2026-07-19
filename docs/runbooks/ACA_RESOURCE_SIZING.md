# Azure Container Apps Resource Sizing

<!-- LAST_VERIFIED: 5ddcb13 -->

This runbook defines the CPU, memory, and scale-to-zero contract for the
PipelineHealer Azure Container Apps reference deployment. The Bicep parameter
files are the source of truth. Live resource values must be checked separately
because an operator can apply a targeted Container Apps update without changing
the repository.

## Environment Contract

| Environment | Parameter file | App | CPU | Memory | Minimum replicas |
| --- | --- | --- | ---: | ---: | ---: |
| Development | `infra/main.bicepparam` | Backend | 0.5 vCPU | 1 GiB | 0 |
| Development | `infra/main.bicepparam` | Frontend | 0.25 vCPU | 0.5 GiB | 0 |
| Production | `infra/main.prod.bicepparam` | Backend | 1 vCPU | 2 GiB | 0 |
| Production | `infra/main.prod.bicepparam` | Frontend | 0.5 vCPU | 1 GiB | 0 |

`infra/main.bicep` keeps the backend maximum at 5 replicas and the frontend
maximum at 3 replicas. The production values above preserve the allocations
that existed before the development rightsizing change. They are an IaC
contract, not proof that the current production apps match the template.

## Validation Rules

The backend and frontend each accept one complete Consumption-plan resource
object. CPU and memory cannot be chosen independently. The allowed pairs are:

| CPU | Memory |
| ---: | ---: |
| 0.25 vCPU | 0.5 GiB |
| 0.5 vCPU | 1 GiB |
| 0.75 vCPU | 1.5 GiB |
| 1 vCPU | 2 GiB |
| 1.25 vCPU | 2.5 GiB |
| 1.5 vCPU | 3 GiB |
| 1.75 vCPU | 3.5 GiB |
| 2 vCPU | 4 GiB |

The Bicep `@allowed` constraint compares the complete object. A mixed pair such
as 0.5 vCPU with 2 GiB is invalid and must fail validation before deployment.
Keep the CPU values as strings in the parameter files. The template converts
CPU to the numeric ARM value when it builds each Container App resource.

Run these checks before a resource change:

```bash
az bicep build --file infra/main.bicep --stdout >/dev/null
az bicep build-params --file infra/main.bicepparam --stdout >/dev/null

infisical run --env prod --path /pipelinehealer/prod --projectId <infisical-project-id> -- \
  az bicep build-params --file infra/main.prod.bicepparam --stdout >/dev/null
```

The production parameter file requires secret environment variables while it
compiles. Use the approved secret source and keep compiled output out of logs.
Validate and preview against the intended environment before applying:

```bash
az deployment group validate \
  --resource-group "$PH_RG" \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam

az deployment group what-if \
  --resource-group "$PH_RG" \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

Use `infra/main.prod.bicepparam` only for a production review. Do not apply a
full resource-group deployment when `what-if` includes unrelated drift.

## Scale-to-Zero Tradeoff

`minReplicas=0` reduces idle compute cost. The first request after both apps
reach zero replicas pays a cold-start delay, so run `bash scripts/ph.sh warm`
before a timed demo and `bash scripts/ph.sh lowcost` afterward.

The completed development canary produced this single observation from
confirmed zero replicas:

- Backend `/health`: HTTP 200, `healthy`, version `0.9.0`, in 29.829 seconds.
- Frontend: HTTP 200 in 21.686 seconds.
- Both apps later reported `Healthy`, `ScaledToZero`, and 0 replicas.

These timings show the cost and viability of scale-to-zero at the approved dev
sizes. They are not a latency SLO, load test, percentile, or production
benchmark. Frontend HTTP 200 proves that the frontend served a response; it
does not by itself prove backend readiness or an end-to-end remediation flow.

## Rollback

The last known dev allocation before rightsizing was:

| App | CPU | Memory |
| --- | ---: | ---: |
| Backend | 1 vCPU | 2 GiB |
| Frontend | 0.5 vCPU | 1 GiB |

For a normal rollback:

1. Revert the dev pairs in `infra/main.bicepparam` in a reviewed commit.
2. Rebuild both the template and parameter file, then run ARM validation.
3. Run `az deployment group what-if` and confirm that only the intended
   Container Apps resource values will change.
4. Apply the deployment, verify both resource pairs, and health-check the
   backend and frontend.
5. Confirm the apps can return to `Healthy`, `ScaledToZero`, and 0 replicas.

If the full resource-group preview contains unrelated drift, do not apply it.
Restore only the two Container App resource pairs:

```bash
az containerapp update \
  --resource-group "$PH_RG" \
  --name "$PH_BACKEND_APP" \
  --cpu 1 \
  --memory 2Gi

az containerapp update \
  --resource-group "$PH_RG" \
  --name "$PH_FRONTEND_APP" \
  --cpu 0.5 \
  --memory 1Gi
```

After an emergency targeted rollback, align `infra/main.bicepparam` in a
follow-up PR so the next full deployment cannot silently restore the rejected
sizes. Do not change images, environment variables, replica limits, production,
or registry state as part of a resource-only rollback.

## Verification and Proof Boundary

The development rightsizing rollout landed through
[PR #236](https://github.com/Canepro/pipelinehealer/pull/236) and merged as
`5ddcb13ac7a854fe04a68bed6d57baa6620ff1f9`.

Verified for that rollout:

- `infra/main.bicep` built successfully.
- The dev and production parameter files compiled with their expected pairs.
- ARM validation succeeded against the existing dev resource group.
- ARM rejected an invalid 0.5 vCPU / 2 GiB pair.
- The backend suite passed 422 tests.
- All four PR CI jobs passed: ShellCheck Scripts, Version Sync, Backend Tests
  and Types, and Frontend Lint and Build.
- The live dev backend and frontend passed the cold-start checks above.
- The prior dev pairs were restored and health-checked as a rollback exercise,
  then the approved canary pairs were restored.
- Dev retained `minReplicas=0`, and both apps returned to zero replicas.

The full resource-group `what-if` contained unrelated infrastructure drift, so
it was not applied. The live canary and rollback used targeted Container Apps
resource updates. Production allocations and images were unchanged. No
production deployment, production cold-start test, ACR mutation, or application
code change is covered by this proof.
