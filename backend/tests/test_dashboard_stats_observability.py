"""Dashboard stats observability metrics tests."""

from datetime import timedelta

import pytest

from src.models import (
    ActivityRecord,
    LLMModelPath,
    MCPModelPath,
    RemediationStatus,
    utcnow,
)
from src.storage import InMemoryStorage


@pytest.mark.asyncio
async def test_stats_include_mcp_enabled_runs_and_llm_fallback_rate_30d() -> None:
    storage = InMemoryStorage()

    recent_with_fallback = ActivityRecord(
        repositoryId="1",
        repository_name="octo/demo",
        workflow_run_id=101,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
        llm_model_path=LLMModelPath(
            provider="azure_openai",
            model="gpt-5-mini",
            fallback_used=True,
            call_count=2,
            total_latency_ms=120.0,
        ),
        mcp_model_path=MCPModelPath(
            provider="github",
            enabled=True,
            available=True,
            read_only=True,
            reason="ok",
        ),
    )
    await storage.create_activity(recent_with_fallback)

    recent_without_fallback = ActivityRecord(
        repositoryId="1",
        repository_name="octo/demo",
        workflow_run_id=102,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
        llm_model_path=LLMModelPath(
            provider="azure_openai",
            model="gpt-5-mini",
            fallback_used=False,
            call_count=1,
            total_latency_ms=90.0,
        ),
        mcp_model_path=MCPModelPath(
            provider="github",
            enabled=True,
            available=True,
            read_only=True,
            reason="ok",
        ),
    )
    await storage.create_activity(recent_without_fallback)

    old_with_fallback = ActivityRecord(
        repositoryId="1",
        repository_name="octo/demo",
        workflow_run_id=103,
        workflow_name="CI",
        status=RemediationStatus.COMPLETED,
        llm_model_path=LLMModelPath(
            provider="azure_openai",
            model="gpt-5-mini",
            fallback_used=True,
            call_count=1,
            total_latency_ms=80.0,
        ),
        mcp_model_path=MCPModelPath(
            provider="github",
            enabled=True,
            available=True,
            read_only=True,
            reason="ok",
        ),
    )
    await storage.create_activity(old_with_fallback)
    old_with_fallback.created_at = utcnow() - timedelta(days=45)

    stats = await storage.get_stats()
    assert stats.total_runs_processed == 3
    assert stats.mcp_enabled_runs_30d == 2
    assert stats.llm_fallback_rate_30d == 50.0
