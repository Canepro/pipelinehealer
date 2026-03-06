# Feature: Auth And Access

<!-- LAST_VERIFIED: a01bc4f -->

This guide explains how users authenticate to PipelineHealer and how admin-only actions are protected.

## What This Feature Covers

- API access auth modes: `api_key`, `entra`, `hybrid`
- Frontend Entra sign-in (MSAL)
- Admin protection for `/api/settings*`
- Common login/authorization errors and fixes

## Do I Need Entra?

Short answer: no, not for baseline usage.

- Baseline repo adoption can run with key auth (`api_key`) or migration-safe `hybrid`.
- Entra is needed only if you want Microsoft sign-in session flows in the UI.
- `hybrid` means both auth methods are valid at once (keys + Entra session), and is recommended during testing/migration.
- Frontend `VITE_*` auth vars are runtime env values for container deployments (Helm/ACA/compose).
  - static-hosting fallback still exists (`import.meta.env`) for non-container builds.

## Quick Start

1. Pick one auth path:
   - key-only baseline:
     - backend: `AUTH_MODE=api_key`
     - frontend: `VITE_AUTH_MODE=none` (or leave unset)
   - both methods (recommended rollout/testing):
     - backend: `AUTH_MODE=hybrid`
     - frontend: `VITE_AUTH_MODE=entra`
     - operators can use either session login or key headers
   - Entra session path (migration-safe):
     - backend: `AUTH_MODE=entra`
     - frontend: `VITE_AUTH_MODE=entra`
2. Configure matching required variables for the chosen path.
3. Verify settings:
   - `bash scripts/ph.sh settings:check | jq '.auth_mode,.entra_auth_enabled,.entra_admin_roles'`
4. Test access:
   - key mode: use `X-API-Key` / `X-Admin-Key`
   - Entra mode: sign in and open `/settings` or `/control-center`
     - admin pages now auto-use the current signed-in session
     - `X-Admin-Key` remains available as a manual fallback/override

## Auth Modes

- `api_key`: legacy header auth (`X-API-Key`, `X-Admin-Key`)
- `entra`: bearer-token only (`Authorization: Bearer ...`)
- `hybrid`: accepts bearer or key headers (recommended rollout mode)

Recommended:
- Use `hybrid` during rollout.
- Switch to `entra` after all clients are updated.

## Entra App Registration Checklist

1. Create API app (`PipelineHealer API`).
2. In `Expose an API`, define scope `PipelineHealer.Access`.
3. In `App roles`, define role `PipelineHealer.Admin`.
4. Set API app manifest `requestedAccessTokenVersion` to `2`.
5. Create SPA app (`PipelineHealer SPA`).
6. Add SPA redirect URIs:
   - `https://<frontend-fqdn>`
   - `https://<frontend-fqdn>/app`
   - `http://localhost:5173` (local optional)
7. Add API permission in SPA app:
   - delegated scope `PipelineHealer.Access` from API app
   - grant admin consent
8. Assign user/group in Enterprise Applications to `PipelineHealer Admin`.

## Required Environment Variables

If using key-only auth (`api_key`):
- Entra variables are optional.
- Use `X-API-Key` and `X-Admin-Key` headers for protected/admin routes.

If using Entra session auth (`entra` or `hybrid` with login session):
- Use the backend + frontend variables below.

Backend:
- `AUTH_MODE`
- `ENTRA_TENANT_ID`
- `ENTRA_CLIENT_ID`
- Optional: `ENTRA_ALLOWED_AUDIENCES`, `ENTRA_ADMIN_ROLES`, `ENTRA_ISSUER`, `ENTRA_JWKS_URL`

Frontend:
- `VITE_AUTH_MODE=entra`
- `VITE_ENTRA_CLIENT_ID`
- `VITE_ENTRA_API_SCOPE`
- `VITE_ENTRA_TENANT_ID` or `VITE_ENTRA_AUTHORITY`

## Common Mistakes

- `AADSTS50011` redirect mismatch:
  - Add the exact URI from the error, including `/app`.
- `AADSTS90002` tenant mismatch:
  - Verify exact tenant ID; prefer explicit `VITE_ENTRA_AUTHORITY` with primary domain.
- UI shows 401 after sign-in:
  - Run `bash scripts/ph.sh deploy:env` for backend auth changes.
  - If frontend `VITE_*` changed, run `bash scripts/ph.sh deploy:env`.
- Settings or Control Center says invalid admin key while using session:
  - Session can be stale; re-login or clear site data.
  - Confirm frontend runtime still has `VITE_AUTH_MODE=entra`.

## Verify With API

Bearer call:
```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" "$BACKEND_URL/api/stats"
```

Key call:
```bash
curl -H "X-API-Key: $API_AUTH_KEY" "$BACKEND_URL/api/stats"
```

Admin settings with key:
```bash
curl -H "X-API-Key: $API_AUTH_KEY" -H "X-Admin-Key: $ADMIN_API_KEY" "$BACKEND_URL/api/settings"
```

## Related Docs

- `../API.md` (`Authentication`, `/api/settings*`)
- `../LOCAL_DEMO_RUNBOOK.md` (beginner portal steps + troubleshooting)
