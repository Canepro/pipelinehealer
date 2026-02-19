#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/release_checklist.sh [patch|minor|major|x.y.z]" >&2
  return 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Release checklist helper (prints commands only, does not modify files).

Usage:
  bash scripts/release_checklist.sh [patch|minor|major|x.y.z]

Examples:
  bash scripts/release_checklist.sh
  bash scripts/release_checklist.sh patch
  bash scripts/release_checklist.sh minor
  bash scripts/release_checklist.sh 0.2.1
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [[ $# -gt 1 ]]; then
  usage
  exit 2
fi

need_cmd python3

cd "$REPO_ROOT"

current_version="$(tr -d '\r\n' < VERSION 2>/dev/null || true)"
if [[ -z "${current_version:-}" ]]; then
  echo "VERSION file is missing or empty." >&2
  exit 1
fi

bump="${1:-}"
next_version=""
release_tag="vX.Y.Z"

if [[ -n "$bump" ]]; then
  if [[ "$bump" =~ ^(major|minor|patch)$ ]]; then
    next_version="$(CURRENT_VERSION="$current_version" BUMP="$bump" python3 - <<'PY'
import os

current = os.environ["CURRENT_VERSION"].strip()
major, minor, patch = map(int, current.split("."))
bump = os.environ["BUMP"].strip()

if bump == "major":
    major += 1
    minor = 0
    patch = 0
elif bump == "minor":
    minor += 1
    patch = 0
elif bump == "patch":
    patch += 1
else:
    raise SystemExit("Invalid bump type")

print(f"{major}.{minor}.{patch}")
PY
)"
  elif [[ "$bump" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    next_version="$bump"
  else
    echo "Invalid bump value: $bump" >&2
    usage
    exit 2
  fi
  release_tag="v${next_version}"
fi

echo "Release Checklist (dry-run)"
echo "Current version: $current_version"
if [[ -n "$next_version" ]]; then
  echo "Planned next version: $next_version"
fi
echo
echo "1) Preflight"
echo "git status --short"
echo "bash scripts/check_version_sync.sh"
echo "bash scripts/release_scope_check.sh"
echo
echo "2) Update CHANGELOG.md under [Unreleased]"
echo
echo "3) Generate release files"
if [[ -n "$bump" ]]; then
  echo "bash scripts/release.sh $bump"
else
  echo "bash scripts/release.sh <patch|minor|major|x.y.z>"
fi
echo
echo "4) Validate generated state"
echo "bash scripts/check_version_sync.sh"
echo "python3 -m pytest backend/tests/test_phase2_security.py::test_api_routes_allow_development_without_key -q"
echo "cd frontend && bun run build && cd .."
echo
echo "5) Commit + tag + push"
echo "git add VERSION backend/pyproject.toml frontend/package.json charts/pipelinehealer/Chart.yaml CHANGELOG.md"
echo "git commit -m \"chore(release): ${release_tag}\""
echo "git tag -a ${release_tag} -m \"Release ${release_tag}\""
echo "git push origin main --follow-tags"
echo
echo "6) Verify publish"
echo "git ls-remote --tags origin | grep \"refs/tags/${release_tag}\""
echo "gh release view ${release_tag}"
