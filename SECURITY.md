<!-- LAST_VERIFIED: e1a9ae4 -->

# Security Policy

## Reporting a Vulnerability

If you find a security issue, do not open a public issue with exploit details.

- Contact the maintainer directly via GitHub profile contact options.
- Include:
  - affected component/file
  - reproduction steps
  - impact assessment
  - suggested mitigation (if available)

## Secrets and Credentials

This repository is public. Treat any committed secret as compromised.

If a secret is exposed:

1. Rotate or revoke it immediately.
2. Remove it from the runtime path.
3. Replace with a new secret through secure secret management.

Use:

- local `.env` for development only (never commit)
- Infisical for project/runtime/API/CI/service credentials when available
- GitHub secrets for GitHub-hosted automation
- Azure Key Vault for Azure-native deployments that already depend on it

Public documentation, examples, and reports must not include plaintext
secrets, local machine paths, personal accounts, tenant identifiers, Infisical
project IDs, private registry names, or private image digests. Keep generated
operator evidence in untracked `reports/` unless it has been deliberately
redacted for publication.

## Auth and Runtime Security Defaults

- `/api/*` requires `X-API-Key` outside development.
- `/api/settings*` uses dual-key auth outside development: `X-API-Key` + `X-Admin-Key`.
- In `AUTH_MODE=entra` or bearer-based `hybrid` flows, admin settings routes can also use bearer auth with the configured Entra admin role.
- Production should keep webhook signature verification enabled.

## Supported Hardening Areas

Security-focused contributions are welcome for:

- auth and access control
- webhook verification and replay resistance
- dependency and container supply-chain hygiene
- safe remediation boundaries and policy enforcement
