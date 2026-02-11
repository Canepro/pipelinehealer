#!/bin/sh
set -eu

# Local compose default; Azure sets this via container app env vars.
: "${BACKEND_UPSTREAM:=http://backend:8000}"
: "${API_AUTH_KEY:=}"

envsubst '${BACKEND_UPSTREAM} ${API_AUTH_KEY}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g "daemon off;"
