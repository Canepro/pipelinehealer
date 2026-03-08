"""Operator-facing LLM capability assessment derived from config and live activity evidence."""

from datetime import datetime, timedelta
from typing import Any

from ..models import (
    ActivityRecord,
    DiagnosisSource,
    FailureType,
    LLMCapabilityEvidenceView,
    LLMCapabilityState,
    RemediationAction,
    utcnow,
)
from ..storage import ActivityStorage

_CAPABILITY_LOOKBACK_DAYS = 14
_CAPABILITY_SCAN_PAGE_SIZE = 200


def _required_llm_config_present(settings: Any) -> bool:
    provider = str(getattr(settings, "llm_provider", "azure_openai") or "").strip().lower()
    if provider == "openai_compatible":
        return all(
            str(value or "").strip()
            for value in (
                getattr(settings, "openai_compatible_base_url", ""),
                getattr(settings, "openai_compatible_model", ""),
                getattr(settings, "openai_compatible_api_key", ""),
            )
        )
    if provider == "custom":
        return False
    return all(
        str(value or "").strip()
        for value in (
            getattr(settings, "azure_openai_endpoint", ""),
            getattr(settings, "azure_openai_deployment_name", ""),
        )
    )


def _configured_models(settings: Any) -> set[str]:
    provider = str(getattr(settings, "llm_provider", "azure_openai") or "").strip().lower()
    models = {
        str(getattr(settings, "llm_model_analysis", "") or "").strip(),
        str(getattr(settings, "llm_model_diagnosis", "") or "").strip(),
        str(getattr(settings, "llm_model_remediation", "") or "").strip(),
    }
    default_model = (
        str(getattr(settings, "openai_compatible_model", "") or "").strip()
        if provider == "openai_compatible"
        else str(getattr(settings, "azure_openai_deployment_name", "") or "").strip()
    )
    if default_model:
        models.add(default_model)
    return {model for model in models if model}


def _activity_matches_runtime(
    activity: ActivityRecord,
    *,
    provider: str,
    configured_models: set[str],
) -> bool:
    path = activity.llm_model_path
    if path is None or path.call_count <= 0:
        return False
    if str(path.provider or "").strip().lower() != provider:
        return False
    return not configured_models or str(path.model or "").strip() in configured_models


def _to_evidence(activity: ActivityRecord) -> LLMCapabilityEvidenceView:
    path = activity.llm_model_path
    diagnosis = activity.diagnosis
    remediation = activity.remediation_result
    return LLMCapabilityEvidenceView(
        activity_id=activity.id,
        workflow_run_id=activity.workflow_run_id,
        observed_at=activity.updated_at,
        model=path.model if path is not None else "unknown",
        fallback_used=bool(path.fallback_used) if path is not None else False,
        error_count=int(path.error_count) if path is not None else 0,
        failure_type=activity.failure_type.value if activity.failure_type else None,
        diagnosis_source=diagnosis.diagnosis_source.value if diagnosis and diagnosis.diagnosis_source else None,
        diagnosis_confidence=diagnosis.confidence if diagnosis else None,
        remediation_action=remediation.action_taken.value if remediation else None,
        remediation_success=remediation.success if remediation else None,
    )


def _is_full_capability_activity(activity: ActivityRecord) -> bool:
    path = activity.llm_model_path
    diagnosis = activity.diagnosis
    remediation = activity.remediation_result
    if path is None or path.error_count > 0 or path.fallback_used:
        return False
    if diagnosis is None or diagnosis.diagnosis_source != DiagnosisSource.LLM:
        return False
    if activity.failure_type in (None, FailureType.UNKNOWN):
        return False
    if diagnosis.confidence < 0.5:
        return False
    if remediation is None or not remediation.success:
        return False
    if remediation.action_taken == RemediationAction.SKIP:
        return False
    details = remediation.details or {}
    return details.get("not_auto_reason_code") != "LOW_CONFIDENCE"


async def _latest_matching_activity(
    *,
    storage: ActivityStorage,
    provider: str,
    configured_models: set[str],
    since: datetime,
) -> ActivityRecord | None:
    offset = 0
    latest: ActivityRecord | None = None

    while True:
        page = await storage.get_activities(
            limit=_CAPABILITY_SCAN_PAGE_SIZE,
            offset=offset,
            since=since,
        )
        if not page:
            break

        for activity in page:
            if not _activity_matches_runtime(
                activity,
                provider=provider,
                configured_models=configured_models,
            ):
                continue
            if latest is None or activity.updated_at > latest.updated_at:
                latest = activity

        if len(page) < _CAPABILITY_SCAN_PAGE_SIZE:
            break
        offset += len(page)

    return latest


async def build_llm_capability_snapshot(
    *,
    settings: Any,
    storage: ActivityStorage,
    provider_health: dict[str, Any],
) -> dict[str, Any]:
    """Classify current LLM runtime maturity using config and recent live evidence."""
    implemented = bool(provider_health.get("implemented"))
    available = bool(provider_health.get("available"))
    configured = _required_llm_config_present(settings)
    snapshot: dict[str, Any] = {
        "configured": configured,
        "provider_ready": available,
        "operation_compatible": False,
        "full_capability": False,
        "capability_state": LLMCapabilityState.NOT_CONFIGURED,
        "capability_summary": "LLM runtime is not configured.",
        "last_validated_at": None,
        "last_validation": None,
    }

    if not implemented:
        snapshot["capability_state"] = LLMCapabilityState.NOT_IMPLEMENTED
        snapshot["capability_summary"] = (
            "The selected provider is scaffolded only and cannot execute live remediation tasks."
        )
        return snapshot

    if not configured:
        return snapshot

    if not available:
        snapshot["capability_state"] = LLMCapabilityState.CONFIGURED
        snapshot["capability_summary"] = (
            "Required LLM settings are present, but provider readiness checks are failing."
        )
        return snapshot

    provider = str(provider_health.get("provider", "") or "").strip().lower()
    configured_models = _configured_models(settings)
    since = utcnow() - timedelta(days=_CAPABILITY_LOOKBACK_DAYS)
    latest = await _latest_matching_activity(
        storage=storage,
        provider=provider,
        configured_models=configured_models,
        since=since,
    )

    if latest is None:
        snapshot["capability_state"] = LLMCapabilityState.PROVIDER_READY
        snapshot["capability_summary"] = (
            "Provider readiness checks pass, but there is no recent live activity for the current model routing."
        )
        return snapshot

    evidence = _to_evidence(latest)
    snapshot["last_validated_at"] = evidence.observed_at
    snapshot["last_validation"] = evidence

    if evidence.error_count > 0:
        snapshot["capability_state"] = LLMCapabilityState.DEGRADED
        snapshot["capability_summary"] = (
            f"Recent live activity for model '{evidence.model}' hit LLM call errors; the runtime is in degraded mode."
        )
        return snapshot

    snapshot["operation_compatible"] = True
    if _is_full_capability_activity(latest):
        snapshot["full_capability"] = True
        snapshot["capability_state"] = LLMCapabilityState.FULL_CAPABILITY
        snapshot["capability_summary"] = (
            f"Recent live activity for model '{evidence.model}' completed with successful LLM diagnosis and remediation."
        )
        return snapshot

    snapshot["capability_state"] = LLMCapabilityState.OPERATION_COMPATIBLE
    if evidence.fallback_used:
        snapshot["capability_summary"] = (
            f"Recent live activity for model '{evidence.model}' succeeded only after compatibility fallback."
        )
    else:
        snapshot["capability_summary"] = (
            f"Recent live activity for model '{evidence.model}' completed without LLM call errors, but full remediation capability is not yet proven."
        )
    return snapshot
