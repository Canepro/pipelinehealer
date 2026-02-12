#!/usr/bin/env bash
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
  --wait-seconds <n>          Wait after triggers before verification (default: 75)
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
WAIT_SECONDS="75"
TRIGGERS_CSV="dependency,lint,test,build_config,timeout"
DO_WEBHOOK_SYNC="1"
DO_RESET="1"
DO_TRIGGER="1"

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

echo "Backend URL: $BACKEND_URL"
echo "Demo repo  : $DEMO_REPO"

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
  "$SCRIPT_DIR/reset_demo_fixtures.sh" --repo-dir "$DEMO_REPO_DIR"
fi

if [[ "$DO_TRIGGER" == "1" ]]; then
  echo "Dispatching workflow runs..."
  IFS=',' read -r -a trigger_types <<< "$TRIGGERS_CSV"
  for failure_type in "${trigger_types[@]}"; do
    gh workflow run CI -R "$DEMO_REPO" -f "failure_type=$failure_type"
  done
fi

echo "Recent workflow runs:"
gh run list -R "$DEMO_REPO" --workflow CI --limit 10

echo "Waiting ${WAIT_SECONDS}s before verification..."
sleep "$WAIT_SECONDS"

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
