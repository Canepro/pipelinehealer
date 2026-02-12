#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Reset demo-repo to ensure dependency/lint failure scenarios are reproducible.

Usage:
  scripts/demo/reset_demo_fixtures.sh [--repo-dir <path>] [--remote <name>] [--branch <name>] [--skip-push]

Options:
  --repo-dir <path>   Demo repo checkout path (default: ./demo-repo)
  --remote <name>     Git remote name (default: origin)
  --branch <name>     Branch to update (default: main)
  --skip-push         Do not push after commit
  -h, --help          Show this help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DEMO_REPO_DIR="$REPO_ROOT/demo-repo"
REMOTE_NAME="origin"
BRANCH_NAME="main"
SKIP_PUSH="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      DEMO_REPO_DIR="$2"
      shift 2
      ;;
    --remote)
      REMOTE_NAME="$2"
      shift 2
      ;;
    --branch)
      BRANCH_NAME="$2"
      shift 2
      ;;
    --skip-push)
      SKIP_PUSH="1"
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

if [[ ! -d "$DEMO_REPO_DIR/.git" ]]; then
  echo "Demo repo not found at: $DEMO_REPO_DIR" >&2
  exit 1
fi

for cmd in git node; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

pushd "$DEMO_REPO_DIR" >/dev/null

AUTOSTASH_CREATED="0"
AUTOSTASH_REF=""
AUTOSTASH_TAG=""

restore_autostash() {
  if [[ "$AUTOSTASH_CREATED" == "1" && -n "$AUTOSTASH_REF" ]]; then
    echo "Restoring local demo-repo changes from autostash..."
    # If pop conflicts, keep stash entry so user can recover manually.
    git stash pop "$AUTOSTASH_REF" >/dev/null || {
      echo "Autostash restore had conflicts. Stash kept as: $AUTOSTASH_REF" >&2
    }
  fi
}

# Keep this after pushd so local edits do not break one-command demo flows.
trap restore_autostash EXIT

if ! git diff --quiet || ! git diff --cached --quiet || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
  AUTOSTASH_TAG="pipelinehealer-demo-reset-autostash-$(date +%s)"
  git stash push -u -m "$AUTOSTASH_TAG" >/dev/null
  AUTOSTASH_REF="$(
    git stash list --format='%gd %s' \
      | awk -v tag="$AUTOSTASH_TAG" 'index($0, tag) { print $1; exit }'
  )"
  if [[ -n "$AUTOSTASH_REF" ]]; then
    AUTOSTASH_CREATED="1"
  fi
fi

git checkout "$BRANCH_NAME"
git pull --ff-only "$REMOTE_NAME" "$BRANCH_NAME"

# Ensure dependency failure fixture exists by removing left-pad from package.json.
node -e 'const fs=require("fs");const p=JSON.parse(fs.readFileSync("package.json","utf8"));if(p.dependencies){delete p.dependencies["left-pad"];}fs.writeFileSync("package.json",JSON.stringify(p,null,2)+"\n");'

# Ensure lint failure fixture exists by removing ESLint v9 flat config.
rm -f eslint.config.js

if ! git diff --quiet; then
  git add package.json eslint.config.js
  git commit -m "chore: reset demo fixtures for dependency/lint failure scenarios"
  if [[ "$SKIP_PUSH" != "1" ]]; then
    if ! git push "$REMOTE_NAME" "$BRANCH_NAME"; then
      git pull --rebase "$REMOTE_NAME" "$BRANCH_NAME"
      git push "$REMOTE_NAME" "$BRANCH_NAME"
    fi
  fi
  echo "Demo fixtures reset complete."
else
  if [[ "$SKIP_PUSH" != "1" ]]; then
    AHEAD_COUNT="$(git rev-list --count "${REMOTE_NAME}/${BRANCH_NAME}..HEAD" 2>/dev/null || echo "0")"
    if [[ "$AHEAD_COUNT" != "0" ]]; then
      git push "$REMOTE_NAME" "$BRANCH_NAME"
      echo "No new fixture changes needed; pushed $AHEAD_COUNT pending commit(s)."
    else
      echo "No fixture changes needed."
    fi
  else
    echo "No fixture changes needed."
  fi
fi

popd >/dev/null
