#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/check_version_sync.sh" >&2
  return 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

need_cmd python3

VERSION_FILE="$REPO_ROOT/VERSION"
PYPROJECT_FILE="$REPO_ROOT/backend/pyproject.toml"
FRONTEND_PKG_FILE="$REPO_ROOT/frontend/package.json"
CHART_FILE="$REPO_ROOT/charts/pipelinehealer/Chart.yaml"

if [[ ! -f "$VERSION_FILE" || ! -f "$PYPROJECT_FILE" || ! -f "$FRONTEND_PKG_FILE" || ! -f "$CHART_FILE" ]]; then
  echo "Missing one or more required files: VERSION, backend/pyproject.toml, frontend/package.json, charts/pipelinehealer/Chart.yaml" >&2
  exit 1
fi

readarray -t versions < <(
  VERSION_FILE="$VERSION_FILE" PYPROJECT_FILE="$PYPROJECT_FILE" FRONTEND_PKG_FILE="$FRONTEND_PKG_FILE" CHART_FILE="$CHART_FILE" \
    python3 - <<'PY'
import json
import os
import re
from pathlib import Path

version_file = Path(os.environ["VERSION_FILE"]).read_text(encoding="utf-8").strip()
pyproject_raw = Path(os.environ["PYPROJECT_FILE"]).read_text(encoding="utf-8")
pkg_json = json.loads(Path(os.environ["FRONTEND_PKG_FILE"]).read_text(encoding="utf-8"))
chart_raw = Path(os.environ["CHART_FILE"]).read_text(encoding="utf-8")

match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_raw, re.MULTILINE)
if not match:
    raise SystemExit("Unable to parse backend version from backend/pyproject.toml")

backend_version = match.group(1).strip()
frontend_version = str(pkg_json.get("version", "")).strip()
chart_version_match = re.search(r'^version\s*:\s*"?([^"\n]+)"?', chart_raw, re.MULTILINE)
chart_app_version_match = re.search(r'^appVersion\s*:\s*"?([^"\n]+)"?', chart_raw, re.MULTILINE)
if not chart_version_match or not chart_app_version_match:
    raise SystemExit("Unable to parse chart version/appVersion from charts/pipelinehealer/Chart.yaml")

chart_version = chart_version_match.group(1).strip()
chart_app_version = chart_app_version_match.group(1).strip()

print(version_file)
print(backend_version)
print(frontend_version)
print(chart_version)
print(chart_app_version)
PY
)

root_version="${versions[0]:-}"
backend_version="${versions[1]:-}"
frontend_version="${versions[2]:-}"
chart_version="${versions[3]:-}"
chart_app_version="${versions[4]:-}"

if [[ -z "$root_version" || -z "$backend_version" || -z "$frontend_version" || -z "$chart_version" || -z "$chart_app_version" ]]; then
  echo "Unable to determine versions from one or more files." >&2
  exit 1
fi

if ! [[ "$root_version" == "$backend_version" && "$root_version" == "$frontend_version" && "$root_version" == "$chart_version" && "$root_version" == "$chart_app_version" ]]; then
  echo "Version mismatch detected." >&2
  echo "  VERSION:                $root_version" >&2
  echo "  backend/pyproject.toml: $backend_version" >&2
  echo "  frontend/package.json:  $frontend_version" >&2
  echo "  chart version:          $chart_version" >&2
  echo "  chart appVersion:       $chart_app_version" >&2
  exit 1
fi

echo "Version sync OK: $root_version"
