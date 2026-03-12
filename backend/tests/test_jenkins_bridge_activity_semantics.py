"""Regression tests for Jenkins bridge activity semantics and low-evidence fallback."""

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.config import reset_settings
from src.models import (
    Diagnosis,
    ExternalDiagnosticStatus,
    FailureType,
    JenkinsBridgePayload,
    RemediationAction,
    RemediationResult,
)
from src.storage import InMemoryStorage


class _DummyGitHubTools:
    def refresh_runtime_settings(self) -> None:
        return None


class _StaticDiagnosisAgent:
    def __init__(self, diagnosis: Diagnosis) -> None:
        self._diagnosis = diagnosis

    def refresh_runtime_settings(self) -> None:
        return None

    def preview_pattern_diagnosis(self, log_analyses):  # type: ignore[no-untyped-def]
        _ = log_analyses
        return None

    async def diagnose(self, *args, **kwargs) -> Diagnosis:  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return self._diagnosis.model_copy(deep=True)


class _StaticRemediationAgent:
    def refresh_runtime_settings(self) -> None:
        return None

    async def remediate(self, *args, **kwargs) -> RemediationResult:  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return RemediationResult(
            success=True,
            action_taken=RemediationAction.CREATE_ISSUE,
            details={},
        )


class _EmptyLearningContextRetriever:
    async def retrieve(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return []


def _payload(*, log_excerpt: str) -> JenkinsBridgePayload:
    return JenkinsBridgePayload.model_validate(
        {
            "schema_version": "1.0",
            "provider": "jenkins",
            "delivery_id": "jenkins:security-validation#56",
            "sent_at": "2026-03-12T15:12:50Z",
            "repository": "Canepro/rocketchat-k8s",
            "branch": "main",
            "commit_sha": "a" * 40,
            "job": {
                "name": "security-validation-rocketchat-k8s",
                "url": "https://jenkins.canepro.me/job/security-validation-rocketchat-k8s/56/",
                "build_number": 56,
                "result": "FAILURE",
                "duration_ms": 5000,
            },
            "failure": {
                "stage": "security-validation",
                "step": "security-validation",
                "command": "",
                "summary": "Scheduled Jenkins security validation failed",
                "log_excerpt": log_excerpt,
            },
            "artifacts": [],
            "metadata": {
                "jenkins_instance": "jenkins.canepro.me",
                "triggered_by": "schedule",
            },
        }
    )


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    reset_settings()
    yield
    reset_settings()


@pytest.mark.asyncio
async def test_process_bridge_failure_marks_summary_only_payload_as_low_evidence() -> None:
    storage = InMemoryStorage()
    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=storage)  # type: ignore[arg-type]
    orchestrator._diagnosis_agent = _StaticDiagnosisAgent(  # type: ignore[assignment]
        Diagnosis(
            failure_type=FailureType.UNKNOWN,
            confidence=0.1,
            root_cause="Could not determine exact Jenkins failure",
            suggested_fix="Inspect the Jenkins job logs for detailed failure messages.",
            is_auto_fixable=False,
        )
    )
    orchestrator._remediation_agent = _StaticRemediationAgent()  # type: ignore[assignment]
    orchestrator._learning_context_retriever = _EmptyLearningContextRetriever()  # type: ignore[assignment]

    activity = await orchestrator.process_bridge_failure(_payload(log_excerpt=""))

    assert activity.source_metadata["provider"] == "jenkins"
    assert activity.source_metadata["job_result"] == "FAILURE"
    assert activity.source_metadata["evidence_quality"] == "summary_only"
    assert activity.diagnosis is not None
    assert (
        activity.diagnosis.root_cause
        == "Jenkins reported a failed job, but the bridge payload did not include enough evidence to classify the failure precisely."
    )
    assert (
        activity.diagnosis.suggested_fix
        == "Open the Jenkins job, capture the failing log excerpt or artifact output, and rerun the job or resend the bridge event after the specific tool, credential, or infrastructure error is visible."
    )
    assert activity.diagnosis.error_details["classification_state"] == "insufficient_jenkins_evidence"
    assert activity.diagnosis.error_details["bridge_evidence_quality"] == "summary_only"
    assert activity.external_diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert activity.external_diagnostics[0].metadata["display_state"] == "context_only"


@pytest.mark.asyncio
async def test_process_bridge_failure_keeps_richer_bridge_diagnosis_intact() -> None:
    storage = InMemoryStorage()
    orchestrator = OrchestratorAgent(github_tools=_DummyGitHubTools(), storage=storage)  # type: ignore[arg-type]
    orchestrator._diagnosis_agent = _StaticDiagnosisAgent(  # type: ignore[assignment]
        Diagnosis(
            failure_type=FailureType.BUILD_CONFIG,
            confidence=0.82,
            root_cause="Critical vulnerability threshold exceeded",
            suggested_fix="Reduce the Trivy threshold or remediate the reported image vulnerabilities.",
            is_auto_fixable=False,
            error_details={"reason_code": "security_threshold_exceeded"},
        )
    )
    orchestrator._remediation_agent = _StaticRemediationAgent()  # type: ignore[assignment]
    orchestrator._learning_context_retriever = _EmptyLearningContextRetriever()  # type: ignore[assignment]

    activity = await orchestrator.process_bridge_failure(
        _payload(log_excerpt="trivy scan failed: critical vulnerability threshold exceeded")
    )

    assert activity.source_metadata["evidence_quality"] == "log_excerpt"
    assert activity.diagnosis is not None
    assert activity.diagnosis.root_cause == "Critical vulnerability threshold exceeded"
    assert (
        activity.diagnosis.suggested_fix
        == "Reduce the Trivy threshold or remediate the reported image vulnerabilities."
    )
    assert activity.diagnosis.error_details["bridge_evidence_quality"] == "log_excerpt"
    assert "classification_state" not in activity.diagnosis.error_details
    assert activity.external_diagnostics[0].metadata["display_state"] == "log_excerpt"
