# PipelineHealer Agent Handoff Receiver

<!-- LAST_VERIFIED: b5d6a5b -->

Minimal Azure Functions app used as the deployment-facing boundary for Assign-to-Agent webhook delivery.

Current scope (`BL-051`):
- authenticated HTTP receiver for normalized handoff events
- structured logging for activity metadata
- health endpoint for deployment verification

Current `BL-052` scope:
- generic outbound event routing from the same normalized handoff event
- first sink types: `webhook`, `rocketchat_webhook`
- non-fatal delivery behavior so the receiver can acknowledge the handoff even if one notification target fails

Planned follow-on:
- additional adapters (`slack_webhook`, `teams_webhook`)
- richer operator status surfacing for downstream notification dependencies

Routes:
- `GET /api/healthz` (`anonymous`)
- `POST /api/agent-handoff` (`function` auth)

## Configuration

The function app is configured via environment variables / application settings:

- `NOTIFY_TARGETS_JSON`
  - optional JSON array describing outbound notification targets for this app
  - invalid targets are ignored and reported through logs plus `GET /api/healthz`
  - event routing is opt-in per target through `events`
  - supported target fields:
    - `type`: `webhook` or `rocketchat_webhook`
    - `url`: full `http(s)` URL
    - `enabled`: optional JSON boolean, default `true`
    - `name`: optional operator-friendly label
    - `events`: optional `"*"` or list of event types; defaults to `"*"`
    - `headers`: optional object of extra HTTP headers, supported only for `webhook`
  - example:

```json
[
  {
    "name": "ops-webhook",
    "type": "webhook",
    "url": "https://example.com/notify",
    "events": ["agent_handoff_requested"],
    "headers": {
      "X-Receiver-Token": "replace-me"
    }
  },
  {
    "name": "rocket-chat",
    "type": "rocketchat_webhook",
    "url": "https://chat.example.com/hooks/abc123",
    "events": "*"
  }
]
```

- `NOTIFY_DELIVERY_TIMEOUT_SECONDS`
  - optional per-request notification delivery timeout
  - defaults to `10`

- `NOTIFY_MAX_TARGETS`
  - optional upper bound for synchronous fan-out on one request
  - defaults to `5`
  - extra configured targets are reported as invalid so the receiver ack path stays bounded

## Event Contract

The receiver uses the same outbound handoff payload emitted by PipelineHealer. Current events default to `agent_handoff_requested` when the sender does not provide an explicit `event_type`.

Generic `webhook` targets receive the full event payload unchanged.

`rocketchat_webhook` targets receive a compact chat message derived from the same payload:
- repository
- workflow name
- activity id
- activity status
- failure type when available
- request id when available

## Operational Notes

- The receiver acknowledges accepted handoff requests even if one or more notification targets fail.
- Delivery failures are logged with target name, type, and error code.
- The receiver intentionally caps synchronous fan-out with `NOTIFY_MAX_TARGETS` so a misconfigured notification list cannot stretch the handoff acknowledgement path indefinitely.
- `GET /api/healthz` includes configured/invalid target counts so deployment verification can catch bad JSON or unsupported sink types early.
