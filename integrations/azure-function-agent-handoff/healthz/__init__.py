from shared import json_response, utc_timestamp


def main(req):  # type: ignore[no-untyped-def]
    _ = req
    return json_response(
        {
            "status": "ok",
            "service": "pipelinehealer-agent-handoff-receiver",
            "timestamp": utc_timestamp(),
        }
    )
