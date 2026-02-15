"""Runtime model-switch behavior tests for mutable deployment updates."""

import pytest

from src.agents.log_analyzer import LogAnalyzerAgent
from src.agents.orchestrator import OrchestratorAgent
from src.config import get_settings, reset_settings
from src.storage import InMemoryStorage


class _DummyGitHubTools:
    def refresh_runtime_settings(self) -> None:
        return None


class _LogsGitHubTools:
    async def get_failed_jobs_logs(self, owner: str, repo: str, run_id: int):
        _ = owner, repo, run_id
        return {"build": "ERROR: module not found"}


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    reset_settings()
    yield
    reset_settings()


@pytest.mark.asyncio
async def test_orchestrator_refresh_rebuilds_cached_agents_with_new_deployment(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    reset_settings()

    sequence = 0

    def _fake_create_cloud_agent(*, name, instructions, credential, settings=None):  # type: ignore[no-untyped-def]
        _ = instructions, credential
        nonlocal sequence
        sequence += 1
        return {
            "seq": sequence,
            "name": name,
            "deployment": getattr(settings, "azure_openai_deployment_name", ""),
        }

    monkeypatch.setattr("src.agents.log_analyzer.create_cloud_agent", _fake_create_cloud_agent)
    monkeypatch.setattr("src.agents.diagnosis.create_cloud_agent", _fake_create_cloud_agent)
    monkeypatch.setattr("src.agents.remediation.create_cloud_agent", _fake_create_cloud_agent)
    monkeypatch.setattr("src.agents.orchestrator.create_cloud_agent", _fake_create_cloud_agent)

    orchestrator = OrchestratorAgent(  # type: ignore[arg-type]
        github_tools=_DummyGitHubTools(),
        storage=InMemoryStorage(),
    )

    first_orchestrator = await orchestrator._get_agent()
    first_log = await orchestrator._log_analyzer._get_agent()
    first_diag = await orchestrator._diagnosis_agent._get_agent()
    first_remediation = await orchestrator._remediation_agent._get_agent()

    assert first_orchestrator["deployment"] == "gpt-5-mini"
    assert first_log["deployment"] == "gpt-5-mini"
    assert first_diag["deployment"] == "gpt-5-mini"
    assert first_remediation["deployment"] == "gpt-5-mini"

    settings = get_settings()
    settings.azure_openai_deployment_name = "gpt-5-pro"
    orchestrator.refresh_runtime_settings()

    second_orchestrator = await orchestrator._get_agent()
    second_log = await orchestrator._log_analyzer._get_agent()
    second_diag = await orchestrator._diagnosis_agent._get_agent()
    second_remediation = await orchestrator._remediation_agent._get_agent()

    assert second_orchestrator["deployment"] == "gpt-5-pro"
    assert second_log["deployment"] == "gpt-5-pro"
    assert second_diag["deployment"] == "gpt-5-pro"
    assert second_remediation["deployment"] == "gpt-5-pro"
    assert second_orchestrator is not first_orchestrator
    assert second_log is not first_log
    assert second_diag is not first_diag
    assert second_remediation is not first_remediation


@pytest.mark.asyncio
async def test_log_analysis_uses_new_deployment_after_refresh(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    reset_settings()

    class _FakeAgent:
        def __init__(self, deployment: str) -> None:
            self._deployment = deployment

        async def run(self, prompt: str) -> str:
            _ = prompt
            return f"deployment={self._deployment}"

    def _fake_create_cloud_agent(*, name, instructions, credential, settings=None):  # type: ignore[no-untyped-def]
        _ = name, instructions, credential
        deployment = getattr(settings, "azure_openai_deployment_name", "")
        return _FakeAgent(deployment=deployment)

    monkeypatch.setattr("src.agents.log_analyzer.create_cloud_agent", _fake_create_cloud_agent)

    analyzer = LogAnalyzerAgent(github_tools=_LogsGitHubTools())  # type: ignore[arg-type]
    initial = await analyzer.analyze("owner", "repo", 123)
    assert initial
    assert "deployment=gpt-5-mini" in initial[0].summary

    settings = get_settings()
    settings.azure_openai_deployment_name = "gpt-5-pro"
    analyzer.refresh_runtime_settings()
    switched = await analyzer.analyze("owner", "repo", 123)

    assert switched
    assert "deployment=gpt-5-pro" in switched[0].summary
