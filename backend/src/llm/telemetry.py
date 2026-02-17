"""Per-activity LLM telemetry collection for model-path observability."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass

from ..models import LLMModelPath


@dataclass
class LLMCallEvent:
    """One observed LLM invocation event."""

    provider: str
    model: str
    fallback_used: bool
    latency_ms: float
    success: bool


class LLMTelemetryCollector:
    """Collect LLM invocation events and summarize them for one activity."""

    def __init__(self) -> None:
        self._events: list[LLMCallEvent] = []

    def record(self, event: LLMCallEvent) -> None:
        self._events.append(event)

    def to_model_path(self) -> LLMModelPath | None:
        if not self._events:
            return None

        preferred = self._events[0]
        provider_counts: dict[str, int] = {}
        model_counts: dict[str, int] = {}
        for event in self._events:
            provider_counts[event.provider] = provider_counts.get(event.provider, 0) + 1
            model_counts[event.model] = model_counts.get(event.model, 0) + 1

        provider = max(provider_counts, key=lambda key: provider_counts[key], default=preferred.provider)
        model = max(model_counts, key=lambda key: model_counts[key], default=preferred.model)
        return LLMModelPath(
            provider=provider,
            model=model,
            fallback_used=any(event.fallback_used for event in self._events),
            call_count=len(self._events),
            total_latency_ms=round(sum(event.latency_ms for event in self._events), 2),
            error_count=sum(1 for event in self._events if not event.success),
        )


_collector_var: contextvars.ContextVar[LLMTelemetryCollector | None] = contextvars.ContextVar(
    "llm_telemetry_collector",
    default=None,
)


def set_llm_telemetry_collector(
    collector: LLMTelemetryCollector,
) -> contextvars.Token[LLMTelemetryCollector | None]:
    """Set active telemetry collector for current async context."""
    return _collector_var.set(collector)


def reset_llm_telemetry_collector(token: contextvars.Token[LLMTelemetryCollector | None]) -> None:
    """Restore previous telemetry collector for current async context."""
    _collector_var.reset(token)


def record_llm_call(
    *,
    provider: str,
    model: str,
    fallback_used: bool,
    latency_ms: float,
    success: bool,
) -> None:
    """Record one LLM call event if an activity collector is active."""
    collector = _collector_var.get()
    if collector is None:
        return
    collector.record(
        LLMCallEvent(
            provider=provider,
            model=model,
            fallback_used=fallback_used,
            latency_ms=latency_ms,
            success=success,
        )
    )
