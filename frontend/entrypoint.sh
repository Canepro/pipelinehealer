#!/bin/sh
set -eu

# Local compose default; Azure sets this via container app env vars.
: "${BACKEND_UPSTREAM:=http://backend:8000}"

envsubst '${BACKEND_UPSTREAM}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g "daemon off;"
