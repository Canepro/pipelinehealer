#!/usr/bin/env bash
set -euo pipefail

warn() {
  echo "PipelineHealer bridge: $*" >&2
}

trim() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

json_escape() {
  local value="${1:-}"
  value="$(printf '%s' "$value" | LC_ALL=C tr -d '\000-\010\013\014\016-\037')"
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/}
  value=${value//$'\t'/\\t}
  value=${value//$'\f'/\\f}
  value=${value//$'\b'/\\b}
  printf '%s' "$value"
}

extract_url_path() {
  local url="$1"
  local without_scheme rest

  case "$url" in
    http://*) without_scheme="${url#http://}" ;;
    https://*) without_scheme="${url#https://}" ;;
    *) return 1 ;;
  esac

  [[ -n "$without_scheme" ]] || return 1
  [[ "$without_scheme" == */* ]] || {
    printf '/\n'
    return 0
  }

  rest="${without_scheme#*/}"
  rest="${rest#/}"
  rest="${rest%%\?*}"
  rest="${rest%%\#*}"
  printf '/%s\n' "$rest"
}

extract_url_host() {
  local url="$1"
  local without_scheme

  case "$url" in
    http://*) without_scheme="${url#http://}" ;;
    https://*) without_scheme="${url#https://}" ;;
    *) return 1 ;;
  esac

  without_scheme="${without_scheme%%/*}"
  without_scheme="${without_scheme%%\?*}"
  without_scheme="${without_scheme%%\#*}"
  printf '%s\n' "$without_scheme"
}

sanitize_commit_sha() {
  local commit="${1:-}"
  if [[ "$commit" =~ ^[0-9a-fA-F]{40}$ ]]; then
    printf '%s\n' "$commit"
  else
    printf '\n'
  fi
}

extract_repository_from_git_url() {
  local url="${1:-}"
  local repo=""

  case "$url" in
    https://github.com/*)
      repo="${url#https://github.com/}"
      ;;
    http://github.com/*)
      repo="${url#http://github.com/}"
      ;;
    ssh://git@github.com/*)
      repo="${url#ssh://git@github.com/}"
      ;;
    git@github.com:*)
      repo="${url#git@github.com:}"
      ;;
    *)
      return 1
      ;;
  esac

  repo="${repo%.git}"
  repo="${repo#/}"
  [[ "$repo" == */* ]] || return 1
  printf '%s\n' "$repo"
}

infer_repository() {
  local candidate=""
  local remote_url=""

  for candidate in "${PH_REPOSITORY:-}" "${GITHUB_REPOSITORY:-}"; do
    candidate="$(trim "$candidate")"
    if [[ -n "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  for remote_url in "${GIT_URL:-}" "${PH_GIT_URL:-}"; do
    remote_url="$(trim "$remote_url")"
    if [[ -n "$remote_url" ]] && candidate="$(extract_repository_from_git_url "$remote_url" 2>/dev/null)"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if command -v git >/dev/null 2>&1; then
    remote_url="$(git config --get remote.origin.url 2>/dev/null || true)"
    remote_url="$(trim "$remote_url")"
    if [[ -n "$remote_url" ]] && candidate="$(extract_repository_from_git_url "$remote_url" 2>/dev/null)"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  warn "could not infer repository; set PH_REPOSITORY explicitly. Skipping notification."
  printf '\n'
}

infer_commit_sha() {
  local commit=""

  for commit in "${PH_COMMIT_SHA:-}" "${GIT_COMMIT:-}"; do
    commit="$(sanitize_commit_sha "$commit")"
    if [[ -n "$commit" ]]; then
      printf '%s\n' "$commit"
      return 0
    fi
  done

  if command -v git >/dev/null 2>&1; then
    commit="$(git rev-parse HEAD 2>/dev/null || true)"
    commit="$(sanitize_commit_sha "$commit")"
    if [[ -n "$commit" ]]; then
      printf '%s\n' "$commit"
      return 0
    fi
  fi

  printf '\n'
}

parse_int() {
  local value="${1:-0}"
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$value"
  else
    printf '0\n'
  fi
}

if [[ -z "${PH_BRIDGE_URL:-}" || -z "${PH_BRIDGE_SECRET:-}" ]]; then
  warn "missing PH_BRIDGE_URL or PH_BRIDGE_SECRET; skipping notification"
  exit 0
fi

for cmd in curl openssl tail tr; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    warn "required command '$cmd' is unavailable; skipping notification"
    exit 0
  fi
done

TARGET_URL="${PH_BRIDGE_URL%/}"
TARGET_PATH="$(extract_url_path "$TARGET_URL")" || {
  warn "invalid PH_BRIDGE_URL '${PH_BRIDGE_URL}'"
  exit 0
}

TIMESTAMP="$(date +%s)"
NONCE="${PH_NONCE:-jenkins-${JOB_NAME:-job}-${BUILD_NUMBER:-0}-${TIMESTAMP}}"
BODY_FILE="$(mktemp)"
EXCERPT_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE" "$EXCERPT_FILE"' EXIT

if [[ -n "${PH_LOG_EXCERPT:-}" ]]; then
  printf '%s\n' "${PH_LOG_EXCERPT}" >"$EXCERPT_FILE"
elif [[ -n "${PH_LOG_EXCERPT_FILE:-}" && -f "${PH_LOG_EXCERPT_FILE}" ]]; then
  cat "${PH_LOG_EXCERPT_FILE}" >"$EXCERPT_FILE"
else
  JOB_URL="${PH_JOB_URL:-${BUILD_URL:-}}"
  if [[ -n "$JOB_URL" ]]; then
    curl -fsSL "${JOB_URL%/}/consoleText" >"$EXCERPT_FILE" 2>/dev/null || true
  fi
fi

RAW_EXCERPT=""
MAX_LINES="$(parse_int "${PH_LOG_EXCERPT_MAX_LINES:-120}")"
MAX_CHARS="$(parse_int "${PH_LOG_EXCERPT_MAX_CHARS:-20000}")"
if [[ -f "$EXCERPT_FILE" ]]; then
  RAW_EXCERPT="$(tail -n "$MAX_LINES" "$EXCERPT_FILE" 2>/dev/null || true)"
  if [[ -n "$RAW_EXCERPT" ]]; then
    RAW_EXCERPT="$(printf '%s' "$RAW_EXCERPT" | tail -c "$MAX_CHARS")"
  fi
fi
RAW_ERROR_LINES="${PH_FAILURE_ERROR_LINES:-}"
EXIT_CODE_JSON="null"
if [[ -n "${PH_FAILURE_EXIT_CODE:-}" && "${PH_FAILURE_EXIT_CODE}" =~ ^-?[0-9]+$ ]]; then
  EXIT_CODE_JSON="${PH_FAILURE_EXIT_CODE}"
fi

JOB_URL="${PH_JOB_URL:-${BUILD_URL:-}}"
JOB_HOST="$(extract_url_host "$JOB_URL" 2>/dev/null || true)"
JOB_NAME="${PH_JOB_NAME:-${JOB_NAME:-jenkins-job}}"
SUMMARY="${PH_FAILURE_SUMMARY:-Jenkins job ${JOB_NAME} failed}"
BUILD_NUMBER="$(parse_int "${PH_BUILD_NUMBER:-${BUILD_NUMBER:-0}}")"
DURATION_MS="$(parse_int "${PH_DURATION_MS:-0}")"
COMMIT_SHA="$(infer_commit_sha)"
REPOSITORY="$(infer_repository)"
SENT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -z "$REPOSITORY" ]]; then
  exit 0
fi

cat >"$BODY_FILE" <<EOF
{
  "schema_version": "1.0",
  "provider": "jenkins",
  "delivery_id": "$(json_escape "jenkins:${JOB_NAME}#${BUILD_NUMBER}")",
  "sent_at": "$(json_escape "$SENT_AT")",
  "repository": "$(json_escape "$REPOSITORY")",
  "branch": "$(json_escape "${PH_BRANCH:-${GIT_BRANCH:-${BRANCH_NAME:-unknown}}}")",
  "commit_sha": "$(json_escape "$COMMIT_SHA")",
  "job": {
    "name": "$(json_escape "$JOB_NAME")",
    "url": "$(json_escape "$JOB_URL")",
    "build_number": ${BUILD_NUMBER},
    "result": "$(json_escape "${PH_RESULT:-FAILURE}")",
    "duration_ms": ${DURATION_MS}
  },
  "failure": {
    "stage": "$(json_escape "${PH_FAILURE_STAGE:-}")",
    "step": "$(json_escape "${PH_FAILURE_STEP:-}")",
    "result": "$(json_escape "${PH_FAILURE_RESULT:-}")",
    "tool": "$(json_escape "${PH_FAILURE_TOOL:-}")",
    "command": "$(json_escape "${PH_FAILURE_COMMAND:-}")",
    "exit_code": ${EXIT_CODE_JSON},
    "summary": "$(json_escape "$SUMMARY")",
    "error_lines": $(printf '%s\n' "$RAW_ERROR_LINES" | jq -R . | jq -s .),
    "log_excerpt": "$(json_escape "$RAW_EXCERPT")"
  },
  "artifacts": [],
  "metadata": {
    "jenkins_instance": "$(json_escape "$JOB_HOST")",
    "job_name": "$(json_escape "$JOB_NAME")",
    "build_url": "$(json_escape "$JOB_URL")"
  }
}
EOF

BODY_SHA_OUTPUT="$(openssl dgst -sha256 "$BODY_FILE")"
BODY_SHA="${BODY_SHA_OUTPUT##* }"
CANONICAL="$(printf 'POST\n%s\n%s\n%s\n%s' "$TARGET_PATH" "$TIMESTAMP" "$NONCE" "$BODY_SHA")"
SIGNATURE_OUTPUT="$(printf '%s' "$CANONICAL" | openssl dgst -sha256 -hmac "$PH_BRIDGE_SECRET")"
SIGNATURE="sha256=${SIGNATURE_OUTPUT##* }"

curl -fsS -X POST "$TARGET_URL" \
  -H "Content-Type: application/json" \
  -H "X-PH-Bridge-Provider: jenkins" \
  -H "X-PH-Bridge-Timestamp: $TIMESTAMP" \
  -H "X-PH-Bridge-Nonce: $NONCE" \
  -H "X-PH-Bridge-Signature: $SIGNATURE" \
  --data-binary @"$BODY_FILE"
