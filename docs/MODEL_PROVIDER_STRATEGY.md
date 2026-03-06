# Model Provider Strategy

<!-- LAST_VERIFIED: 745988e -->

PipelineHealer uses Azure as the current reference model-provider path for managed deployment and operational simplicity, but it is being structured to avoid provider lock-in.

## Goals

- Keep current Azure OpenAI/Foundry path stable.
- Add provider-pluggable architecture for future user choice.
- Preserve safety and auditability regardless of provider.

## Target Providers

- Azure OpenAI / Foundry-hosted models (primary now)
- OpenAI-compatible APIs
- Custom/self-hosted gateway (enterprise/private deployments)

Future provider candidates:

- Anthropic Claude (via compatible adapter)
- Grok or other vendor APIs (via custom adapter)

## Design Principles

- Provider abstraction at backend boundary (`LLMProvider` adapters).
- One normalized internal schema for diagnosis/remediation outputs.
- Task-level routing (`analysis`, `diagnosis`, `remediation`) separated from provider selection.
- Explicit fallback chain with audit trail.
- No hidden provider switching: all changes visible in settings and activity metadata.

## Current Phase Status

- `LLM_PROVIDER` runtime setting introduced (`azure_openai`, `openai_compatible`, `custom`).
- Azure provider path remains active default.
- `openai_compatible` provider path is implemented (runtime config + health + execution path).
- `custom` remains scaffolded (no-op with explicit health/status).
- task-level overrides are live via:
  - `LLM_MODEL_ANALYSIS`
  - `LLM_MODEL_DIAGNOSIS`
  - `LLM_MODEL_REMEDIATION`
  These fall back to provider defaults when unset.
- Provider health endpoint available at:
  - `GET /api/settings/llm/provider-health`
- Model-path telemetry is available per activity (`llm_model_path`) and surfaced in UI.
- 0.4 hardening tests now cover:
  - provider contract normalization (consistent diagnosis output shape)
  - transient error retry behavior on openai-compatible runtime path (429, 5xx, timeout)
  - non-retryable fail-fast behavior (for example 401 auth errors)

## Next Implementation Steps

1. Add additional concrete providers beyond `openai_compatible` (for example `custom_gateway`).
2. Expand provider-specific credential/config validation (including proactive auth probes and redaction-safe diagnostics).
3. Add token/cost estimation fields to model-path telemetry.
4. Add UI switch safety rails (guided provider change flow + explicit rollback shortcuts).

## Operations

- Provider switching and rollback runbook: `docs/MODEL_PROVIDER_SWITCH_RUNBOOK.md`
- Kubernetes secondary deploy target: `docs/KUBERNETES_HELM_RUNBOOK.md`
