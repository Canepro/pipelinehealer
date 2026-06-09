#!/usr/bin/env bash
# Local deploy + full-capability settings handoff for Vincent's Mac lane.
# Run from repo root under Infisical injection (never paste secrets into this file).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SETTINGS_FIXTURE="$SCRIPT_DIR/fixtures/full-capability-settings.json"

EXPECTED_COMMIT="${PH_EXPECTED_COMMIT:-69b7b361b4e90218b1b44f4f1aa7a04d8b78133a}"
INFISICAL_PROJECT_ID="${INFISICAL_PROJECT_ID:-70ae1697-055c-4fc1-ba90-85b25f6bf138}"
INFISICAL_ENVIRONMENT="${INFISICAL_ENVIRONMENT:-dev}"
INFISICAL_SECRET_PATH="${INFISICAL_SECRET_PATH:-/personal/pipelinehealer}"

SKIP_DEPLOY="${SKIP_DEPLOY:-0}"
SKIP_SETTINGS="${SKIP_SETTINGS:-0}"
SKIP_BACKFILL="${SKIP_BACKFILL:-0}"
SKIP_VERIFY="${SKIP_VERIFY:-0}"

export AZURE_TENANT_ID="${AZURE_TENANT_ID:-040f4d47-c5be-488d-a48b-4b43fe04cac4}"
export AZURE_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-d3b51a0d-cdf1-445e-bac3-28e65892afbc}"
export PH_RG="${PH_RG:-rg-canepro-ph-dev-eus}"
export PH_BACKEND_APP="${PH_BACKEND_APP:-ca-canepro-ph-backend}"
export PH_FRONTEND_APP="${PH_FRONTEND_APP:-ca-canepro-ph-frontend}"
export PH_ACR_NAME="${PH_ACR_NAME:-caneprophacr01}"

usage() {
  cat <<'EOF'
Usage:
  infisical run --env dev --path /personal/pipelinehealer \
    --projectId 70ae1697-055c-4fc1-ba90-85b25f6bf138 -- \
    bash scripts/local_full_capability_handoff.sh

Optional env overrides:
  SKIP_DEPLOY=1       Skip Azure deploy (settings/backfill/verify only)
  SKIP_SETTINGS=1     Skip PATCH /api/settings
  SKIP_BACKFILL=1     Skip lifecycle marker backfill
  SKIP_VERIFY=1       Skip settings:check assertions
  PH_EXPECTED_COMMIT  Override expected git commit (default: 69b7b36...)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
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

resolve_backend_url() {
  need_cmd az
  local fqdn
  fqdn="$(az containerapp show \
    -g "$PH_RG" \
    -n "$PH_BACKEND_APP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv | tr -d '\r\n')"
  if [[ -z "$fqdn" ]]; then
    echo "Failed to resolve backend FQDN for $PH_BACKEND_APP in $PH_RG" >&2
    exit 1
  fi
  echo "https://$fqdn"
}

verify_git_commit() {
  local actual short_expected short_actual
  actual="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  short_expected="${EXPECTED_COMMIT:0:12}"
  short_actual="${actual:0:12}"
  if [[ "$actual" != "$EXPECTED_COMMIT" && "$short_actual" != "$short_expected" ]]; then
    echo "Warning: HEAD is $actual, expected $EXPECTED_COMMIT" >&2
    echo "Continue only if this is intentional." >&2
  fi
}

sync_main() {
  git -C "$REPO_ROOT" fetch origin main --prune
  git -C "$REPO_ROOT" switch main
  git -C "$REPO_ROOT" pull --ff-only origin main
}

deploy_main() {
  need_cmd az
  az account set --subscription "$AZURE_SUBSCRIPTION_ID"
  bash "$SCRIPT_DIR/ph.sh" deploy --secure-secrets --remote-build
}

patch_settings() {
  need_cmd curl
  need_cmd python3
  if [[ ! -f "$SETTINGS_FIXTURE" ]]; then
    echo "Missing settings fixture: $SETTINGS_FIXTURE" >&2
    exit 1
  fi
  local api_key admin_key base_url
  api_key="$(read_env_key API_AUTH_KEY)"
  admin_key="$(read_env_key ADMIN_API_KEY)"
  if [[ -z "${api_key:-}" || -z "${admin_key:-}" ]]; then
    echo "API_AUTH_KEY and ADMIN_API_KEY must be available (Infisical or backend/.env)" >&2
    exit 1
  fi
  base_url="$(resolve_backend_url)"
  echo "Patching settings via $base_url/api/settings ..."
  curl -fsS -X PATCH "$base_url/api/settings" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    --data @"$SETTINGS_FIXTURE" >/dev/null
  echo "Settings patch accepted."
}

backfill_markers() {
  need_cmd curl
  local api_key admin_key base_url
  api_key="$(read_env_key API_AUTH_KEY)"
  admin_key="$(read_env_key ADMIN_API_KEY)"
  base_url="$(resolve_backend_url)"
  echo "Backfilling lifecycle markers for Canepro/pipelinehealer ..."
  curl -fsS -X POST -G "$base_url/api/settings/lifecycle/backfill-markers" \
    -H "X-API-Key: $api_key" \
    -H "X-Admin-Key: $admin_key" \
    --data-urlencode "repository=Canepro/pipelinehealer"
  echo
}

verify_settings() {
  need_cmd python3
  bash "$SCRIPT_DIR/ph.sh" status
  echo
  local settings_json
  settings_json="$(bash "$SCRIPT_DIR/ph.sh" settings:check)"
  python3 - <<'PY' "$settings_json"
import json
import sys

raw = sys.argv[1]
data = json.loads(raw)

checks = {
    "auto_apply_remediation": True,
    "auto_create_pr": True,
    "auto_create_issue": True,
    "auto_retry_workflow": True,
    "auto_create_tracking_issue_for_prs": True,
    "auto_close_on_workflow_success": True,
    "auto_merge_remediation_prs": True,
    "auto_merge_require_clean_checks": True,
    "gh_aw_tools_enabled": True,
    "gh_aw_ingestion_mode": "hybrid",
    "agent_handoff_enabled": True,
    "mcp_enabled": True,
    "mcp_read_only": False,
    "jenkins_bridge_enabled": True,
    "jenkins_bridge_allow_pr": True,
}

repos = data.get("ph_allowed_repos") or []
required_repos = {"canepro/pipelinehealer", "canepro/pipelinehealer-demo"}
actual_repos = {str(r).strip().lower() for r in repos}

failures = []
for key, expected in checks.items():
    actual = data.get(key)
    if actual != expected:
        failures.append(f"{key}: expected {expected!r}, got {actual!r}")

if not required_repos.issubset(actual_repos):
    failures.append(
        f"ph_allowed_repos: missing required entries; have {sorted(actual_repos)}"
    )

if failures:
    print("Full-capability verification FAILED:", file=sys.stderr)
    for item in failures:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)

print("Full-capability verification PASSED.")
for key in sorted(checks):
    print(f"  {key}={data.get(key)!r}")
print(f"  ph_allowed_repos={repos!r}")
PY
}

main() {
  cd "$REPO_ROOT"
  need_cmd git
  need_cmd bash
  sync_main
  verify_git_commit

  if [[ "$SKIP_DEPLOY" != "1" ]]; then
    deploy_main
  else
    echo "Skipping deploy (SKIP_DEPLOY=1)."
  fi

  if [[ "$SKIP_SETTINGS" != "1" ]]; then
    patch_settings
  else
    echo "Skipping settings patch (SKIP_SETTINGS=1)."
  fi

  if [[ "$SKIP_BACKFILL" != "1" ]]; then
    backfill_markers
  else
    echo "Skipping lifecycle backfill (SKIP_BACKFILL=1)."
  fi

  if [[ "$SKIP_VERIFY" != "1" ]]; then
    verify_settings
  else
    echo "Skipping verification (SKIP_VERIFY=1)."
  fi

  echo
  echo "Handoff complete."
}

main "$@"
