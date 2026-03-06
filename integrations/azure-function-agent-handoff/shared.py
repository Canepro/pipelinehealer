import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

import azure.functions as func

_SUPPORTED_TARGET_TYPES = {"webhook", "rocketchat_webhook"}
_DEFAULT_EVENT_TYPE = "agent_handoff_requested"
_DEFAULT_DELIVERY_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class NotificationTarget:
    index: int
    target_type: str
    url: str
    events: tuple[str, ...]
    enabled: bool = True
    name: str = ""
    headers: tuple[tuple[str, str], ...] = ()


def coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_type(payload: dict[str, Any]) -> str:
    value = str(payload.get("event_type", "")).strip().lower()
    return value or _DEFAULT_EVENT_TYPE


def activity_summary(payload: dict[str, Any]) -> dict[str, str]:
    activity = coerce_dict(payload.get("activity"))
    return {
        "activity_id": str(activity.get("id", "")).strip(),
        "repository": str(activity.get("repository", "")).strip(),
        "workflow_name": str(activity.get("workflow_name", "")).strip(),
        "failure_type": str(activity.get("failure_type", "")).strip(),
        "status": str(activity.get("status", "")).strip(),
    }


def json_response(body: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body),
        status_code=status_code,
        mimetype="application/json",
    )


def _delivery_timeout_seconds() -> int:
    raw = os.getenv("NOTIFY_DELIVERY_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_DELIVERY_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        logging.warning("invalid_notify_delivery_timeout_seconds raw=%s", raw)
        return _DEFAULT_DELIVERY_TIMEOUT_SECONDS
    if value <= 0:
        logging.warning("non_positive_notify_delivery_timeout_seconds raw=%s", raw)
        return _DEFAULT_DELIVERY_TIMEOUT_SECONDS
    return value


def _normalize_events(raw_events: Any) -> tuple[str, ...]:
    # A target without explicit events should still receive the default handoff signal.
    if raw_events is None:
        return ("*",)
    if isinstance(raw_events, str):
        normalized = raw_events.strip().lower()
        return (normalized,) if normalized else ("*",)
    if not isinstance(raw_events, list):
        raise ValueError("events must be a string or list of strings")

    values: list[str] = []
    for item in raw_events:
        if not isinstance(item, str):
            raise ValueError("events list must only contain strings")
        normalized = item.strip().lower()
        if normalized:
            values.append(normalized)
    return tuple(values or ["*"])


def _normalize_headers(raw_headers: Any) -> tuple[tuple[str, str], ...]:
    if raw_headers is None:
        return ()
    if not isinstance(raw_headers, dict):
        raise ValueError("headers must be an object")

    normalized: list[tuple[str, str]] = []
    for key, value in raw_headers.items():
        header_name = str(key).strip()
        header_value = str(value).strip()
        if header_name and header_value:
            normalized.append((header_name, header_value))
    return tuple(normalized)


def _target_name(target_type: str, index: int, raw_name: Any) -> str:
    explicit = str(raw_name or "").strip()
    return explicit or f"{target_type}:{index}"


def parse_notify_targets() -> tuple[list[NotificationTarget], list[str]]:
    raw = os.getenv("NOTIFY_TARGETS_JSON", "").strip()
    if not raw:
        return [], []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logging.warning("invalid_notify_targets_json error=%s", exc)
        return [], ["NOTIFY_TARGETS_JSON must be valid JSON"]

    if not isinstance(parsed, list):
        logging.warning("notify_targets_json_not_list")
        return [], ["NOTIFY_TARGETS_JSON must be a JSON array"]

    targets: list[NotificationTarget] = []
    errors: list[str] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            errors.append(f"target {index}: entry must be an object")
            continue

        try:
            target_type = str(item.get("type", "")).strip().lower()
            if target_type not in _SUPPORTED_TARGET_TYPES:
                raise ValueError(
                    f"unsupported type '{target_type or 'missing'}'; supported types: "
                    + ", ".join(sorted(_SUPPORTED_TARGET_TYPES))
                )

            url = str(item.get("url", "")).strip()
            if not url.startswith(("http://", "https://")):
                raise ValueError("url must be a full http(s) URL")

            target = NotificationTarget(
                index=index,
                target_type=target_type,
                url=url,
                events=_normalize_events(item.get("events")),
                enabled=bool(item.get("enabled", True)),
                name=_target_name(target_type, index, item.get("name")),
                headers=_normalize_headers(item.get("headers")),
            )
            targets.append(target)
        except ValueError as exc:
            errors.append(f"target {index}: {exc}")

    return targets, errors


def notification_target_health() -> dict[str, Any]:
    targets, errors = parse_notify_targets()
    enabled_targets = [target for target in targets if target.enabled]
    return {
        "configured_targets": len(targets),
        "enabled_targets": len(enabled_targets),
        "invalid_targets": len(errors),
        "supported_target_types": sorted(_SUPPORTED_TARGET_TYPES),
        "errors": errors,
    }


def _event_matches(target: NotificationTarget, normalized_event_type: str) -> bool:
    return "*" in target.events or normalized_event_type in target.events


def _webhook_payload(payload: dict[str, Any], _target: NotificationTarget) -> dict[str, Any]:
    return payload


def _rocketchat_payload(payload: dict[str, Any], target: NotificationTarget) -> dict[str, Any]:
    summary = activity_summary(payload)
    request_id = str(payload.get("request_id", "")).strip()
    delivery_id = str(payload.get("delivery_id", "")).strip()
    normalized_event_type = event_type(payload)

    # Keep the chat payload short and human-readable, while preserving the original
    # event contract in a structured attachment for downstream tooling.
    lines = [
        ":robot_face: PipelineHealer handoff received",
        f"Event: {normalized_event_type}",
        f"Repository: {summary['repository'] or 'n/a'}",
        f"Workflow: {summary['workflow_name'] or 'n/a'}",
        f"Activity: {summary['activity_id'] or 'n/a'}",
        f"Status: {summary['status'] or 'n/a'}",
    ]
    if summary["failure_type"]:
        lines.append(f"Failure Type: {summary['failure_type']}")
    if request_id:
        lines.append(f"Request ID: {request_id}")

    return {
        "alias": "PipelineHealer",
        "text": "\n".join(lines),
        "attachments": [
            {
                "title": target.name,
                "text": json.dumps(
                    {
                        "event_type": normalized_event_type,
                        "delivery_id": delivery_id,
                        "activity_id": summary["activity_id"],
                        "repository": summary["repository"],
                        "workflow_name": summary["workflow_name"],
                    }
                ),
            }
        ],
    }


def _payload_for_target(payload: dict[str, Any], target: NotificationTarget) -> dict[str, Any]:
    if target.target_type == "rocketchat_webhook":
        return _rocketchat_payload(payload, target)
    return _webhook_payload(payload, target)


def _post_json(url: str, body: dict[str, Any], headers: tuple[tuple[str, str], ...]) -> tuple[bool, str]:
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": "PipelineHealer-Agent-Handoff-Receiver/0.1",
    }
    for key, value in headers:
        request_headers[key] = value

    payload_bytes = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=payload_bytes, headers=request_headers, method="POST")
    try:
        with request.urlopen(req, timeout=_delivery_timeout_seconds()) as response:
            status_code = getattr(response, "status", 0)
            if 200 <= status_code < 300:
                return True, ""
            return False, f"http_{status_code}"
    except error.HTTPError as exc:
        return False, f"http_{exc.code}"
    except error.URLError as exc:
        return False, f"url_error:{exc.reason}"
    except TimeoutError:
        return False, "timeout"


def deliver_notification_targets(payload: dict[str, Any]) -> dict[str, Any]:
    targets, errors = parse_notify_targets()
    normalized_event_type = event_type(payload)

    delivered = 0
    failed = 0
    skipped = 0
    results: list[dict[str, Any]] = []

    for target in targets:
        if not target.enabled:
            skipped += 1
            results.append({"name": target.name, "type": target.target_type, "status": "disabled"})
            continue
        if not _event_matches(target, normalized_event_type):
            skipped += 1
            results.append({"name": target.name, "type": target.target_type, "status": "event_filtered"})
            continue

        body = _payload_for_target(payload, target)
        success, error_code = _post_json(target.url, body, target.headers)
        if success:
            delivered += 1
            results.append({"name": target.name, "type": target.target_type, "status": "delivered"})
            continue

        failed += 1
        results.append(
            {
                "name": target.name,
                "type": target.target_type,
                "status": "failed",
                "error": error_code or "unknown_error",
            }
        )
        logging.warning(
            "notification_delivery_failed target=%s type=%s error=%s",
            target.name,
            target.target_type,
            error_code or "unknown_error",
        )

    return {
        "configured_targets": len(targets),
        "invalid_targets": len(errors),
        "delivered_targets": delivered,
        "failed_targets": failed,
        "skipped_targets": skipped,
        "errors": errors,
        "results": results,
    }
