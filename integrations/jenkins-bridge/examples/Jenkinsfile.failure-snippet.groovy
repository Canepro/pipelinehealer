// Use absolute paths so capture/send scripts work when stages run inside dir() blocks.
// Call writeLogExcerpt() with no args (workspace-relative path) so fileExists/readFile work correctly.

stage('Validation') {
  steps {
    sh '''
      cat <<'SCRIPT' | sh "${WORKSPACE}/.jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh" "${WORKSPACE}/.pipelinehealer-log-excerpt.txt"
      ./scripts/run-validation.sh
SCRIPT
    '''
  }
}

post {
  failure {
    script {
      if (fileExists('.jenkins/scripts/send-pipelinehealer-bridge.sh')) {
        if (fileExists('.jenkins/scripts/pipelinehealer-bridge-evidence.groovy')) {
          def bridgeEvidence = load '.jenkins/scripts/pipelinehealer-bridge-evidence.groovy'
          bridgeEvidence.writeLogExcerpt()
        }
        sh '''
          set +e
          if [ -f "${WORKSPACE}/.jenkins/scripts/prepare-failure-tooling.sh" ]; then
            bash "${WORKSPACE}/.jenkins/scripts/prepare-failure-tooling.sh" || true
          fi
          export PH_REPOSITORY="owner/repo"
          export PH_FAILURE_STAGE="validation"
          export PH_FAILURE_SUMMARY="Jenkins validation failed"
          if [ -f "${WORKSPACE}/.pipelinehealer-log-excerpt.txt" ]; then
            export PH_LOG_EXCERPT_FILE="${WORKSPACE}/.pipelinehealer-log-excerpt.txt"
          fi
          bash "${WORKSPACE}/.jenkins/scripts/send-pipelinehealer-bridge.sh" >/dev/null || \
            echo "WARNING: Failed to notify PipelineHealer bridge"
        '''
      }
    }
  }
  cleanup {
    cleanWs()
  }
}
