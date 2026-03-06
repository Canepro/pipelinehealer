from shared import json_response, notification_target_health, utc_timestamp


def main(req):  # type: ignore[no-untyped-def]
    _ = req
    target_health = notification_target_health()
    return json_response(
        {
            "status": "ok",
            "service": "pipelinehealer-agent-handoff-receiver",
            "notifications": target_health,
            "timestamp": utc_timestamp(),
        }
    )
