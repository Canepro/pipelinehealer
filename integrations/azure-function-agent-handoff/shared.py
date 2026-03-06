import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

import azure.functions as func

_SUPPORTED_TARGET_TYPES = {
    "rocketchat_webhook",
    "slack_webhook",
    "teams_webhook",
    "webhook",
}
_DEFAULT_EVENT_TYPE = "agent_handoff_requested"
_DEFAULT_DELIVERY_TIMEOUT_SECONDS = 10
_DEFAULT_MAX_TARGETS = 5


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
    # A target without explicit events should receive all handoff events.
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


def _normalize_enabled(raw_enabled: Any) -> bool:
    if raw_enabled is None:
        return True
    if not isinstance(raw_enabled, bool):
        raise ValueError("enabled must be a JSON boolean")
    return raw_enabled


def _max_targets() -> int:
    raw = os.getenv("NOTIFY_MAX_TARGETS", "").strip()
    if not raw:
        return _DEFAULT_MAX_TARGETS
    try:
        value = int(raw)
    except ValueError:
        logging.warning("invalid_notify_max_targets raw=%s", raw)
        return _DEFAULT_MAX_TARGETS
    if value <= 0:
        logging.warning("non_positive_notify_max_targets raw=%s", raw)
        return _DEFAULT_MAX_TARGETS
    return value


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
    max_targets = _max_targets()
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            errors.append(f"target {index}: entry must be an object")
            continue
        if len(targets) >= max_targets:
            errors.append(f"target {index}: exceeds NOTIFY_MAX_TARGETS={max_targets}")
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

            headers = _normalize_headers(item.get("headers"))
            if headers and target_type != "webhook":
                raise ValueError("headers are only supported for webhook targets")

            target = NotificationTarget(
                index=index,
                target_type=target_type,
                url=url,
                events=_normalize_events(item.get("events")),
                enabled=_normalize_enabled(item.get("enabled")),
                name=_target_name(target_type, index, item.get("name")),
                headers=headers,
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


def _chat_lines(payload: dict[str, Any]) -> list[str]:
    summary = activity_summary(payload)
    request_id = str(payload.get("request_id", "")).strip()
    normalized_event_type = event_type(payload)

    lines = [
        "PipelineHealer handoff received",
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
    return lines


def _rocketchat_payload(payload: dict[str, Any], target: NotificationTarget) -> dict[str, Any]:
    summary = activity_summary(payload)
    delivery_id = str(payload.get("delivery_id", "")).strip()
    normalized_event_type = event_type(payload)

    # Keep the chat payload short and human-readable, while preserving the original
    # event contract in a structured attachment for downstream tooling.
    lines = _chat_lines(payload)
    lines[0] = ":robot_face: " + lines[0]

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


def _slack_payload(payload: dict[str, Any], _target: NotificationTarget) -> dict[str, Any]:
    lines = _chat_lines(payload)
    summary = activity_summary(payload)

    # Slack incoming webhooks accept normal message text plus Block Kit.
    fields = [
        {"type": "mrkdwn", "text": f"*Repository*\n{summary['repository'] or 'n/a'}"},
        {"type": "mrkdwn", "text": f"*Workflow*\n{summary['workflow_name'] or 'n/a'}"},
        {"type": "mrkdwn", "text": f"*Activity*\n{summary['activity_id'] or 'n/a'}"},
        {"type": "mrkdwn", "text": f"*Status*\n{summary['status'] or 'n/a'}"},
    ]
    if summary["failure_type"]:
        fields.append({"type": "mrkdwn", "text": f"*Failure Type*\n{summary['failure_type']}"})

    return {
        "text": " | ".join(lines),
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*PipelineHealer handoff received*",
                },
            },
            {
                "type": "section",
                "fields": fields,
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": line} for line in lines[1:]],
            },
        ],
    }


def _teams_payload(payload: dict[str, Any], _target: NotificationTarget) -> dict[str, Any]:
    summary = activity_summary(payload)
    request_id = str(payload.get("request_id", "")).strip()
    normalized_event_type = event_type(payload)

    facts = [
        {"title": "Event", "value": normalized_event_type},
        {"title": "Repository", "value": summary["repository"] or "n/a"},
        {"title": "Workflow", "value": summary["workflow_name"] or "n/a"},
        {"title": "Activity", "value": summary["activity_id"] or "n/a"},
        {"title": "Status", "value": summary["status"] or "n/a"},
    ]
    if summary["failure_type"]:
        facts.append({"title": "Failure Type", "value": summary["failure_type"]})
    if request_id:
        facts.append({"title": "Request ID", "value": request_id})

    # Teams Incoming Webhooks accept a message wrapper containing an Adaptive Card attachment.
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "PipelineHealer handoff received",
                            "weight": "Bolder",
                            "size": "Medium",
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "facts": facts,
                        },
                    ],
                },
            }
        ],
    }


def _payload_for_target(payload: dict[str, Any], target: NotificationTarget) -> dict[str, Any]:
    if target.target_type == "rocketchat_webhook":
        return _rocketchat_payload(payload, target)
    if target.target_type == "slack_webhook":
        return _slack_payload(payload, target)
    if target.target_type == "teams_webhook":
        return _teams_payload(payload, target)
    return _webhook_payload(payload, target)


def _post_json(url: str, body: dict[str, Any], headers: tuple[tuple[str, str], ...]) -> tuple[bool, str]:
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": "PipelineHealer-Agent-Handoff-Receiver/0.1",
    }
    for key, value in headers:
        request_headers[key] = value

    try:
        payload_bytes = json.dumps(body).encode("utf-8")
        req = request.Request(url, data=payload_bytes, headers=request_headers, method="POST")
        with request.urlopen(req, timeout=_delivery_timeout_seconds()) as response:
            status_code = getattr(response, "status", 0)
            if 200 <= status_code < 300:
                return True, ""
            return False, f"http_{status_code}"
    except ValueError as exc:
        return False, f"request_error:{exc}"
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

    # Keep synchronous fan-out bounded until BL-054/next slices decide whether
    # delivery should move to a queue or background worker model.
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
