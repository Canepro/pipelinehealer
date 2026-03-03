# BL-034 Technical Design: Jenkins Bridge Ingestion

<!-- LAST_VERIFIED: 3116334 -->

Status: Draft (design only, no implementation in this document)  
Backlog: `BL-034`  
Target: `v0.3.2` (planned)  
Related issue: [#36](https://github.com/Canepro/pipelinehealer/issues/36)

## Why This Exists

PipelineHealer currently ingests failures primarily from GitHub `workflow_run` webhooks.  
For Jenkins-primary repositories, this can produce no trigger even when failures happen.

`BL-034` adds a signed Jenkins bridge ingest path so Jenkins failures can create auditable PipelineHealer activities using existing diagnosis/remediation flow with safe defaults.

## Goals

1. Accept Jenkins failure payloads through a signed endpoint.
2. Enforce replay protection and repo allowlist policy before processing.
3. Create synthetic activity records with explicit source attribution (`jenkins_bridge`).
4. Reuse existing diagnosis/remediation pipeline in issue-first safe mode.

## Non-Goals (This Scope)

1. Full native Jenkins provider parity (artifact APIs, rerun actions, job orchestration).
2. New remediation write behavior beyond existing policy gates.
3. Replacing GitHub webhook path.

## Proposed API Contract

Endpoint:
- `POST /webhook/jenkins`

Auth model:
- Not API-key based by default.
- Uses dedicated HMAC signature verification for machine-to-machine ingest.

Required headers:
- `X-PH-Bridge-Provider: jenkins`
- `X-PH-Bridge-Timestamp: <unix_epoch_seconds>`
- `X-PH-Bridge-Nonce: <uuid_or_unique_string>`
- `X-PH-Bridge-Signature: sha256=<hex_hmac>`
- `Content-Type: application/json`

Optional headers:
- `X-Request-Id`
- `X-PH-Bridge-Key-Id` (for future key rotation)

Success response:
- `202 Accepted`

```json
{
  "status": "processing",
  "activity_id": "uuid-string",
  "source": "jenkins_bridge",
  "repository": "owner/repo",
  "delivery_id": "jenkins-unique-delivery-id"
}
```

Ignored duplicate response:
- `200 OK`

```json
{
  "status": "ignored",
  "reason": "duplicate_delivery",
  "delivery_id": "jenkins-unique-delivery-id"
}
```

Error responses:
- `401` invalid/missing signature
- `403` repo outside `PH_ALLOWED_REPOS`
- `422` invalid payload schema
- `429` replay window violation (timestamp skew / replay nonce)

## Payload Schema (v1)

```json
{
  "schema_version": "1.0",
  "provider": "jenkins",
  "delivery_id": "jenkins:job/path#1234",
  "sent_at": "2026-02-21T10:10:10Z",
  "repository": "canepro/rocketchat-k8s",
  "branch": "main",
  "commit_sha": "40hexsha",
  "job": {
    "name": "security-validation-rocketchat-k8s",
    "url": "https://jenkins.example/job/security-validation-rocketchat-k8s/23/",
    "build_number": 23,
    "result": "FAILURE",
    "duration_ms": 187000
  },
  "failure": {
    "stage": "Trivy Scan",
    "step": "run-trivy",
    "command": "trivy image ...",
    "summary": "Critical vulnerability threshold exceeded",
    "log_excerpt": "bounded failure excerpt text (max 20k chars)"
  },
  "artifacts": [
    {
      "name": "trivy-results.json",
      "url": "https://jenkins.example/job/.../artifact/trivy-results.json"
    }
  ],
  "metadata": {
    "jenkins_instance": "jenkins.canepro.me",
    "triggered_by": "schedule"
  }
}
```

Validation constraints:
- `repository` must pass existing `owner/repo` normalizer.
- `commit_sha` must be 40-hex when present.
- `log_excerpt` max length (recommended: 20k chars).
- `delivery_id` required and unique in replay window.
- Reject payloads above max body size (recommended: 512 KB).

## Signature and Verification Design

Secret:
- `JENKINS_BRIDGE_SHARED_SECRET` (required when bridge enabled)

Canonical string:
- `METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + NONCE + "\n" + SHA256(raw_body)`

Signature:
- `X-PH-Bridge-Signature = "sha256=" + hex(HMAC_SHA256(secret, canonical_string))`

Verification steps:
1. Bridge enabled flag must be true.
2. Required headers present and provider is `jenkins`.
3. Timestamp within skew window (`JENKINS_BRIDGE_MAX_SKEW_SECONDS`, default 300).
4. Nonce not seen before in replay store window.
5. Signature compare in constant-time.
6. Repo allowlist check (`PH_ALLOWED_REPOS`) before activity creation.

## Replay Protection and Idempotency

Replay store key:
- `provider + ":" + nonce`

Replay TTL:
- `JENKINS_BRIDGE_REPLAY_TTL_SECONDS` (default 86400)

Behavior:
1. First valid request stores nonce key and processes payload.
2. Same nonce in window returns `200 ignored duplicate_delivery`.
3. Distinct nonce but same `delivery_id` also idempotent-ignore.

Storage:
- Use existing durable backend store (Cosmos when configured, in-memory fallback locally).

## Activity Model and Source Attribution

On successful ingest, create activity with:
- `source_selection_path = "jenkins_bridge"`
- provider metadata:
  - `jenkins_job_url`
  - `jenkins_build_number`
  - `delivery_id`
  - `ingested_at`

Failure context mapping:
- `failing_job` <- Jenkins job name
- `failing_step` <- `failure.stage` or `failure.step`
- `failing_command` <- `failure.command`
- `signal` <- `failure.summary` or mapped classifier hint

Remediation policy default:
- issue-first (`AUTO_CREATE_PR=false`) for initial bridge rollout canary.

## Config Additions (Proposed)

- `JENKINS_BRIDGE_ENABLED=false`
- `JENKINS_BRIDGE_SHARED_SECRET=`
- `JENKINS_BRIDGE_MAX_SKEW_SECONDS=300`
- `JENKINS_BRIDGE_REPLAY_TTL_SECONDS=86400`
- `JENKINS_BRIDGE_MAX_BODY_BYTES=524288`

Optional:
- `JENKINS_BRIDGE_ALLOWLIST` (if separate from `PH_ALLOWED_REPOS` is needed later)

## Observability and Audit

Record per-ingest:
- request id
- repository
- delivery id
- signature verification outcome
- replay outcome
- activity id (if created)

Expose counters:
- `jenkins_bridge_ingest_total{status=accepted|ignored|rejected}`
- `jenkins_bridge_replay_block_total`
- `jenkins_bridge_signature_fail_total`

## Test Plan

Unit tests:
1. Canonical string generation deterministic.
2. Valid signature accepted.
3. Tampered body signature rejected.
4. Timestamp outside skew rejected.
5. Nonce replay rejected/ignored.
6. Payload schema validation failures return `422`.
7. Repo allowlist enforcement returns `403`.

Integration/API tests:
1. `POST /webhook/jenkins` creates activity and returns `202`.
2. Duplicate nonce returns ignored duplicate.
3. Valid payload maps into failure context fields correctly.
4. Activity shows `source_selection_path=jenkins_bridge`.

Security tests:
1. Constant-time signature comparison path exercised.
2. Missing secret when enabled fails closed.
3. Oversized payload rejected before deep parsing.

Regression tests:
1. Existing GitHub webhook path unaffected.
2. Existing auth modes (`api_key`, `entra`, `hybrid`) unaffected for `/api/*`.

## Rollout Plan (Design)

Phase 1 (canary):
- enable bridge for one Jenkins-primary repo
- keep `HEAL_MODE=safe`, `AUTO_CREATE_PR=false`

Phase 2:
- expand to selected repos after stable ingest and no replay/signature issues

Phase 3:
- evaluate native Jenkins adapter scope (`BL-035`)

## Open Questions

1. Should we require both HMAC signature and source IP allowlist in production?
2. Should bridge payload include full logs, or only bounded excerpts + artifact URLs?
3. Do we need per-repo bridge secrets now, or global secret with key-id rotation is sufficient?
4. Should `delivery_id` source be Jenkins build URL, queue ID, or caller-provided UUID?
