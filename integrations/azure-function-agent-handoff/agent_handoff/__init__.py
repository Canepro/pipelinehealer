import logging

from shared import (
    activity_summary,
    deliver_notification_targets,
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
    notification_summary = deliver_notification_targets(payload)

    logging.info(
        "agent_handoff_received event_type=%s request_id=%s delivery_id=%s "
        "activity_id=%s repository=%s workflow=%s failure_type=%s configured_targets=%s "
        "delivered_targets=%s failed_targets=%s invalid_targets=%s",
        normalized_event_type,
        request_id,
        delivery_id,
        summary["activity_id"],
        summary["repository"],
        summary["workflow_name"],
        summary["failure_type"],
        notification_summary["configured_targets"],
        notification_summary["delivered_targets"],
        notification_summary["failed_targets"],
        notification_summary["invalid_targets"],
    )

    # Delivery errors are reported in the acknowledgement, but they do not
    # change the receiver's accept/ack contract for the primary handoff path.
    return json_response(
        {
            "accepted": True,
            "event_type": normalized_event_type,
            "activity_id": summary["activity_id"],
            "repository": summary["repository"],
            "notification_summary": notification_summary,
            "received_at": utc_timestamp(),
        }
    )
