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
  local admin_key
  admin_key="$(grep '^ADMIN_API_KEY=' "$REPO_ROOT/backend/.env" | cut -d= -f2- | tr -d '\r\n' || true)"
  if [[ -z "${admin_key:-}" ]]; then
    echo "ADMIN_API_KEY missing in backend/.env" >&2
    exit 1
  fi
  local backend_fqdn
  backend_fqdn="$(az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$BACKEND_APP" --query properties.configuration.ingress.fqdn -o tsv | tr -d '\r\n')"
  curl -fsS -H "X-Admin-Key: $admin_key" "https://$backend_fqdn/api/settings"
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
