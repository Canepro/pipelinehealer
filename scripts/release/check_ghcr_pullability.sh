#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/release/check_ghcr_pullability.sh --owner-lc <owner> --release-tag vX.Y.Z --version X.Y.Z --backend-digest sha256:... --frontend-digest sha256:..." >&2
  return 1
fi

usage() {
  cat <<'EOF'
Validate anonymous GHCR pullability for release artifacts.

Usage:
  bash scripts/release/check_ghcr_pullability.sh \
    --owner-lc <owner-lowercase> \
    --release-tag <vX.Y.Z> \
    --version <X.Y.Z> \
    --backend-digest <sha256:...> \
    --frontend-digest <sha256:...>

Checks:
  - backend image tags: vX.Y.Z + X.Y.Z
  - frontend image tags: vX.Y.Z + X.Y.Z
  - backend/frontend image digests
  - Helm chart tag: X.Y.Z
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

OWNER_LC=""
RELEASE_TAG=""
VERSION=""
BACKEND_DIGEST=""
FRONTEND_DIGEST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner-lc)
      OWNER_LC="${2:-}"
      shift 2
      ;;
    --release-tag)
      RELEASE_TAG="${2:-}"
      shift 2
      ;;
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --backend-digest)
      BACKEND_DIGEST="${2:-}"
      shift 2
      ;;
    --frontend-digest)
      FRONTEND_DIGEST="${2:-}"
      shift 2
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

if [[ -z "$OWNER_LC" || -z "$RELEASE_TAG" || -z "$VERSION" || -z "$BACKEND_DIGEST" || -z "$FRONTEND_DIGEST" ]]; then
  echo "Missing required arguments." >&2
  usage
  exit 2
fi

if [[ "$OWNER_LC" != "${OWNER_LC,,}" ]]; then
  echo "owner-lc must be lowercase: ${OWNER_LC}" >&2
  exit 2
fi

if [[ ! "$BACKEND_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  echo "Invalid backend digest format: ${BACKEND_DIGEST}" >&2
  exit 2
fi

if [[ ! "$FRONTEND_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  echo "Invalid frontend digest format: ${FRONTEND_DIGEST}" >&2
  exit 2
fi

need_cmd curl
need_cmd python3

manifest_accept="application/vnd.oci.image.index.v1+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v2+json"
chart_accept="application/vnd.oci.image.manifest.v1+json"
failed=0

fetch_token() {
  local repository="$1"
  local response token

  response="$(curl -fsSL "https://ghcr.io/token?service=ghcr.io&scope=repository:${repository}:pull")" || {
    echo "::error::Failed to fetch anonymous GHCR token for ${repository}."
    return 1
  }

  token="$(
    TOKEN_RESPONSE="$response" python3 - <<'PY'
import json
import os

raw = os.environ.get("TOKEN_RESPONSE", "")
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("")
    raise SystemExit(0)

print(data.get("token") or data.get("access_token") or "")
PY
)"

  if [[ -z "$token" ]]; then
    echo "::error::Anonymous GHCR token response missing token field for ${repository}."
    return 1
  fi

  printf '%s' "$token"
}

check_manifest() {
  local repository="$1"
  local ref="$2"
  local token="$3"
  local accept="$4"
  local label="$5"
  local ref_path
  local image_ref
  local code

  ref_path="${ref//:/%3A}"
  if [[ "$ref" == sha256:* ]]; then
    image_ref="ghcr.io/${repository}@${ref}"
  else
    image_ref="ghcr.io/${repository}:${ref}"
  fi
  code="$(
    curl -sS -o /dev/null -w '%{http_code}' \
      -H "Authorization: Bearer ${token}" \
      -H "Accept: ${accept}" \
      "https://ghcr.io/v2/${repository}/manifests/${ref_path}"
  )"

  if [[ "$code" == "200" ]]; then
    echo "PASS ${label}: ${image_ref}"
    return 0
  fi

  echo "::error::FAIL ${label}: ${image_ref} returned HTTP ${code}."
  return 1
}

check_repo_refs() {
  local repository="$1"
  local token="$2"
  shift 2

  while [[ $# -gt 0 ]]; do
    local ref="$1"
    local label="$2"
    shift 2

    if ! check_manifest "$repository" "$ref" "$token" "$manifest_accept" "$label"; then
      failed=1
    fi
  done
}

echo "Checking anonymous GHCR pullability for release ${RELEASE_TAG} (${VERSION})..."

backend_repo="${OWNER_LC}/pipelinehealer-backend"
frontend_repo="${OWNER_LC}/pipelinehealer-frontend"
chart_repo="${OWNER_LC}/charts/pipelinehealer"

backend_token="$(fetch_token "$backend_repo")" || exit 1
frontend_token="$(fetch_token "$frontend_repo")" || exit 1
chart_token="$(fetch_token "$chart_repo")" || exit 1

check_repo_refs "$backend_repo" "$backend_token" \
  "$RELEASE_TAG" "backend tag ${RELEASE_TAG}" \
  "$VERSION" "backend tag ${VERSION}" \
  "$BACKEND_DIGEST" "backend digest ${BACKEND_DIGEST}"

check_repo_refs "$frontend_repo" "$frontend_token" \
  "$RELEASE_TAG" "frontend tag ${RELEASE_TAG}" \
  "$VERSION" "frontend tag ${VERSION}" \
  "$FRONTEND_DIGEST" "frontend digest ${FRONTEND_DIGEST}"

if ! check_manifest "$chart_repo" "$VERSION" "$chart_token" "$chart_accept" "chart tag ${VERSION}"; then
  failed=1
fi

if [[ "$failed" -ne 0 ]]; then
  echo "Anonymous GHCR pullability gate failed."
  exit 1
fi

echo "Anonymous GHCR pullability gate passed."
