#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/release.sh <patch|minor|major|x.y.z>" >&2
  return 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Release version bump helper.

Usage:
  bash scripts/release.sh <patch|minor|major|x.y.z>

Examples:
  bash scripts/release.sh patch
  bash scripts/release.sh minor
  bash scripts/release.sh 0.2.3

What it updates:
  - VERSION
  - backend/pyproject.toml (project.version)
  - frontend/package.json (version)
  - charts/pipelinehealer/Chart.yaml (version + appVersion)
  - CHANGELOG.md (adds new release section under Unreleased)

This script does NOT commit or tag automatically.
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

bump="$1"

need_cmd python3
need_cmd date
need_cmd bash

cd "$REPO_ROOT"
bash scripts/check_version_sync.sh >/dev/null

current_version="$(tr -d '\r\n' < VERSION)"
if [[ -z "${current_version:-}" ]]; then
  echo "VERSION file is empty." >&2
  exit 1
fi

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

if [[ "$next_version" == "$current_version" ]]; then
  echo "Next version equals current version ($current_version); nothing to do." >&2
  exit 1
fi

release_tag="v$next_version"
release_date="$(date -u +%Y-%m-%d)"

printf '%s\n' "$next_version" > VERSION

CURRENT_VERSION="$current_version" NEXT_VERSION="$next_version" python3 - <<'PY'
import json
import os
import re
from pathlib import Path

repo_root = Path(".")
current = os.environ["CURRENT_VERSION"].strip()
next_version = os.environ["NEXT_VERSION"].strip()

pyproject_path = repo_root / "backend" / "pyproject.toml"
pyproject_raw = pyproject_path.read_text(encoding="utf-8")
updated = re.sub(
    r'^version\s*=\s*"[^"]+"',
    f'version = "{next_version}"',
    pyproject_raw,
    flags=re.MULTILINE,
    count=1,
)
if updated == pyproject_raw:
    raise SystemExit("Failed to update backend/pyproject.toml version.")
pyproject_path.write_text(updated, encoding="utf-8")

pkg_path = repo_root / "frontend" / "package.json"
pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
pkg["version"] = next_version
pkg_path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")

chart_path = repo_root / "charts" / "pipelinehealer" / "Chart.yaml"
chart_raw = chart_path.read_text(encoding="utf-8")
updated_chart = re.sub(
    r"^version\s*:\s*.*$",
    f"version: {next_version}",
    chart_raw,
    flags=re.MULTILINE,
    count=1,
)
updated_chart = re.sub(
    r'^appVersion\s*:\s*.*$',
    f'appVersion: "{next_version}"',
    updated_chart,
    flags=re.MULTILINE,
    count=1,
)
if updated_chart == chart_raw:
    raise SystemExit("Failed to update charts/pipelinehealer/Chart.yaml version fields.")
chart_path.write_text(updated_chart, encoding="utf-8")
PY

if [[ ! -f CHANGELOG.md ]]; then
  cat > CHANGELOG.md <<'EOF'
# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this repo uses Semantic Versioning.

## [Unreleased]

- _No unreleased entries yet._
EOF
fi

RELEASE_TAG="$release_tag" RELEASE_DATE="$release_date" python3 - <<'PY'
import os
from pathlib import Path

changelog_path = Path("CHANGELOG.md")
raw = changelog_path.read_text(encoding="utf-8")
release_tag = os.environ["RELEASE_TAG"]
release_date = os.environ["RELEASE_DATE"]

marker = "## [Unreleased]"
if marker not in raw:
    raise SystemExit("CHANGELOG.md must contain '## [Unreleased]'")

start = raw.find(marker)
end = raw.find("\n## [", start + len(marker))
if end == -1:
    end = len(raw)

unreleased_body = raw[start + len(marker):end].strip()
if unreleased_body and unreleased_body != "- _No unreleased entries yet._":
    release_body = unreleased_body
else:
    release_body = (
        "### Added\n\n"
        "- _Describe new features here._\n\n"
        "### Changed\n\n"
        "- _Describe behavior changes here._\n\n"
        "### Fixed\n\n"
        "- _Describe fixes here._"
    )

insert = (
    f"{marker}\n\n"
    f"- _No unreleased entries yet._\n\n"
    f"## [{release_tag}] - {release_date}\n\n"
    f"{release_body}\n"
)

new_raw = raw[:start] + insert + raw[end:]
changelog_path.write_text(new_raw.rstrip() + "\n", encoding="utf-8")
PY

echo "Release files updated."
echo "  Current : $current_version"
echo "  Next    : $next_version"
echo "  Tag     : $release_tag"
echo "  Date    : $release_date"
echo
echo "Next steps:"
echo "  1) Edit CHANGELOG.md release notes under [$release_tag]"
echo "  2) git add VERSION backend/pyproject.toml frontend/package.json charts/pipelinehealer/Chart.yaml CHANGELOG.md"
echo "  3) git commit -m \"chore(release): $release_tag\""
echo "  4) git tag -a $release_tag -m \"Release $release_tag\""
echo "  5) git push origin main --follow-tags"
