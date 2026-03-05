#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script. Run it as:" >&2
  echo "  bash scripts/release_scope_check.sh" >&2
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

need_cmd git
need_cmd python3

cd "$REPO_ROOT"

if [[ ! -f CHANGELOG.md ]]; then
  echo "CHANGELOG.md is missing." >&2
  exit 1
fi

latest_tag="${RELEASE_SCOPE_BASE_TAG:-}"
if [[ -z "$latest_tag" ]]; then
  # Prefer highest SemVer tag instead of nearest-ancestor tag so the check
  # remains stable when repository history was rewritten/grafted.
  latest_tag="$(
    git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -n1
  )"
fi

if [[ -z "$latest_tag" ]]; then
  latest_tag="$(git describe --tags --abbrev=0 2>/dev/null || true)"
fi
if [[ -z "$latest_tag" ]]; then
  echo "No release tags found. Skipping release scope check."
  exit 0
fi

if ! git rev-parse -q --verify "refs/tags/${latest_tag}" >/dev/null 2>&1; then
  echo "Release scope check failed: tag '${latest_tag}' does not exist." >&2
  exit 1
fi

mapfile -t commit_rows < <(git log --pretty=format:'%h%x09%s' "${latest_tag}..HEAD")
if [[ ${#commit_rows[@]} -eq 0 ]]; then
  echo "Release scope OK: no commits since ${latest_tag}."
  exit 0
fi

# A commit cannot reference its own hash in CHANGELOG prior to being created.
# We validate all commits except current HEAD; HEAD is expected to be captured by
# a subsequent changelog update/commit before cutting a release.
commit_rows=("${commit_rows[@]:1}")
if [[ ${#commit_rows[@]} -eq 0 ]]; then
  echo "Release scope OK: only current HEAD is ahead of ${latest_tag}."
  exit 0
fi

unreleased_body="$(
python3 - <<'PY'
from pathlib import Path

raw = Path("CHANGELOG.md").read_text(encoding="utf-8")
marker = "## [Unreleased]"
if marker not in raw:
    raise SystemExit("CHANGELOG.md must contain '## [Unreleased]'.")

start = raw.find(marker) + len(marker)
end = raw.find("\n## [", start)
if end == -1:
    end = len(raw)

print(raw[start:end].strip())
PY
)"

if [[ -z "$unreleased_body" ]]; then
  echo "Unreleased section is empty. Add entries for commits since ${latest_tag}." >&2
  exit 1
fi

missing=()
for row in "${commit_rows[@]}"; do
  hash="${row%%$'\t'*}"
  subject="${row#*$'\t'}"
  if [[ "$unreleased_body" != *"$hash"* ]]; then
    missing+=("${hash} ${subject}")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "Release scope check failed: commits since ${latest_tag} missing from CHANGELOG [Unreleased]." >&2
  echo "Missing commit references:" >&2
  for row in "${missing[@]}"; do
    echo "  - ${row}" >&2
  done
  echo >&2
  echo "Add each short commit hash (for example: \`abc1234\`) in relevant Unreleased bullets." >&2
  exit 1
fi

echo "Release scope OK: all ${#commit_rows[@]} non-HEAD commits since ${latest_tag} are referenced in CHANGELOG [Unreleased]."
