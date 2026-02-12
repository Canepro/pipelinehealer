#!/usr/bin/env bash
set -euo pipefail

# Prevent accidental "source ./script.sh" from impacting the caller shell.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/deploy/redeploy_azure_containerapps.sh" >&2
  return 1 2>/dev/null || exit 1
fi

usage() {
  cat <<'EOF'
Redeploy PipelineHealer backend/frontend to Azure Container Apps.

Safe for interactive terminals because it runs as a script (not pasted inline).

Usage:
  scripts/deploy/redeploy_azure_containerapps.sh [options]

Options:
  --resource-group <name>   Azure resource group (default: rg-canepro-ph-dev-eus)
  --acr-name <name>         Azure Container Registry name (default: caneprophacr01)
  --backend-app <name>      Backend Container App (default: ca-canepro-ph-backend)
  --frontend-app <name>     Frontend Container App (default: ca-canepro-ph-frontend)
  --engine <podman|docker>  Force container engine (default: auto-detect)
  --env-file <path>         Backend env file (default: <repo>/backend/.env)
  --image-tag <tag>         Image tag (default: current git short SHA)
  --api-key <value>         Override API_AUTH_KEY (otherwise read from env file)
  --admin-key <value>       Override ADMIN_API_KEY (otherwise read from env file)
  --env-only                Update env vars only; do not build/push or change image
  --no-verify               Skip post-deploy health/settings curl checks
  -h, --help                Show this help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

AZ_RESOURCE_GROUP="rg-canepro-ph-dev-eus"
ACR_NAME="caneprophacr01"
BACKEND_APP="ca-canepro-ph-backend"
FRONTEND_APP="ca-canepro-ph-frontend"
ENV_FILE="$REPO_ROOT/backend/.env"
IMAGE_TAG="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
CONTAINER_ENGINE="auto"
COMPOSE_ENV_FILE=""

API_AUTH_KEY=""
ADMIN_API_KEY=""
MODE="full"
DO_VERIFY="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group)
      AZ_RESOURCE_GROUP="$2"
      shift 2
      ;;
    --acr-name)
      ACR_NAME="$2"
      shift 2
      ;;
    --backend-app)
      BACKEND_APP="$2"
      shift 2
      ;;
    --frontend-app)
      FRONTEND_APP="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --engine)
      CONTAINER_ENGINE="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --api-key)
      API_AUTH_KEY="$2"
      shift 2
      ;;
    --admin-key)
      ADMIN_API_KEY="$2"
      shift 2
      ;;
    --env-only)
      MODE="env_only"
      shift
      ;;
    --no-verify)
      DO_VERIFY="0"
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

if [[ "$ENV_FILE" != /* ]]; then
  ENV_FILE="$REPO_ROOT/$ENV_FILE"
fi

for cmd in az curl tr grep cut; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

if [[ "$MODE" != "env_only" ]]; then
  for cmd in git; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "Missing required command for full deploy: $cmd" >&2
      exit 1
    fi
  done
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

read_env_key() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r\n' || true
}

if [[ -z "${API_AUTH_KEY:-}" ]]; then
  API_AUTH_KEY="$(read_env_key "API_AUTH_KEY")"
fi
if [[ -z "${ADMIN_API_KEY:-}" ]]; then
  ADMIN_API_KEY="$(read_env_key "ADMIN_API_KEY")"
fi

if [[ -z "${API_AUTH_KEY:-}" || -z "${ADMIN_API_KEY:-}" ]]; then
  echo "Missing API_AUTH_KEY and/or ADMIN_API_KEY." >&2
  echo "Set them in $ENV_FILE or pass --api-key and --admin-key." >&2
  exit 1
fi

if [[ "$API_AUTH_KEY" == *"replace_me"* || "$ADMIN_API_KEY" == *"replace_me"* ]]; then
  echo "API_AUTH_KEY/ADMIN_API_KEY are placeholder values. Use real keys before deploy." >&2
  exit 1
fi

BACKEND_FQDN="$(
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n'
)"
BACKEND_URL="https://$BACKEND_FQDN"

detect_engine() {
  if [[ "$CONTAINER_ENGINE" == "podman" || "$CONTAINER_ENGINE" == "docker" ]]; then
    echo "$CONTAINER_ENGINE"
    return 0
  fi

  if command -v podman >/dev/null 2>&1; then
    if podman info >/dev/null 2>&1; then
      echo "podman"
      return 0
    fi
    # Try recovering Podman Desktop / podman machine automatically.
    if podman machine start >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
      echo "podman"
      return 0
    fi
  fi

  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "docker"
    return 0
  fi

  return 1
}

echo "Resource group : $AZ_RESOURCE_GROUP"
echo "Backend app    : $BACKEND_APP"
echo "Frontend app   : $FRONTEND_APP"
echo "Mode           : $MODE"

if [[ "$MODE" == "full" ]]; then
  if ! CONTAINER_ENGINE="$(detect_engine)"; then
    echo "No working container engine found for full deploy." >&2
    echo "Try one of the following, then rerun:" >&2
    echo "  podman machine start" >&2
    echo "  # or start Docker Desktop" >&2
    echo "Or run env-only mode (no image build):" >&2
    echo "  bash scripts/deploy/redeploy_azure_containerapps.sh --env-only" >&2
    exit 1
  fi
  echo "Container engine: $CONTAINER_ENGINE"

  ACR_LOGIN="$(az acr show -n "$ACR_NAME" --query loginServer -o tsv | tr -d '\r\n')"
  ACR_TOKEN="$(az acr login -n "$ACR_NAME" --expose-token --query accessToken -o tsv | tr -d '\r\n')"
  "$CONTAINER_ENGINE" login "$ACR_LOGIN" -u 00000000-0000-0000-0000-000000000000 -p "$ACR_TOKEN"

  COMPOSE_ENV_FILE="$ENV_FILE"
  if [[ "$CONTAINER_ENGINE" == "podman" ]] && command -v wslpath >/dev/null 2>&1; then
    # podman compose may invoke docker-compose.exe on Windows; it needs a Windows path.
    if [[ "$ENV_FILE" == /mnt/* ]]; then
      COMPOSE_ENV_FILE="$(wslpath -w "$ENV_FILE")"
    fi
  fi
  echo "Compose env file: $COMPOSE_ENV_FILE"

  (
    cd "$REPO_ROOT"
    "$CONTAINER_ENGINE" compose --env-file "$COMPOSE_ENV_FILE" build backend frontend
    "$CONTAINER_ENGINE" tag pipelinehealer-backend:latest  "$ACR_LOGIN/pipelinehealer-backend:$IMAGE_TAG"
    "$CONTAINER_ENGINE" tag pipelinehealer-frontend:latest "$ACR_LOGIN/pipelinehealer-frontend:$IMAGE_TAG"
    "$CONTAINER_ENGINE" push "$ACR_LOGIN/pipelinehealer-backend:$IMAGE_TAG"
    "$CONTAINER_ENGINE" push "$ACR_LOGIN/pipelinehealer-frontend:$IMAGE_TAG"
  )

  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --image "$ACR_LOGIN/pipelinehealer-backend:$IMAGE_TAG" \
    --set-env-vars API_AUTH_KEY="$API_AUTH_KEY" ADMIN_API_KEY="$ADMIN_API_KEY" >/dev/null

  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --image "$ACR_LOGIN/pipelinehealer-frontend:$IMAGE_TAG" \
    --set-env-vars BACKEND_UPSTREAM="$BACKEND_URL" API_AUTH_KEY="$API_AUTH_KEY" >/dev/null
else
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --set-env-vars API_AUTH_KEY="$API_AUTH_KEY" ADMIN_API_KEY="$ADMIN_API_KEY" >/dev/null

  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --set-env-vars BACKEND_UPSTREAM="$BACKEND_URL" API_AUTH_KEY="$API_AUTH_KEY" >/dev/null
fi

FRONTEND_FQDN="$(
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n'
)"

echo "Backend URL : https://$BACKEND_FQDN"
echo "Frontend URL: https://$FRONTEND_FQDN"

if [[ "$DO_VERIFY" == "1" ]]; then
  curl -fsS "https://$BACKEND_FQDN/health" >/dev/null
  curl -fsS \
    -H "X-API-Key: $API_AUTH_KEY" \
    -H "X-Admin-Key: $ADMIN_API_KEY" \
    "https://$BACKEND_FQDN/api/settings" >/dev/null
  echo "Verification passed: backend health + admin settings endpoint."
fi

echo "Done."
