#!/usr/bin/env bash
# shellcheck disable=SC2102  # config[url] etc. are gh-cli syntax, not shell ranges
set -euo pipefail

usage() {
  cat <<'EOF'
Verify PipelineHealer artifact lifecycle on a live Azure deployment.

Phases:
  0) Preflight — settings and repo allow-list
  1) First failure — reset fixtures, dispatch one failure, confirm issue + markers
  2) Dedup — dispatch the same failure again, confirm issue reuse (no duplicate)
  3) Green close — dispatch a green CI run, confirm the review issue auto-closes

Usage:
  scripts/demo/run_lifecycle_e2e.sh [options]

Options:
  --repo <owner/repo>         Demo repo (or DEMO_REPO)
  --resource-group <name>     Azure resource group (or PH_RG)
  --backend-app <name>        Azure backend Container App (or PH_BACKEND_APP)
  --failure-type <name>       workflow_dispatch failure_type (default: lint)
  --wait-seconds <n>          Max seconds per activity wait phase (default: 180)
  --green-wait-seconds <n>    Max seconds to wait for issue auto-close (default: 240)
  --demo-repo-dir <path>      Local checkout of demo repo (default: ./demo-repo)
  --skip-webhook-sync         Do not alter GitHub webhooks
  --skip-reset                Do not reset demo fixtures before phase 1
  --skip-dedup                Skip phase 2 (signature reuse)
  --skip-green-close          Skip phase 3 (success webhook auto-close)
  --strict                    Exit non-zero when verification criteria are not met
  -h, --help                  Show this help

Recommended (Infisical-injected operator lane):
  export DEMO_REPO=Canepro/pipelinehealer-demo
  export PH_RG=rg-canepro-ph-dev-eus
  export PH_BACKEND_APP=ca-canepro-ph-backend
  infisical run --env dev --path /personal/pipelinehealer \
    --projectId <project-id> -- \
    bash scripts/ph.sh demo:lifecycle --repo "$DEMO_REPO" --strict
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DEMO_REPO="${DEMO_REPO:-}"
AZ_RESOURCE_GROUP="${PH_RG:-}"
BACKEND_APP="${PH_BACKEND_APP:-}"
DEMO_REPO_DIR="$REPO_ROOT/demo-repo"
FAILURE_TYPE="lint"
WAIT_SECONDS="180"
GREEN_WAIT_SECONDS="240"
DO_WEBHOOK_SYNC="1"
DO_RESET="1"
DO_DEDUP="1"
DO_GREEN_CLOSE="1"
STRICT_MODE="0"

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
    --failure-type)
      FAILURE_TYPE="$2"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="$2"
      shift 2
      ;;
    --green-wait-seconds)
      GREEN_WAIT_SECONDS="$2"
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
    --skip-dedup)
      DO_DEDUP="0"
      shift
      ;;
    --skip-green-close)
      DO_GREEN_CLOSE="0"
      shift
      ;;
    --strict)
      STRICT_MODE="1"
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

missing_config=()
[[ -n "${DEMO_REPO:-}" ]] || missing_config+=("--repo or DEMO_REPO")
[[ -n "${AZ_RESOURCE_GROUP:-}" ]] || missing_config+=("--resource-group or PH_RG")
[[ -n "${BACKEND_APP:-}" ]] || missing_config+=("--backend-app or PH_BACKEND_APP")
if [[ "${#missing_config[@]}" -gt 0 ]]; then
  echo "Missing Azure demo target configuration:" >&2
  printf '  %s\n' "${missing_config[@]}" >&2
  exit 2
fi

for cmd in gh az curl python3 git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

if ! [[ "$WAIT_SECONDS" =~ ^[0-9]+$ ]] || ! [[ "$GREEN_WAIT_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "--wait-seconds and --green-wait-seconds must be non-negative integers." >&2
  exit 2
fi

resolve_backend_url() {
  if [[ -n "${PH_BACKEND_URL:-}" ]]; then
    echo "${PH_BACKEND_URL%/}"
    return 0
  fi
  local fqdn
  fqdn="$(
    az containerapp show \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$BACKEND_APP" \
      --query properties.configuration.ingress.fqdn \
      -o tsv | tr -d '\r\n'
  )"
  if [[ -z "$fqdn" ]]; then
    echo "Failed to resolve backend FQDN for $BACKEND_APP in $AZ_RESOURCE_GROUP" >&2
    exit 1
  fi
  echo "https://$fqdn"
}

read_env_key() {
  local key="$1"
  if [[ -n "${!key:-}" ]]; then
    printf '%s\n' "${!key}"
    return 0
  fi
  local file="${PH_ENV_FILE:-$REPO_ROOT/backend/.env}"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  grep -E "^${key}=" "$file" | tail -n1 | cut -d= -f2- | tr -d '\r\n' || true
}

BACKEND_URL="$(resolve_backend_url)"
WEBHOOK_SECRET="$(read_env_key GITHUB_WEBHOOK_SECRET)"
API_AUTH_KEY="$(read_env_key API_AUTH_KEY)"
ADMIN_API_KEY="$(read_env_key ADMIN_API_KEY)"
BACKEND_FQDN="${BACKEND_URL#https://}"

STRICT_FAILURES=()
MARK_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
FIRST_DISPATCH_UTC=""
TARGET_ISSUE_NUMBER=""
FIRST_RUN_ID=""
SECOND_RUN_ID=""
GREEN_RUN_ID=""

record_failure() {
  STRICT_FAILURES+=("$1")
  echo "FAIL: $1" >&2
}

pass_check() {
  echo "PASS: $1"
}

echo "Lifecycle E2E verification"
echo "  Backend URL : $BACKEND_URL"
echo "  Demo repo   : $DEMO_REPO"
echo "  Failure type: $FAILURE_TYPE"
echo "  Strict mode : $([[ "$STRICT_MODE" == "1" ]] && echo enabled || echo disabled)"
echo

if [[ "$DO_WEBHOOK_SYNC" == "1" ]]; then
  echo "Phase 0a: sync webhooks (disable smee, enable Azure)..."
  SMEE_HOOK_ID="$(gh api "repos/$DEMO_REPO/hooks" --jq '.[] | select(.config.url | contains("smee.io")) | .id' | head -n1 | tr -d '\r\n' || true)"
  AZURE_HOOK_ID="$(gh api "repos/$DEMO_REPO/hooks" --jq ".[] | select(.config.url | contains(\"$BACKEND_FQDN\")) | .id" | head -n1 | tr -d '\r\n' || true)"

  if [[ -n "${SMEE_HOOK_ID:-}" ]]; then
    gh api -X PATCH "repos/$DEMO_REPO/hooks/$SMEE_HOOK_ID" -F active=false >/dev/null
  fi

  if [[ -z "${AZURE_HOOK_ID:-}" ]]; then
    if [[ -z "$WEBHOOK_SECRET" ]]; then
      record_failure "webhook_secret_missing"
    else
      gh api -X POST "repos/$DEMO_REPO/hooks" \
        -f name=web \
        -F active=true \
        -f config[url]="$BACKEND_URL/webhook/github" \
        -f config[content_type]=json \
        -f config[secret]="$WEBHOOK_SECRET" \
        -f events[]="workflow_run" >/dev/null
      pass_check "created Azure workflow_run webhook"
    fi
  else
    patch_args=(
      -F active=true
      -f "config[url]=$BACKEND_URL/webhook/github"
      -f config[content_type]=json
      -f events[]="workflow_run"
    )
    if [[ -n "$WEBHOOK_SECRET" ]]; then
      patch_args+=(-f "config[secret]=$WEBHOOK_SECRET")
    else
      record_failure "webhook_secret_missing"
    fi
    gh api -X PATCH "repos/$DEMO_REPO/hooks/$AZURE_HOOK_ID" "${patch_args[@]}" >/dev/null
    pass_check "Azure workflow_run webhook active"
  fi
fi

echo "Phase 0b: preflight settings..."
if [[ -z "$API_AUTH_KEY" || -z "$ADMIN_API_KEY" ]]; then
  record_failure "api_or_admin_key_missing"
else
  settings_json="$(curl -fsS "$BACKEND_URL/api/settings" \
    -H "X-API-Key: $API_AUTH_KEY" \
    -H "X-Admin-Key: $ADMIN_API_KEY")"
  if python3 - <<'PY' "$settings_json" "$DEMO_REPO"
import json
import sys

data = json.loads(sys.argv[1])
repo = sys.argv[2].lower()
allowed = {str(r).strip().lower() for r in (data.get("ph_allowed_repos") or [])}
checks = {
    "auto_close_on_workflow_success": True,
    "auto_apply_remediation": True,
    "auto_create_issue": True,
}
failures = []
for key, expected in checks.items():
    actual = data.get(key)
    if actual != expected:
        failures.append(f"{key}={actual!r} (expected {expected!r})")
if repo not in allowed:
    failures.append(f"{repo} not in ph_allowed_repos")
if failures:
    print("Preflight settings FAILED:")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)
print("Preflight settings OK:")
for key in sorted(checks):
    print(f"  {key}={data.get(key)!r}")
PY
  then
    pass_check "settings preflight"
  else
    record_failure "settings_preflight"
  fi
fi

fetch_activities() {
  if [[ -n "$API_AUTH_KEY" ]]; then
    curl -fsS -H "X-API-Key: $API_AUTH_KEY" "$BACKEND_URL/api/activities?limit=100"
  else
    curl -fsS "$BACKEND_URL/api/activities?limit=100"
  fi
}

wait_for_run_activity() {
  local run_id="$1"
  local label="$2"
  local elapsed=0
  local interval=5
  local payload_file activity_json

  while (( elapsed < WAIT_SECONDS )); do
    activity_json="$(fetch_activities)"
    payload_file="$(mktemp)"
    printf '%s' "$activity_json" > "$payload_file"
    if python3 - "$payload_file" "$run_id" <<'PY'
import json
import sys

payload_path = sys.argv[1]
run_id = int(sys.argv[2])
with open(payload_path, encoding="utf-8") as fh:
    payload = json.load(fh)

for item in payload:
    if item.get("workflow_run_id") == run_id:
        status = str(item.get("status", "")).lower()
        print(json.dumps({"status": status, "activity": item}))
        sys.exit(0 if status in {"completed", "failed", "skipped"} else 2)
print(json.dumps({"status": "missing", "activity": None}))
sys.exit(2)
PY
    then
      rm -f "$payload_file"
      return 0
    fi
    rm -f "$payload_file"
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
  record_failure "${label}_activity_timeout"
  return 1
}

capture_run_ids_after_dispatch() {
  local count="$1"
  mapfile -t ids < <(
    gh run list -R "$DEMO_REPO" --workflow CI --limit 30 \
      --json databaseId,event,headBranch,createdAt \
      --jq ".[] | select(.event==\"workflow_dispatch\" and .headBranch==\"main\" and .createdAt >= \"$MARK_UTC\") | .databaseId" \
      | head -n "$count"
  )
  printf '%s\n' "${ids[@]}"
}

dispatch_failure() {
  gh workflow run CI -R "$DEMO_REPO" -f "failure_type=$FAILURE_TYPE"
}

dispatch_green() {
  gh workflow run CI -R "$DEMO_REPO" -f "failure_type=none"
}

issue_body_for_number() {
  local issue_number="$1"
  gh api "repos/$DEMO_REPO/issues/$issue_number" --jq '.body // ""'
}

issue_state_for_number() {
  local issue_number="$1"
  gh api "repos/$DEMO_REPO/issues/$issue_number" --jq '.state // ""'
}

issue_number_from_run_activity() {
  local run_id="$1"
  local payload_file activity_json

  if [[ -z "$API_AUTH_KEY" ]]; then
    return 1
  fi
  activity_json="$(fetch_activities)"
  payload_file="$(mktemp)"
  printf '%s' "$activity_json" > "$payload_file"
  python3 - "$payload_file" "$run_id" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
run_id = int(sys.argv[2])
activity = next((item for item in payload if item.get("workflow_run_id") == run_id), None)
if activity is None:
    sys.exit(1)
result = activity.get("remediation_result") or {}
details = result.get("details") or {}
issue_number = details.get("issue_number")
if isinstance(issue_number, int):
    print(issue_number)
    sys.exit(0)
issue_url = str(result.get("issue_url") or details.get("issue_url") or "")
match = re.search(r"/issues/(\d+)(?:$|[/?#])", issue_url)
if match:
    print(match.group(1))
    sys.exit(0)
sys.exit(1)
PY
  local status=$?
  rm -f "$payload_file"
  return "$status"
}

latest_open_ph_issue_number() {
  local since_utc="$1"
  gh issue list -R "$DEMO_REPO" --state open --label pipelinehealer --limit 30 \
    --json number,createdAt,title \
    --jq "[.[] | select(.createdAt >= \"$since_utc\")] | sort_by(.createdAt) | reverse | .[0].number // empty"
}

open_ph_issue_count_since() {
  local since_utc="$1"
  gh issue list -R "$DEMO_REPO" --state open --label pipelinehealer --limit 100 \
    --json number,createdAt \
    --jq "[.[] | select(.createdAt >= \"$since_utc\")] | length"
}

if [[ "$DO_RESET" == "1" ]]; then
  echo "Phase 1a: reset demo fixtures..."
  if [[ -d "$DEMO_REPO_DIR/.git" ]]; then
    bash "$SCRIPT_DIR/reset_demo_fixtures.sh" --repo-dir "$DEMO_REPO_DIR"
  else
    echo "Local demo repo checkout missing at $DEMO_REPO_DIR; cloning temporary copy..."
    tmp_demo_dir="$(mktemp -d)"
    git clone "https://github.com/$DEMO_REPO.git" "$tmp_demo_dir" >/dev/null
    bash "$SCRIPT_DIR/reset_demo_fixtures.sh" --repo-dir "$tmp_demo_dir"
    rm -rf "$tmp_demo_dir"
  fi
  pass_check "demo fixtures reset"
fi

echo "Phase 1b: dispatch first $FAILURE_TYPE failure..."
FIRST_DISPATCH_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
MARK_UTC="$FIRST_DISPATCH_UTC"
dispatch_failure
sleep 5
mapfile -t FIRST_IDS < <(capture_run_ids_after_dispatch 1)
if [[ "${#FIRST_IDS[@]}" -lt 1 ]]; then
  record_failure "first_dispatch_run_missing"
else
  FIRST_RUN_ID="${FIRST_IDS[0]}"
  echo "  first run id: $FIRST_RUN_ID"
  if wait_for_run_activity "$FIRST_RUN_ID" "first_failure"; then
    pass_check "first failure activity terminal"
  fi
fi

echo "Phase 1c: verify issue markers on first failure..."
if [[ -n "$FIRST_RUN_ID" && -n "$API_AUTH_KEY" ]]; then
  activity_json="$(fetch_activities)"
  analysis_file="$(mktemp)"
  printf '%s' "$activity_json" > "$analysis_file"
  python3 - "$analysis_file" "$FIRST_RUN_ID" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
run_id = int(sys.argv[2])
activity = next((item for item in payload if item.get("workflow_run_id") == run_id), None)
if activity is None:
    print("missing_activity")
    sys.exit(1)
result = activity.get("remediation_result") or {}
details = result.get("details") or {}
issue_url = result.get("issue_url") or details.get("issue_url")
print(json.dumps({
    "issue_url": issue_url,
    "reused_existing_issue": details.get("reused_existing_issue"),
    "action_taken": result.get("action_taken"),
}))
PY
  rm -f "$analysis_file"
fi

TARGET_ISSUE_NUMBER=""
if [[ -n "$FIRST_RUN_ID" ]]; then
  TARGET_ISSUE_NUMBER="$(issue_number_from_run_activity "$FIRST_RUN_ID" || true)"
fi
if [[ -z "$TARGET_ISSUE_NUMBER" ]]; then
  TARGET_ISSUE_NUMBER="$(latest_open_ph_issue_number "$FIRST_DISPATCH_UTC" || true)"
fi
if [[ -z "$TARGET_ISSUE_NUMBER" ]]; then
  record_failure "no_open_ph_issue_after_first_failure"
else
  echo "  tracking issue #$TARGET_ISSUE_NUMBER"
  issue_body="$(issue_body_for_number "$TARGET_ISSUE_NUMBER")"
  if python3 - <<'PY' "$issue_body"
import sys
body = sys.argv[1]
required = [
    "<!-- pipelinehealer:generated-issue:review -->",
    "<!-- pipelinehealer:signature:",
    "<!-- pipelinehealer:workflow-name:",
    "<!-- pipelinehealer:head-branch:",
]
missing = [marker for marker in required if marker not in body]
if missing:
    print("missing_markers:", ",".join(missing))
    sys.exit(1)
print("markers_ok")
PY
  then
    pass_check "issue lifecycle markers present"
  else
    record_failure "issue_markers_missing"
  fi
fi

if [[ "$DO_DEDUP" == "1" ]]; then
  echo "Phase 2: dispatch duplicate $FAILURE_TYPE failure (expect reuse)..."
  MARK_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  open_before="$(open_ph_issue_count_since "$FIRST_DISPATCH_UTC")"
  dispatch_failure
  sleep 5
  mapfile -t SECOND_IDS < <(capture_run_ids_after_dispatch 1)
  if [[ "${#SECOND_IDS[@]}" -lt 1 ]]; then
    record_failure "second_dispatch_run_missing"
  else
    SECOND_RUN_ID="${SECOND_IDS[0]}"
    echo "  second run id: $SECOND_RUN_ID"
    if wait_for_run_activity "$SECOND_RUN_ID" "second_failure"; then
      pass_check "second failure activity terminal"
    fi
    open_after="$(open_ph_issue_count_since "$FIRST_DISPATCH_UTC")"
    if [[ "$open_after" -le "$open_before" ]]; then
      pass_check "no duplicate open PH issue (open count $open_before -> $open_after)"
    else
      record_failure "duplicate_open_ph_issue_created"
    fi

    if [[ -n "$SECOND_RUN_ID" && -n "$API_AUTH_KEY" ]]; then
      activity_json="$(fetch_activities)"
      dedup_file="$(mktemp)"
      printf '%s' "$activity_json" > "$dedup_file"
      if python3 - "$dedup_file" "$SECOND_RUN_ID" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
run_id = int(sys.argv[2])
activity = next((item for item in payload if item.get("workflow_run_id") == run_id), None)
if activity is None:
    sys.exit(1)
details = (activity.get("remediation_result") or {}).get("details") or {}
print(json.dumps(details))
if details.get("reused_existing_issue") is True:
    sys.exit(0)
sys.exit(2)
PY
      then
        pass_check "activity reports reused_existing_issue"
      else
        record_failure "reused_existing_issue_not_reported"
      fi
      rm -f "$dedup_file"
    fi
  fi
fi

if [[ "$DO_GREEN_CLOSE" == "1" && -n "$TARGET_ISSUE_NUMBER" ]]; then
  echo "Phase 3: dispatch green CI run (expect auto-close of issue #$TARGET_ISSUE_NUMBER)..."
  MARK_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  dispatch_green
  sleep 5
  mapfile -t GREEN_IDS < <(capture_run_ids_after_dispatch 1)
  if [[ "${#GREEN_IDS[@]}" -lt 1 ]]; then
    record_failure "green_dispatch_run_missing"
  else
    GREEN_RUN_ID="${GREEN_IDS[0]}"
    echo "  green run id: $GREEN_RUN_ID"
    green_elapsed=0
    green_interval=10
    closed="0"
    while (( green_elapsed < GREEN_WAIT_SECONDS )); do
      state="$(issue_state_for_number "$TARGET_ISSUE_NUMBER")"
      if [[ "$state" == "closed" ]]; then
        closed="1"
        break
      fi
      run_status="$(gh run view "$GREEN_RUN_ID" -R "$DEMO_REPO" --json status,conclusion --jq '.status + ":" + (.conclusion // "")' 2>/dev/null || echo unknown:)"
      echo "  waiting (${green_elapsed}s): issue #$TARGET_ISSUE_NUMBER state=$state green_run=$run_status"
      sleep "$green_interval"
      green_elapsed=$((green_elapsed + green_interval))
    done
    if [[ "$closed" == "1" ]]; then
      pass_check "issue #$TARGET_ISSUE_NUMBER auto-closed after green run"
      comments="$(gh api "repos/$DEMO_REPO/issues/$TARGET_ISSUE_NUMBER/comments" --jq '.[-1].body // ""')"
      if [[ "$comments" == *"Closed automatically because the tracked workflow succeeded."* ]]; then
        pass_check "auto-close audit comment present"
      else
        record_failure "auto_close_audit_comment_missing"
      fi
    else
      record_failure "issue_not_auto_closed_after_green_run"
    fi
  fi
fi

echo
echo "Lifecycle verification summary:"
echo "  first_run_id=${FIRST_RUN_ID:-n/a}"
echo "  second_run_id=${SECOND_RUN_ID:-n/a}"
echo "  green_run_id=${GREEN_RUN_ID:-n/a}"
echo "  tracked_issue=${TARGET_ISSUE_NUMBER:-n/a}"
if [[ "${#STRICT_FAILURES[@]}" -gt 0 ]]; then
  echo "  failures=${STRICT_FAILURES[*]}"
else
  echo "  failures=none"
fi

echo
echo "Open PH issues (post-run):"
gh issue list -R "$DEMO_REPO" --state open --label pipelinehealer --limit 10

if [[ "$STRICT_MODE" == "1" && "${#STRICT_FAILURES[@]}" -gt 0 ]]; then
  exit 1
fi
