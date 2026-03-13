# Jenkins Bridge Integration Kit

<!-- LAST_VERIFIED: 49948c6 -->

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
    only when the wrapped command fails (no file on success).
  - Preserves the wrapped command's exit code.
  - Invoke with absolute path (e.g. `"${WORKSPACE}/.jenkins/scripts/capture-..."`)
    when the stage runs inside a `dir()` block.
- `pipelinehealer-bridge-evidence.groovy`
  - Groovy helper that synthesizes a log excerpt when the shell capture wrapper
    did not run (e.g. failure before the wrapped step). Fetches `${BUILD_URL}consoleText`
    via Jenkins API (optional `jenkins-api-token` credential; falls back to
    unauthenticated). Use workspace-relative paths or call `writeLogExcerpt()` with
    no args so `fileExists`/`readFile` work correctly.
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

1. Use **absolute paths** for capture and send scripts
   (`"${WORKSPACE}/.jenkins/scripts/..."`) so they resolve when stages run
   inside `dir()` blocks.
2. Wrap the shell step most likely to fail with the shell capture helper.
3. In `post { failure }`, load `pipelinehealer-bridge-evidence.groovy` and call
   `writeLogExcerpt()` (no args) before sending, so setup/bootstrap failures
   still produce log evidence.
4. Export `PH_LOG_EXCERPT_FILE` from the failure block before invoking the
   sender; use `bash "${WORKSPACE}/.jenkins/scripts/send-pipelinehealer-bridge.sh"`.
5. Keep workspace cleanup in `post { cleanup { ... } }`, not before the bridge
   notifier runs.

Optional structured bridge fields:

- `PH_FAILURE_COMMAND` — explicit failing command
- `PH_FAILURE_RESULT` — stage/step result when it differs from the overall job result
- `PH_FAILURE_TOOL` — tool name (`terraform`, `checkov`, `trivy`, etc.)
- `PH_FAILURE_EXIT_CODE` — numeric exit code
- `PH_FAILURE_ERROR_LINES` — newline-delimited extracted error lines

These are additive hints. The bridge remains backward-compatible when they are absent.

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
      cat <<'SCRIPT' | sh "${WORKSPACE}/.jenkins/scripts/capture-pipelinehealer-bridge-excerpt.sh" "${WORKSPACE}/.pipelinehealer-log-excerpt.txt"
      terraform plan -no-color -input=false -out=tfplan
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
            sh "${WORKSPACE}/.jenkins/scripts/prepare-failure-tooling.sh" || true
          fi
          export PH_REPOSITORY="owner/repo"
          export PH_FAILURE_STAGE="terraform-plan"
          export PH_FAILURE_SUMMARY="Jenkins Terraform plan failed"
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
```

## Why This Pattern Is Preferred

Use the shell capture helper for the step most likely to fail; use the Groovy
evidence helper as a fallback when no excerpt file exists (e.g. failure before the
wrapped step). The Groovy helper fetches `${BUILD_URL}/consoleText` so
PipelineHealer still gets log evidence instead of summary-only.

Benefits:

- direct excerpt capture avoids controller memory and auth when the wrapped step ran
- consoleText fallback covers setup/bootstrap failures without rawBuild script approval
- absolute script paths work inside `dir()` blocks; workspace-relative paths for
  `writeLogExcerpt()` keep `fileExists`/`readFile` correct
- sends bounded, LLM-usable evidence instead of only a short summary
- stays portable across multibranch, PR, and scheduled Jenkins jobs

For the backend contract, see
[docs/reference/API.md](../../docs/reference/API.md).

For the minimal snippet, see
[examples/Jenkinsfile.failure-snippet.groovy](examples/Jenkinsfile.failure-snippet.groovy).
