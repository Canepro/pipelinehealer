#!/usr/bin/env bash
set -euo pipefail

# Prevent accidental "source ./script.sh" from impacting the caller shell.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/deploy/redeploy_azure_containerapps.sh" >&2
  # shellcheck disable=SC2317
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
  --release-version <ver>   Deploy existing ACR release images (vX.Y.Z or X.Y.Z) by digest
  --api-key <value>         Override API_AUTH_KEY (otherwise read from env file)
  --admin-key <value>       Override ADMIN_API_KEY (otherwise read from env file)
  --env-only                Update env vars only; do not build/push or change image
  --acr-retain-tags <n>     Keep newest n tags in ACR per repo after full deploy (default: 25, 0 disables)
  --skip-acr-prune          Disable post-deploy ACR pruning
  --skip-local-image-prune  Keep old local ACR tags after full deploy
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
RELEASE_VERSION=""
DO_VERIFY="1"
PRUNE_ACR_IMAGES="1"
ACR_RETAIN_TAGS="25"
PRUNE_LOCAL_IMAGES="1"

BACKEND_RUNTIME_ENV_KEYS=(
  "AUTH_MODE"
  "ENTRA_TENANT_ID"
  "ENTRA_CLIENT_ID"
  "ENTRA_ISSUER"
  "ENTRA_JWKS_URL"
  "ENTRA_ALLOWED_AUDIENCES"
  "ENTRA_ADMIN_ROLES"
  "AZURE_OPENAI_ENDPOINT"
  "AZURE_OPENAI_DEPLOYMENT_NAME"
  "AZURE_OPENAI_API_VERSION"
  "AZURE_OPENAI_API_KEY"
  "HEAL_MODE"
  "MAX_REMEDIATION_ATTEMPTS"
  "AUTO_CREATE_PR"
  "AUTO_CREATE_TRACKING_ISSUE_FOR_PRS"
  "PH_ALLOWED_REPOS"
  "AUDIT_SALT"
  "VERIFY_WEBHOOK_SIGNATURE"
  "VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT"
  "PIPELINE_STEP_TIMEOUT_SECONDS"
  "GITHUB_API_MAX_RETRIES"
  "GITHUB_API_RETRY_BASE_SECONDS"
  "GITHUB_API_RETRY_MAX_SECONDS"
  "LOG_PROMPT_MAX_CHARS"
  "LOG_PROMPT_HEAD_CHARS"
  "LOG_PROMPT_TAIL_CHARS"
  "GH_AW_TOOLS_ENABLED"
  "GH_AW_INGESTION_MODE"
  "GH_AW_KNOWN_WORKFLOWS"
  "EXTERNAL_DIAGNOSTICS_WAIT_SECONDS"
  "EXTERNAL_DIAGNOSTICS_POLL_INTERVAL_SECONDS"
  "LLM_PROVIDER"
  "OPENAI_COMPATIBLE_BASE_URL"
  "OPENAI_COMPATIBLE_MODEL"
  "OPENAI_COMPATIBLE_API_KEY"
  "MCP_ENABLED"
  "MCP_PROVIDER"
  "MCP_READ_ONLY"
  "MCP_TIMEOUT_SECONDS"
  "MCP_MAX_RETRIES"
  "AZURE_OPENAI_CHAT_API_VERSION"
)

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
    --release-version)
      RELEASE_VERSION="$2"
      MODE="release"
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
    --acr-retain-tags)
      ACR_RETAIN_TAGS="$2"
      shift 2
      ;;
    --skip-acr-prune)
      PRUNE_ACR_IMAGES="0"
      shift
      ;;
    --skip-local-image-prune)
      PRUNE_LOCAL_IMAGES="0"
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

if [[ "$MODE" == "full" ]]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "Missing required command for full deploy: git" >&2
    exit 1
  fi
fi

if [[ "$MODE" == "release" && -z "${RELEASE_VERSION:-}" ]]; then
  echo "Missing required value: --release-version <vX.Y.Z|X.Y.Z>" >&2
  exit 2
fi

if ! [[ "$ACR_RETAIN_TAGS" =~ ^[0-9]+$ ]]; then
  echo "Invalid value for --acr-retain-tags: '$ACR_RETAIN_TAGS' (expected non-negative integer)." >&2
  exit 2
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

BACKEND_SET_ENV_VARS=(
  "API_AUTH_KEY=$API_AUTH_KEY"
  "ADMIN_API_KEY=$ADMIN_API_KEY"
)

for key in "${BACKEND_RUNTIME_ENV_KEYS[@]}"; do
  value="$(read_env_key "$key")"
  if [[ -n "$value" ]]; then
    BACKEND_SET_ENV_VARS+=("$key=$value")
  fi
done

FRONTEND_SET_ENV_VARS=(
  "BACKEND_UPSTREAM=$BACKEND_URL"
  "API_AUTH_KEY=$API_AUTH_KEY"
)

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

prune_local_repo_tags() {
  local engine="$1"
  local repo="$2"
  local keep_tag="$3"
  local refs removed kept
  removed=0
  kept=0
  refs="$(
    "$engine" image ls \
      --filter "reference=${repo}:*" \
      --format '{{.Repository}}:{{.Tag}}' 2>/dev/null || true
  )"

  if [[ -z "${refs:-}" ]]; then
    echo "Local image cleanup: no local tags found for $repo"
    return 0
  fi

  while IFS= read -r ref; do
    [[ -z "$ref" || "$ref" == "<none>:<none>" ]] && continue
    if [[ "$ref" == "$repo:$keep_tag" || "$ref" == "$repo:latest" ]]; then
      kept=$((kept + 1))
      continue
    fi
    if "$engine" image rm "$ref" >/dev/null 2>&1; then
      removed=$((removed + 1))
    fi
  done <<< "$refs"

  echo "Local image cleanup ($repo): removed $removed old tag(s), kept $kept."
}

prune_local_images() {
  local engine="$1"
  local acr_login="$2"
  local image_tag="$3"
  prune_local_repo_tags "$engine" "$acr_login/pipelinehealer-backend" "$image_tag"
  prune_local_repo_tags "$engine" "$acr_login/pipelinehealer-frontend" "$image_tag"
  "$engine" image prune -f >/dev/null 2>&1 || true
}

prune_acr_repository() {
  local acr_name="$1"
  local repo="$2"
  local keep_tag="$3"
  local retain_count="$4"
  local rows
  rows="$(
    az acr repository show-tags \
      -n "$acr_name" \
      --repository "$repo" \
      --detail \
      --orderby time_desc \
      --query "[].{name:name,digest:digest}" \
      -o tsv 2>/dev/null || true
  )"

  if [[ -z "${rows:-}" ]]; then
    echo "ACR cleanup: no tags found for $repo"
    return 0
  fi

  local index=0
  local keep_count=0
  local candidate_count=0
  local tag digest
  local -A keep_digests=()
  local -A delete_digests=()
  local -a delete_pairs=()

  while IFS=$'\t' read -r tag digest; do
    [[ -z "$tag" || -z "$digest" ]] && continue
    if [[ "$index" -lt "$retain_count" || "$tag" == "latest" || "$tag" == "$keep_tag" || "$tag" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
      keep_digests["$digest"]=1
      keep_count=$((keep_count + 1))
    else
      delete_pairs+=("${tag}"$'\t'"${digest}")
      candidate_count=$((candidate_count + 1))
    fi
    index=$((index + 1))
  done <<< "$rows"

  if [[ "$candidate_count" -eq 0 ]]; then
    echo "ACR cleanup ($repo): nothing to prune (kept $keep_count tag(s))."
    return 0
  fi

  local removed_tag_refs=0
  local removed_manifests=0
  local failures=0
  local pair
  for pair in "${delete_pairs[@]}"; do
    tag="${pair%%$'\t'*}"
    digest="${pair#*$'\t'}"
    if [[ -n "${keep_digests[$digest]:-}" ]]; then
      if az acr repository untag -n "$acr_name" --image "$repo:$tag" >/dev/null 2>&1; then
        removed_tag_refs=$((removed_tag_refs + 1))
      else
        failures=$((failures + 1))
      fi
      continue
    fi
    if [[ -n "${delete_digests[$digest]:-}" ]]; then
      continue
    fi
    if az acr repository delete -n "$acr_name" --image "$repo@$digest" --yes >/dev/null 2>&1; then
      removed_manifests=$((removed_manifests + 1))
      delete_digests["$digest"]=1
    else
      failures=$((failures + 1))
    fi
  done

  echo "ACR cleanup ($repo): removed $removed_tag_refs old tag ref(s), deleted $removed_manifests manifest(s), kept $keep_count tag(s)."
  if [[ "$failures" -gt 0 ]]; then
    echo "ACR cleanup ($repo): $failures operation(s) failed." >&2
  fi
}

prune_acr_images() {
  local acr_name="$1"
  local keep_tag="$2"
  local retain_count="$3"
  prune_acr_repository "$acr_name" "pipelinehealer-backend" "$keep_tag" "$retain_count"
  prune_acr_repository "$acr_name" "pipelinehealer-frontend" "$keep_tag" "$retain_count"
}

resolve_release_digest() {
  local repo="$1"
  local release_ref="$2"
  local digest
  local candidate
  local candidates=()

  release_ref="$(printf '%s' "$release_ref" | tr -d '\r\n')"
  candidates+=("$release_ref")
  if [[ "$release_ref" == v* ]]; then
    candidates+=("${release_ref#v}")
  else
    candidates+=("v$release_ref")
  fi

  for candidate in "${candidates[@]}"; do
    [[ -z "$candidate" ]] && continue
    digest="$(
      az acr repository show \
        -n "$ACR_NAME" \
        --image "$repo:$candidate" \
        --query digest \
        -o tsv 2>/dev/null | tr -d '\r\n' || true
    )"
    if [[ -n "$digest" ]]; then
      printf '%s\n' "$digest"
      return 0
    fi
  done

  return 1
}

echo "Resource group : $AZ_RESOURCE_GROUP"
echo "Backend app    : $BACKEND_APP"
echo "Frontend app   : $FRONTEND_APP"
echo "Mode           : $MODE"
echo "Image tag      : $IMAGE_TAG"
if [[ "$MODE" == "release" ]]; then
  echo "Release version: $RELEASE_VERSION"
fi

ACR_LOGIN=""
if [[ "$MODE" == "full" || "$MODE" == "release" ]]; then
  ACR_LOGIN="$(az acr show -n "$ACR_NAME" --query loginServer -o tsv | tr -d '\r\n')"
  if [[ -z "$ACR_LOGIN" ]]; then
    echo "Failed to resolve ACR login server for '$ACR_NAME'." >&2
    exit 1
  fi
fi

expected_backend_image=""
expected_frontend_image=""

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
    --set-env-vars "${BACKEND_SET_ENV_VARS[@]}" >/dev/null

  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --image "$ACR_LOGIN/pipelinehealer-frontend:$IMAGE_TAG" \
    --set-env-vars "${FRONTEND_SET_ENV_VARS[@]}" >/dev/null
  expected_backend_image="$ACR_LOGIN/pipelinehealer-backend:$IMAGE_TAG"
  expected_frontend_image="$ACR_LOGIN/pipelinehealer-frontend:$IMAGE_TAG"
elif [[ "$MODE" == "release" ]]; then
  backend_digest="$(resolve_release_digest "pipelinehealer-backend" "$RELEASE_VERSION" || true)"
  frontend_digest="$(resolve_release_digest "pipelinehealer-frontend" "$RELEASE_VERSION" || true)"

  if [[ -z "$backend_digest" || -z "$frontend_digest" ]]; then
    echo "Unable to resolve release image digests for version '$RELEASE_VERSION' from ACR '$ACR_NAME'." >&2
    echo "Ensure release images exist (tags vX.Y.Z and/or X.Y.Z)." >&2
    exit 1
  fi

  expected_backend_image="$ACR_LOGIN/pipelinehealer-backend@$backend_digest"
  expected_frontend_image="$ACR_LOGIN/pipelinehealer-frontend@$frontend_digest"

  echo "Resolved backend digest : $backend_digest"
  echo "Resolved frontend digest: $frontend_digest"

  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --image "$expected_backend_image" \
    --set-env-vars "${BACKEND_SET_ENV_VARS[@]}" >/dev/null

  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --image "$expected_frontend_image" \
    --set-env-vars "${FRONTEND_SET_ENV_VARS[@]}" >/dev/null
else
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --set-env-vars "${BACKEND_SET_ENV_VARS[@]}" >/dev/null

  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --set-env-vars "${FRONTEND_SET_ENV_VARS[@]}" >/dev/null
fi

DEPLOYED_BACKEND_IMAGE="$(
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$BACKEND_APP" \
    --query properties.template.containers[0].image \
    -o tsv | tr -d '\r\n'
)"
DEPLOYED_FRONTEND_IMAGE="$(
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --query properties.template.containers[0].image \
    -o tsv | tr -d '\r\n'
)"

FRONTEND_FQDN="$(
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$FRONTEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n'
)"

echo "Backend URL : https://$BACKEND_FQDN"
echo "Frontend URL: https://$FRONTEND_FQDN"
echo "Backend image : $DEPLOYED_BACKEND_IMAGE"
echo "Frontend image: $DEPLOYED_FRONTEND_IMAGE"

if [[ "$MODE" == "full" || "$MODE" == "release" ]]; then
  if [[ "$DEPLOYED_BACKEND_IMAGE" != "$expected_backend_image" || "$DEPLOYED_FRONTEND_IMAGE" != "$expected_frontend_image" ]]; then
    echo "Error: deployed image mismatch after $MODE deploy." >&2
    echo "Expected backend : $expected_backend_image" >&2
    echo "Actual backend   : $DEPLOYED_BACKEND_IMAGE" >&2
    echo "Expected frontend: $expected_frontend_image" >&2
    echo "Actual frontend  : $DEPLOYED_FRONTEND_IMAGE" >&2
    exit 1
  fi
fi

if [[ "$DO_VERIFY" == "1" ]]; then
  curl -fsS "https://$BACKEND_FQDN/health" >/dev/null
  curl -fsS \
    -H "X-API-Key: $API_AUTH_KEY" \
    -H "X-Admin-Key: $ADMIN_API_KEY" \
    "https://$BACKEND_FQDN/api/settings" >/dev/null
  echo "Verification passed: backend health + admin settings endpoint."
fi

if [[ "$MODE" == "full" && "$PRUNE_LOCAL_IMAGES" == "1" ]]; then
  prune_local_images "$CONTAINER_ENGINE" "$ACR_LOGIN" "$IMAGE_TAG"
fi

if [[ "$MODE" == "full" && "$PRUNE_ACR_IMAGES" == "1" && "$ACR_RETAIN_TAGS" -gt 0 ]]; then
  prune_acr_images "$ACR_NAME" "$IMAGE_TAG" "$ACR_RETAIN_TAGS"
fi

echo "Done."
