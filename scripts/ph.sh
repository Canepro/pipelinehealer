#!/usr/bin/env bash
set -euo pipefail

# Prevent accidental sourcing from terminating the caller shell.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/ph.sh <command>" >&2
  return 1 2>/dev/null || exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AZ_RESOURCE_GROUP="${PH_RG:-rg-canepro-ph-dev-eus}"
BACKEND_APP="${PH_BACKEND_APP:-ca-canepro-ph-backend}"
FRONTEND_APP="${PH_FRONTEND_APP:-ca-canepro-ph-frontend}"
DEPLOY_LOG="${PH_DEPLOY_LOG:-/tmp/ph-redeploy.log}"
DEPLOY_PID="${PH_DEPLOY_PID:-/tmp/ph-redeploy.pid}"

usage() {
  cat <<'EOF'
PipelineHealer one-command runner.

Usage:
  bash scripts/ph.sh <command> [options]

Commands:
  deploy            Full Azure redeploy (build/push/update/verify)
  deploy:env        Update runtime env vars only (no image rebuild)
  deploy:bg         Run redeploy in background and write log to /tmp/ph-redeploy.log
  deploy:logs       Follow detached redeploy logs
  deploy:status     Show detached redeploy process status
  webhook:add       Add/update Azure webhook for one repo and disable stale smee hook
  webhook:disable   Disable Azure webhook for one repo
  rollout:canary    Configure issue-only canary mode for selected repos and attach webhooks
  demo:e2e          Run scripted Azure E2E demo flow
  demo:reset        Reset demo fixture repo for dependency/lint failures
  warm              Set backend/frontend min-replicas to 1
  lowcost           Set backend/frontend min-replicas to 0
  status            Show backend/frontend Container App status
  settings:check    Call backend /api/settings using ADMIN_API_KEY from backend/.env
  help              Show this help

Examples:
  bash scripts/ph.sh deploy
  bash scripts/ph.sh deploy:bg
  bash scripts/ph.sh deploy:logs
  bash scripts/ph.sh webhook:add --repo owner/repo
  bash scripts/ph.sh rollout:canary --repos owner/repo1,owner/repo2
  bash scripts/ph.sh demo:e2e --skip-webhook-sync
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
  awk -v k="$key" -v v="$value" '
    BEGIN { done = 0 }
    $0 ~ ("^" k "=") { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

resolve_backend_fqdn() {
  need_cmd az
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n'
}

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

  # We keep exactly one active Azure direct webhook and disable stale smee channels.
  local smee_hook_ids azure_hook_ids azure_hook_id
  smee_hook_ids="$(gh api "repos/$repo/hooks" --jq '.[] | select((.config.url // "") | contains("smee.io")) | .id' || true)"
  azure_hook_ids="$(gh api "repos/$repo/hooks" --jq ".[] | select((.config.url // \"\") | contains(\"$backend_fqdn\")) | .id" || true)"
  azure_hook_id="$(echo "${azure_hook_ids:-}" | head -n1 | tr -d '\r\n')"

  if [[ "$mode" == "disable" ]]; then
    if [[ -z "${azure_hook_ids:-}" ]]; then
      echo "No Azure webhook found for $repo ($backend_fqdn)."
      return 0
    fi
    while IFS= read -r hook_id; do
      [[ -z "${hook_id:-}" ]] && continue
      gh api -X PATCH "repos/$repo/hooks/$hook_id" -F active=false >/dev/null
      echo "Disabled Azure webhook id=$hook_id for $repo"
    done <<< "$azure_hook_ids"
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

  if [[ -z "${azure_hook_id:-}" ]]; then
    gh api -X POST "repos/$repo/hooks" \
      -f name=web \
      -F active=true \
      -f config[url]="$backend_url/webhook/github" \
      -f config[content_type]=json \
      -f config[secret]="$webhook_secret" \
      -f events[]="workflow_run" >/dev/null
    echo "Created Azure webhook for $repo -> $backend_url/webhook/github"
  else
    gh api -X PATCH "repos/$repo/hooks/$azure_hook_id" \
      -F active=true \
      -f config[url]="$backend_url/webhook/github" \
      -f config[content_type]=json \
      -f config[secret]="$webhook_secret" \
      -f events[]="workflow_run" >/dev/null
    echo "Updated Azure webhook id=$azure_hook_id for $repo -> $backend_url/webhook/github"
  fi
}

cmd_webhook_add() {
  local repo=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo)
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

cmd_rollout_canary() {
  local repos_csv=""
  local issue_only="1"
  local apply_env="1"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repos)
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

scale_mode() {
  local min="$1"
  need_cmd az
  az containerapp update -g "$AZ_RESOURCE_GROUP" -n "$BACKEND_APP" --min-replicas "$min" >/dev/null
  az containerapp update -g "$AZ_RESOURCE_GROUP" -n "$FRONTEND_APP" --min-replicas "$min" >/dev/null
  echo "Set min-replicas=$min on $BACKEND_APP and $FRONTEND_APP"
}

settings_check() {
  need_cmd az
  need_cmd curl
  if [[ ! -f "$REPO_ROOT/backend/.env" ]]; then
    echo "Missing env file: $REPO_ROOT/backend/.env" >&2
    exit 1
  fi
  local api_key
  local admin_key
  api_key="$(grep '^API_AUTH_KEY=' "$REPO_ROOT/backend/.env" | tail -n1 | cut -d= -f2- | tr -d '\r\n' || true)"
  admin_key="$(grep '^ADMIN_API_KEY=' "$REPO_ROOT/backend/.env" | tail -n1 | cut -d= -f2- | tr -d '\r\n' || true)"
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
  local backend_fqdn
  backend_fqdn="$(az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$BACKEND_APP" --query properties.configuration.ingress.fqdn -o tsv | tr -d '\r\n')"
  curl -fsS \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    "https://$backend_fqdn/api/settings"
  echo
}

show_status() {
  need_cmd az
  az containerapp list \
    -g "$AZ_RESOURCE_GROUP" \
    --query "[?name=='$BACKEND_APP' || name=='$FRONTEND_APP'].{name:name,minReplicas:properties.template.scale.minReplicas,fqdn:properties.configuration.ingress.fqdn,latestReady:properties.latestReadyRevisionName}" \
    -o table
}

deploy_bg() {
  need_cmd nohup
  nohup bash "$SCRIPT_DIR/deploy/redeploy_azure_containerapps.sh" "$@" >"$DEPLOY_LOG" 2>&1 &
  local pid="$!"
  echo "$pid" > "$DEPLOY_PID"
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
  demo:e2e)
    bash "$SCRIPT_DIR/demo/run_e2e_azure.sh" "$@"
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
  *)
    echo "Unknown command: $COMMAND" >&2
    usage
    exit 2
    ;;
esac
