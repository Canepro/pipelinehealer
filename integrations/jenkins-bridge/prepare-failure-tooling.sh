#!/bin/sh
set -u

warn() {
  echo "Failure tooling bootstrap: $*" >&2
}

missing_tools() {
  missing=""
  for tool in bash curl jq openssl tail tee tr; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing="$missing $tool"
    fi
  done
  printf '%s\n' "${missing# }"
}

MISSING="$(missing_tools)"
[ -z "$MISSING" ] && exit 0

warn "missing tools:${MISSING}"

if command -v apk >/dev/null 2>&1; then
  apk add --no-cache bash ca-certificates coreutils curl jq openssl >/dev/null 2>&1 || {
    warn "apk install failed"
    exit 0
  }
  update-ca-certificates >/dev/null 2>&1 || true
  exit 0
fi

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update >/dev/null 2>&1 || {
    warn "apt-get update failed"
    exit 0
  }
  apt-get install -y bash ca-certificates coreutils curl jq openssl >/dev/null 2>&1 || {
    warn "apt-get install failed"
    exit 0
  }
  update-ca-certificates >/dev/null 2>&1 || true
  exit 0
fi

warn "no supported package manager found; continuing without installing tools"
exit 0
