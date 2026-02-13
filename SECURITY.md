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
- Azure Key Vault / GitHub secrets for hosted paths

## Auth and Runtime Security Defaults

- `/api/*` requires `X-API-Key` outside development.
- `/api/settings*` uses dual-key auth outside development: `X-API-Key` + `X-Admin-Key`.
- Production should keep webhook signature verification enabled.

## Supported Hardening Areas

Security-focused contributions are welcome for:

- auth and access control
- webhook verification and replay resistance
- dependency and container supply-chain hygiene
- safe remediation boundaries and policy enforcement
