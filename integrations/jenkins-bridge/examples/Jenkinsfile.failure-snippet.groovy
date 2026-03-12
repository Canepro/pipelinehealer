stage('Validation') {
  steps {
    sh '''
      cat <<'SCRIPT' | sh .jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh "${WORKSPACE}/.pipelinehealer-log-excerpt.txt"
      ./scripts/run-validation.sh
SCRIPT
    '''
  }
}

post {
  failure {
    script {
      sh '''
        set +e
        if [ -f .jenkins/scripts/prepare-failure-tooling.sh ]; then
          sh .jenkins/scripts/prepare-failure-tooling.sh || true
        fi
        export PH_REPOSITORY="owner/repo"
        export PH_FAILURE_STAGE="validation"
        export PH_FAILURE_SUMMARY="Jenkins validation failed"
        if [ -f "${WORKSPACE}/.pipelinehealer-log-excerpt.txt" ]; then
          export PH_LOG_EXCERPT_FILE="${WORKSPACE}/.pipelinehealer-log-excerpt.txt"
        fi
        bash .jenkins/scripts/send-pipelinehealer-bridge.sh >/dev/null || \
          echo "WARNING: Failed to notify PipelineHealer bridge"
      '''
    }
  }
  cleanup {
    cleanWs()
  }
}
