#!/usr/bin/env bash
set -euo pipefail

# Safe pytest wrapper to avoid indefinitely stuck runs.
# Usage:
#   bash scripts/pytest_safe.sh backend/tests -q
#   PYTEST_TIMEOUT_SECONDS=2400 bash scripts/pytest_safe.sh backend/tests -q

TIMEOUT_SECONDS="${PYTEST_TIMEOUT_SECONDS:-1800}" # 30 min default
CAPTURE_MODE="${PYTEST_CAPTURE_MODE:-no}" # default to no capture to avoid pytest tmpfile errors in some WSL setups

PYTEST_ARGS=("$@")
HAS_CAPTURE_FLAG=false

for arg in "${PYTEST_ARGS[@]}"; do
  if [[ "$arg" == --capture* || "$arg" == -s ]]; then
    HAS_CAPTURE_FLAG=true
    break
  fi
done

if [[ "$HAS_CAPTURE_FLAG" == false ]]; then
  PYTEST_ARGS=(--capture="$CAPTURE_MODE" "${PYTEST_ARGS[@]}")
fi

if command -v timeout >/dev/null 2>&1; then
  exec timeout --foreground --signal=TERM --kill-after=30s "${TIMEOUT_SECONDS}s" \
    python3 -m pytest "${PYTEST_ARGS[@]}"
fi

echo "warning: 'timeout' command not found; running pytest without timeout guard" >&2
exec python3 -m pytest "${PYTEST_ARGS[@]}"
