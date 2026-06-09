# Lifecycle E2E Verification Runbook

<!-- LAST_VERIFIED: pending -->

Use this runbook to prove the **artifact lifecycle loop** on a live deployment after lifecycle-marker backfill:

1. **First failure** creates (or upgrades) a review issue with signature/workflow/branch markers.
2. **Repeat failure** reuses the same issue (`reused_existing_issue`) instead of opening a duplicate.
3. **Green workflow run** auto-closes the tracked issue with an audit comment.

This complements the broader demo matrix in `docs/runbooks/DEMO_SCRIPT.md` (`demo:e2e`), which covers PR creation, external diagnostics, and MCP counters. This runbook is intentionally narrow: lifecycle trust only.

## Prerequisites

- Azure backend deployed with lifecycle code (`auto_close_on_workflow_success`, signature dedup, marker emission).
- Valid `GITHUB_PERSONAL_ACCESS_TOKEN` synced into the backend (Infisical → ACA env-only redeploy).
- Demo repo in `PH_ALLOWED_REPOS` (recommended: `Canepro/pipelinehealer-demo`).
- Operator shell with `gh`, `az`, `curl`, and Infisical injection (or `backend/.env` with API keys).

Required env (dev lane example):

```bash
export DEMO_REPO=Canepro/pipelinehealer-demo
export PH_RG=rg-canepro-ph-dev-eus
export PH_BACKEND_APP=ca-canepro-ph-backend
export PH_FRONTEND_APP=ca-canepro-ph-frontend
```

## One-Command Verification (Recommended)

Run under Infisical so API keys and webhook secrets are injected:

```bash
infisical run --env dev --path /personal/pipelinehealer \
  --projectId 70ae1697-055c-4fc1-ba90-85b25f6bf138 -- \
  bash scripts/ph.sh demo:lifecycle --repo "$DEMO_REPO" --strict
```

What the script does:

| Phase | Action | Pass criteria |
|-------|--------|---------------|
| **0** | Webhook sync + settings preflight | Azure `workflow_run` webhook active; `auto_close_on_workflow_success=true`, repo allow-listed |
| **1** | Reset fixtures → dispatch `failure_type=lint` | Activity reaches terminal state; open PH issue contains `signature`, `workflow-name`, `head-branch` markers |
| **2** | Dispatch same `lint` failure again | Open PH issue count does not increase; activity reports `reused_existing_issue=true` |
| **3** | Dispatch `failure_type=none` (green CI) | Tracked issue closes; last comment contains auto-close audit text |

Strict mode exits non-zero on any failed check.

## Manual Checklist (If You Prefer Step-by-Step)

### 0. Preflight

```bash
bash scripts/ph.sh status
bash scripts/ph.sh settings:check
```

Confirm:

- `auto_close_on_workflow_success=true`
- `auto_apply_remediation=true`
- `auto_create_issue=true`
- Demo repo appears in `ph_allowed_repos`

### 1. First failure → markers

```bash
bash scripts/ph.sh demo:reset
gh workflow run CI --repo "$DEMO_REPO" --field failure_type=lint
```

Wait for PipelineHealer activity (Dashboard → Activity Detail, or API):

```bash
curl -sS -H "X-API-Key: $API_AUTH_KEY" \
  "$BACKEND_URL/api/activities?limit=20" | python3 -m json.tool
```

On the new GitHub issue, confirm HTML comment markers:

- `<!-- pipelinehealer:generated-issue:review -->`
- `<!-- pipelinehealer:signature:... -->`
- `<!-- pipelinehealer:workflow-name:ci -->`
- `<!-- pipelinehealer:head-branch:main -->`

Activity Detail should show remediation metadata (issue URL, no duplicate PR noise for lint).

### 2. Dedup → reuse

```bash
gh workflow run CI --repo "$DEMO_REPO" --field failure_type=lint
```

Pass checks:

- **No new open PH issue** for the same signature (issue count stable or comment appended to existing issue).
- Activity for the second run includes `reused_existing_issue: true` in remediation details.
- Trust Ops / Activity table shows reuse linkage when present.

### 3. Green run → auto-close

```bash
gh workflow run CI --repo "$DEMO_REPO" --field failure_type=none
```

Wait for the CI run to succeed. The success `workflow_run` webhook should trigger green-close.

Pass checks:

- Tracked review issue state becomes **closed**.
- Issue timeline includes comment: `Closed automatically because the tracked workflow succeeded.`
- Activity history remains intact (no deletion of prior failure activities).

## Partial Runs / Troubleshooting

Skip phases when iterating:

```bash
# Dedup + green-close only (fixtures already primed)
bash scripts/ph.sh demo:lifecycle --repo "$DEMO_REPO" --skip-reset

# Marker + dedup only (leave issue open for inspection)
bash scripts/ph.sh demo:lifecycle --repo "$DEMO_REPO" --skip-green-close

# Use a different failure signature
bash scripts/ph.sh demo:lifecycle --repo "$DEMO_REPO" --failure-type test
```

Common failures:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Backfill / issue list `401` | Expired or wrong-scope GitHub PAT | Rotate PAT in Infisical; `bash scripts/ph.sh deploy:env --secure-secrets` |
| No activity after dispatch | Webhook points at wrong backend or smee still active | Re-run with webhook sync (default) or `bash scripts/ph.sh webhook:add --repo "$DEMO_REPO"` |
| Issue lacks workflow markers | Pre-rollout legacy issue | `POST /api/settings/lifecycle/backfill-markers?repository=owner/repo` |
| Green run does not close issue | Missing workflow/branch markers, or no recent CREATE_ISSUE activity for that workflow | Confirm markers on issue; confirm first failure produced CREATE_ISSUE activity |
| `reused_existing_issue` false on second run | Different signature (branch/workflow/title drift) | Use same `failure_type`, same branch (`main`), same workflow (`CI`) |

## Unit Test Fallback (No Azure Access)

When live credentials are unavailable, run lifecycle unit tests locally:

```bash
cd backend
uv pip install -e ".[dev]"
pytest -q \
  backend/tests/test_phase1_correctness.py \
  -k "signature or reused_existing_issue or close_issues_on_workflow_success or backfill_legacy"
```

These tests cover signature scoping, dedup reuse, green-close, and legacy marker backfill without hitting GitHub or Azure.

## Related Docs

- `docs/runbooks/DEMO_SCRIPT.md` — full demo recording flow
- `docs/runbooks/LOCAL_DEMO_RUNBOOK.md` — operator setup and Azure/local profiles
- `docs/features/02-diagnosis-and-remediation.md` — remediation and lifecycle behavior
- `docs/reference/API.md` — `POST /api/settings/lifecycle/backfill-markers`
