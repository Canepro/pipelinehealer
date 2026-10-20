#!/usr/bin/env bash
# Start the PipelineHealer backend with Infisical-injected secrets.
# Local backend/.env stays in place; Infisical supplies runtime secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

PROJECT_ID="${INFISICAL_PROJECT_ID:-70ae1697-055c-4fc1-ba90-85b25f6bf138}"
ENV_NAME="${INFISICAL_ENVIRONMENT:-dev}"
SECRET_PATH="${INFISICAL_SECRET_PATH:-/personal/pipelinehealer}"
PORT="${API_PORT:-8000}"

exec infisical run \
  --env "$ENV_NAME" \
  --path "$SECRET_PATH" \
  --projectId "$PROJECT_ID" \
  -- uvicorn src.main:app --reload --host 127.0.0.1 --port "$PORT"
