#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash integrations/jenkins-bridge/install.sh <target-repo> [--with-examples]

Copies the supported PipelineHealer Jenkins bridge assets into the target repo:
  .jenkins/scripts/send-pipelinehealer-bridge.sh
  .jenkins/scripts/prepare-failure-tooling.sh
  .jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh
  .jenkins/scripts/pipelinehealer-bridge-evidence.groovy

Optional:
  --with-examples   also copy .jenkins/examples/Jenkinsfile.failure-snippet.groovy
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 1
fi

TARGET_REPO="$1"
WITH_EXAMPLES="${2:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "$WITH_EXAMPLES" && "$WITH_EXAMPLES" != "--with-examples" ]]; then
  echo "Unknown option: $WITH_EXAMPLES" >&2
  usage
  exit 1
fi

if [[ ! -d "$TARGET_REPO" ]]; then
  echo "Target repo does not exist: $TARGET_REPO" >&2
  exit 1
fi

mkdir -p "$TARGET_REPO/.jenkins/scripts"

cp "$SCRIPT_DIR/send-pipelinehealer-bridge.sh" \
  "$TARGET_REPO/.jenkins/scripts/send-pipelinehealer-bridge.sh"
cp "$SCRIPT_DIR/prepare-failure-tooling.sh" \
  "$TARGET_REPO/.jenkins/scripts/prepare-failure-tooling.sh"
cp "$SCRIPT_DIR/capture-pipelinehealer-bridge-excerpt.sh" \
  "$TARGET_REPO/.jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh"
cp "$SCRIPT_DIR/pipelinehealer-bridge-evidence.groovy" \
  "$TARGET_REPO/.jenkins/scripts/pipelinehealer-bridge-evidence.groovy"

chmod +x "$TARGET_REPO/.jenkins/scripts/send-pipelinehealer-bridge.sh"
chmod +x "$TARGET_REPO/.jenkins/scripts/prepare-failure-tooling.sh"
chmod +x "$TARGET_REPO/.jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh"

if [[ "$WITH_EXAMPLES" == "--with-examples" ]]; then
  mkdir -p "$TARGET_REPO/.jenkins/examples"
  cp "$SCRIPT_DIR/examples/Jenkinsfile.failure-snippet.groovy" \
    "$TARGET_REPO/.jenkins/examples/Jenkinsfile.failure-snippet.groovy"
fi

cat <<EOF
Installed PipelineHealer Jenkins bridge assets into:
  $TARGET_REPO/.jenkins/scripts

Next steps:
1. Use absolute paths for capture/send scripts (\${WORKSPACE}/.jenkins/scripts/...) when stages use dir().
2. In post { failure }, load pipelinehealer-bridge-evidence.groovy and call writeLogExcerpt() before sending.
3. Export PH_REPOSITORY, PH_FAILURE_STAGE, PH_FAILURE_SUMMARY, and PH_LOG_EXCERPT_FILE; then run send-pipelinehealer-bridge.sh.
4. Keep workspace cleanup in post { cleanup { ... } }.
EOF
