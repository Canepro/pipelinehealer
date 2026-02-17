from src.llm.telemetry import (
    LLMTelemetryCollector,
    record_llm_call,
    reset_llm_telemetry_collector,
    set_llm_telemetry_collector,
)


def test_llm_telemetry_collector_summarizes_calls() -> None:
    collector = LLMTelemetryCollector()
    token = set_llm_telemetry_collector(collector)
    try:
        record_llm_call(
            provider="azure_openai",
            model="gpt-5-mini",
            fallback_used=False,
            latency_ms=120.0,
            success=True,
        )
        record_llm_call(
            provider="azure_openai",
            model="gpt-5-mini",
            fallback_used=True,
            latency_ms=80.0,
            success=False,
        )
    finally:
        reset_llm_telemetry_collector(token)

    summary = collector.to_model_path()
    assert summary is not None
    assert summary.provider == "azure_openai"
    assert summary.model == "gpt-5-mini"
    assert summary.fallback_used is True
    assert summary.call_count == 2
    assert summary.total_latency_ms == 200.0
    assert summary.error_count == 1


def test_record_llm_call_without_active_collector_is_noop() -> None:
    # Should not raise even when no collector context is active.
    record_llm_call(
        provider="azure_openai",
        model="gpt-5-mini",
        fallback_used=False,
        latency_ms=1.0,
        success=True,
    )

