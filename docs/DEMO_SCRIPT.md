# PipelineHealer Demo Recording Guide (Single-File Runbook)

<!-- LAST_VERIFIED: d0bd771 -->

Use this as the only doc during recording day. It includes:

- exact commands to run (copy-paste ready with safe defaults)
- checks to confirm each step
- fast fallback commands
- final 2-minute SHOW/TELL script

Related docs:

- `docs/LOCAL_DEMO_RUNBOOK.md` for deeper setup/troubleshooting
- `docs/HACKATHON_LOG.md` for submission checklist and milestone status
- `docs/API.md` for full API endpoint reference and best practices
- `docs/CLI.md` for the full CLI command reference

Default values used in this runbook:

```bash
export RELEASE_TAG="${RELEASE_TAG:-v0.3.1}"
export DEMO_REPO="${DEMO_REPO:-Canepro/pipelinehealer-demo}"
```

## Demo Flow (3-4 Minutes)

1. Dashboard story: show `Processed`, `Actioned`, `Safety Gated`, `Issue-Only`, plus header KPIs `MCP Runs (30d)` and `LLM Fallback (30d)`.
2. Explainability drilldown: open a focused activity and show `PipelineHealer Decision` first (root cause + remediation result), then `Failure Context` (job/step/command/signal), reason code, and the `Evidence Layers` block (`Confidence Impact by Source` + `Structured Context`).
3. External findings: expand the "External Findings Details" panel to show ci-doctor's structured root cause, recommended actions, and doctor metadata.
4. MCP observability (if enabled): in activity detail, show `MCP Observability` summary (`Provider`, `Status`, `Read Only`, `Reason`) where reason includes friendly text plus raw code; expand details for `Configured Tools`, `Source Attribution`, and `Tool Usage`/Action Audit (friendly status + raw codes). Clarify that `Tool Calls = 0` can still be valid when passive `gh_aw` diagnostics were used.
5. Safety boundary: show `Why Safety Gated` microcopy and explain policy-driven issue fallback.
6. Runtime policy + audit proof: open `/settings`, use the section tabs (`Runtime Controls`, `AI & Integrations`, `Security & Advanced`), show the Active Policy banner, and point out `Save & Persist` as one-step durable save, then run `bash scripts/ph.sh audit:proof --limit 5`.

## 1) Pre-Record Setup (5-10 minutes before)

Run from repo root:

```bash
cd /mnt/d/repos/pipelinehealer
git status --short
git fetch origin main
git checkout main
git pull --ff-only origin main
gh auth status
az account show --output table
bash scripts/ph.sh deploy:release --release-version "$RELEASE_TAG"
bash scripts/ph.sh warm
bash scripts/ph.sh status
bash scripts/ph.sh settings:check
```

Pass checks:

- `status` shows both apps with `MinReplicas` = `1`
- `settings:check` returns JSON (not `401`)
- response includes expected runtime values (for example `github_auth_mode`, `max_remediation_attempts`, `azure_openai_api_version`)
- `git status --short` is empty (or only known intentional files)

If `settings:check` fails with `401`:

```bash
bash scripts/ph.sh deploy:env
bash scripts/ph.sh settings:check
```

If `deploy:release` fails due Azure auth/session context:

```bash
az account show
az login
bash scripts/ph.sh deploy:release --release-version "$RELEASE_TAG"
```

## 2) Optional Clean Slate for Demo Repo

```bash
bash scripts/ph.sh demo:reset
```

Pass check:

- command ends with `Demo fixtures reset complete.` or `No fixture changes needed.`

## 3) Main E2E Demo Command (Use On Camera)

```bash
bash scripts/ph.sh demo:e2e --repo "$DEMO_REPO" --triggers dependency,lint,test,build_config,timeout --wait-seconds 180 --ci-signal-wait-seconds 180
```

What this command does:

- syncs webhooks (disables stale `smee.io`, enables Azure webhook)
- ensures demo fixtures are in the expected state
- triggers all five demo failure scenarios (`dependency`, `lint`, `test`, `build_config`, `timeout`)
- polls activity states to terminal (`completed` / `failed`) and prints runs, PRs, issues, and backend activity output
- triggers an on-demand backfill sweep before final summary so late external diagnostics can be attached without waiting for the 10-minute background sweep
- waits for a CI doctor workflow signal (`CI Failure Doctor` / `ci-doctor`) and prints whether that signal was observed
- prints MCP verification counters so you can separate passive diagnostics, hybrid diagnostics, and direct MCP tool usage

Pass checks in output:

- workflow dispatch events created
- at least one dependency/lint remediation shows PR creation
- test/build_config/timeout produce issues (or structured failure records)
- `CI doctor signal detected` appears (best effort; if delayed, run `bash scripts/ph.sh backfill` and verify in Activity Detail)
- MCP interpretation:
  - `mcp_tool_calls_total > 0` = direct MCP invocation observed
  - `mcp_tool_calls_total = 0` + passive diagnostics/source attribution = passive mode worked as designed
  - In hybrid mode, expect mixed source attribution in one activity (`gh_aw_passive` + `github_mcp_direct` and/or `github_mcp_blocked`)

Rehearsal-only strict gate:

```bash
bash scripts/ph.sh demo:e2e --repo "$DEMO_REPO" --triggers dependency,lint,test,build_config,timeout --wait-seconds 180 --ci-signal-wait-seconds 300 --strict
```

### Single Failure Type (faster, focused demo)

If you only want to show one failure type on camera:

```bash
gh workflow run CI --repo "$DEMO_REPO" --field failure_type=dependency
```

Then verify:

```bash
bash scripts/ph.sh demo:proof --repo "$DEMO_REPO" --limit 5
```

## 4) Verification Commands (If You Need Extra Proof)

```bash
bash scripts/ph.sh demo:proof --repo "$DEMO_REPO" --limit 10
bash scripts/ph.sh urls
bash scripts/ph.sh settings:check
bash scripts/ph.sh audit:proof --limit 5
bash scripts/ph.sh settings:audit --limit 5
bash scripts/ph.sh logs
bash scripts/ph.sh logs:grep --pattern "debug-mode"
```

Expected result pattern:

- PRs: dependency + lint
- Issues: test + build_config + timeout
- Admin audit proof should show latest entries containing `request_id`, actor fingerprint, and old/new change values.
- Settings page should show runtime scope clearly (`Allowlist (N)` or `Unrestricted`) in the Effective Runtime Policy banner and keep controls organized by section tabs.

### External diagnostics enrichment

ci-doctor findings use a fast-path wait budget (default 60s) during pipeline execution. If findings are not published within that window, the backfill sweep runs automatically every 10 minutes and enriches activities when results arrive.

For immediate results, trigger manually:

```bash
bash scripts/ph.sh backfill
```

Or use the "Backfill Diagnostics" button on the Activity Detail page in the UI.

Enriched activities show an "External Findings Details" collapsible panel in Activity Detail with structured root cause, recommended actions, and doctor metadata.

## 5) 2-Minute Recording Script (Final)

Timing sanity check (March 3, 2026):
- core `TELL` script (excluding optional insert) is ~147 words
- at ~110-130 WPM, spoken narration is ~68-80 seconds
- keep transitions/clicks concise; treat the optional differentiator as a swap-in, not an add-on, to stay under 2:00

### 0:00-0:15

SHOW: Failed GitHub Actions run, red CI status indicator.

TELL: CI failures slow delivery and interrupt engineering flow. PipelineHealer is a multi-agent system that turns failed GitHub Actions runs into structured remediation.

### 0:15-0:30

SHOW: GitHub repository, you coding, and AI assistant workflow notes.

TELL: We built PipelineHealer with AI-assisted development to reduce repetitive DevOps triage and make incident response faster, clearer, and safer.

### 0:30-0:50

SHOW: Dashboard home, highlighting agent modules.

![Dashboard — processed count, safety gating, failure breakdown, explainability snapshot](screens/dashboard.png)

TELL: PipelineHealer listens for `workflow_run.completed` failures, then runs a four-agent pipeline: Log Analyzer, Diagnosis, Remediation, and Orchestrator. Each agent has a focused role, and the orchestration keeps the flow deterministic and observable.

### 0:50-1:30

SHOW: Terminal running:

```bash
bash scripts/ph.sh demo:e2e --repo "$DEMO_REPO" --triggers dependency,lint,test,build_config,timeout --wait-seconds 180 --ci-signal-wait-seconds 180
```

SHOW: Output with webhook sync, workflow/activity output, and dashboard updating in real time.

TELL: This command syncs webhooks, triggers failures, and shows PipelineHealer detect, diagnose, and remediate automatically. Deterministic fixes become PRs; uncertain cases become structured issues. If ci-doctor findings arrive, they are ingested and shown in External Findings with full traceability.

### 1:30-2:00

SHOW: Activities list with completed runs, then drill into an activity with external findings.

![Activities — completed runs with Doctor Signal badges and failure types](screens/activities.png)

SHOW: Expand the External Findings Details panel on an enriched activity.

![External Findings — ci-doctor analysis with summary, root cause, recommended actions, and AI metadata](screens/external-findings.png)

TELL: PipelineHealer shifts teams from reactive troubleshooting to structured, automated remediation, improving CI/CD reliability with clear, auditable actions.

### Optional 30-Second Differentiator Insert

Use this if you want to emphasize why PipelineHealer stands out in a crowded AI hackathon field:

TELL: PipelineHealer is not just an AI that opens PRs. It is an AI-governed remediation system with explicit trust boundaries. High-confidence, deterministic cases become reviewable PRs. Low-confidence cases become structured issues with a proposed fix, reason code, and validation steps, so uncertainty is visible instead of hidden. That gives teams speed without losing control: every action is policy-bound, auditable, and observable in the dashboard.

## 6) Post-Record Cleanup

Merge or close demo artifacts if needed:

```bash
gh pr list -R "$DEMO_REPO"
gh issue list -R "$DEMO_REPO" --state open
```

Return to low-cost mode:

```bash
bash scripts/ph.sh lowcost
bash scripts/ph.sh status
```

Pass check:

- `MinReplicas` returns to `0` for backend and frontend

## 7) Quick Troubleshooting

`401` from `/api/settings`:

```bash
bash scripts/ph.sh deploy:env
bash scripts/ph.sh settings:check
```

`AADSTS50011` redirect URI mismatch during Entra sign-in:

- Add the exact redirect URI used by the app (for example `https://<frontend-fqdn>/app`) in the SPA app registration.
- Wait 1-2 minutes for propagation and retry in incognito.

`401 Invalid bearer token` after successful Entra login:

- Confirm backend `AUTH_MODE` and `ENTRA_*` values are synced (`bash scripts/ph.sh deploy:env`).
- If frontend `VITE_ENTRA_*` changed, sync runtime env (`bash scripts/ph.sh deploy:env`) and hard refresh browser cache.

`Client error '403 Forbidden' for GitHub issue/PR creation`:

- Most common cause: token lacks repository write permissions for the target repo.
- For fine-grained PATs, ensure repository access is granted and Issues/PR write permissions are enabled.
- Check repo settings (Issues enabled, repo not archived/read-only).
- Verify token scope/access with:

```bash
gh auth status
gh issue create -R "$DEMO_REPO" -t "PipelineHealer auth test" -b "test"
```

- Ensure `GITHUB_PERSONAL_ACCESS_TOKEN` in `backend/.env` is correct, then sync:

```bash
bash scripts/ph.sh deploy:env
```

Terminal closes unexpectedly:

- run scripts with `bash scripts/...`
- do not use `source` or `. scripts/...`

Podman unavailable (only relevant for local/full-build deploy path):

```bash
podmanup
```

Then re-run deploy:

```bash
bash scripts/ph.sh deploy
```
