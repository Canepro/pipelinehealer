# Feature: Settings And Policy Controls

<!-- LAST_VERIFIED: c9f507b -->

This guide explains runtime controls, persistence behavior, and governance guardrails.

## What This Feature Covers

- Settings page workflow (`/settings`)
- Settings posture overview cards (runtime/scope/provider/security) for quick read before edits
- Setup assistants for startup-managed integration boundaries (Assign-to-Agent receiver and notification targets)
- Runtime vs persisted settings
- Admin audit trail
- Guardrails for repos, retries, and MCP tool policy
- Task-level model routing overrides (`analysis`, `diagnosis`, `remediation`)
- Control Center learning queue governance (`candidate -> approved -> active` lifecycle)
- Control Center sectioned operator views (`Governance Overview`, `Learning & Ops`, `Trust Ops`, `Audit & Trace`)

## Quick Start

1. Open `/settings`.
2. Authenticate as admin:
   - key mode: enter `X-Admin-Key`
   - Entra mode: signed-in sessions auto-load Settings and Control Center
     - keep `X-Admin-Key` for fallback or troubleshooting overrides
3. Change only one policy group at a time.
4. Use **Save & Persist** to apply and persist in one action.
5. Re-open Control Center for read-only governance verification after each save.
6. Use Control Center section tabs to reduce cognitive load while preserving full detail:
   - `Governance Overview`: posture, policy impact, model routing, MCP policy effect
   - `Learning & Ops`: candidate lifecycle actions, readiness evidence, guidance outcomes, and logs/investigation commands
   - `Trust Ops`: recent human-review queue and compact trust reporting from activity feedback
   - `Audit & Trace`: collapsible audit timeline and request-trace review

## Startup-Managed Integration Setup

- Settings manages runtime-safe controls directly:
  - Assign-to-Agent enablement
  - handoff mode
  - retry/timeout values
  - webhook allowlist hosts
- Startup-only or secret-bearing integration values stay deployment-managed:
  - receiver URL
  - downstream notification webhook URLs
  - provider/shared-secret material
- To reduce operator friction without persisting secrets into generic runtime settings, Settings includes assistants that generate:
  - portable env blocks
  - sample payloads
  - smoke-test commands
  - single-target `NOTIFY_TARGETS_JSON` examples for supported receiver sink types, including SMTP-backed email

## Runtime vs Durable

- Settings UI `Save & Persist` updates runtime and then performs durable persistence.
- Runtime settings apply immediately.
- Persisted settings survive restarts/redeploys.
- Persistence uses the configured durable backend:
  - `cosmos` via `COSMOS_DB_ENDPOINT`
  - `postgres` via `POSTGRES_DSN`
  - with in-memory fallback only for explicit local/dev/demo paths

API and CLI equivalents:
```bash
bash scripts/ph.sh settings:check
bash scripts/ph.sh settings:audit --limit 10
bash scripts/ph.sh settings:persist --from-settings
```

Backend API calls used by Save & Persist:
- `PATCH /api/settings`
- `POST /api/settings/persist`

## Runtime Action Control Model

Settings and Control Center share the same runtime controls:
- `heal_mode`: planning strategy (`safe`, `demo`, `freestyle`, `debug`)
- `auto_apply_remediation`: global execution gate
  - `false` => plan-only dry-run (no PR/issue/retry side effects)
- `auto_create_pr`: allow PR artifact publishing
- `auto_create_issue`: allow issue artifact publishing
- `auto_retry_workflow`: allow workflow retry action

This separation lets operators run mixed policies safely, for example:
- issue-first canary: `auto_apply_remediation=true`, `auto_create_pr=false`, `auto_create_issue=true`, `auto_retry_workflow=false`
- full dry-run audit mode: `auto_apply_remediation=false` (other action toggles are ignored until re-enabled)

Learning queue API calls (Control Center):
- `GET /api/settings/learning/queue`
- `POST /api/settings/learning/queue/refresh`
- `POST /api/settings/learning/queue/{candidate_id}/decision`
- `POST /api/settings/learning/feedback`

Learning queue posture:
- **Candidate**: recurring successful pattern detected; not active
- **Approved**: human-reviewed and accepted for potential activation
- **Active**: approved and enabled as a promoted operational pattern
- **Rejected/Retired**: explicitly blocked from active use

Control Center now exposes more than status alone for each candidate:
- readiness reasons and whether force-activation would be required
- sample activity links for provenance review
- verification pass rate and guidance helped/hurt counts

Promotion-readiness gates (for `activate`):
- approval gate: candidate should be approved first
- occurrence gate: at least 2 recurring successful occurrences
- success-rate gate: at least 80% success
- sample gate: at least 2 sample activity IDs
- verification-sample gate: at least 1 verified activity
- verification quality gate: at least 80% verification pass rate

Force activation:
- `force_activate=true` is allowed only for `action=activate`
- bypasses readiness gates intentionally
- always leaves an explicit audit trail + forced-activation metadata

## MCP Guardrail Policy Model

Per-tool policy values:
- `disabled`
- `read_only`
- `write_with_approval`
- `auto`

Current tool keys:
- `fetch_failure_context`
- `fetch_runbook_context`
- `publish_artifact`
- `rerun_pipeline`

Recommended baseline:
- keep writes blocked by default (`MCP_READ_ONLY=true`)
- explicitly allow repos with `mcp_repo_allowlist`
- use short timeout/retry budgets

## Repo Scope Controls

- `ph_allowed_repos`: webhook processing scope
- `mcp_repo_allowlist`: MCP action scope

Best practice:
- use explicit owner/repo allowlists.
- avoid wildcard/global scope in shared environments.

## Task Model Routing

Optional runtime settings:
- `llm_model_analysis`
- `llm_model_diagnosis`
- `llm_model_remediation`

Behavior:
- If a task override is set, that model/deployment is used for the task.
- If empty, PipelineHealer falls back to the provider default model (`azure_openai_deployment_name` or `openai_compatible_model`).

## Audit Trail

Every settings change logs:
- changed keys and old/new values
- actor fingerprint
- request ID
- client metadata

Use request IDs in admin changes:
```bash
curl -X PATCH \
  -H "X-API-Key: $API_AUTH_KEY" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "X-Request-Id: policy-update-001" \
  -H "Content-Type: application/json" \
  -d '{"heal_mode":"safe"}' \
  "$BACKEND_URL/api/settings"
```

## Common Mistakes

- Updating frontend `VITE_*` runtime values without refreshing browser cache:
  - run `deploy:env`, then hard refresh to pick up latest `runtime-config.js`.
- Large multi-setting edits without request ID:
  - harder to trace/rollback.
- Leaving allowlists empty in production:
  - expands blast radius.

## Related Docs

- `../API.md` (`GET/PATCH/POST /api/settings*`)
- `../CLI.md` (`settings:persist` flags)
