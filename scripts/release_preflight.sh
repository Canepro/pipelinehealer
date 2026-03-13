#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/release_preflight.sh [--allow-dirty] [--allow-non-main] [--allow-empty-unreleased]" >&2
  return 1
fi

usage() {
  cat <<'EOF'
Release preflight guardrail runner.

Usage:
  bash scripts/release_preflight.sh [options]

Options:
  --allow-dirty             Do not require a clean git working tree.
  --allow-non-main          Do not require the current branch to be main.
  --allow-empty-unreleased  Allow CHANGELOG [Unreleased] to remain placeholder/empty.
                            Intended for post-`scripts/release.sh` release branches.
  -h, --help                Show help.

Checks:
  - clean working tree (default)
  - on main branch (default)
  - VERSION/backend/frontend/chart sync
  - release scope coverage in CHANGELOG [Unreleased]
  - non-empty CHANGELOG [Unreleased] notes (default)

Important:
  - before running `scripts/release.sh`, keep real notes in CHANGELOG [Unreleased]
  - after running `scripts/release.sh` on a release branch, use
    `--allow-empty-unreleased` because the script resets [Unreleased] to the
    placeholder while creating the concrete `## [vX.Y.Z] - YYYY-MM-DD` section
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

allow_dirty=0
allow_non_main=0
allow_empty_unreleased=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-dirty)
      allow_dirty=1
      shift
      ;;
    --allow-non-main)
      allow_non_main=1
      shift
      ;;
    --allow-empty-unreleased)
      allow_empty_unreleased=1
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

need_cmd git
need_cmd bash
need_cmd python3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [[ "$allow_dirty" -eq 0 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Preflight failed: working tree is not clean." >&2
    git status --short >&2
    exit 1
  fi
fi

if [[ "$allow_non_main" -eq 0 ]]; then
  branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$branch" != "main" ]]; then
    echo "Preflight failed: current branch is '$branch' (expected 'main')." >&2
    exit 1
  fi
fi

bash scripts/check_version_sync.sh
bash scripts/release_scope_check.sh

if [[ "$allow_empty_unreleased" -eq 0 ]]; then
  python3 - <<'PY'
from pathlib import Path
import re

raw = Path("CHANGELOG.md").read_text(encoding="utf-8")
marker = "## [Unreleased]"
if marker not in raw:
    raise SystemExit("Preflight failed: CHANGELOG.md missing '## [Unreleased]'.")

start = raw.find(marker) + len(marker)
end = raw.find("\n## [", start)
if end == -1:
    end = len(raw)
body = raw[start:end].strip()
if not body:
    raise SystemExit("Preflight failed: CHANGELOG [Unreleased] is empty.")
if body == "- _No unreleased entries yet._":
    raise SystemExit("Preflight failed: CHANGELOG [Unreleased] still has placeholder text.")
if not re.search(r"(?m)^\s*[-*]\s+\S+", body):
    raise SystemExit("Preflight failed: CHANGELOG [Unreleased] has no bullet entries.")
PY
fi

if [[ "$allow_empty_unreleased" -eq 1 ]]; then
  echo "Preflight note: allowing placeholder/empty CHANGELOG [Unreleased] for a post-cut release branch."
fi

echo "Release preflight passed."
