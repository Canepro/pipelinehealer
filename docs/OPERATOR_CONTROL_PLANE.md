<!-- LAST_VERIFIED: 7280f80 -->

# Operator Control Plane

This document defines the product contract for configuration, settings provenance, and operator-facing control surfaces.

It exists to keep `v0.4.0` implementation work aligned with the intended product model before code changes expand the surface area further.

## Product Model

PipelineHealer is an OSS-first, policy-aware pipeline remediation platform.

Current shipped provider paths are:

- GitHub Actions failure ingestion via `/webhook/github`
- signed Jenkins bridge ingestion via `/webhook/jenkins`
- GitHub-oriented diagnostics/tooling through `gh_aw` and MCP integrations

These are provider paths, not the product boundary.

The product boundary is:

- normalize pipeline failure evidence into a common activity model
- apply diagnosis and remediation under explicit policy controls
- preserve auditability and explainability across all actions
- expose one coherent operator control plane regardless of deployment target

Azure Container Apps is the current reference managed deployment, not the identity of the product.

## Design Rules

### 1. OSS-first, platform-adapted

Core behavior must be understandable and operable across:

- local host-native development
- Docker/Podman
- Helm/Kubernetes
- Azure Container Apps
- future deployment targets

Platform-specific mechanisms such as ACA secret refs, Key Vault-backed injection, Helm values, or `.env` files are adapters around the same settings model.

### 2. Deterministic configuration

Operators should not need tribal knowledge to know why the system behaves a certain way.

For any non-trivial capability, the product must make clear:

- what is configured
- what is actually effective at runtime
- whether an external dependency is missing
- where the effective value came from

### 3. No hidden deployment-only toggles for supported capability

If a capability is intended to be operator-managed, it should not require out-of-band infra edits for normal steady-state use.

Deployment-only wiring is acceptable for:

- secrets and secret references
- identity bindings
- startup-only infrastructure configuration

But the normal operator flow should be available through the product surface whenever the feature is considered supported.

### 4. Configured vs effective must be explicit

The UI must not blur:

- configured policy
- effective runtime behavior
- blocked state due to global override
- unavailable state due to missing dependency

Example:

- a write tool configured as `write_with_approval` while global read-only mode is enabled must not visually read as both "allowed" and "blocked" without explaining precedence

### 5. Red means blocked, dangerous, or failing

Severity and color semantics must stay stable across the app.

- red: blocked, failing, destructive, or risky
- green: healthy, allowed, configured correctly
- amber/secondary: approval required, degraded, warning
- neutral/outline: inactive, informational, or not configured

Normal enabled states should not be styled as destructive by default.

## Settings Taxonomy

The control plane should distinguish the following classes of settings:

### Startup settings

Require process restart or deployment restart to take effect.

Examples:

- provider secrets
- startup auth wiring
- base deployment endpoints
- secret-backed webhook credentials

### Runtime-mutable settings

Can be changed through the product and take effect immediately or near-immediately.

Examples:

- remediation policy toggles
- MCP tool policies
- diagnostics mode and wait budgets
- operator-facing capability gates

### External dependency settings

Depend on another system being available.

Examples:

- Assign-to-Agent webhook receiver
- Jenkins bridge sender configuration
- provider credentials for third-party integrations

These should expose both configuration state and dependency state.

## Provenance Model

For supported operator settings, the API/UI should eventually expose provenance in a normalized form.

Recommended source categories:

- `default`
- `env`
- `secretref`
- `persisted_runtime_override`
- `computed`

Recommended operator-visible fields:

- effective value
- source
- requires restart (`true|false`)
- mutable in UI (`true|false`)
- blocked reason or missing dependency reason when applicable

## Operator Surface Expectations

### Settings

Primary place to configure supported behavior.

Should answer:

- What can I change here?
- What is effective right now?
- What still depends on external wiring?
- What requires restart or redeploy?

### Control Center

Primary place to inspect runtime posture, governance, and audit.

Should answer:

- Why is a tool/path allowed, approval-gated, blocked, or inactive?
- What policy is configured?
- What runtime condition is overriding it?

### Activity Detail

Primary place to inspect one specific execution.

Should answer:

- what happened
- why PipelineHealer chose that path
- what external evidence/path was used
- whether downstream actions were blocked by policy or missing dependency

## Current `v0.4.0` Focus Areas

The `v0.4.0` control-plane rework is driven by four concrete gaps:

1. configuration truth is split across deployment env, secret refs, and persisted runtime overrides
2. MCP governance surfaces mix configured and effective state in confusing ways
3. Assign-to-Agent is present but not operator-ready from the main Settings surface
4. visual semantics across Settings, Control Center, and Activity Detail are not consistent enough for a serious operator product

Tracked roadmap items:

- `BL-047` config provenance and source-of-truth visibility
- `BL-048` Assign-to-Agent UI activation path
- `BL-049` MCP governance IA rework
- `BL-050` operator-surface visual/system coherence pass

## Non-Goals

This document does not require:

- removing Azure support or Azure-first runbooks
- hiding deployment-specific options from advanced operators
- forcing every infrastructure concern into the UI
- abstracting away real provider differences

It does require that the product-level contract remain coherent and portable.

