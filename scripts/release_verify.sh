#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/release_verify.sh vX.Y.Z [--skip-workflow-check]" >&2
  return 1
fi

usage() {
  cat <<'EOF'
Release publish verification helper.

Usage:
  bash scripts/release_verify.sh vX.Y.Z [--skip-workflow-check]

What it verifies:
  1) tag exists on origin
  2) GitHub Release exists and includes release_images.md
  3) release notes include "## Container Images"
  4) release workflow run for the tag commit succeeded (default)
  5) anonymous GHCR pullability gate passes for backend/frontend/chart
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 2
fi

release_tag="$1"
skip_workflow_check=0

if [[ $# -eq 2 ]]; then
  if [[ "$2" == "--skip-workflow-check" ]]; then
    skip_workflow_check=1
  else
    echo "Unknown argument: $2" >&2
    usage
    exit 2
  fi
fi

if [[ ! "$release_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid tag format: $release_tag (expected vX.Y.Z)." >&2
  exit 2
fi

version="${release_tag#v}"

need_cmd git
need_cmd gh
need_cmd curl
need_cmd python3
need_cmd bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

origin_url="$(git remote get-url origin)"
owner_repo="$(
  ORIGIN_URL="$origin_url" python3 - <<'PY'
import os
import re

url = os.environ.get("ORIGIN_URL", "").strip()
patterns = [
    r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$",
]
for pattern in patterns:
    match = re.search(pattern, url)
    if match:
        print(f"{match.group(1)}/{match.group(2)}")
        raise SystemExit(0)
raise SystemExit("Unable to parse owner/repo from origin URL.")
PY
)"
owner="${owner_repo%%/*}"
repo="${owner_repo#*/}"
owner_lc="$(echo "$owner" | tr '[:upper:]' '[:lower:]')"

tag_sha="$(git ls-remote --tags origin "refs/tags/${release_tag}^{}" | awk '{print $1}' | head -n1)"
if [[ -z "$tag_sha" ]]; then
  tag_sha="$(git ls-remote --tags origin "refs/tags/${release_tag}" | awk '{print $1}' | head -n1)"
fi

if [[ -z "$tag_sha" ]]; then
  echo "Verification failed: tag ${release_tag} not found on origin." >&2
  exit 1
fi
echo "PASS remote tag: ${release_tag} (${tag_sha})"

release_json="$(gh release view "$release_tag" --repo "$owner_repo" --json url,body,assets,isDraft,isPrerelease)"
RELEASE_JSON="$release_json" python3 - <<'PY'
import json
import os

raw = os.environ.get("RELEASE_JSON", "")
data = json.loads(raw)
if data.get("isDraft"):
    raise SystemExit("Verification failed: release is still draft.")
if data.get("isPrerelease"):
    raise SystemExit("Verification failed: release is marked prerelease.")
assets = {item.get("name", "") for item in data.get("assets", [])}
if "release_images.md" not in assets:
    raise SystemExit("Verification failed: release_images.md asset is missing.")
body = data.get("body") or ""
if "## Container Images" not in body:
    raise SystemExit("Verification failed: release notes missing '## Container Images'.")
print(f"PASS GitHub release: {data.get('url')}")
PY

if [[ "$skip_workflow_check" -eq 0 ]]; then
  runs_json_file="$(mktemp)"
  cleanup_runs_json() {
    rm -f "$runs_json_file"
  }
  trap cleanup_runs_json EXIT

  gh api --paginate "/repos/${owner_repo}/actions/workflows/release.yml/runs?per_page=100" >"$runs_json_file"
  RUNS_JSON_FILE="$runs_json_file" TAG_SHA="$tag_sha" python3 - <<'PY'
import json
import os
from pathlib import Path

tag_sha = os.environ.get("TAG_SHA", "").strip()
raw = Path(os.environ["RUNS_JSON_FILE"]).read_text(encoding="utf-8")

decoder = json.JSONDecoder()
pages = []
idx = 0
while idx < len(raw):
    while idx < len(raw) and raw[idx].isspace():
        idx += 1
    if idx >= len(raw):
        break
    page, next_idx = decoder.raw_decode(raw, idx)
    pages.append(page)
    idx = next_idx

runs = []
for page in pages:
    if isinstance(page, dict):
        runs.extend(page.get("workflow_runs", []))

candidate = None
for run in runs:
    if str(run.get("head_sha", "")).strip() == tag_sha and run.get("event") == "push":
        candidate = run
        break
if candidate is None:
    raise SystemExit(
        "Verification failed: no release workflow run found for tag commit across paginated history."
    )
conclusion = (candidate.get("conclusion") or "").strip().lower()
status = (candidate.get("status") or "").strip().lower()
if status != "completed" or conclusion != "success":
    raise SystemExit(
        f"Verification failed: release workflow run not successful (status={status}, conclusion={conclusion})."
    )
print(f"PASS release workflow: {candidate.get('html_url')}")
PY

  trap - EXIT
  cleanup_runs_json
else
  echo "SKIP release workflow check (--skip-workflow-check)"
fi

get_token() {
  local repository="$1"
  local response token
  response="$(curl -fsSL "https://ghcr.io/token?service=ghcr.io&scope=repository:${repository}:pull")"
  token="$(
    TOKEN_RESPONSE="$response" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["TOKEN_RESPONSE"])
print(data.get("token") or data.get("access_token") or "")
PY
)"
  if [[ -z "$token" ]]; then
    echo "Unable to fetch GHCR anonymous token for ${repository}." >&2
    exit 1
  fi
  printf '%s' "$token"
}

get_digest() {
  local repository="$1"
  local ref="$2"
  local token="$3"
  curl -sSI \
    -H "Authorization: Bearer ${token}" \
    -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v2+json' \
    "https://ghcr.io/v2/${repository}/manifests/${ref}" \
    | tr -d '\r' \
    | awk 'BEGIN{IGNORECASE=1}/^docker-content-digest:/{print $2; exit}'
}

backend_repo="${owner_lc}/pipelinehealer-backend"
frontend_repo="${owner_lc}/pipelinehealer-frontend"
backend_token="$(get_token "$backend_repo")"
frontend_token="$(get_token "$frontend_repo")"
backend_digest="$(get_digest "$backend_repo" "$release_tag" "$backend_token")"
frontend_digest="$(get_digest "$frontend_repo" "$release_tag" "$frontend_token")"

if [[ -z "$backend_digest" || -z "$frontend_digest" ]]; then
  echo "Verification failed: unable to resolve backend/frontend digest from GHCR." >&2
  exit 1
fi

bash scripts/release/check_ghcr_pullability.sh \
  --owner-lc "$owner_lc" \
  --release-tag "$release_tag" \
  --version "$version" \
  --backend-digest "$backend_digest" \
  --frontend-digest "$frontend_digest"

echo "Release verification passed for ${release_tag}."
