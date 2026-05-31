#!/bin/sh
set -eu

# Local compose default; Azure sets this via container app env vars.
: "${BACKEND_UPSTREAM:=http://backend:8000}"
: "${API_AUTH_KEY:=}"
: "${VITE_AUTH_MODE:=none}"
: "${VITE_ENTRA_TENANT_ID:=}"
: "${VITE_ENTRA_CLIENT_ID:=}"
: "${VITE_ENTRA_AUTHORITY:=}"
: "${VITE_ENTRA_API_SCOPE:=}"
: "${VITE_ENTRA_REDIRECT_URI:=}"
: "${VITE_ENTRA_POST_LOGOUT_REDIRECT_URI:=}"
: "${VITE_API_URL:=}"
: "${VITE_API_AUTH_KEY:=}"
: "${VITE_API_TIMEOUT_MS:=15000}"

case "$(printf '%s' "$VITE_AUTH_MODE" | tr '[:upper:]' '[:lower:]')" in
  entra)
    API_PROXY_AUTH_HEADER=""
    ;;
  *)
    if [ -n "$API_AUTH_KEY" ]; then
      API_PROXY_AUTH_HEADER="proxy_set_header X-API-Key ${API_AUTH_KEY};"
    else
      API_PROXY_AUTH_HEADER=""
    fi
    ;;
esac
export API_PROXY_AUTH_HEADER

# shellcheck disable=SC2016 # envsubst needs literal variable names here.
envsubst '${BACKEND_UPSTREAM} ${API_PROXY_AUTH_HEADER}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

js_escape() {
  # Minimal JSON-string-safe escaping for runtime config values.
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\r\n' '  '
}

cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__PH_RUNTIME_CONFIG__ = Object.freeze({
  VITE_AUTH_MODE: "$(js_escape "$VITE_AUTH_MODE")",
  VITE_ENTRA_TENANT_ID: "$(js_escape "$VITE_ENTRA_TENANT_ID")",
  VITE_ENTRA_CLIENT_ID: "$(js_escape "$VITE_ENTRA_CLIENT_ID")",
  VITE_ENTRA_AUTHORITY: "$(js_escape "$VITE_ENTRA_AUTHORITY")",
  VITE_ENTRA_API_SCOPE: "$(js_escape "$VITE_ENTRA_API_SCOPE")",
  VITE_ENTRA_REDIRECT_URI: "$(js_escape "$VITE_ENTRA_REDIRECT_URI")",
  VITE_ENTRA_POST_LOGOUT_REDIRECT_URI: "$(js_escape "$VITE_ENTRA_POST_LOGOUT_REDIRECT_URI")",
  VITE_API_URL: "$(js_escape "$VITE_API_URL")",
  VITE_API_AUTH_KEY: "$(js_escape "$VITE_API_AUTH_KEY")",
  VITE_API_TIMEOUT_MS: "$(js_escape "$VITE_API_TIMEOUT_MS")"
})
EOF

exec nginx -g "daemon off;"
