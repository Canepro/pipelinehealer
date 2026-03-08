import httpx
import pytest

from src.config import reset_settings
from src.main import app
from src.models import (
    ActivityRecord,
    Diagnosis,
    DiagnosisSource,
    FailureType,
    LLMModelPath,
    RemediationAction,
    RemediationResult,
    RemediationStatus,
)
from src.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def clear_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.setenv("API_AUTH_KEY", "api-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("LLM_PROVIDER", "azure_openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.cognitiveservices.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.1-codex-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    reset_settings()
    yield
    reset_settings()


async def _get_llm_provider_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(
            "/api/settings/llm/provider-health",
            headers={
                "X-API-Key": "api-secret",
                "X-Admin-Key": "admin-secret",
            },
        )


@pytest.mark.asyncio
async def test_llm_provider_health_reports_provider_ready_without_live_validation() -> None:
    app.state.storage = InMemoryStorage()

    response = await _get_llm_provider_health()

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["provider_ready"] is True
    assert body["operation_compatible"] is False
    assert body["full_capability"] is False
    assert body["capability_state"] == "provider_ready"
    assert body["last_validation"] is None


@pytest.mark.asyncio
async def test_llm_provider_health_reports_degraded_recent_llm_failure() -> None:
    storage = InMemoryStorage()
    app.state.storage = storage
    await storage.create_activity(
        ActivityRecord(
            repositoryId="repo-1",
            repository_name="Canepro/pipelinehealer-demo",
            workflow_run_id=101,
            workflow_name="CI",
            status=RemediationStatus.COMPLETED,
            failure_type=FailureType.UNKNOWN,
            diagnosis=Diagnosis(
                failure_type=FailureType.UNKNOWN,
                confidence=0.3,
                root_cause="OperationNotSupported",
                diagnosis_source=DiagnosisSource.LLM,
            ),
            llm_model_path=LLMModelPath(
                provider="azure_openai",
                model="gpt-5.1-codex-mini",
                fallback_used=False,
                call_count=2,
                total_latency_ms=800.0,
                error_count=2,
            ),
            remediation_result=RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_ISSUE,
                issue_url="https://github.com/Canepro/pipelinehealer-demo/issues/1",
                details={"not_auto_reason_code": "LOW_CONFIDENCE"},
            ),
        )
    )

    response = await _get_llm_provider_health()

    assert response.status_code == 200
    body = response.json()
    assert body["capability_state"] == "degraded"
    assert body["operation_compatible"] is False
    assert body["full_capability"] is False
    assert body["last_validation"]["error_count"] == 2
    assert body["last_validation"]["model"] == "gpt-5.1-codex-mini"


@pytest.mark.asyncio
async def test_llm_provider_health_reports_full_capability_after_successful_llm_activity() -> None:
    storage = InMemoryStorage()
    app.state.storage = storage
    await storage.create_activity(
        ActivityRecord(
            repositoryId="repo-1",
            repository_name="Canepro/pipelinehealer-demo",
            workflow_run_id=202,
            workflow_name="CI",
            status=RemediationStatus.COMPLETED,
            failure_type=FailureType.LINT,
            diagnosis=Diagnosis(
                failure_type=FailureType.LINT,
                confidence=0.91,
                root_cause="ESLint flat config missing",
                diagnosis_source=DiagnosisSource.LLM,
                affected_files=["eslint.config.js"],
                suggested_fix="Add eslint.config.js",
            ),
            llm_model_path=LLMModelPath(
                provider="azure_openai",
                model="gpt-5.1-codex-mini",
                fallback_used=False,
                call_count=2,
                total_latency_ms=24000.0,
                error_count=0,
            ),
            remediation_result=RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_PR,
                pr_url="https://github.com/Canepro/pipelinehealer-demo/pull/141",
            ),
        )
    )

    response = await _get_llm_provider_health()

    assert response.status_code == 200
    body = response.json()
    assert body["capability_state"] == "full_capability"
    assert body["operation_compatible"] is True
    assert body["full_capability"] is True
    assert body["last_validation"]["failure_type"] == "lint"
    assert body["last_validation"]["diagnosis_source"] == "llm"
    assert body["last_validation"]["remediation_action"] == "create_pr"
