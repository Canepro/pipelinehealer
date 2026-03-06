#!/usr/bin/env bash
set -euo pipefail

# Safe pytest wrapper to avoid indefinitely stuck runs.
# Usage:
#   bash scripts/pytest_safe.sh backend/tests -q
#   PYTEST_TIMEOUT_SECONDS=2400 bash scripts/pytest_safe.sh backend/tests -q

TIMEOUT_SECONDS="${PYTEST_TIMEOUT_SECONDS:-1800}" # 30 min default

if command -v timeout >/dev/null 2>&1; then
  exec timeout --foreground --signal=TERM --kill-after=30s "${TIMEOUT_SECONDS}s" \
    python3 -m pytest "$@"
fi

echo "warning: 'timeout' command not found; running pytest without timeout guard" >&2
exec python3 -m pytest "$@"
