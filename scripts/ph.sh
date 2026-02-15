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
  deploy:env        Update runtime env vars only (no image rebuild)
  deploy:bg         Run redeploy in background and write log to /tmp/ph-deploy-<rg>/
  deploy:logs       Follow detached redeploy logs
  deploy:status     Show detached redeploy process status
  urls              Print Azure backend/frontend URLs
  webhook:add       Add/update Azure webhook for one repo and disable stale smee hook
  webhook:disable   Disable Azure webhook for one repo
  rollout:canary    Configure issue-only canary mode for selected repos and attach webhooks
  demo:e2e          Run scripted Azure E2E demo flow
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
  settings:persist  Persist selected settings to backend/.env and redeploy env-only
  audit:proof       Create two traceable admin audit entries and print latest audit records
  help              Show this help

Examples:
  bash scripts/ph.sh deploy
  bash scripts/ph.sh deploy:bg
  bash scripts/ph.sh deploy:logs
  bash scripts/ph.sh urls
  bash scripts/ph.sh webhook:add --repo owner/repo
  bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2
  bash scripts/ph.sh demo:e2e --skip-webhook-sync
  bash scripts/ph.sh demo:proof --repo owner/repo
  bash scripts/ph.sh settings:persist --from-settings
  bash scripts/ph.sh settings:persist --repos owner/repo1,owner/repo2 --gh-aw-tools-enabled true --gh-aw-ingestion-mode passive
  bash scripts/ph.sh audit:proof --limit 5
  bash scripts/ph.sh logs
  bash scripts/ph.sh logs:grep --pattern "debug-mode"
  bash scripts/ph.sh warm
  bash scripts/ph.sh lowcost
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

resolve_backend_fqdn() {
  need_cmd az
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n'
}

resolve_frontend_fqdn() {
  need_cmd az
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n'
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
  need_cmd az
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
  local backend_fqdn
  backend_fqdn="$(resolve_backend_fqdn)"
  curl -fsS \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    "https://$backend_fqdn/api/settings"
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
  local backend_fqdn
  backend_fqdn="$(resolve_backend_fqdn)"
  curl -fsS \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    "https://$backend_fqdn/api/settings/audit?limit=$limit"
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

  local api_key admin_key backend_fqdn base_url current_auto next_auto
  mapfile -t _keys < <(read_auth_keys)
  api_key="${_keys[0]}"
  admin_key="${_keys[1]}"
  backend_fqdn="$(resolve_backend_fqdn)"
  base_url="https://$backend_fqdn"

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
  local backend_fqdn frontend_fqdn
  backend_fqdn="$(resolve_backend_fqdn)"
  frontend_fqdn="$(resolve_frontend_fqdn)"
  echo "Backend URL : https://$backend_fqdn"
  echo "Frontend URL: https://$frontend_fqdn"
}

show_status() {
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

cmd_logs() {
  need_cmd az
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
}

cmd_logs_raw() {
  need_cmd az
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
  az containerapp logs show \
    -n "$BACKEND_APP" \
    -g "$AZ_RESOURCE_GROUP" \
    --tail "$tail_count" \
    --type console 2>/dev/null \
    || true
}

cmd_logs_grep() {
  need_cmd az
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
  az containerapp logs show \
    -n "$BACKEND_APP" \
    -g "$AZ_RESOURCE_GROUP" \
    --tail "$tail_count" \
    --type console 2>/dev/null \
    | grep -iE "$pattern" \
    || true
}

# ---------------------------------------------------------------------------
# settings:persist — helpers for parse, validate, persist, apply
# ---------------------------------------------------------------------------

_persist_parse_args() {
  # Populate global locals from CLI arguments.
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repos)
        require_arg "$1" "${2-}"
        _sp_repos_csv="$2"
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
      --azure-openai-deployment-name)
        require_arg "$1" "${2-}"
        _sp_azure_openai_deployment_name="$2"
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
  if [[ "$_sp_from_settings" != "1" && "$_sp_clear_repos" != "1" && -z "${_sp_repos_csv:-}" && -z "${_sp_heal_mode:-}" && -z "${_sp_auto_create_pr:-}" && -z "${_sp_max_remediation_attempts:-}" && -z "${_sp_pipeline_step_timeout_seconds:-}" && -z "${_sp_gh_aw_tools_enabled:-}" && -z "${_sp_gh_aw_ingestion_mode:-}" && -z "${_sp_gh_aw_known_workflows:-}" && -z "${_sp_azure_openai_deployment_name:-}" ]]; then
    echo "Usage: bash scripts/ph.sh settings:persist --from-settings [--skip-redeploy]" >&2
    echo "   or: bash scripts/ph.sh settings:persist <flags...> [--skip-redeploy]" >&2
    echo "" >&2
    echo "Direct flags: --repos CSV  --clear-repos  --heal-mode MODE" >&2
    echo "  --auto-create-pr true|false  --max-remediation-attempts N" >&2
    echo "  --pipeline-step-timeout-seconds N  --gh-aw-tools-enabled true|false" >&2
    echo "  --gh-aw-ingestion-mode disabled|passive  --gh-aw-known-workflows CSV" >&2
    echo "  --azure-openai-deployment-name NAME" >&2
    exit 2
  fi

  if [[ "$_sp_from_settings" == "1" ]]; then
    local has_direct="0"
    [[ "$_sp_clear_repos" == "1" || -n "${_sp_repos_csv:-}" || -n "${_sp_gh_aw_tools_enabled:-}" || -n "${_sp_gh_aw_ingestion_mode:-}" || -n "${_sp_gh_aw_known_workflows:-}" || -n "${_sp_azure_openai_deployment_name:-}" || -n "${_sp_heal_mode:-}" || -n "${_sp_auto_create_pr:-}" || -n "${_sp_max_remediation_attempts:-}" || -n "${_sp_pipeline_step_timeout_seconds:-}" ]] && has_direct="1"
    if [[ "$has_direct" == "1" ]]; then
      echo "Use --from-settings by itself (optionally with --skip-redeploy)." >&2
      exit 2
    fi
  fi

  if [[ "$_sp_clear_repos" == "1" && -n "${_sp_repos_csv:-}" ]]; then
    echo "Use either --repos or --clear-repos, not both." >&2
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
      disabled|passive) _sp_gh_aw_ingestion_mode="${_sp_gh_aw_ingestion_mode,,}" ;;
      *) echo "Invalid --gh-aw-ingestion-mode value: $_sp_gh_aw_ingestion_mode (expected disabled|passive)" >&2; exit 2 ;;
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
  _sp_azure_openai_deployment_name="$(echo "$settings_json" | jq -r '.azure_openai_deployment_name')"
}

_persist_write_env() {
  # Write populated _sp_ vars to backend/.env.
  local normalized_csv="${_sp_repos_csv:-}"
  if [[ "$_sp_clear_repos" != "1" && -n "$normalized_csv" ]]; then
    normalized_csv="$(echo "$normalized_csv" | tr -d '[:space:]')"
  fi

  upsert_env_key "PH_ALLOWED_REPOS" "$normalized_csv"

  # Helper: write key if value is non-empty.
  _write_if_set() { [[ -n "${2:-}" ]] && upsert_env_key "$1" "$2"; }

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
  _write_if_set "GH_AW_TOOLS_ENABLED" "${_sp_gh_aw_tools_enabled:-}"
  _write_if_set "GH_AW_INGESTION_MODE" "${_sp_gh_aw_ingestion_mode:-}"

  local normalized_workflows="${_sp_gh_aw_known_workflows:-}"
  [[ -n "$normalized_workflows" ]] && normalized_workflows="$(echo "$normalized_workflows" | tr -d '[:space:]')"
  _write_if_set "GH_AW_KNOWN_WORKFLOWS" "$normalized_workflows"

  _write_if_set "AZURE_OPENAI_DEPLOYMENT_NAME" "${_sp_azure_openai_deployment_name:-}"
}

_persist_print_summary() {
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
    echo "  GH_AW_TOOLS_ENABLED=${_sp_gh_aw_tools_enabled:-<unchanged>}"
    echo "  GH_AW_INGESTION_MODE=${_sp_gh_aw_ingestion_mode:-<unchanged>}"
    echo "  GH_AW_KNOWN_WORKFLOWS=${_sp_gh_aw_known_workflows:-<unchanged>}"
    echo "  AZURE_OPENAI_DEPLOYMENT_NAME=${_sp_azure_openai_deployment_name:-<unchanged>}"
  elif [[ "$_sp_clear_repos" == "1" ]]; then
    echo "Persisted PH_ALLOWED_REPOS=<empty> to backend/.env"
  else
    echo "Persisted settings to backend/.env"
    [[ -n "${_sp_repos_csv:-}" ]] && echo "  PH_ALLOWED_REPOS=${_sp_repos_csv}"
    [[ -n "${_sp_heal_mode:-}" ]] && echo "  HEAL_MODE=${_sp_heal_mode}"
    [[ -n "${_sp_auto_create_pr:-}" ]] && echo "  AUTO_CREATE_PR=${_sp_auto_create_pr}"
    [[ -n "${_sp_max_remediation_attempts:-}" ]] && echo "  MAX_REMEDIATION_ATTEMPTS=${_sp_max_remediation_attempts}"
    [[ -n "${_sp_pipeline_step_timeout_seconds:-}" ]] && echo "  PIPELINE_STEP_TIMEOUT_SECONDS=${_sp_pipeline_step_timeout_seconds}"
    [[ -n "${_sp_gh_aw_tools_enabled:-}" ]] && echo "  GH_AW_TOOLS_ENABLED=${_sp_gh_aw_tools_enabled}"
    [[ -n "${_sp_gh_aw_ingestion_mode:-}" ]] && echo "  GH_AW_INGESTION_MODE=${_sp_gh_aw_ingestion_mode}"
    [[ -n "${_sp_gh_aw_known_workflows:-}" ]] && echo "  GH_AW_KNOWN_WORKFLOWS=${_sp_gh_aw_known_workflows}"
    [[ -n "${_sp_azure_openai_deployment_name:-}" ]] && echo "  AZURE_OPENAI_DEPLOYMENT_NAME=${_sp_azure_openai_deployment_name}"
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
  _sp_clear_repos="0"
  _sp_skip_redeploy="0"
  _sp_from_settings="0"
  _sp_gh_aw_tools_enabled=""
  _sp_gh_aw_ingestion_mode=""
  _sp_gh_aw_known_workflows=""
  _sp_azure_openai_deployment_name=""
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

  _persist_parse_args "$@"
  _persist_validate

  if [[ "$_sp_from_settings" == "1" ]]; then
    _persist_hydrate_from_live
  fi

  _persist_write_env

  if [[ "$_sp_skip_redeploy" != "1" ]]; then
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" --env-only
  fi

  _persist_print_summary
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
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" "$@"
    ;;
  deploy:env)
    bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" --env-only "$@"
    ;;
  deploy:bg)
    deploy_bg "$@"
    ;;
  deploy:logs)
    if [[ ! -f "$DEPLOY_LOG" ]]; then
      echo "No log file yet: $DEPLOY_LOG"
      exit 0
    fi
    tail -f "$DEPLOY_LOG"
    ;;
  deploy:status)
    deploy_status
    ;;
  urls)
    show_urls
    ;;
  demo:e2e)
    bash "$SCRIPT_DIR/demo/run_e2e_azure.sh" "$@"
    ;;
  demo:proof)
    cmd_demo_proof "$@"
    ;;
  webhook:add)
    cmd_webhook_add "$@"
    ;;
  webhook:disable)
    cmd_webhook_disable "$@"
    ;;
  rollout:canary)
    cmd_rollout_canary "$@"
    ;;
  demo:reset)
    bash "$SCRIPT_DIR/demo/reset_demo_fixtures.sh" "$@"
    ;;
  warm)
    scale_mode 1
    ;;
  lowcost)
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
  audit:proof)
    audit_proof "$@"
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
