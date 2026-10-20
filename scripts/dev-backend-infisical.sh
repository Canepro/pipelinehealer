#!/usr/bin/env bash
# Start the PipelineHealer backend with Infisical-injected secrets.
# Local backend/.env stays in place; Infisical supplies runtime secret values.
# Set INFISICAL_PROJECT_ID in the environment or backend/.env metadata first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if [[ -f .env ]]; then
  # Load metadata-only keys without printing values.
  set -a
  # shellcheck disable=SC1090,SC1091
  source <(python3 - <<'PY'
from pathlib import Path
keep = {
  "INFISICAL_PROJECT_ID",
  "INFISICAL_ENVIRONMENT",
  "INFISICAL_SECRET_PATH",
  "INFISICAL_CLI_PATH",
  "API_PORT",
}
for line in Path(".env").read_text().splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    k = k.strip()
    if k not in keep:
        continue
    v = v.strip().strip("'").strip('"')
    # Emit single-quoted assignments so sourced values cannot expand $(...) or $VAR.
    vv = v.replace("'", "'\\''")
    print(f"{k}='{vv}'")
PY
)
  set +a
fi

PROJECT_ID="${INFISICAL_PROJECT_ID:-}"
ENV_NAME="${INFISICAL_ENVIRONMENT:-dev}"
SECRET_PATH="${INFISICAL_SECRET_PATH:-/personal/pipelinehealer}"
PORT="${API_PORT:-8000}"
INFISICAL_BIN="${INFISICAL_CLI_PATH:-infisical}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "INFISICAL_PROJECT_ID is required. Set it in backend/.env metadata or the environment." >&2
  exit 2
fi

UVICORN_CMD=(uvicorn)
if [[ -x "$ROOT/backend/.venv/bin/uvicorn" ]]; then
  UVICORN_CMD=("$ROOT/backend/.venv/bin/uvicorn")
elif command -v uv >/dev/null 2>&1; then
  UVICORN_CMD=(uv run uvicorn)
fi

exec "$INFISICAL_BIN" run \
  --env "$ENV_NAME" \
  --path "$SECRET_PATH" \
  --projectId "$PROJECT_ID" \
  -- "${UVICORN_CMD[@]}" src.main:app --reload --host 127.0.0.1 --port "$PORT"
