#!/usr/bin/env bash
# shellcheck disable=SC2102  # config[url] etc. are gh-cli syntax, not shell ranges
set -euo pipefail

# Prevent accidental sourcing from terminating the caller shell.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/ph.sh <command>" >&2
  # shellcheck disable=SC2317
  return 1 2>/dev/null || exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AZ_RESOURCE_GROUP="${PH_RG:-rg-canepro-ph-dev-eus}"
BACKEND_APP="${PH_BACKEND_APP:-ca-canepro-ph-backend}"
FRONTEND_APP="${PH_FRONTEND_APP:-ca-canepro-ph-frontend}"

# Namespace background deploy state files by resource group to avoid collisions
# between concurrent runs, different users, or multiple repos.
_deploy_state_dir="/tmp/ph-deploy-${AZ_RESOURCE_GROUP}"
mkdir -p "$_deploy_state_dir" 2>/dev/null || true
DEPLOY_LOG="${PH_DEPLOY_LOG:-$_deploy_state_dir/redeploy.log}"
DEPLOY_PID="${PH_DEPLOY_PID:-$_deploy_state_dir/redeploy.pid}"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
PipelineHealer one-command runner.

Usage:
  bash scripts/ph.sh <command> [options]

Commands:
  deploy            Full Azure redeploy (build/push/update/verify)
  deploy:release    Azure redeploy from existing ACR release images (no local build)
  deploy:env        Update runtime env vars only (no image rebuild)
  deploy:bg         Run redeploy in background and write log to /tmp/ph-deploy-<rg>/
  deploy:logs       Follow detached redeploy logs
  deploy:status     Show detached redeploy process status
  urls              Print Azure backend/frontend URLs
  webhook:add       Add/update Azure webhook for one repo and disable stale smee hook
  webhook:disable   Disable Azure webhook for one repo
  rollout:canary    Configure issue-only canary mode for selected repos and attach webhooks
  demo:e2e          Run scripted Azure E2E demo flow with CI-signal verification
  demo:proof        Show latest CI runs, PRs, and issues for a repo (default demo repo)
  demo:reset        Reset demo fixture repo for dependency/lint failures
  warm              Set backend/frontend min-replicas to 1
  lowcost           Set backend/frontend min-replicas to 0
  status            Show backend/frontend Container App status
  logs              Show recent backend container logs (filtered, last 300 lines)
  logs:raw          Show raw unfiltered backend container logs (last 200 lines)
  logs:grep         Grep backend logs for a pattern: --pattern <regex>
  settings:check    Call backend /api/settings using ADMIN_API_KEY from backend/.env
  settings:audit    Call backend /api/settings/audit using API+ADMIN keys from backend/.env
  settings:persist  Persist selected settings to backend/.env, API-audit when reachable, and redeploy env-only
  settings:persist:verify  Persist settings (skip redeploy by default) and verify audit entry was recorded
  audit:proof       Create two traceable admin audit entries and print latest audit records
  aoai:check        Verify Azure OpenAI connectivity from local backend container
  backfill          Trigger on-demand backfill sweep for external diagnostics (ci-doctor)
  help              Show this help

Examples:
  bash scripts/ph.sh deploy
  bash scripts/ph.sh deploy --secure-secrets
  bash scripts/ph.sh deploy:release --release-version vX.Y.Z
  bash scripts/ph.sh deploy:release --release-version vX.Y.Z --secure-secrets
  bash scripts/ph.sh deploy:env --secure-secrets
  bash scripts/ph.sh deploy:bg
  bash scripts/ph.sh deploy:logs
  bash scripts/ph.sh urls
  bash scripts/ph.sh webhook:add --repo owner/repo
  bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2
  bash scripts/ph.sh demo:e2e --skip-webhook-sync
  bash scripts/ph.sh demo:e2e --triggers dependency,lint,test,build_config,timeout --wait-seconds 180 --ci-signal-wait-seconds 180 --strict
  bash scripts/ph.sh demo:proof --repo owner/repo
  bash scripts/ph.sh settings:persist --from-settings
  bash scripts/ph.sh settings:persist:verify --from-settings
  bash scripts/ph.sh settings:persist --repos-add owner/repo1,owner/repo2 --gh-aw-tools-enabled true --gh-aw-ingestion-mode hybrid
  bash scripts/ph.sh settings:persist --repos-remove owner/legacy-repo
  bash scripts/ph.sh settings:persist --repos-replace owner/repo1,owner/repo2 --skip-redeploy
  bash scripts/ph.sh audit:proof --limit 5
  bash scripts/ph.sh logs
  bash scripts/ph.sh logs:grep --pattern "debug-mode"
  bash scripts/ph.sh warm
  bash scripts/ph.sh lowcost

Local mode:
  Set PH_BACKEND_URL to target a local backend instead of Azure:

  PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh settings:check
  PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh logs --tail 100
  PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh backfill

  Commands that work locally: settings:check, settings:audit, audit:proof,
  aoai:check, backfill, logs, logs:raw, logs:grep, demo:proof, demo:reset, help.

  Azure-only commands (deploy, deploy:release, warm, lowcost, status, urls, webhook:*,
  rollout:canary, demo:e2e) print a clear error when PH_BACKEND_URL is set.
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

# Guard: ensure a --flag has a following value argument.
# Usage: require_arg "--flag" "${2-}"
require_arg() {
  local flag="$1"
  local value="${2-}"
  if [[ -z "$value" || "$value" == --* ]]; then
    echo "Error: $flag requires a value argument." >&2
    exit 2
  fi
}

env_file() {
  # Single source of truth for runtime settings used by helper commands.
  echo "$REPO_ROOT/backend/.env"
}

read_env_key() {
  local key="$1"
  local file
  file="$(env_file)"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  grep -E "^${key}=" "$file" | tail -n1 | cut -d= -f2- | tr -d '\r\n' || true
}

upsert_env_key() {
  local key="$1"
  local value="$2"
  local file
  file="$(env_file)"
  if [[ ! -f "$file" ]]; then
    echo "Missing env file: $file" >&2
    exit 1
  fi

  # Replace in place if key exists; append if missing.
  local tmp
  tmp="$(mktemp)"
  chmod 600 "$tmp"
  awk -v k="$key" -v v="$value" '
    BEGIN { done = 0 }
    $0 ~ ("^" k "=") { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
  chmod 600 "$file"
}

# ---------------------------------------------------------------------------
# Local vs Azure mode
# ---------------------------------------------------------------------------
# Set PH_BACKEND_URL to target a local backend (e.g. http://127.0.0.1:8000).
# When set, API-calling commands (settings:check, settings:audit, audit:proof,
# backfill, logs, logs:raw, logs:grep) work against the local instance.
# Azure-only commands (deploy, warm, lowcost, status, webhook:*, urls) will
# print a clear message and exit.

is_local_mode() {
  [[ -n "${PH_BACKEND_URL:-}" ]]
}

_validate_http_url() {
  # Accept only fully-qualified http(s) base URLs without path/query fragments.
  [[ "$1" =~ ^https?://[^/[:space:]]+$ ]]
}

require_azure() {
  if is_local_mode; then
    echo "Error: '$1' requires an Azure deployment. It does not apply in local mode (PH_BACKEND_URL is set)." >&2
    echo "See docs/LOCAL_DEMO_RUNBOOK.md for local equivalents." >&2
    exit 1
  fi
}

resolve_backend_url() {
  if is_local_mode; then
    # Strip trailing slash for consistency
    local local_url
    local_url="${PH_BACKEND_URL%/}"
    if ! _validate_http_url "$local_url"; then
      echo "Invalid PH_BACKEND_URL: '$local_url' (expected http(s)://host[:port])" >&2
      return 1
    fi
    echo "$local_url"
  else
    need_cmd az
    local fqdn
    fqdn="$(az containerapp show \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$BACKEND_APP" \
      --query properties.configuration.ingress.fqdn \
      -o tsv | tr -d '\r\n')"
    if [[ -z "$fqdn" ]]; then
      echo "Failed to resolve backend FQDN for '$BACKEND_APP' in '$AZ_RESOURCE_GROUP'." >&2
      return 1
    fi
    echo "https://$fqdn"
  fi
}

resolve_backend_fqdn() {
  if is_local_mode; then
    echo "Error: resolve_backend_fqdn called in local mode. Use resolve_backend_url instead." >&2
    exit 1
  fi
  need_cmd az
  local fqdn
  fqdn="$(az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n')"
  if [[ -z "$fqdn" ]]; then
    echo "Failed to resolve backend FQDN for '$BACKEND_APP' in '$AZ_RESOURCE_GROUP'." >&2
    return 1
  fi
  echo "$fqdn"
}

resolve_frontend_fqdn() {
  require_azure "urls"
  need_cmd az
  local fqdn
  fqdn="$(az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n')"
  if [[ -z "$fqdn" ]]; then
    echo "Failed to resolve frontend FQDN for '$FRONTEND_APP' in '$AZ_RESOURCE_GROUP'." >&2
    return 1
  fi
  echo "$fqdn"
}

read_auth_keys() {
  local api_key admin_key
  api_key="$(read_env_key "API_AUTH_KEY")"
  admin_key="$(read_env_key "ADMIN_API_KEY")"
  if [[ -z "${api_key:-}" ]]; then
    echo "API_AUTH_KEY missing in backend/.env" >&2
    exit 1
  fi
  if [[ -z "${admin_key:-}" ]]; then
    echo "ADMIN_API_KEY missing in backend/.env" >&2
    exit 1
  fi
  if [[ "$api_key" == *"replace_me"* || "$admin_key" == *"replace_me"* ]]; then
    echo "API_AUTH_KEY/ADMIN_API_KEY are placeholder values in backend/.env. Set real keys first." >&2
    exit 1
  fi
  printf '%s\n%s\n' "$api_key" "$admin_key"
}

# ---------------------------------------------------------------------------
# Webhook management
# ---------------------------------------------------------------------------

sync_repo_webhook() {
  local repo="$1"
  local mode="$2"  # add|disable
  need_cmd gh
  need_cmd az

  if [[ -z "${repo:-}" || "$repo" != */* ]]; then
    echo "Invalid repo value: '$repo' (expected owner/name)" >&2
    exit 2
  fi

  local backend_fqdn backend_url webhook_secret
  backend_fqdn="$(resolve_backend_fqdn)"
  backend_url="https://$backend_fqdn"
  webhook_secret="$(read_env_key "GITHUB_WEBHOOK_SECRET")"

  if [[ "$mode" == "add" && -z "${webhook_secret:-}" ]]; then
    echo "GITHUB_WEBHOOK_SECRET is empty in $(env_file); cannot create/update webhook." >&2
    exit 1
  fi

  # Disable ALL PipelineHealer hooks (matched by /webhook/github path) plus
  # stale smee channels, then activate exactly one canonical Azure hook. This
  # catches hooks pointing to previous Azure FQDNs that a simple hostname
  # match would miss.
  local smee_hook_ids ph_hook_ids ph_hook_id
  smee_hook_ids="$(gh api "repos/$repo/hooks" --jq '.[] | select((.config.url // "") | contains("smee.io")) | .id' || true)"
  ph_hook_ids="$(gh api "repos/$repo/hooks" --jq '.[] | select((.config.url // "") | endswith("/webhook/github")) | .id' || true)"
  ph_hook_id=""

  if [[ "$mode" == "disable" ]]; then
    if [[ -z "${ph_hook_ids:-}" ]]; then
      echo "No PipelineHealer webhook found for $repo."
      return 0
    fi
    while IFS= read -r hook_id; do
      [[ -z "${hook_id:-}" ]] && continue
      gh api -X PATCH "repos/$repo/hooks/$hook_id" -F active=false >/dev/null
      echo "Disabled webhook id=$hook_id for $repo"
    done <<< "$ph_hook_ids"
    return 0
  fi

  # Disable smee hooks to avoid duplicate deliveries when using Azure direct routing.
  if [[ -n "${smee_hook_ids:-}" ]]; then
    while IFS= read -r hook_id; do
      [[ -z "${hook_id:-}" ]] && continue
      gh api -X PATCH "repos/$repo/hooks/$hook_id" -F active=false >/dev/null
      echo "Disabled stale smee webhook id=$hook_id for $repo"
    done <<< "$smee_hook_ids"
  fi

  # Disable stale PipelineHealer hooks pointing to old FQDNs, then re-use or
  # create the one that matches the current backend FQDN.
  if [[ -n "${ph_hook_ids:-}" ]]; then
    while IFS= read -r hook_id; do
      [[ -z "${hook_id:-}" ]] && continue
      local hook_url
      hook_url="$(gh api "repos/$repo/hooks/$hook_id" --jq '.config.url // ""' || true)"
      if [[ "$hook_url" == *"$backend_fqdn"* ]]; then
        ph_hook_id="$hook_id"
      else
        gh api -X PATCH "repos/$repo/hooks/$hook_id" -F active=false >/dev/null
        echo "Disabled stale PipelineHealer webhook id=$hook_id (was $hook_url)"
      fi
    done <<< "$ph_hook_ids"
  fi

  if [[ -z "${ph_hook_id:-}" ]]; then
    gh api -X POST "repos/$repo/hooks" \
      -f name=web \
      -F active=true \
      -f config[url]="$backend_url/webhook/github" \
      -f config[content_type]=json \
      -f config[secret]="$webhook_secret" \
      -f events[]="workflow_run" >/dev/null
    echo "Created Azure webhook for $repo -> $backend_url/webhook/github"
  else
    gh api -X PATCH "repos/$repo/hooks/$ph_hook_id" \
      -F active=true \
      -f config[url]="$backend_url/webhook/github" \
      -f config[content_type]=json \
      -f config[secret]="$webhook_secret" \
      -f events[]="workflow_run" >/dev/null
    echo "Updated Azure webhook id=$ph_hook_id for $repo -> $backend_url/webhook/github"
  fi
}

cmd_webhook_add() {
  local repo=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo)
        require_arg "$1" "${2-}"
        repo="$2"
        shift 2
        ;;
      *)
        echo "Unknown argument for webhook:add: $1" >&2
        exit 2
        ;;
    esac
  done
  if [[ -z "${repo:-}" ]]; then
    echo "Usage: bash scripts/ph.sh webhook:add --repo owner/name" >&2
    exit 2
  fi
  sync_repo_webhook "$repo" "add"
}

cmd_webhook_disable() {
  local repo=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo)
        require_arg "$1" "${2-}"
        repo="$2"
        shift 2
        ;;
      *)
        echo "Unknown argument for webhook:disable: $1" >&2
        exit 2
        ;;
    esac
  done
  if [[ -z "${repo:-}" ]]; then
    echo "Usage: bash scripts/ph.sh webhook:disable --repo owner/name" >&2
    exit 2
  fi
  sync_repo_webhook "$repo" "disable"
}

# ---------------------------------------------------------------------------
# Canary rollout
# ---------------------------------------------------------------------------

cmd_rollout_canary() {
  local repos_csv=""
  local issue_only="1"
  local apply_env="1"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repos)
        require_arg "$1" "${2-}"
        repos_csv="$2"
        shift 2
        ;;
      --allow-prs)
        issue_only="0"
        shift
        ;;
      --skip-env-sync)
        apply_env="0"
        shift
        ;;
      *)
        echo "Unknown argument for rollout:canary: $1" >&2
        exit 2
        ;;
    esac
  done

  if [[ -z "${repos_csv:-}" ]]; then
    echo "Usage: bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2 [--allow-prs] [--skip-env-sync]" >&2
    exit 2
  fi

  local normalized_csv
  normalized_csv="$(echo "$repos_csv" | tr -d '[:space:]')"
  if [[ -z "${normalized_csv:-}" ]]; then
    echo "No valid repos found in --repos input." >&2
    exit 2
  fi

  IFS=',' read -r -a repos <<< "$normalized_csv"
  if [[ "${#repos[@]}" -eq 0 ]]; then
    echo "No valid repos found in --repos input." >&2
    exit 2
  fi

  # Canary defaults: constrain scope and keep remediation conservative.
  upsert_env_key "PH_ALLOWED_REPOS" "$normalized_csv"
  upsert_env_key "HEAL_MODE" "safe"
  if [[ "$issue_only" == "1" ]]; then
    upsert_env_key "AUTO_CREATE_PR" "false"
  fi

  # Push updated env to Azure before wiring hooks so runtime policy is active first.
  if [[ "$apply_env" == "1" ]]; then
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" --env-only
  fi

  local repo
  for repo in "${repos[@]}"; do
    sync_repo_webhook "$repo" "add"
  done

  echo "Canary rollout complete."
  echo "  PH_ALLOWED_REPOS=$normalized_csv"
  echo "  HEAL_MODE=safe"
  if [[ "$issue_only" == "1" ]]; then
    echo "  AUTO_CREATE_PR=false (issue-only observation mode)"
  else
    echo "  AUTO_CREATE_PR unchanged (PR creation allowed)"
  fi
}

# ---------------------------------------------------------------------------
# Scale management
# ---------------------------------------------------------------------------

scale_mode() {
  local min="$1"
  need_cmd az
  az containerapp update -g "$AZ_RESOURCE_GROUP" -n "$BACKEND_APP" --min-replicas "$min" >/dev/null
  az containerapp update -g "$AZ_RESOURCE_GROUP" -n "$FRONTEND_APP" --min-replicas "$min" >/dev/null
  echo "Set min-replicas=$min on $BACKEND_APP and $FRONTEND_APP"
}

# ---------------------------------------------------------------------------
# Settings / audit
# ---------------------------------------------------------------------------

settings_check() {
  need_cmd curl
  if [[ ! -f "$REPO_ROOT/backend/.env" ]]; then
    echo "Missing env file: $REPO_ROOT/backend/.env" >&2
    exit 1
  fi
  fetch_settings_json
  echo
}

fetch_settings_json() {
  need_cmd curl
  local api_key admin_key
  mapfile -t _keys < <(read_auth_keys)
  api_key="${_keys[0]}"
  admin_key="${_keys[1]}"
  local base_url
  base_url="$(resolve_backend_url)"
  curl -fsS \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    "$base_url/api/settings"
}

settings_audit() {
  need_cmd curl
  local limit="20"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --limit)
        require_arg "$1" "${2-}"
        limit="$2"
        shift 2
        ;;
      --limit=*)
        limit="${1#*=}"
        shift
        ;;
      *)
        echo "Unknown argument for settings:audit: $1" >&2
        exit 2
        ;;
    esac
  done
  local api_key admin_key
  mapfile -t _keys < <(read_auth_keys)
  api_key="${_keys[0]}"
  admin_key="${_keys[1]}"
  local base_url
  base_url="$(resolve_backend_url)"
  curl -fsS \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    "$base_url/api/settings/audit?limit=$limit"
  echo
}

audit_proof() {
  need_cmd curl
  need_cmd python3
  local limit="5"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --limit)
        require_arg "$1" "${2-}"
        limit="$2"
        shift 2
        ;;
      --limit=*)
        limit="${1#*=}"
        shift
        ;;
      *)
        echo "Unknown argument for audit:proof: $1" >&2
        exit 2
        ;;
    esac
  done

  local api_key admin_key base_url current_auto next_auto
  mapfile -t _keys < <(read_auth_keys)
  api_key="${_keys[0]}"
  admin_key="${_keys[1]}"
  base_url="$(resolve_backend_url)"

  current_auto="$(curl -fsS \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    "$base_url/api/settings" | python3 -c 'import sys,json; print("true" if json.load(sys.stdin).get("auto_create_pr", False) else "false")')"
  if [[ "$current_auto" == "true" ]]; then
    next_auto="false"
  else
    next_auto="true"
  fi

  local rid_a rid_b
  rid_a="ph-audit-proof-a"
  rid_b="ph-audit-proof-b"

  curl -fsS -X PATCH \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    -H "Content-Type: application/json" \
    -H "X-Request-Id: $rid_a" \
    -d "{\"auto_create_pr\":$next_auto}" \
    "$base_url/api/settings" >/dev/null

  curl -fsS -X PATCH \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    -H "Content-Type: application/json" \
    -H "X-Request-Id: $rid_b" \
    -d "{\"auto_create_pr\":$current_auto}" \
    "$base_url/api/settings" >/dev/null

  echo "Created audit proof entries: $rid_a, $rid_b"
  settings_audit --limit "$limit"
}

# ---------------------------------------------------------------------------
# Demo proof
# ---------------------------------------------------------------------------

cmd_demo_proof() {
  need_cmd gh
  local repo="Canepro/pipelinehealer-demo"
  local limit="10"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo)
        require_arg "$1" "${2-}"
        repo="$2"
        shift 2
        ;;
      --limit)
        require_arg "$1" "${2-}"
        limit="$2"
        shift 2
        ;;
      --limit=*)
        limit="${1#*=}"
        shift
        ;;
      *)
        echo "Unknown argument for demo:proof: $1" >&2
        exit 2
        ;;
    esac
  done
  echo "Recent CI runs:"
  gh run list -R "$repo" --workflow CI --limit "$limit"
  echo
  echo "Open PRs:"
  gh pr list -R "$repo"
  echo
  echo "Open issues:"
  gh issue list -R "$repo" --state open --limit "$limit"
}

# ---------------------------------------------------------------------------
# URLs / status
# ---------------------------------------------------------------------------

show_urls() {
  require_azure "urls"
  local backend_fqdn frontend_fqdn
  backend_fqdn="$(resolve_backend_fqdn)"
  frontend_fqdn="$(resolve_frontend_fqdn)"
  echo "Backend URL : https://$backend_fqdn"
  echo "Frontend URL: https://$frontend_fqdn"
}

show_status() {
  require_azure "status"
  need_cmd az
  az containerapp list \
    -g "$AZ_RESOURCE_GROUP" \
    --query "[?name=='$BACKEND_APP' || name=='$FRONTEND_APP'].{name:name,minReplicas:properties.template.scale.minReplicas,fqdn:properties.configuration.ingress.fqdn,latestReady:properties.latestReadyRevisionName}" \
    -o table
}

# ---------------------------------------------------------------------------
# Background deploy
# ---------------------------------------------------------------------------

deploy_bg() {
  need_cmd nohup
  nohup bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" "$@" >"$DEPLOY_LOG" 2>&1 &
  local pid="$!"
  echo "$pid" > "$DEPLOY_PID"
  sleep 1
  if ! ps -p "$pid" >/dev/null 2>&1; then
    echo "Background deploy failed to start. Recent log output:" >&2
    if [[ -f "$DEPLOY_LOG" ]]; then
      tail -n 40 "$DEPLOY_LOG" >&2 || true
    fi
    exit 1
  fi
  echo "Started redeploy in background."
  echo "PID: $pid"
  echo "Log: $DEPLOY_LOG"
}

deploy_status() {
  if [[ ! -f "$DEPLOY_PID" ]]; then
    echo "No deploy pid file found: $DEPLOY_PID"
    return 0
  fi
  local pid
  pid="$(cat "$DEPLOY_PID")"
  if ps -p "$pid" >/dev/null 2>&1; then
    echo "Deploy is running (PID $pid)."
  else
    echo "Deploy is not running (last PID $pid)."
  fi
  if [[ -f "$DEPLOY_LOG" ]]; then
    echo
    echo "Last deploy log lines:"
    tail -n 20 "$DEPLOY_LOG"
  fi
}

# ---------------------------------------------------------------------------
# Log inspection (grep -tolerant: empty output is not an error)
# ---------------------------------------------------------------------------

_detect_compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v podman >/dev/null 2>&1; then
    echo "podman compose"
  else
    echo ""
  fi
}

cmd_logs() {
  local tail_count="300"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tail)
        require_arg "$1" "${2-}"
        tail_count="$2"
        shift 2
        ;;
      --tail=*) tail_count="${1#*=}"; shift ;;
      *) echo "Unknown argument for logs: $1" >&2; exit 2 ;;
    esac
  done
  if is_local_mode; then
    local compose_cmd
    compose_cmd="$(_detect_compose_cmd)"
    if [[ -z "$compose_cmd" ]]; then
      echo "No docker/podman compose found. View logs from the terminal running uvicorn instead." >&2
      exit 1
    fi
    $compose_cmd --env-file "$REPO_ROOT/backend/.env" logs --tail "$tail_count" backend 2>/dev/null \
      | grep -v "azure.cosmos" \
      | grep -v "x-ms-" \
      || true
  else
    need_cmd az
    az containerapp logs show \
      -n "$BACKEND_APP" \
      -g "$AZ_RESOURCE_GROUP" \
      --tail "$tail_count" \
      --type console 2>/dev/null \
      | grep -v "azure.cosmos" \
      | grep -v "x-ms-" \
      | grep -v "headers:" \
      | grep -v "'Content" \
      | grep -v "'Cache" \
      | grep -v "'Accept" \
      | grep -v "'authorization" \
      | grep -v "'Server'" \
      | grep -v "'Date'" \
      | grep -v "'lsn'" \
      | grep -v "body is sent" \
      | grep -v "method:" \
      | grep -v "Connecting to" \
      | grep -v "Successfully Connected" \
      || true
  fi
}

cmd_logs_raw() {
  local tail_count="200"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tail)
        require_arg "$1" "${2-}"
        tail_count="$2"
        shift 2
        ;;
      --tail=*) tail_count="${1#*=}"; shift ;;
      *) echo "Unknown argument for logs:raw: $1" >&2; exit 2 ;;
    esac
  done
  if is_local_mode; then
    local compose_cmd
    compose_cmd="$(_detect_compose_cmd)"
    if [[ -z "$compose_cmd" ]]; then
      echo "No docker/podman compose found. View logs from the terminal running uvicorn instead." >&2
      exit 1
    fi
    $compose_cmd --env-file "$REPO_ROOT/backend/.env" logs --tail "$tail_count" backend 2>/dev/null || true
  else
    need_cmd az
    az containerapp logs show \
      -n "$BACKEND_APP" \
      -g "$AZ_RESOURCE_GROUP" \
      --tail "$tail_count" \
      --type console 2>/dev/null \
      || true
  fi
}

cmd_logs_grep() {
  local pattern="" tail_count="500"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pattern)
        require_arg "$1" "${2-}"
        pattern="$2"
        shift 2
        ;;
      --pattern=*) pattern="${1#*=}"; shift ;;
      --tail)
        require_arg "$1" "${2-}"
        tail_count="$2"
        shift 2
        ;;
      --tail=*) tail_count="${1#*=}"; shift ;;
      *) echo "Unknown argument for logs:grep: $1" >&2; exit 2 ;;
    esac
  done
  if [[ -z "${pattern:-}" ]]; then
    echo "Usage: bash scripts/ph.sh logs:grep --pattern <regex> [--tail N]" >&2
    exit 2
  fi
  if is_local_mode; then
    local compose_cmd
    compose_cmd="$(_detect_compose_cmd)"
    if [[ -z "$compose_cmd" ]]; then
      echo "No docker/podman compose found. View logs from the terminal running uvicorn instead." >&2
      exit 1
    fi
    $compose_cmd --env-file "$REPO_ROOT/backend/.env" logs --tail "$tail_count" backend 2>/dev/null \
      | grep -iE "$pattern" \
      || true
  else
    need_cmd az
    az containerapp logs show \
      -n "$BACKEND_APP" \
      -g "$AZ_RESOURCE_GROUP" \
      --tail "$tail_count" \
      --type console 2>/dev/null \
      | grep -iE "$pattern" \
      || true
  fi
}

# ---------------------------------------------------------------------------
# settings:persist — helpers for parse, validate, persist, apply
# ---------------------------------------------------------------------------

_persist_parse_args() {
  # Populate global locals from CLI arguments.
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repos|--repos-add)
        require_arg "$1" "${2-}"
        if [[ -n "${_sp_repos_add_csv:-}" ]]; then
          _sp_repos_add_csv="${_sp_repos_add_csv},$2"
        else
          _sp_repos_add_csv="$2"
        fi
        shift 2
        ;;
      --repos-remove)
        require_arg "$1" "${2-}"
        if [[ -n "${_sp_repos_remove_csv:-}" ]]; then
          _sp_repos_remove_csv="${_sp_repos_remove_csv},$2"
        else
          _sp_repos_remove_csv="$2"
        fi
        shift 2
        ;;
      --repos-replace)
        require_arg "$1" "${2-}"
        _sp_repos_replace_csv="$2"
        shift 2
        ;;
      --clear-repos)
        _sp_clear_repos="1"
        shift
        ;;
      --from-settings)
        _sp_from_settings="1"
        shift
        ;;
      --heal-mode)
        require_arg "$1" "${2-}"
        _sp_heal_mode="$2"
        shift 2
        ;;
      --auto-create-pr)
        require_arg "$1" "${2-}"
        _sp_auto_create_pr="$2"
        shift 2
        ;;
      --max-remediation-attempts)
        require_arg "$1" "${2-}"
        _sp_max_remediation_attempts="$2"
        shift 2
        ;;
      --pipeline-step-timeout-seconds)
        require_arg "$1" "${2-}"
        _sp_pipeline_step_timeout_seconds="$2"
        shift 2
        ;;
      --external-diagnostics-wait-seconds)
        require_arg "$1" "${2-}"
        _sp_external_diagnostics_wait_seconds="$2"
        shift 2
        ;;
      --external-diagnostics-poll-interval-seconds)
        require_arg "$1" "${2-}"
        _sp_external_diagnostics_poll_interval_seconds="$2"
        shift 2
        ;;
      --gh-aw-tools-enabled)
        require_arg "$1" "${2-}"
        _sp_gh_aw_tools_enabled="$2"
        shift 2
        ;;
      --gh-aw-ingestion-mode)
        require_arg "$1" "${2-}"
        _sp_gh_aw_ingestion_mode="$2"
        shift 2
        ;;
      --gh-aw-known-workflows)
        require_arg "$1" "${2-}"
        _sp_gh_aw_known_workflows="$2"
        shift 2
        ;;
      --mcp-enabled)
        require_arg "$1" "${2-}"
        _sp_mcp_enabled="$2"
        shift 2
        ;;
      --mcp-provider)
        require_arg "$1" "${2-}"
        _sp_mcp_provider="$2"
        shift 2
        ;;
      --mcp-read-only)
        require_arg "$1" "${2-}"
        _sp_mcp_read_only="$2"
        shift 2
        ;;
      --mcp-timeout-seconds)
        require_arg "$1" "${2-}"
        _sp_mcp_timeout_seconds="$2"
        shift 2
        ;;
      --mcp-max-retries)
        require_arg "$1" "${2-}"
        _sp_mcp_max_retries="$2"
        shift 2
        ;;
      --mcp-tool-policies)
        require_arg "$1" "${2-}"
        _sp_mcp_tool_policies="$2"
        shift 2
        ;;
      --mcp-repo-allowlist)
        require_arg "$1" "${2-}"
        _sp_mcp_repo_allowlist="$2"
        shift 2
        ;;
      --clear-mcp-repo-allowlist)
        _sp_clear_mcp_repo_allowlist="1"
        shift
        ;;
      --azure-openai-deployment-name)
        require_arg "$1" "${2-}"
        _sp_azure_openai_deployment_name="$2"
        shift 2
        ;;
      --llm-model-analysis)
        require_arg "$1" "${2-}"
        _sp_llm_model_analysis="$2"
        shift 2
        ;;
      --llm-model-diagnosis)
        require_arg "$1" "${2-}"
        _sp_llm_model_diagnosis="$2"
        shift 2
        ;;
      --llm-model-remediation)
        require_arg "$1" "${2-}"
        _sp_llm_model_remediation="$2"
        shift 2
        ;;
      --skip-redeploy)
        _sp_skip_redeploy="1"
        shift
        ;;
      *)
        echo "Unknown argument for settings:persist: $1" >&2
        exit 2
        ;;
    esac
  done
}

_persist_validate() {
  # Check that the flag combination is valid and normalize values.
  if [[ "$_sp_from_settings" != "1" && "$_sp_clear_repos" != "1" && "$_sp_clear_mcp_repo_allowlist" != "1" && -z "${_sp_repos_add_csv:-}" && -z "${_sp_repos_remove_csv:-}" && -z "${_sp_repos_replace_csv:-}" && -z "${_sp_heal_mode:-}" && -z "${_sp_auto_create_pr:-}" && -z "${_sp_max_remediation_attempts:-}" && -z "${_sp_pipeline_step_timeout_seconds:-}" && -z "${_sp_external_diagnostics_wait_seconds:-}" && -z "${_sp_external_diagnostics_poll_interval_seconds:-}" && -z "${_sp_gh_aw_tools_enabled:-}" && -z "${_sp_gh_aw_ingestion_mode:-}" && -z "${_sp_gh_aw_known_workflows:-}" && -z "${_sp_mcp_enabled:-}" && -z "${_sp_mcp_provider:-}" && -z "${_sp_mcp_read_only:-}" && -z "${_sp_mcp_timeout_seconds:-}" && -z "${_sp_mcp_max_retries:-}" && -z "${_sp_mcp_tool_policies:-}" && -z "${_sp_mcp_repo_allowlist:-}" && -z "${_sp_azure_openai_deployment_name:-}" && -z "${_sp_llm_model_analysis:-}" && -z "${_sp_llm_model_diagnosis:-}" && -z "${_sp_llm_model_remediation:-}" ]]; then
    echo "Usage: bash scripts/ph.sh settings:persist --from-settings [--skip-redeploy]" >&2
    echo "   or: bash scripts/ph.sh settings:persist <flags...> [--skip-redeploy]" >&2
    echo "" >&2
    echo "Direct flags: --repos-add CSV [alias: --repos]  --repos-remove CSV  --repos-replace CSV  --clear-repos  --heal-mode MODE" >&2
    echo "  --auto-create-pr true|false  --max-remediation-attempts N" >&2
    echo "  --pipeline-step-timeout-seconds N  --gh-aw-tools-enabled true|false" >&2
    echo "  --external-diagnostics-wait-seconds N  --external-diagnostics-poll-interval-seconds N" >&2
    echo "  --gh-aw-ingestion-mode disabled|passive|hybrid  --gh-aw-known-workflows CSV" >&2
    echo "  --mcp-enabled true|false  --mcp-provider disabled|github|azure_monitor|custom" >&2
    echo "  --mcp-read-only true|false  --mcp-timeout-seconds N  --mcp-max-retries N" >&2
    echo "  --mcp-tool-policies \"tool=mode,tool2=mode\"  --mcp-repo-allowlist CSV  --clear-mcp-repo-allowlist" >&2
    echo "  --azure-openai-deployment-name NAME" >&2
    echo "  --llm-model-analysis NAME  --llm-model-diagnosis NAME  --llm-model-remediation NAME" >&2
    exit 2
  fi

  if [[ "$_sp_from_settings" == "1" ]]; then
    local has_direct="0"
    [[ "$_sp_clear_repos" == "1" || -n "${_sp_repos_add_csv:-}" || -n "${_sp_repos_remove_csv:-}" || -n "${_sp_repos_replace_csv:-}" || -n "${_sp_gh_aw_tools_enabled:-}" || -n "${_sp_gh_aw_ingestion_mode:-}" || -n "${_sp_gh_aw_known_workflows:-}" || -n "${_sp_external_diagnostics_wait_seconds:-}" || -n "${_sp_external_diagnostics_poll_interval_seconds:-}" || -n "${_sp_mcp_enabled:-}" || -n "${_sp_mcp_provider:-}" || -n "${_sp_mcp_read_only:-}" || -n "${_sp_mcp_timeout_seconds:-}" || -n "${_sp_mcp_max_retries:-}" || -n "${_sp_mcp_tool_policies:-}" || -n "${_sp_mcp_repo_allowlist:-}" || "$_sp_clear_mcp_repo_allowlist" == "1" || -n "${_sp_azure_openai_deployment_name:-}" || -n "${_sp_llm_model_analysis:-}" || -n "${_sp_llm_model_diagnosis:-}" || -n "${_sp_llm_model_remediation:-}" || -n "${_sp_heal_mode:-}" || -n "${_sp_auto_create_pr:-}" || -n "${_sp_max_remediation_attempts:-}" || -n "${_sp_pipeline_step_timeout_seconds:-}" ]] && has_direct="1"
    if [[ "$has_direct" == "1" ]]; then
      echo "Use --from-settings by itself (optionally with --skip-redeploy)." >&2
      exit 2
    fi
  fi

  if [[ "$_sp_clear_repos" == "1" && ( -n "${_sp_repos_add_csv:-}" || -n "${_sp_repos_remove_csv:-}" || -n "${_sp_repos_replace_csv:-}" ) ]]; then
    echo "Use --clear-repos by itself (do not combine with --repos-add/--repos-remove/--repos-replace)." >&2
    exit 2
  fi
  if [[ -n "${_sp_repos_replace_csv:-}" && ( -n "${_sp_repos_add_csv:-}" || -n "${_sp_repos_remove_csv:-}" ) ]]; then
    echo "Use either --repos-replace or --repos-add/--repos-remove, not both." >&2
    exit 2
  fi
  if [[ "$_sp_clear_mcp_repo_allowlist" == "1" && -n "${_sp_mcp_repo_allowlist:-}" ]]; then
    echo "Use either --mcp-repo-allowlist or --clear-mcp-repo-allowlist, not both." >&2
    exit 2
  fi

  # Normalize boolean/enum values.
  if [[ -n "${_sp_gh_aw_tools_enabled:-}" ]]; then
    case "${_sp_gh_aw_tools_enabled,,}" in
      true|false) _sp_gh_aw_tools_enabled="${_sp_gh_aw_tools_enabled,,}" ;;
      *) echo "Invalid --gh-aw-tools-enabled value: $_sp_gh_aw_tools_enabled (expected true|false)" >&2; exit 2 ;;
    esac
  fi

  if [[ -n "${_sp_gh_aw_ingestion_mode:-}" ]]; then
    case "${_sp_gh_aw_ingestion_mode,,}" in
      disabled|passive|hybrid) _sp_gh_aw_ingestion_mode="${_sp_gh_aw_ingestion_mode,,}" ;;
      *) echo "Invalid --gh-aw-ingestion-mode value: $_sp_gh_aw_ingestion_mode (expected disabled|passive|hybrid)" >&2; exit 2 ;;
    esac
  fi

  if [[ -n "${_sp_heal_mode:-}" ]]; then
    case "${_sp_heal_mode,,}" in
      safe|demo|debug) _sp_heal_mode="${_sp_heal_mode,,}" ;;
      *) echo "Invalid --heal-mode value: $_sp_heal_mode (expected safe|demo|debug)" >&2; exit 2 ;;
    esac
  fi

  if [[ -n "${_sp_auto_create_pr:-}" ]]; then
    case "${_sp_auto_create_pr,,}" in
      true|false) _sp_auto_create_pr="${_sp_auto_create_pr,,}" ;;
      *) echo "Invalid --auto-create-pr value: $_sp_auto_create_pr (expected true|false)" >&2; exit 2 ;;
    esac
  fi

  if [[ -n "${_sp_mcp_enabled:-}" ]]; then
    case "${_sp_mcp_enabled,,}" in
      true|false) _sp_mcp_enabled="${_sp_mcp_enabled,,}" ;;
      *) echo "Invalid --mcp-enabled value: $_sp_mcp_enabled (expected true|false)" >&2; exit 2 ;;
    esac
  fi

  if [[ -n "${_sp_mcp_read_only:-}" ]]; then
    case "${_sp_mcp_read_only,,}" in
      true|false) _sp_mcp_read_only="${_sp_mcp_read_only,,}" ;;
      *) echo "Invalid --mcp-read-only value: $_sp_mcp_read_only (expected true|false)" >&2; exit 2 ;;
    esac
  fi

  if [[ -n "${_sp_mcp_provider:-}" ]]; then
    case "${_sp_mcp_provider,,}" in
      disabled|github|azure_monitor|custom) _sp_mcp_provider="${_sp_mcp_provider,,}" ;;
      *) echo "Invalid --mcp-provider value: $_sp_mcp_provider (expected disabled|github|azure_monitor|custom)" >&2; exit 2 ;;
    esac
  fi

  if [[ -n "${_sp_mcp_timeout_seconds:-}" ]]; then
    if ! [[ "${_sp_mcp_timeout_seconds}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      echo "Invalid --mcp-timeout-seconds value: $_sp_mcp_timeout_seconds (expected number > 0)" >&2
      exit 2
    fi
    if [[ "${_sp_mcp_timeout_seconds}" == "0" || "${_sp_mcp_timeout_seconds}" == "0.0" ]]; then
      echo "--mcp-timeout-seconds must be > 0" >&2
      exit 2
    fi
  fi

  if [[ -n "${_sp_mcp_max_retries:-}" && ! "${_sp_mcp_max_retries}" =~ ^[0-9]+$ ]]; then
    echo "Invalid --mcp-max-retries value: $_sp_mcp_max_retries (expected integer >= 0)" >&2
    exit 2
  fi

  if [[ -n "${_sp_external_diagnostics_wait_seconds:-}" ]]; then
    if ! [[ "${_sp_external_diagnostics_wait_seconds}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      echo "Invalid --external-diagnostics-wait-seconds value: $_sp_external_diagnostics_wait_seconds (expected number >= 0)" >&2
      exit 2
    fi
  fi

  if [[ -n "${_sp_external_diagnostics_poll_interval_seconds:-}" ]]; then
    if ! [[ "${_sp_external_diagnostics_poll_interval_seconds}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      echo "Invalid --external-diagnostics-poll-interval-seconds value: $_sp_external_diagnostics_poll_interval_seconds (expected number > 0)" >&2
      exit 2
    fi
    if [[ "${_sp_external_diagnostics_poll_interval_seconds}" == "0" || "${_sp_external_diagnostics_poll_interval_seconds}" == "0.0" ]]; then
      echo "--external-diagnostics-poll-interval-seconds must be > 0" >&2
      exit 2
    fi
  fi
}

_persist_hydrate_from_live() {
  # Fetch live settings from backend and populate all _sp_ vars.
  need_cmd jq
  local settings_json
  settings_json="$(fetch_settings_json)"
  _sp_repos_csv="$(echo "$settings_json" | jq -r '.ph_allowed_repos | join(",")')"
  _sp_gh_aw_tools_enabled="$(echo "$settings_json" | jq -r '.gh_aw_tools_enabled | if . then "true" else "false" end')"
  _sp_gh_aw_ingestion_mode="$(echo "$settings_json" | jq -r '.gh_aw_ingestion_mode')"
  _sp_gh_aw_known_workflows="$(echo "$settings_json" | jq -r '.gh_aw_known_workflows | join(",")')"
  _sp_heal_mode="$(echo "$settings_json" | jq -r '.heal_mode')"
  _sp_auto_create_pr="$(echo "$settings_json" | jq -r '.auto_create_pr | if . then "true" else "false" end')"
  _sp_auto_create_tracking_issue_for_prs="$(echo "$settings_json" | jq -r '.auto_create_tracking_issue_for_prs | if . then "true" else "false" end')"
  _sp_max_remediation_attempts="$(echo "$settings_json" | jq -r '.max_remediation_attempts')"
  _sp_verify_webhook_signature_in_development="$(echo "$settings_json" | jq -r '.verify_webhook_signature_in_development | if . then "true" else "false" end')"
  _sp_pipeline_step_timeout_seconds="$(echo "$settings_json" | jq -r '.pipeline_step_timeout_seconds')"
  _sp_github_api_max_retries="$(echo "$settings_json" | jq -r '.github_api_max_retries')"
  _sp_github_api_retry_base_seconds="$(echo "$settings_json" | jq -r '.github_api_retry_base_seconds')"
  _sp_github_api_retry_max_seconds="$(echo "$settings_json" | jq -r '.github_api_retry_max_seconds')"
  _sp_log_prompt_max_chars="$(echo "$settings_json" | jq -r '.log_prompt_max_chars')"
  _sp_log_prompt_head_chars="$(echo "$settings_json" | jq -r '.log_prompt_head_chars')"
  _sp_log_prompt_tail_chars="$(echo "$settings_json" | jq -r '.log_prompt_tail_chars')"
  _sp_external_diagnostics_wait_seconds="$(echo "$settings_json" | jq -r '.external_diagnostics_wait_seconds')"
  _sp_external_diagnostics_poll_interval_seconds="$(echo "$settings_json" | jq -r '.external_diagnostics_poll_interval_seconds')"
  _sp_mcp_enabled="$(echo "$settings_json" | jq -r '.mcp_enabled | if . then "true" else "false" end')"
  _sp_mcp_provider="$(echo "$settings_json" | jq -r '.mcp_provider')"
  _sp_mcp_read_only="$(echo "$settings_json" | jq -r '.mcp_read_only | if . then "true" else "false" end')"
  _sp_mcp_timeout_seconds="$(echo "$settings_json" | jq -r '.mcp_timeout_seconds')"
  _sp_mcp_max_retries="$(echo "$settings_json" | jq -r '.mcp_max_retries')"
  _sp_mcp_tool_policies="$(
    echo "$settings_json" | jq -r '
      .mcp_tool_policies
      | to_entries
      | sort_by(.key)
      | map("\(.key)=\(.value)")
      | join(",")
    '
  )"
  _sp_mcp_repo_allowlist="$(echo "$settings_json" | jq -r '.mcp_repo_allowlist | join(",")')"
  _sp_azure_openai_deployment_name="$(echo "$settings_json" | jq -r '.azure_openai_deployment_name')"
  _sp_llm_model_analysis="$(echo "$settings_json" | jq -r '.llm_model_analysis // ""')"
  _sp_llm_model_diagnosis="$(echo "$settings_json" | jq -r '.llm_model_diagnosis // ""')"
  _sp_llm_model_remediation="$(echo "$settings_json" | jq -r '.llm_model_remediation // ""')"
}

_persist_extract_live_repos_csv() {
  # Best-effort read of current runtime allowlist from /api/settings.
  local settings_json
  settings_json="$(fetch_settings_json)"
  SETTINGS_JSON="$settings_json" python3 - <<'PY'
import json
import os


def normalize(values):
    normalized = []
    seen = set()
    for raw in values:
        token = str(raw or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


payload = json.loads(os.environ.get("SETTINGS_JSON", "{}"))
repos = payload.get("ph_allowed_repos")
if not isinstance(repos, list):
    raise SystemExit(1)
print(",".join(normalize(repos)))
PY
}

_persist_resolve_repos_csv() {
  # Compose final PH_ALLOWED_REPOS from add/remove/replace/clear semantics.
  _sp_force_repos_patch="0"
  _sp_repo_resolution_note=""

  if [[ "$_sp_from_settings" == "1" ]]; then
    [[ -n "${_sp_repos_csv:-}" ]] && _sp_force_repos_patch="1"
    return 0
  fi

  local has_repo_direct="0"
  [[ "$_sp_clear_repos" == "1" || -n "${_sp_repos_add_csv:-}" || -n "${_sp_repos_remove_csv:-}" || -n "${_sp_repos_replace_csv:-}" ]] && has_repo_direct="1"
  if [[ "$has_repo_direct" != "1" ]]; then
    return 0
  fi

  _sp_force_repos_patch="1"

  local base_csv="" base_source="none"
  if [[ "$_sp_clear_repos" != "1" && -z "${_sp_repos_replace_csv:-}" ]]; then
    if base_csv="$(_persist_extract_live_repos_csv 2>/dev/null)"; then
      base_source="live_api"
    else
      base_csv="$(read_env_key "PH_ALLOWED_REPOS")"
      base_source="backend/.env"
    fi
  fi

  _sp_repos_csv="$(
    SP_REPO_BASE_CSV="$base_csv" \
    SP_REPO_ADD_CSV="${_sp_repos_add_csv:-}" \
    SP_REPO_REMOVE_CSV="${_sp_repos_remove_csv:-}" \
    SP_REPO_REPLACE_CSV="${_sp_repos_replace_csv:-}" \
    SP_REPO_CLEAR="${_sp_clear_repos:-0}" \
    python3 - <<'PY'
import os


def csv_list(raw):
    values = []
    seen = set()
    for item in (raw or "").split(","):
        token = item.strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        values.append(token)
    return values


clear = os.getenv("SP_REPO_CLEAR", "0") == "1"
replace = csv_list(os.getenv("SP_REPO_REPLACE_CSV", ""))

if clear:
    result = []
elif replace:
    result = replace
else:
    base = csv_list(os.getenv("SP_REPO_BASE_CSV", ""))
    add = csv_list(os.getenv("SP_REPO_ADD_CSV", ""))
    remove = set(csv_list(os.getenv("SP_REPO_REMOVE_CSV", "")))
    result = [repo for repo in base if repo not in remove]
    for repo in add:
        if repo in remove:
            continue
        if repo not in result:
            result.append(repo)

print(",".join(result))
PY
  )"

  if [[ "$_sp_clear_repos" == "1" ]]; then
    _sp_repo_resolution_note="PH_ALLOWED_REPOS action: clear"
  elif [[ -n "${_sp_repos_replace_csv:-}" ]]; then
    _sp_repo_resolution_note="PH_ALLOWED_REPOS action: replace (explicit)"
  else
    _sp_repo_resolution_note="PH_ALLOWED_REPOS action: merge (base=${base_source})"
  fi
}

_try_read_auth_keys() {
  local api_key admin_key
  api_key="$(read_env_key "API_AUTH_KEY")"
  admin_key="$(read_env_key "ADMIN_API_KEY")"
  if [[ -z "${api_key:-}" || -z "${admin_key:-}" ]]; then
    return 1
  fi
  if [[ "$api_key" == *"replace_me"* || "$admin_key" == *"replace_me"* ]]; then
    return 1
  fi
  printf '%s\n%s\n' "$api_key" "$admin_key"
}

_persist_build_patch_payload_json() {
  SP_REPOS_CSV="${_sp_repos_csv:-}" \
  SP_CLEAR_REPOS="${_sp_clear_repos:-0}" \
  SP_FORCE_REPOS_PATCH="${_sp_force_repos_patch:-0}" \
  SP_HEAL_MODE="${_sp_heal_mode:-}" \
  SP_AUTO_CREATE_PR="${_sp_auto_create_pr:-}" \
  SP_MAX_REMEDIATION_ATTEMPTS="${_sp_max_remediation_attempts:-}" \
  SP_PIPELINE_STEP_TIMEOUT_SECONDS="${_sp_pipeline_step_timeout_seconds:-}" \
  SP_EXTERNAL_DIAGNOSTICS_WAIT_SECONDS="${_sp_external_diagnostics_wait_seconds:-}" \
  SP_EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS="${_sp_external_diagnostics_poll_interval_seconds:-}" \
  SP_GH_AW_TOOLS_ENABLED="${_sp_gh_aw_tools_enabled:-}" \
  SP_GH_AW_INGESTION_MODE="${_sp_gh_aw_ingestion_mode:-}" \
  SP_GH_AW_KNOWN_WORKFLOWS="${_sp_gh_aw_known_workflows:-}" \
  SP_MCP_ENABLED="${_sp_mcp_enabled:-}" \
  SP_MCP_PROVIDER="${_sp_mcp_provider:-}" \
  SP_MCP_READ_ONLY="${_sp_mcp_read_only:-}" \
  SP_MCP_TIMEOUT_SECONDS="${_sp_mcp_timeout_seconds:-}" \
  SP_MCP_MAX_RETRIES="${_sp_mcp_max_retries:-}" \
  SP_MCP_TOOL_POLICIES="${_sp_mcp_tool_policies:-}" \
  SP_MCP_REPO_ALLOWLIST="${_sp_mcp_repo_allowlist:-}" \
  SP_CLEAR_MCP_REPO_ALLOWLIST="${_sp_clear_mcp_repo_allowlist:-0}" \
  SP_AZURE_OPENAI_DEPLOYMENT_NAME="${_sp_azure_openai_deployment_name:-}" \
  SP_LLM_MODEL_ANALYSIS="${_sp_llm_model_analysis:-}" \
  SP_LLM_MODEL_DIAGNOSIS="${_sp_llm_model_diagnosis:-}" \
  SP_LLM_MODEL_REMEDIATION="${_sp_llm_model_remediation:-}" \
  python3 - <<'PY'
import json
import os


def csv_list(raw: str) -> list[str]:
    values: list[str] = []
    for item in (raw or "").split(","):
        token = item.strip().lower()
        if token:
            values.append(token)
    return values


def parse_bool(raw: str):
    value = (raw or "").strip().lower()
    if value == "":
        return None
    return value == "true"


def parse_int(raw: str):
    value = (raw or "").strip()
    if value == "":
        return None
    return int(value)


def parse_float(raw: str):
    value = (raw or "").strip()
    if value == "":
        return None
    return float(value)


def parse_mcp_tool_policies(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        if "=" not in token:
            continue
        tool, mode = token.split("=", 1)
        tool_key = tool.strip().lower()
        mode_value = mode.strip().lower()
        if tool_key and mode_value:
            parsed[tool_key] = mode_value
    return parsed


payload: dict[str, object] = {}

repos_csv = os.getenv("SP_REPOS_CSV", "")
force_repos_patch = os.getenv("SP_FORCE_REPOS_PATCH", "0") == "1"
if force_repos_patch or os.getenv("SP_CLEAR_REPOS", "0") == "1" or repos_csv.strip():
    payload["ph_allowed_repos"] = [] if os.getenv("SP_CLEAR_REPOS", "0") == "1" else csv_list(repos_csv)

heal_mode = (os.getenv("SP_HEAL_MODE", "") or "").strip().lower()
if heal_mode:
    payload["heal_mode"] = heal_mode

auto_create_pr = parse_bool(os.getenv("SP_AUTO_CREATE_PR", ""))
if auto_create_pr is not None:
    payload["auto_create_pr"] = auto_create_pr

max_remediation_attempts = parse_int(os.getenv("SP_MAX_REMEDIATION_ATTEMPTS", ""))
if max_remediation_attempts is not None:
    payload["max_remediation_attempts"] = max_remediation_attempts

pipeline_step_timeout_seconds = parse_float(os.getenv("SP_PIPELINE_STEP_TIMEOUT_SECONDS", ""))
if pipeline_step_timeout_seconds is not None:
    payload["pipeline_step_timeout_seconds"] = pipeline_step_timeout_seconds

external_diagnostics_wait_seconds = parse_float(os.getenv("SP_EXTERNAL_DIAGNOSTICS_WAIT_SECONDS", ""))
if external_diagnostics_wait_seconds is not None:
    payload["external_diagnostics_wait_seconds"] = external_diagnostics_wait_seconds

external_diagnostics_poll_interval_seconds = parse_float(
    os.getenv("SP_EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS", "")
)
if external_diagnostics_poll_interval_seconds is not None:
    payload["external_diagnostics_poll_interval_seconds"] = external_diagnostics_poll_interval_seconds

gh_aw_tools_enabled = parse_bool(os.getenv("SP_GH_AW_TOOLS_ENABLED", ""))
if gh_aw_tools_enabled is not None:
    payload["gh_aw_tools_enabled"] = gh_aw_tools_enabled

gh_aw_ingestion_mode = (os.getenv("SP_GH_AW_INGESTION_MODE", "") or "").strip().lower()
if gh_aw_ingestion_mode:
    payload["gh_aw_ingestion_mode"] = gh_aw_ingestion_mode

gh_aw_known_workflows = csv_list(os.getenv("SP_GH_AW_KNOWN_WORKFLOWS", ""))
if gh_aw_known_workflows:
    payload["gh_aw_known_workflows"] = gh_aw_known_workflows

mcp_enabled = parse_bool(os.getenv("SP_MCP_ENABLED", ""))
if mcp_enabled is not None:
    payload["mcp_enabled"] = mcp_enabled

mcp_provider = (os.getenv("SP_MCP_PROVIDER", "") or "").strip().lower()
if mcp_provider:
    payload["mcp_provider"] = mcp_provider

mcp_read_only = parse_bool(os.getenv("SP_MCP_READ_ONLY", ""))
if mcp_read_only is not None:
    payload["mcp_read_only"] = mcp_read_only

mcp_timeout_seconds = parse_float(os.getenv("SP_MCP_TIMEOUT_SECONDS", ""))
if mcp_timeout_seconds is not None:
    payload["mcp_timeout_seconds"] = mcp_timeout_seconds

mcp_max_retries = parse_int(os.getenv("SP_MCP_MAX_RETRIES", ""))
if mcp_max_retries is not None:
    payload["mcp_max_retries"] = mcp_max_retries

mcp_tool_policies = parse_mcp_tool_policies(os.getenv("SP_MCP_TOOL_POLICIES", ""))
if mcp_tool_policies:
    payload["mcp_tool_policies"] = mcp_tool_policies

mcp_repo_allowlist_raw = os.getenv("SP_MCP_REPO_ALLOWLIST", "")
if os.getenv("SP_CLEAR_MCP_REPO_ALLOWLIST", "0") == "1" or mcp_repo_allowlist_raw.strip():
    payload["mcp_repo_allowlist"] = (
        [] if os.getenv("SP_CLEAR_MCP_REPO_ALLOWLIST", "0") == "1" else csv_list(mcp_repo_allowlist_raw)
    )

deployment_name = (os.getenv("SP_AZURE_OPENAI_DEPLOYMENT_NAME", "") or "").strip()
if deployment_name:
    payload["azure_openai_deployment_name"] = deployment_name

llm_model_analysis = (os.getenv("SP_LLM_MODEL_ANALYSIS", "") or "").strip()
if llm_model_analysis:
    payload["llm_model_analysis"] = llm_model_analysis

llm_model_diagnosis = (os.getenv("SP_LLM_MODEL_DIAGNOSIS", "") or "").strip()
if llm_model_diagnosis:
    payload["llm_model_diagnosis"] = llm_model_diagnosis

llm_model_remediation = (os.getenv("SP_LLM_MODEL_REMEDIATION", "") or "").strip()
if llm_model_remediation:
    payload["llm_model_remediation"] = llm_model_remediation

print(json.dumps(payload, separators=(",", ":")))
PY
}

_persist_patch_runtime_via_api() {
  need_cmd curl
  need_cmd python3
  local api_key admin_key
  local key_blob
  if ! key_blob="$(_try_read_auth_keys)"; then
    _sp_api_patch_note="Audit/API patch skipped: API_AUTH_KEY or ADMIN_API_KEY missing (or placeholder)."
    return 1
  fi
  api_key="$(printf '%s\n' "$key_blob" | sed -n '1p')"
  admin_key="$(printf '%s\n' "$key_blob" | sed -n '2p')"

  local base_url
  base_url="$(resolve_backend_url 2>/dev/null || true)"
  if [[ -z "$base_url" ]] || ! _validate_http_url "$base_url"; then
    _sp_api_patch_note="Audit/API patch skipped: unable to resolve backend URL (got '${base_url:-<empty>}')."
    return 1
  fi

  local payload_json
  payload_json="$(_persist_build_patch_payload_json)"
  if [[ "$payload_json" == "{}" ]]; then
    _sp_api_patch_note="Audit/API patch not needed: no runtime fields changed."
    return 0
  fi

  local rid
  rid="ph-settings-persist-patch-$(date +%s)-$RANDOM"
  if curl -fsS -X PATCH \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    -H "Content-Type: application/json" \
    -H "X-Request-Id: $rid" \
    -d "$payload_json" \
    "$base_url/api/settings" >/dev/null; then
    _sp_api_patch_request_id="$rid"
    _sp_api_patch_note="Applied runtime settings via API patch (request_id=$rid)."
    return 0
  fi

  _sp_api_patch_note="Audit/API patch failed; continuing with local env persistence only (unaudited for runtime patch)."
  return 1
}

_persist_record_via_api() {
  need_cmd curl
  local api_key admin_key
  local key_blob
  if ! key_blob="$(_try_read_auth_keys)"; then
    _sp_api_persist_note="Audit/API persist skipped: API_AUTH_KEY or ADMIN_API_KEY missing (or placeholder)."
    return 1
  fi
  api_key="$(printf '%s\n' "$key_blob" | sed -n '1p')"
  admin_key="$(printf '%s\n' "$key_blob" | sed -n '2p')"

  local base_url
  base_url="$(resolve_backend_url 2>/dev/null || true)"
  if [[ -z "$base_url" ]] || ! _validate_http_url "$base_url"; then
    _sp_api_persist_note="Audit/API persist skipped: unable to resolve backend URL (got '${base_url:-<empty>}')."
    return 1
  fi

  local rid
  rid="ph-settings-persist-apply-$(date +%s)-$RANDOM"
  if curl -fsS -X POST \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    -H "Content-Type: application/json" \
    -H "X-Request-Id: $rid" \
    -d '{"skip_redeploy":true}' \
    "$base_url/api/settings/persist" >/dev/null; then
    _sp_api_persist_request_id="$rid"
    _sp_api_persist_note="Recorded durable persist via API (request_id=$rid, skip_redeploy=true)."
    return 0
  fi

  _sp_api_persist_note="Audit/API persist call failed; local env persistence still applied."
  return 1
}

_persist_write_env() {
  # Write populated _sp_ vars to backend/.env.
  local normalized_csv="${_sp_repos_csv:-}"
  if [[ "$_sp_from_settings" == "1" || "$_sp_clear_repos" == "1" || -n "$normalized_csv" || "${_sp_force_repos_patch:-0}" == "1" ]]; then
    if [[ "$_sp_clear_repos" != "1" && -n "$normalized_csv" ]]; then
      normalized_csv="$(echo "$normalized_csv" | tr -d '[:space:]')"
    fi
    upsert_env_key "PH_ALLOWED_REPOS" "$normalized_csv"
  fi
  local normalized_mcp_repo_csv="${_sp_mcp_repo_allowlist:-}"
  if [[ "$_sp_from_settings" == "1" || "$_sp_clear_mcp_repo_allowlist" == "1" || -n "$normalized_mcp_repo_csv" ]]; then
    if [[ "$_sp_clear_mcp_repo_allowlist" != "1" && -n "$normalized_mcp_repo_csv" ]]; then
      normalized_mcp_repo_csv="$(echo "$normalized_mcp_repo_csv" | tr -d '[:space:]')"
    fi
    upsert_env_key "MCP_REPO_ALLOWLIST" "$normalized_mcp_repo_csv"
  fi

  # Helper: write key if value is non-empty.
  _write_if_set() {
    if [[ -n "${2:-}" ]]; then
      upsert_env_key "$1" "$2"
    fi
    return 0
  }

  _write_if_set "HEAL_MODE" "${_sp_heal_mode:-}"
  _write_if_set "AUTO_CREATE_PR" "${_sp_auto_create_pr:-}"
  _write_if_set "AUTO_CREATE_TRACKING_ISSUE_FOR_PRS" "${_sp_auto_create_tracking_issue_for_prs:-}"
  _write_if_set "MAX_REMEDIATION_ATTEMPTS" "${_sp_max_remediation_attempts:-}"
  _write_if_set "VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT" "${_sp_verify_webhook_signature_in_development:-}"
  _write_if_set "PIPELINE_STEP_TIMEOUT_SECONDS" "${_sp_pipeline_step_timeout_seconds:-}"
  _write_if_set "GITHUB_API_MAX_RETRIES" "${_sp_github_api_max_retries:-}"
  _write_if_set "GITHUB_API_RETRY_BASE_SECONDS" "${_sp_github_api_retry_base_seconds:-}"
  _write_if_set "GITHUB_API_RETRY_MAX_SECONDS" "${_sp_github_api_retry_max_seconds:-}"
  _write_if_set "LOG_PROMPT_MAX_CHARS" "${_sp_log_prompt_max_chars:-}"
  _write_if_set "LOG_PROMPT_HEAD_CHARS" "${_sp_log_prompt_head_chars:-}"
  _write_if_set "LOG_PROMPT_TAIL_CHARS" "${_sp_log_prompt_tail_chars:-}"
  _write_if_set "EXTERNAL_DIAGNOSTICS_WAIT_SECONDS" "${_sp_external_diagnostics_wait_seconds:-}"
  _write_if_set "EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS" "${_sp_external_diagnostics_poll_interval_seconds:-}"
  _write_if_set "GH_AW_TOOLS_ENABLED" "${_sp_gh_aw_tools_enabled:-}"
  _write_if_set "GH_AW_INGESTION_MODE" "${_sp_gh_aw_ingestion_mode:-}"
  _write_if_set "MCP_ENABLED" "${_sp_mcp_enabled:-}"
  _write_if_set "MCP_PROVIDER" "${_sp_mcp_provider:-}"
  _write_if_set "MCP_READ_ONLY" "${_sp_mcp_read_only:-}"
  _write_if_set "MCP_TIMEOUT_SECONDS" "${_sp_mcp_timeout_seconds:-}"
  _write_if_set "MCP_MAX_RETRIES" "${_sp_mcp_max_retries:-}"
  _write_if_set "MCP_TOOL_POLICIES" "${_sp_mcp_tool_policies:-}"

  local normalized_workflows="${_sp_gh_aw_known_workflows:-}"
  [[ -n "$normalized_workflows" ]] && normalized_workflows="$(echo "$normalized_workflows" | tr -d '[:space:]')"
  _write_if_set "GH_AW_KNOWN_WORKFLOWS" "$normalized_workflows"

  _write_if_set "AZURE_OPENAI_DEPLOYMENT_NAME" "${_sp_azure_openai_deployment_name:-}"
  if [[ "$_sp_from_settings" == "1" ]]; then
    upsert_env_key "LLM_MODEL_ANALYSIS" "${_sp_llm_model_analysis:-}"
    upsert_env_key "LLM_MODEL_DIAGNOSIS" "${_sp_llm_model_diagnosis:-}"
    upsert_env_key "LLM_MODEL_REMEDIATION" "${_sp_llm_model_remediation:-}"
  else
    _write_if_set "LLM_MODEL_ANALYSIS" "${_sp_llm_model_analysis:-}"
    _write_if_set "LLM_MODEL_DIAGNOSIS" "${_sp_llm_model_diagnosis:-}"
    _write_if_set "LLM_MODEL_REMEDIATION" "${_sp_llm_model_remediation:-}"
  fi
}

_persist_print_summary() {
  [[ -n "${_sp_api_patch_note:-}" ]] && echo "$_sp_api_patch_note"
  [[ -n "${_sp_api_persist_note:-}" ]] && echo "$_sp_api_persist_note"
  [[ -n "${_sp_repo_resolution_note:-}" ]] && echo "$_sp_repo_resolution_note"

  if [[ "$_sp_from_settings" == "1" ]]; then
    echo "Persisted effective live mutable settings to backend/.env:"
    echo "  PH_ALLOWED_REPOS=${_sp_repos_csv:-<empty>}"
    echo "  HEAL_MODE=${_sp_heal_mode:-<unchanged>}"
    echo "  AUTO_CREATE_PR=${_sp_auto_create_pr:-<unchanged>}"
    echo "  AUTO_CREATE_TRACKING_ISSUE_FOR_PRS=${_sp_auto_create_tracking_issue_for_prs:-<unchanged>}"
    echo "  MAX_REMEDIATION_ATTEMPTS=${_sp_max_remediation_attempts:-<unchanged>}"
    echo "  VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT=${_sp_verify_webhook_signature_in_development:-<unchanged>}"
    echo "  PIPELINE_STEP_TIMEOUT_SECONDS=${_sp_pipeline_step_timeout_seconds:-<unchanged>}"
    echo "  GITHUB_API_MAX_RETRIES=${_sp_github_api_max_retries:-<unchanged>}"
    echo "  GITHUB_API_RETRY_BASE_SECONDS=${_sp_github_api_retry_base_seconds:-<unchanged>}"
    echo "  GITHUB_API_RETRY_MAX_SECONDS=${_sp_github_api_retry_max_seconds:-<unchanged>}"
    echo "  LOG_PROMPT_MAX_CHARS=${_sp_log_prompt_max_chars:-<unchanged>}"
    echo "  LOG_PROMPT_HEAD_CHARS=${_sp_log_prompt_head_chars:-<unchanged>}"
    echo "  LOG_PROMPT_TAIL_CHARS=${_sp_log_prompt_tail_chars:-<unchanged>}"
    echo "  EXTERNAL_DIAGNOSTICS_WAIT_SECONDS=${_sp_external_diagnostics_wait_seconds:-<unchanged>}"
    echo "  EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS=${_sp_external_diagnostics_poll_interval_seconds:-<unchanged>}"
    echo "  GH_AW_TOOLS_ENABLED=${_sp_gh_aw_tools_enabled:-<unchanged>}"
    echo "  GH_AW_INGESTION_MODE=${_sp_gh_aw_ingestion_mode:-<unchanged>}"
    echo "  GH_AW_KNOWN_WORKFLOWS=${_sp_gh_aw_known_workflows:-<unchanged>}"
    echo "  MCP_ENABLED=${_sp_mcp_enabled:-<unchanged>}"
    echo "  MCP_PROVIDER=${_sp_mcp_provider:-<unchanged>}"
    echo "  MCP_READ_ONLY=${_sp_mcp_read_only:-<unchanged>}"
    echo "  MCP_TIMEOUT_SECONDS=${_sp_mcp_timeout_seconds:-<unchanged>}"
    echo "  MCP_MAX_RETRIES=${_sp_mcp_max_retries:-<unchanged>}"
    echo "  MCP_TOOL_POLICIES=${_sp_mcp_tool_policies:-<unchanged>}"
    echo "  MCP_REPO_ALLOWLIST=${_sp_mcp_repo_allowlist:-<unchanged>}"
    echo "  AZURE_OPENAI_DEPLOYMENT_NAME=${_sp_azure_openai_deployment_name:-<unchanged>}"
    echo "  LLM_MODEL_ANALYSIS=${_sp_llm_model_analysis:-<empty>}"
    echo "  LLM_MODEL_DIAGNOSIS=${_sp_llm_model_diagnosis:-<empty>}"
    echo "  LLM_MODEL_REMEDIATION=${_sp_llm_model_remediation:-<empty>}"
  else
    echo "Persisted settings to backend/.env"
    if [[ "${_sp_force_repos_patch:-0}" == "1" ]]; then
      if [[ -n "${_sp_repos_csv:-}" ]]; then
        echo "  PH_ALLOWED_REPOS=${_sp_repos_csv}"
      else
        echo "  PH_ALLOWED_REPOS=<empty>"
      fi
    fi
    [[ -n "${_sp_heal_mode:-}" ]] && echo "  HEAL_MODE=${_sp_heal_mode}"
    [[ -n "${_sp_auto_create_pr:-}" ]] && echo "  AUTO_CREATE_PR=${_sp_auto_create_pr}"
    [[ -n "${_sp_max_remediation_attempts:-}" ]] && echo "  MAX_REMEDIATION_ATTEMPTS=${_sp_max_remediation_attempts}"
    [[ -n "${_sp_pipeline_step_timeout_seconds:-}" ]] && echo "  PIPELINE_STEP_TIMEOUT_SECONDS=${_sp_pipeline_step_timeout_seconds}"
    [[ -n "${_sp_external_diagnostics_wait_seconds:-}" ]] && echo "  EXTERNAL_DIAGNOSTICS_WAIT_SECONDS=${_sp_external_diagnostics_wait_seconds}"
    [[ -n "${_sp_external_diagnostics_poll_interval_seconds:-}" ]] && echo "  EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS=${_sp_external_diagnostics_poll_interval_seconds}"
    [[ -n "${_sp_gh_aw_tools_enabled:-}" ]] && echo "  GH_AW_TOOLS_ENABLED=${_sp_gh_aw_tools_enabled}"
    [[ -n "${_sp_gh_aw_ingestion_mode:-}" ]] && echo "  GH_AW_INGESTION_MODE=${_sp_gh_aw_ingestion_mode}"
    [[ -n "${_sp_gh_aw_known_workflows:-}" ]] && echo "  GH_AW_KNOWN_WORKFLOWS=${_sp_gh_aw_known_workflows}"
    [[ -n "${_sp_mcp_enabled:-}" ]] && echo "  MCP_ENABLED=${_sp_mcp_enabled}"
    [[ -n "${_sp_mcp_provider:-}" ]] && echo "  MCP_PROVIDER=${_sp_mcp_provider}"
    [[ -n "${_sp_mcp_read_only:-}" ]] && echo "  MCP_READ_ONLY=${_sp_mcp_read_only}"
    [[ -n "${_sp_mcp_timeout_seconds:-}" ]] && echo "  MCP_TIMEOUT_SECONDS=${_sp_mcp_timeout_seconds}"
    [[ -n "${_sp_mcp_max_retries:-}" ]] && echo "  MCP_MAX_RETRIES=${_sp_mcp_max_retries}"
    [[ -n "${_sp_mcp_tool_policies:-}" ]] && echo "  MCP_TOOL_POLICIES=${_sp_mcp_tool_policies}"
    [[ -n "${_sp_mcp_repo_allowlist:-}" ]] && echo "  MCP_REPO_ALLOWLIST=${_sp_mcp_repo_allowlist}"
    [[ -n "${_sp_azure_openai_deployment_name:-}" ]] && echo "  AZURE_OPENAI_DEPLOYMENT_NAME=${_sp_azure_openai_deployment_name}"
    [[ -n "${_sp_llm_model_analysis:-}" ]] && echo "  LLM_MODEL_ANALYSIS=${_sp_llm_model_analysis}"
    [[ -n "${_sp_llm_model_diagnosis:-}" ]] && echo "  LLM_MODEL_DIAGNOSIS=${_sp_llm_model_diagnosis}"
    [[ -n "${_sp_llm_model_remediation:-}" ]] && echo "  LLM_MODEL_REMEDIATION=${_sp_llm_model_remediation}"
  fi

  if [[ "$_sp_skip_redeploy" == "1" ]]; then
    echo "Skipped env-only redeploy (--skip-redeploy)."
  else
    echo "Applied env-only redeploy."
  fi
}

cmd_settings_persist() {
  # State variables (shared across helpers via naming convention).
  _sp_repos_csv=""
  _sp_repos_add_csv=""
  _sp_repos_remove_csv=""
  _sp_repos_replace_csv=""
  _sp_clear_repos="0"
  _sp_force_repos_patch="0"
  _sp_repo_resolution_note=""
  _sp_skip_redeploy="0"
  _sp_from_settings="0"
  _sp_gh_aw_tools_enabled=""
  _sp_gh_aw_ingestion_mode=""
  _sp_gh_aw_known_workflows=""
  _sp_mcp_enabled=""
  _sp_mcp_provider=""
  _sp_mcp_read_only=""
  _sp_mcp_timeout_seconds=""
  _sp_mcp_max_retries=""
  _sp_mcp_tool_policies=""
  _sp_mcp_repo_allowlist=""
  _sp_clear_mcp_repo_allowlist="0"
  _sp_azure_openai_deployment_name=""
  _sp_llm_model_analysis=""
  _sp_llm_model_diagnosis=""
  _sp_llm_model_remediation=""
  _sp_heal_mode=""
  _sp_auto_create_pr=""
  _sp_auto_create_tracking_issue_for_prs=""
  _sp_max_remediation_attempts=""
  _sp_verify_webhook_signature_in_development=""
  _sp_pipeline_step_timeout_seconds=""
  _sp_github_api_max_retries=""
  _sp_github_api_retry_base_seconds=""
  _sp_github_api_retry_max_seconds=""
  _sp_log_prompt_max_chars=""
  _sp_log_prompt_head_chars=""
  _sp_log_prompt_tail_chars=""
  _sp_external_diagnostics_wait_seconds=""
  _sp_external_diagnostics_poll_interval_seconds=""
  _sp_api_patch_note=""
  _sp_api_patch_request_id=""
  _sp_api_persist_note=""
  _sp_api_persist_request_id=""

  _persist_parse_args "$@"
  _persist_validate
  _persist_resolve_repos_csv

  local patch_succeeded="1"
  if [[ "$_sp_from_settings" == "1" ]]; then
    _persist_hydrate_from_live
    _sp_api_patch_note="Audit/API patch not needed in --from-settings mode."
  else
    if ! _persist_patch_runtime_via_api; then
      patch_succeeded="0"
    fi
  fi

  if [[ "$patch_succeeded" == "1" ]]; then
    _persist_record_via_api || true
  else
    _sp_api_persist_note="Skipped API persist call because runtime API patch failed."
  fi

  _persist_write_env

  if [[ "$_sp_skip_redeploy" != "1" ]]; then
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" --env-only
  fi

  _persist_print_summary
}

cmd_settings_persist_verify() {
  local audit_limit="10"
  local has_skip_redeploy="0"
  local persist_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --audit-limit)
        require_arg "$1" "${2-}"
        audit_limit="$2"
        shift 2
        ;;
      --audit-limit=*)
        audit_limit="${1#*=}"
        shift
        ;;
      *)
        [[ "$1" == "--skip-redeploy" ]] && has_skip_redeploy="1"
        persist_args+=("$1")
        shift
        ;;
    esac
  done

  if [[ "$has_skip_redeploy" == "0" ]]; then
    persist_args+=(--skip-redeploy)
    echo "No --skip-redeploy provided; defaulting to --skip-redeploy for safe verification."
  fi

  local persist_output
  if ! persist_output="$(cmd_settings_persist "${persist_args[@]}" 2>&1)"; then
    echo "$persist_output"
    echo "settings:persist failed; cannot verify audit entry." >&2
    return 1
  fi
  echo "$persist_output"

  local expected_request_id
  expected_request_id="$(printf '%s\n' "$persist_output" | sed -n 's/.*request_id=\([^,)]*\).*/\1/p' | tail -n1)"
  if [[ -z "$expected_request_id" ]]; then
    echo "Could not extract request_id from settings:persist output; audit verification failed." >&2
    return 1
  fi

  local audit_json
  if ! audit_json="$(cmd_settings_audit --limit "$audit_limit" 2>/dev/null)"; then
    echo "Failed to read settings audit after persist." >&2
    return 1
  fi

  if EXPECTED_REQUEST_ID="$expected_request_id" AUDIT_JSON="$audit_json" python3 - <<'PY'
import json
import os

expected = os.environ["EXPECTED_REQUEST_ID"]
raw_audit_json = os.environ.get("AUDIT_JSON", "")
try:
    data = json.loads(raw_audit_json)
except Exception:
    print("settings:audit did not return valid JSON", file=os.sys.stderr)
    raise SystemExit(1)

if not isinstance(data, list):
    print("settings:audit response is not a list", file=os.sys.stderr)
    raise SystemExit(1)

for entry in data:
    if not isinstance(entry, dict):
        continue
    if entry.get("request_id") != expected:
        continue
    changed = entry.get("changed_keys") or []
    if "persist_settings" in changed:
        print("Audit verification passed: found persist_settings entry for request_id", expected)
        raise SystemExit(0)

print(f"No matching persist_settings audit entry found for request_id {expected}", file=os.sys.stderr)
raise SystemExit(1)
PY
  then
    return 0
  fi

  echo "settings:persist completed but audit verification failed." >&2
  return 1
}

# ---------------------------------------------------------------------------
# Backfill external diagnostics
# ---------------------------------------------------------------------------

cmd_backfill() {
  need_cmd curl
  local max_age_hours="24"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --max-age-hours)
        require_arg "$1" "${2-}"
        max_age_hours="$2"
        shift 2
        ;;
      --max-age-hours=*) max_age_hours="${1#*=}"; shift ;;
      *) echo "Unknown argument for backfill: $1" >&2; exit 2 ;;
    esac
  done

  local api_key
  mapfile -t _keys < <(read_auth_keys)
  api_key="${_keys[0]}"
  local base_url
  base_url="$(resolve_backend_url)"

  echo "Triggering backfill sweep (max_age_hours=$max_age_hours)..."
  curl -fsS -X POST \
    -H "X-API-Key: $api_key" \
    "$base_url/api/backfill-diagnostics?max_age_hours=$max_age_hours"
  echo
}

# ---------------------------------------------------------------------------
# Azure OpenAI connectivity check (local docker backend container)
# ---------------------------------------------------------------------------

cmd_aoai_check() {
  local compose_cmd
  compose_cmd="$(_detect_compose_cmd)"
  if [[ -z "$compose_cmd" ]]; then
    echo "No docker/podman compose found. Cannot run containerized AOAI check." >&2
    exit 1
  fi

  echo "Checking Azure OpenAI connectivity from backend container..."
  $compose_cmd --env-file "$REPO_ROOT/backend/.env" exec backend python3 - <<'PY'
import os
import sys
from openai import AzureOpenAI

missing = [k for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_API_KEY") if not os.environ.get(k)]
if missing:
    print(f"AOAI connectivity FAILED: missing env vars: {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(2)

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
deployment = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
api_key = os.environ["AZURE_OPENAI_API_KEY"]
api_version = os.environ.get("AZURE_OPENAI_CHAT_API_VERSION", "2024-12-01-preview")

client = AzureOpenAI(
    api_key=api_key,
    api_version=api_version,
    azure_endpoint=endpoint,
)

resp = client.chat.completions.create(
    model=deployment,
    messages=[{"role": "user", "content": "Reply with OK"}],
    max_tokens=8,
)
print("model connectivity OK.")
print((resp.choices[0].message.content or "").strip())
PY
}

# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
  usage
  exit 0
fi

COMMAND="$1"
shift

case "$COMMAND" in
  help|-h|--help)
    usage
    ;;
  deploy)
    require_azure "deploy"
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" "$@"
    ;;
  deploy:release)
    require_azure "deploy:release"
    if [[ "$*" == *"--help"* || "$*" == *"-h"* ]]; then
      bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" --help
      exit 0
    fi
    if [[ $# -eq 0 ]]; then
      echo "Missing required args for deploy:release." >&2
      echo "Usage: bash scripts/ph.sh deploy:release --release-version <vX.Y.Z|X.Y.Z>" >&2
      exit 2
    fi
    if [[ "$*" != *"--release-version"* ]]; then
      echo "deploy:release requires --release-version <vX.Y.Z|X.Y.Z>." >&2
      exit 2
    fi
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" "$@"
    ;;
  deploy:env)
    require_azure "deploy:env"
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" --env-only "$@"
    ;;
  deploy:bg)
    require_azure "deploy:bg"
    deploy_bg "$@"
    ;;
  deploy:logs)
    require_azure "deploy:logs"
    if [[ ! -f "$DEPLOY_LOG" ]]; then
      echo "No log file yet: $DEPLOY_LOG"
      exit 0
    fi
    tail -f "$DEPLOY_LOG"
    ;;
  deploy:status)
    require_azure "deploy:status"
    deploy_status
    ;;
  urls)
    show_urls
    ;;
  demo:e2e)
    require_azure "demo:e2e"
    bash "$SCRIPT_DIR/demo/run_e2e_azure.sh" "$@"
    ;;
  demo:proof)
    cmd_demo_proof "$@"
    ;;
  webhook:add)
    require_azure "webhook:add"
    cmd_webhook_add "$@"
    ;;
  webhook:disable)
    require_azure "webhook:disable"
    cmd_webhook_disable "$@"
    ;;
  rollout:canary)
    require_azure "rollout:canary"
    cmd_rollout_canary "$@"
    ;;
  demo:reset)
    bash "$SCRIPT_DIR/demo/reset_demo_fixtures.sh" "$@"
    ;;
  warm)
    require_azure "warm"
    scale_mode 1
    ;;
  lowcost)
    require_azure "lowcost"
    scale_mode 0
    ;;
  status)
    show_status
    ;;
  settings:check)
    settings_check
    ;;
  settings:audit)
    settings_audit "$@"
    ;;
  settings:persist)
    cmd_settings_persist "$@"
    ;;
  settings:persist:verify)
    cmd_settings_persist_verify "$@"
    ;;
  audit:proof)
    audit_proof "$@"
    ;;
  backfill)
    cmd_backfill "$@"
    ;;
  aoai:check)
    cmd_aoai_check "$@"
    ;;
  logs)
    cmd_logs "$@"
    ;;
  logs:raw)
    cmd_logs_raw "$@"
    ;;
  logs:grep)
    cmd_logs_grep "$@"
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    usage
    exit 2
    ;;
esac
