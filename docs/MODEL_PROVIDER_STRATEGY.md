# Model Provider Strategy

<!-- LAST_VERIFIED: 43798ee -->

PipelineHealer is Azure-first today for hackathon delivery and operational simplicity, but is being structured to avoid provider lock-in.

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
- Non-Azure values are scaffolded and reported as not-yet-implemented.
- Provider health endpoint available at:
  - `GET /api/settings/llm/provider-health`

## Next Implementation Steps

1. Implement concrete non-Azure provider adapters.
2. Add provider-specific credential/config validation.
3. Add model-path telemetry to activity metadata and explainability UI.
4. Add contract tests to ensure parity across providers.
