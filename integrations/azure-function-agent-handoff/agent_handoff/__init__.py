import logging

from shared import (
    activity_summary,
    configured_target_count,
    event_type,
    json_response,
    utc_timestamp,
)


def main(req):  # type: ignore[no-untyped-def]
    try:
        payload = req.get_json()
    except ValueError:
        return json_response({"error": "invalid_json"}, status_code=400)

    if not isinstance(payload, dict):
        return json_response({"error": "payload_must_be_object"}, status_code=400)

    summary = activity_summary(payload)
    normalized_event_type = event_type(payload)
    request_id = str(payload.get("request_id", "")).strip()
    delivery_id = str(payload.get("delivery_id", "")).strip()
    targets = configured_target_count()

    logging.info(
        "agent_handoff_received event_type=%s request_id=%s delivery_id=%s "
        "activity_id=%s repository=%s workflow=%s failure_type=%s targets=%s",
        normalized_event_type,
        request_id,
        delivery_id,
        summary["activity_id"],
        summary["repository"],
        summary["workflow"],
        summary["failure_type"],
        targets,
    )

    # BL-051 keeps the receiver boundary intentionally narrow: accept,
    # authenticate via Function auth, log structured metadata, and return an
    # acknowledgement. Generic outbound routing lands in BL-052.
    return json_response(
        {
            "accepted": True,
            "event_type": normalized_event_type,
            "activity_id": summary["activity_id"],
            "repository": summary["repository"],
            "configured_targets": targets,
            "received_at": utc_timestamp(),
        }
    )
