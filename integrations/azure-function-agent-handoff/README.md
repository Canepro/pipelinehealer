# PipelineHealer Agent Handoff Receiver

Minimal Azure Functions app used as the deployment-facing boundary for Assign-to-Agent webhook delivery.

Current scope (`BL-051`):
- authenticated HTTP receiver for normalized handoff events
- structured logging for activity metadata
- health endpoint for deployment verification

Planned follow-on (`BL-052`):
- generic outbound event routing
- pluggable notification sinks (`webhook`, Slack, Teams, Rocket.Chat)

Routes:
- `GET /api/healthz` (`anonymous`)
- `POST /api/agent-handoff` (`function` auth)

## Configuration

The function app is configured via environment variables / application settings:

- `NOTIFY_TARGETS_JSON`
  - optional JSON array describing configured outbound targets for this app
  - current `BL-051` code only counts configured targets and surfaces that count in logs/responses
  - `BL-052` will consume this for real routing behavior
  - expected shape example:

```json
[
  {
    "type": "webhook",
    "url": "https://example.com/notify"
  }
]
```
