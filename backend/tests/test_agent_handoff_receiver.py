"""Tests for the reference Assign-to-Agent receiver notification sinks."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest


def _load_receiver_shared_module() -> Any:
    module_name = "pipelinehealer_agent_handoff_shared_test"
    module_path = (
        Path(__file__).resolve().parents[2]
        / "integrations"
        / "azure-function-agent-handoff"
        / "shared.py"
    )

    azure_module = types.ModuleType("azure")
    functions_module = types.ModuleType("azure.functions")

    class _HttpResponse:  # pragma: no cover - only needed for import compatibility
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    functions_module.HttpResponse = _HttpResponse
    azure_module.functions = functions_module
    sys.modules["azure"] = azure_module
    sys.modules["azure.functions"] = functions_module

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def receiver_shared(monkeypatch: pytest.MonkeyPatch) -> Any:
    for key in [
        "NOTIFY_TARGETS_JSON",
        "NOTIFY_EMAIL_SMTP_HOST",
        "NOTIFY_EMAIL_SMTP_PORT",
        "NOTIFY_EMAIL_SMTP_USERNAME",
        "NOTIFY_EMAIL_SMTP_PASSWORD",
        "NOTIFY_EMAIL_SMTP_STARTTLS",
        "NOTIFY_EMAIL_SMTP_SSL",
        "NOTIFY_EMAIL_FROM_ADDRESS",
    ]:
        monkeypatch.delenv(key, raising=False)
    return _load_receiver_shared_module()


def test_notification_target_health_reports_missing_email_transport(
    monkeypatch: pytest.MonkeyPatch,
    receiver_shared: Any,
) -> None:
    monkeypatch.setenv(
        "NOTIFY_TARGETS_JSON",
        '[{"type":"email","to":["ops@example.com"],"events":["agent_handoff_requested"]}]',
    )

    health = receiver_shared.notification_target_health()
    assert health["configured_targets"] == 1
    assert health["enabled_targets"] == 1
    assert health["invalid_targets"] >= 1
    assert any("NOTIFY_EMAIL_SMTP_HOST" in error for error in health["errors"])
    assert "email" in health["supported_target_types"]


def test_deliver_notification_targets_sends_email(
    monkeypatch: pytest.MonkeyPatch,
    receiver_shared: Any,
) -> None:
    monkeypatch.setenv(
        "NOTIFY_TARGETS_JSON",
        (
            '[{"type":"email","name":"ops-email","to":["ops@example.com"],'
            '"subject_prefix":"[PH]","events":["agent_handoff_requested"]}]'
        ),
    )
    monkeypatch.setenv("NOTIFY_EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("NOTIFY_EMAIL_SMTP_PORT", "587")
    monkeypatch.setenv("NOTIFY_EMAIL_SMTP_STARTTLS", "false")
    monkeypatch.setenv("NOTIFY_EMAIL_FROM_ADDRESS", "pipelinehealer@example.com")

    sent_messages: list[Any] = []

    class _FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            assert host == "smtp.example.com"
            assert port == 587
            assert timeout == 10.0

        def __enter__(self) -> "_FakeSMTP":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            raise AssertionError("login should not be used without credentials")

        def send_message(self, message: Any) -> None:
            sent_messages.append(message)

    monkeypatch.setattr(receiver_shared.smtplib, "SMTP", _FakeSMTP)

    result = receiver_shared.deliver_notification_targets(
        {
            "event_type": "agent_handoff_requested",
            "request_id": "req-123",
            "activity": {
                "id": "activity-123",
                "repository": "Canepro/pipelinehealer",
                "workflow_name": "CI",
                "status": "failed",
                "failure_type": "dependency",
            },
            "context": "PipelineHealer context excerpt",
        }
    )

    assert result["delivered_targets"] == 1
    assert result["failed_targets"] == 0
    assert len(sent_messages) == 1
    message = sent_messages[0]
    assert message["To"] == "ops@example.com"
    assert message["From"] == "pipelinehealer@example.com"
    assert "[PH]" in message["Subject"]
    assert "Canepro/pipelinehealer" in message.get_content()


def test_rocketchat_payload_prioritizes_operator_context(receiver_shared: Any) -> None:
    payload = receiver_shared._rocketchat_payload(  # noqa: SLF001 - focused formatter coverage
        {
            "event_type": "agent_handoff_requested",
            "request_id": "req-123",
            "delivery_id": "delivery-123",
            "activity": {
                "id": "activity-123",
                "repository": "Canepro/pipelinehealer",
                "workflow_name": "CI",
                "status": "completed",
                "failure_type": "dependency",
            },
            "summary": {
                "activity_url": "https://frontend.example/app/activities/activity-123",
                "root_cause": "The workflow failed because left-pad is missing.",
                "suggested_fix": "Add left-pad to dependencies.",
                "remediation_action": "create_issue",
                "remediation_success": True,
                "issue_url": "https://github.com/Canepro/pipelinehealer/issues/321",
            },
        },
        receiver_shared.NotificationTarget(
            index=1,
            target_type="rocketchat_webhook",
            name="rocket-chat",
        ),
    )

    assert "PipelineHealer handoff requested" in payload["text"]
    assert "Diagnosis: The workflow failed because left-pad is missing." in payload["text"]
    assert "Suggested fix: Add left-pad to dependencies." in payload["text"]
    assert "Remediation: create issue succeeded" in payload["text"]
    assert "Open activity: https://frontend.example/app/activities/activity-123" in payload["text"]
    assert "Open issue: https://github.com/Canepro/pipelinehealer/issues/321" in payload["text"]
    assert "Delivery ID: delivery-123" in payload["attachments"][0]["text"]
