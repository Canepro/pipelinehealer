# PipelineHealer 2-Minute Demo Script

Use this for hackathon recording and live demos.

## Goal

Show end-to-end value quickly:

1. CI fails
2. PipelineHealer detects and diagnoses
3. PipelineHealer creates PRs/issues
4. Dashboard reflects results

## Pre-Demo Checklist (Do This First)

- Azure backend URL responds at `/health`
- Azure frontend opens and dashboard loads
- Webhook from demo repo points to backend `/webhook/github`
- `HEAL_MODE=safe` in backend
- Demo repo is reset so:
  - `dependency` and `lint` can produce PRs
  - `test`, `build_config`, `timeout` produce issues
- Keep Container Apps warm during demo (`min-replicas=1`) if needed

## 2-Minute Run of Show

## 0:00 - 0:20 (Problem + Architecture)

Say:

"PipelineHealer is a multi-agent CI/CD self-healing system. A failed GitHub workflow triggers webhook ingestion, AI diagnosis, and automated remediation as PR or issue."

Show:

- Frontend dashboard at `/`
- Briefly click `Settings` and show `environment`, `heal_mode`, and security flags

## 0:20 - 0:40 (Trigger Failures)

Run:

```bash
REPO="Canepro/pipelinehealer-demo"
for t in dependency lint test build_config timeout; do
  gh workflow run CI -R "$REPO" -f failure_type="$t"
done
```

Say:

"I’m triggering all five failure types now."

## 0:40 - 1:20 (Show Healing Outputs)

Run:

```bash
REPO="Canepro/pipelinehealer-demo"
gh run list -R "$REPO" --workflow CI --limit 10
gh pr list -R "$REPO"
gh issue list -R "$REPO" --state open
```

Expected:

- PRs for `dependency` and `lint`
- Issues for `test`, `build_config`, `timeout`

Say:

"Safe mode creates deterministic fix PRs where confidence is high, and issues for changes that still need human review."

## 1:20 - 1:50 (Dashboard Evidence)

Show:

- Dashboard charts updated
- Activities table with recent runs
- Open one activity detail to show diagnosis + remediation action

Optional API proof:

```bash
curl -sS -H "X-API-Key: $API_AUTH_KEY" "https://<backend-fqdn>/api/activities?limit=20"
```

## 1:50 - 2:00 (Close)

Say:

"This demonstrates agentic DevOps: detect, diagnose, and remediate CI failures with auditable outputs and safe defaults."

## Post-Demo Cleanup

Merge demo PRs and optionally close superseded issues:

```bash
REPO="Canepro/pipelinehealer-demo"
gh pr list -R "$REPO"
```

Return Azure apps to low-cost mode:

```bash
RG="rg-canepro-ph-dev-eus"
az containerapp update -g "$RG" -n ca-canepro-ph-backend --min-replicas 0
az containerapp update -g "$RG" -n ca-canepro-ph-frontend --min-replicas 0
```
