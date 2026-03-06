import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import azure.functions as func


def coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def configured_target_count() -> int:
    raw = os.getenv("NOTIFY_TARGETS_JSON", "").strip()
    if not raw:
        return 0
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logging.warning("invalid_notify_targets_json")
        return 0
    if not isinstance(parsed, list):
        logging.warning("notify_targets_json_not_list")
        return 0
    return len(parsed)


def event_type(payload: dict[str, Any]) -> str:
    value = str(payload.get("event_type", "")).strip().lower()
    return value or "agent_handoff_requested"


def activity_summary(payload: dict[str, Any]) -> dict[str, str]:
    activity = coerce_dict(payload.get("activity"))
    return {
        "activity_id": str(activity.get("id", "")).strip(),
        "repository": str(activity.get("repository", "")).strip(),
        "workflow": str(activity.get("workflow", "")).strip(),
        "failure_type": str(activity.get("failure_type", "")).strip(),
    }


def json_response(body: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body),
        status_code=status_code,
        mimetype="application/json",
    )


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
