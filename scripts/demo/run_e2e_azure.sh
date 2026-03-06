#!/usr/bin/env bash
# shellcheck disable=SC2102  # config[url] etc. are gh-cli syntax, not shell ranges
set -euo pipefail

usage() {
  cat <<'EOF'
Run Azure E2E demo verification for PipelineHealer.

This script:
1) Resolves Azure backend URL
2) Switches webhook routing to Azure (disables smee hook, enables Azure hook)
3) Resets demo fixtures for dependency/lint scenarios
4) Triggers failure matrix runs
5) Prints PRs/issues/activities for verification

Usage:
  scripts/demo/run_e2e_azure.sh [options]

Options:
  --repo <owner/repo>         Demo repo (default: Canepro/pipelinehealer-demo)
  --resource-group <name>     Azure resource group (default: rg-canepro-ph-dev-eus)
  --backend-app <name>        Azure backend Container App (default: ca-canepro-ph-backend)
  --demo-repo-dir <path>      Local checkout of demo repo (default: ./demo-repo)
  --wait-seconds <n>          Max seconds to wait for activity terminal status (default: 180)
  --ci-signal-wait-seconds <n> Extra seconds to wait for CI doctor signal (default: 180)
  --skip-backfill             Do not trigger on-demand external diagnostics backfill
  --strict                    Exit non-zero when verification criteria are not met
  --triggers <csv>            Failure types CSV (default: dependency,lint,test,build_config,timeout)
  --skip-webhook-sync         Do not alter GitHub webhooks
  --skip-reset                Do not reset demo fixtures
  --skip-trigger              Do not dispatch workflow runs
  -h, --help                  Show this help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DEMO_REPO="Canepro/pipelinehealer-demo"
AZ_RESOURCE_GROUP="rg-canepro-ph-dev-eus"
BACKEND_APP="ca-canepro-ph-backend"
DEMO_REPO_DIR="$REPO_ROOT/demo-repo"
WAIT_SECONDS="180"
CI_SIGNAL_WAIT_SECONDS="180"
TRIGGERS_CSV="dependency,lint,test,build_config,timeout"
DO_WEBHOOK_SYNC="1"
DO_RESET="1"
DO_TRIGGER="1"
DO_BACKFILL="1"
STRICT_MODE="0"
DISPATCHED_RUN_IDS=()
DISPATCH_MARK_UTC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      DEMO_REPO="$2"
      shift 2
      ;;
    --resource-group)
      AZ_RESOURCE_GROUP="$2"
      shift 2
      ;;
    --backend-app)
      BACKEND_APP="$2"
      shift 2
      ;;
    --demo-repo-dir)
      DEMO_REPO_DIR="$2"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="$2"
      shift 2
      ;;
    --ci-signal-wait-seconds)
      CI_SIGNAL_WAIT_SECONDS="$2"
      shift 2
      ;;
    --strict)
      STRICT_MODE="1"
      shift
      ;;
    --skip-backfill)
      DO_BACKFILL="0"
      shift
      ;;
    --triggers)
      TRIGGERS_CSV="$2"
      shift 2
      ;;
    --skip-webhook-sync)
      DO_WEBHOOK_SYNC="0"
      shift
      ;;
    --skip-reset)
      DO_RESET="0"
      shift
      ;;
    --skip-trigger)
      DO_TRIGGER="0"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

for cmd in gh az curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

BACKEND_FQDN="$(
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n'
)"
BACKEND_URL="https://$BACKEND_FQDN"

ENV_FILE="$REPO_ROOT/backend/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing backend env file: $ENV_FILE" >&2
  exit 1
fi

WEBHOOK_SECRET="$(grep '^GITHUB_WEBHOOK_SECRET=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n' || true)"
API_AUTH_KEY="$(grep '^API_AUTH_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n' || true)"
MAX_REMEDIATION_ATTEMPTS="$(grep '^MAX_REMEDIATION_ATTEMPTS=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n' || true)"
MAX_REMEDIATION_ATTEMPTS="${MAX_REMEDIATION_ATTEMPTS:-3}"

if ! [[ "$WAIT_SECONDS" =~ ^[0-9]+$ ]] || ! [[ "$CI_SIGNAL_WAIT_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "--wait-seconds and --ci-signal-wait-seconds must be non-negative integers." >&2
  exit 2
fi

IFS=',' read -r -a trigger_types_raw <<< "$TRIGGERS_CSV"
trigger_types=()
for trigger in "${trigger_types_raw[@]}"; do
  cleaned="$(echo "$trigger" | tr -d '[:space:]')"
  if [[ -n "$cleaned" ]]; then
    trigger_types+=("$cleaned")
  fi
done

if [[ "${#trigger_types[@]}" -eq 0 ]]; then
  echo "No valid trigger types provided via --triggers." >&2
  exit 1
fi

echo "Backend URL: $BACKEND_URL"
echo "Demo repo  : $DEMO_REPO"
echo "Strict mode: $([[ "$STRICT_MODE" == "1" ]] && echo "enabled" || echo "disabled")"

if [[ "$MAX_REMEDIATION_ATTEMPTS" =~ ^[0-9]+$ ]] && (( MAX_REMEDIATION_ATTEMPTS < ${#trigger_types[@]} )); then
  echo "Warning: MAX_REMEDIATION_ATTEMPTS=$MAX_REMEDIATION_ATTEMPTS but this run triggers ${#trigger_types[@]} failure types."
  echo "Some runs may be skipped by safety guard (\"Max remediation attempts reached for this repository\")."
  echo "Recommended: set MAX_REMEDIATION_ATTEMPTS>=${#trigger_types[@]} in backend/.env, then run:"
  echo "  bash scripts/ph.sh deploy:env"
fi

if [[ "$DO_WEBHOOK_SYNC" == "1" ]]; then
  echo "Syncing webhooks (disable smee, enable Azure)..."
  SMEE_HOOK_ID="$(gh api "repos/$DEMO_REPO/hooks" --jq '.[] | select(.config.url | contains("smee.io")) | .id' | head -n1 | tr -d '\r\n' || true)"
  AZURE_HOOK_ID="$(gh api "repos/$DEMO_REPO/hooks" --jq ".[] | select(.config.url | contains(\"$BACKEND_FQDN\")) | .id" | head -n1 | tr -d '\r\n' || true)"

  if [[ -n "${SMEE_HOOK_ID:-}" ]]; then
    gh api -X PATCH "repos/$DEMO_REPO/hooks/$SMEE_HOOK_ID" -F active=false >/dev/null
  fi

  if [[ -z "${AZURE_HOOK_ID:-}" ]]; then
    if [[ -z "$WEBHOOK_SECRET" ]]; then
      echo "GITHUB_WEBHOOK_SECRET is empty in backend/.env; cannot create webhook." >&2
      exit 1
    fi
    gh api -X POST "repos/$DEMO_REPO/hooks" \
      -f name=web \
      -F active=true \
      -f config[url]="$BACKEND_URL/webhook/github" \
      -f config[content_type]=json \
      -f config[secret]="$WEBHOOK_SECRET" \
      -f events[]="workflow_run" >/dev/null
  else
    gh api -X PATCH "repos/$DEMO_REPO/hooks/$AZURE_HOOK_ID" \
      -F active=true \
      -f config[url]="$BACKEND_URL/webhook/github" \
      -f config[content_type]=json \
      -f config[secret]="$WEBHOOK_SECRET" \
      -f events[]="workflow_run" >/dev/null
  fi

  gh api "repos/$DEMO_REPO/hooks" --jq '.[] | {id,active,url:.config.url,events,last_response:.last_response.code}'
fi

if [[ "$DO_RESET" == "1" ]]; then
  echo "Resetting demo fixtures..."
  bash "$SCRIPT_DIR/reset_demo_fixtures.sh" --repo-dir "$DEMO_REPO_DIR"
fi

if [[ "$DO_TRIGGER" == "1" ]]; then
  echo "Dispatching workflow runs..."
  DISPATCH_MARK_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  for failure_type in "${trigger_types[@]}"; do
    gh workflow run CI -R "$DEMO_REPO" -f "failure_type=$failure_type"
  done

  # Capture the just-dispatched workflow IDs so verification can poll for completion.
  mapfile -t DISPATCHED_RUN_IDS < <(
    gh run list -R "$DEMO_REPO" --workflow CI --limit 50 \
      --json databaseId,event,headBranch,createdAt \
      --jq ".[] | select(.event==\"workflow_dispatch\" and .headBranch==\"main\" and .createdAt >= \"$DISPATCH_MARK_UTC\") | .databaseId"
  )
fi

echo "Recent workflow runs:"
gh run list -R "$DEMO_REPO" --workflow CI --limit 10

if [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 ]]; then
  echo "Polling activities for dispatched runs (max ${WAIT_SECONDS}s): ${DISPATCHED_RUN_IDS[*]}"
  elapsed=0
  interval=5
  activities_json="[]"
  activities_payload_file=""
  activities_settled="0"
  while (( elapsed < WAIT_SECONDS )); do
    if [[ -n "$API_AUTH_KEY" ]]; then
      activities_json="$(curl -sS -H "X-API-Key: $API_AUTH_KEY" "$BACKEND_URL/api/activities?limit=100")"
    else
      activities_json="$(curl -sS "$BACKEND_URL/api/activities?limit=100")"
    fi

    activities_payload_file="$(mktemp)"
    printf '%s' "$activities_json" > "$activities_payload_file"
    if python3 - "$activities_payload_file" "${DISPATCHED_RUN_IDS[@]}" <<'PY'
import json
import sys

if len(sys.argv) < 2:
    print("Missing payload file path")
    sys.exit(1)

payload_path = sys.argv[1]
target_ids = {int(x) for x in sys.argv[2:] if x}
with open(payload_path, encoding="utf-8") as fh:
    payload = json.load(fh)
status_by_run = {}
for item in payload:
    rid = item.get("workflow_run_id")
    status = str(item.get("status", "")).lower()
    if isinstance(rid, int) and rid in target_ids and rid not in status_by_run:
        status_by_run[rid] = status

final = {"completed", "failed", "skipped"}
missing = sorted(target_ids - set(status_by_run.keys()))
non_final = sorted([rid for rid, st in status_by_run.items() if st not in final])

if missing or non_final:
    parts = []
    if missing:
        parts.append("missing=" + ",".join(str(x) for x in missing))
    if non_final:
        parts.append("non_final=" + ",".join(f"{rid}:{status_by_run[rid]}" for rid in non_final))
    print("Pending:", " | ".join(parts))
    sys.exit(1)

print("All dispatched runs reached terminal activity states.")
sys.exit(0)
PY
    then
      rm -f "$activities_payload_file"
      activities_settled="1"
      break
    fi
    rm -f "$activities_payload_file"

    sleep "$interval"
    elapsed=$((elapsed + interval))
  done

  if (( elapsed >= WAIT_SECONDS )); then
    echo "Timed out waiting for all activities to settle."
  fi
else
  echo "No dispatched workflow IDs captured; waiting ${WAIT_SECONDS}s before verification..."
  sleep "$WAIT_SECONDS"
fi

if [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 && "$DO_BACKFILL" == "1" ]]; then
  if [[ -n "$API_AUTH_KEY" ]]; then
    echo "Triggering on-demand diagnostics backfill..."
    curl -fsS -X POST \
      -H "X-API-Key: $API_AUTH_KEY" \
      "$BACKEND_URL/api/backfill-diagnostics?max_age_hours=24" >/dev/null \
      || echo "Warning: backfill trigger failed; continuing with current activity snapshot."
  else
    echo "Skipping on-demand backfill: API_AUTH_KEY missing in backend/.env."
  fi
fi

if [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 ]]; then
  if [[ -n "$API_AUTH_KEY" ]]; then
    activities_json="$(curl -sS -H "X-API-Key: $API_AUTH_KEY" "$BACKEND_URL/api/activities?limit=100")"
  else
    activities_json="$(curl -sS "$BACKEND_URL/api/activities?limit=100")"
  fi
fi

echo "Verification summary:"
summary_tmp="$(mktemp)"
printf '%s' "${activities_json:-[]}" > "$summary_tmp"
python3 - "$summary_tmp" "${DISPATCHED_RUN_IDS[@]}" <<'PY'
import json
import sys

payload_path = sys.argv[1]
target_ids = {int(x) for x in sys.argv[2:] if x}
with open(payload_path, encoding="utf-8") as fh:
    payload = json.load(fh)

activities = []
for item in payload:
    rid = item.get("workflow_run_id")
    if isinstance(rid, int) and rid in target_ids:
        activities.append(item)

final = {"completed", "failed", "skipped"}
terminal = 0
ci_available = 0
ci_unavailable = 0
mcp_tool_calls_total = 0
passive_only_signals = 0
for item in activities:
    if str(item.get("status", "")).lower() in final:
        terminal += 1
    mcp = item.get("mcp_model_path") or {}
    invocations = mcp.get("tool_invocations") or {}
    item_tool_calls = 0
    if isinstance(invocations, dict):
        for value in invocations.values():
            if isinstance(value, int):
                item_tool_calls += value
    mcp_tool_calls_total += item_tool_calls
    source_attribution = mcp.get("source_attribution") or {}
    if isinstance(source_attribution, dict) and source_attribution and item_tool_calls == 0:
        passive_only_signals += 1
    for diag in item.get("external_diagnostics") or []:
        source = str(diag.get("source", "")).lower()
        status = str(diag.get("status", "")).lower()
        if source == "ci-doctor":
            if status == "available":
                ci_available += 1
            elif status == "unavailable":
                ci_unavailable += 1

print(f"  dispatched_runs={len(target_ids)}")
print(f"  activities_found={len(activities)}")
print(f"  activities_terminal={terminal}")
print(f"  ci_doctor_available={ci_available}")
print(f"  ci_doctor_unavailable={ci_unavailable}")
print(f"  mcp_tool_calls_total={mcp_tool_calls_total}")
print(f"  passive_only_signal_activities={passive_only_signals}")
if passive_only_signals > 0:
    print("  note=passive_diagnostics_visible_without_direct_mcp_calls")
PY
rm -f "$summary_tmp"

# Best-effort CI doctor signal check for recently dispatched runs.
ci_elapsed=0
ci_interval=10
ci_signal="0"
if [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 ]]; then
  echo "Waiting for CI doctor workflow signal (max ${CI_SIGNAL_WAIT_SECONDS}s)..."
fi
while [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 ]] && (( ci_elapsed <= CI_SIGNAL_WAIT_SECONDS )); do
  ci_status_sample="$(
    gh run list -R "$DEMO_REPO" --limit 80 \
      --json workflowName,event,status,conclusion,createdAt \
      --jq "[.[] | select(.event==\"workflow_run\") | select((.workflowName // \"\") | ascii_downcase | test(\"ci failure doctor|ci-doctor\")) | select((\"$DISPATCH_MARK_UTC\" == \"\") or (.createdAt >= \"$DISPATCH_MARK_UTC\")) | {status, conclusion}] | .[:3]" \
      | tr -d '\r\n'
  )"
  ci_signal_count="$(
    gh run list -R "$DEMO_REPO" --limit 80 \
      --json databaseId,event,workflowName,status,createdAt \
      --jq "[.[] | select(.event==\"workflow_run\") | select((.workflowName // \"\") | ascii_downcase | test(\"ci failure doctor|ci-doctor\")) | select((\"$DISPATCH_MARK_UTC\" == \"\") or (.createdAt >= \"$DISPATCH_MARK_UTC\")) ] | length" \
      | tr -d '\r\n'
  )"
  ci_signal_count="${ci_signal_count:-0}"
  if [[ "$ci_signal_count" =~ ^[0-9]+$ ]] && (( ci_signal_count > 0 )); then
    ci_signal="1"
    echo "CI doctor signal detected (workflow_run diagnostic run observed: ${ci_status_sample:-[]})."
    break
  fi
  if (( ci_elapsed >= CI_SIGNAL_WAIT_SECONDS )); then
    break
  fi
  sleep "$ci_interval"
  ci_elapsed=$((ci_elapsed + ci_interval))
done

if [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 && "$ci_signal" != "1" ]]; then
  echo "Warning: no CI doctor workflow_run signal found within wait window."
fi

echo "Open PRs:"
gh pr list -R "$DEMO_REPO"

echo "Open issues:"
gh issue list -R "$DEMO_REPO" --state open

echo "Recent activities:"
if [[ -n "$API_AUTH_KEY" ]]; then
  curl -sS -H "X-API-Key: $API_AUTH_KEY" "$BACKEND_URL/api/activities?limit=20"
else
  curl -sS "$BACKEND_URL/api/activities?limit=20"
fi
echo

if [[ "$STRICT_MODE" == "1" ]]; then
  strict_failures=()
  if [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 && "${activities_settled:-0}" != "1" ]]; then
    strict_failures+=("activities_not_terminal_within_wait_seconds")
  fi
  if [[ "${#DISPATCHED_RUN_IDS[@]}" -gt 0 && "$ci_signal" != "1" ]]; then
    strict_failures+=("ci_doctor_signal_not_observed")
  fi
  if [[ "${#strict_failures[@]}" -gt 0 ]]; then
    echo "Strict verification failed: ${strict_failures[*]}" >&2
    exit 1
  fi
fi
