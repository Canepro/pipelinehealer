# Jenkins Bridge Integration Kit

<!-- LAST_VERIFIED: c78ae9b -->

Reusable Jenkins-side assets for PipelineHealer's signed Jenkins bridge.

Use this kit when Jenkins is the primary CI system and you want failed jobs to
create PipelineHealer activities with direct, bounded failure evidence instead
of summary-only bridge context.

## Support Stance

Recommended rollout order:

1. Use these files as a repo-local drop-in under `.jenkins/scripts/`.
2. Standardize the same pattern later via a Jenkins Shared Library if your
   controller manages many repos.
3. Keep the sender shell-based so it works on vanilla controllers and does not
   require a custom Jenkins plugin.

Preferred Jenkins support:

- no extra plugin required for the supported shell-capture path
- optional: Jenkins Shared Libraries for org-wide reuse
- optional: `Pipeline Utility Steps` if you want a Groovy `tee` wrapper locally
- intentionally avoided: `currentBuild.rawBuild` or other script-approval-heavy
  APIs, because they do not scale cleanly across OSS or locked-down controllers

## Files

- `install.sh`
  - Copies the supported bridge assets into a target repo's
    `.jenkins/scripts/` directory
  - Optionally copies examples into `.jenkins/examples/`
- `send-pipelinehealer-bridge.sh`
  - Signs and sends the Jenkins bridge payload to `POST /webhook/jenkins`
  - Prefers `PH_LOG_EXCERPT_FILE` or `PH_LOG_EXCERPT`
  - Falls back to a best-effort `consoleText` scrape only when no direct
    excerpt is provided
  - Infers repository and commit metadata when Jenkins env wiring is partial
- `prepare-failure-tooling.sh`
  - Installs minimal failure-path dependencies on common agent images
  - Keeps bridge notification best-effort instead of turning a tooling miss
    into a second failure
- `capture-pipelinehealer-bridge-excerpt.sh`
  - Captures the stdout/stderr of an inline shell script into a workspace file
  - Preserves the wrapped command's exit code
  - Works on stock Jenkins agents without requiring the Jenkins `tee` step
- `pipelinehealer-bridge-evidence.groovy`
  - Optional Groovy helper when your controller already supports the Jenkins
    `tee` step
  - Not the required path for OSS portability
- `examples/Jenkinsfile.failure-snippet.groovy`
  - Minimal failure-path pattern for direct use or Shared Library wrapping

## Install

From the PipelineHealer repo root:

```bash
bash integrations/jenkins-bridge/install.sh /path/to/your-repo --with-examples
```

That creates:

- `.jenkins/scripts/send-pipelinehealer-bridge.sh`
- `.jenkins/scripts/prepare-failure-tooling.sh`
- `.jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh`
- `.jenkins/scripts/pipelinehealer-bridge-evidence.groovy`
- optional: `.jenkins/examples/Jenkinsfile.failure-snippet.groovy`

## Recommended Jenkinsfile Pattern

1. Wrap the shell step most likely to fail with the shell capture helper.
2. Export `PH_LOG_EXCERPT_FILE` from the failure block before invoking the
   sender.
3. Keep workspace cleanup in `post { cleanup { ... } }`, not before the bridge
   notifier runs.

Important Groovy/Jenkinsfile note:

- prefer `sh '''...'''` for these shell blocks so `${WORKSPACE}` and similar
  env references are expanded by the shell, not by Groovy
- if you intentionally use `sh """..."""`, escape Jenkins env references as
  `\${WORKSPACE}`, `\${BUILD_URL}`, and similar, or use `${env.WORKSPACE}`
  explicitly
- this matters for excerpt paths and generated output filenames; unescaped
  GString interpolation can fail before the bridge helper runs

Example:

```groovy
stage('Terraform Plan') {
  steps {
    sh '''
      cat <<'SCRIPT' | sh .jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh "${WORKSPACE}/.pipelinehealer-log-excerpt.txt"
      terraform plan -no-color -input=false -out=tfplan
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
        export PH_FAILURE_STAGE="terraform-plan"
        export PH_FAILURE_SUMMARY="Jenkins Terraform plan failed"
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
```

## Why This Pattern Is Preferred

Direct workspace excerpt capture is more reliable than scraping
`${BUILD_URL}/consoleText`.

Benefits:

- works even when Jenkins UI/API auth is restricted
- keeps evidence local to the failing build context
- sends bounded, LLM-usable evidence instead of only a short summary
- does not require Jenkins script approval exceptions or extra controller plugins
- stays portable across multibranch, PR, and scheduled Jenkins jobs

For the backend contract and rollout guidance, see
[docs/JENKINS_BRIDGE_TECHNICAL_DESIGN.md](../../docs/JENKINS_BRIDGE_TECHNICAL_DESIGN.md).

For the minimal snippet, see
[examples/Jenkinsfile.failure-snippet.groovy](examples/Jenkinsfile.failure-snippet.groovy).
