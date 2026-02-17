import type { AdminSettingsAuditEntry, AppSettings } from '../../api/client'

export type SettingsFormState = {
  llm_provider: 'azure_openai' | 'openai_compatible' | 'custom'
  heal_mode: 'safe' | 'demo' | 'debug'
  auto_create_pr: boolean
  auto_create_tracking_issue_for_prs: boolean
  max_remediation_attempts: number
  verify_webhook_signature_in_development: boolean
  pipeline_step_timeout_seconds: number
  github_api_max_retries: number
  github_api_retry_base_seconds: number
  github_api_retry_max_seconds: number
  log_prompt_max_chars: number
  log_prompt_head_chars: number
  log_prompt_tail_chars: number
  gh_aw_tools_enabled: boolean
  gh_aw_ingestion_mode: 'disabled' | 'passive'
  gh_aw_known_workflows: string[]
  ph_allowed_repos: string[]
  azure_openai_deployment_name: string
}

export const REPO_FULL_NAME_REGEX = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

export const normalizeRepoInput = (value: string): string | null => {
  const text = value.trim()
  if (!text) return null

  let candidate = text
  try {
    const parsed = new URL(text)
    const host = parsed.hostname.toLowerCase()
    if (host !== 'github.com' && host !== 'www.github.com') return null
    const parts = parsed.pathname
      .replace(/^\/+|\/+$/g, '')
      .replace(/\.git$/i, '')
      .split('/')
      .filter(Boolean)
    if (parts.length !== 2) return null
    candidate = `${parts[0]}/${parts[1]}`
  } catch {
    if (text.startsWith('git@github.com:')) {
      candidate = text.slice('git@github.com:'.length).replace(/\.git$/i, '')
    }
  }

  candidate = candidate.replace(/^\/+|\/+$/g, '').replace(/\.git$/i, '').toLowerCase()
  if (!REPO_FULL_NAME_REGEX.test(candidate)) return null
  return candidate
}

export const toSettingsForm = (data: AppSettings): SettingsFormState => ({
  llm_provider:
    data.llm_provider === 'openai_compatible'
      ? 'openai_compatible'
      : data.llm_provider === 'custom'
        ? 'custom'
        : 'azure_openai',
  heal_mode: data.heal_mode === 'demo' ? 'demo' : data.heal_mode === 'debug' ? 'debug' : 'safe',
  auto_create_pr: data.auto_create_pr,
  auto_create_tracking_issue_for_prs: data.auto_create_tracking_issue_for_prs,
  max_remediation_attempts: data.max_remediation_attempts,
  verify_webhook_signature_in_development: data.verify_webhook_signature_in_development,
  pipeline_step_timeout_seconds: data.pipeline_step_timeout_seconds,
  github_api_max_retries: data.github_api_max_retries,
  github_api_retry_base_seconds: data.github_api_retry_base_seconds,
  github_api_retry_max_seconds: data.github_api_retry_max_seconds,
  log_prompt_max_chars: data.log_prompt_max_chars,
  log_prompt_head_chars: data.log_prompt_head_chars,
  log_prompt_tail_chars: data.log_prompt_tail_chars,
  gh_aw_tools_enabled: data.gh_aw_tools_enabled,
  gh_aw_ingestion_mode: data.gh_aw_ingestion_mode === 'passive' ? 'passive' : 'disabled',
  gh_aw_known_workflows: data.gh_aw_known_workflows ?? [],
  ph_allowed_repos: data.ph_allowed_repos ?? [],
  azure_openai_deployment_name: data.azure_openai_deployment_name ?? '',
})

export const formatAuditValue = (value: unknown) => {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value === null || value === undefined) return 'null'
  return JSON.stringify(value)
}

export const isAuditValueEqual = (left: unknown, right: unknown) => {
  if (Object.is(left, right)) return true
  if (typeof left === 'object' && left !== null && typeof right === 'object' && right !== null) {
    try {
      return JSON.stringify(left) === JSON.stringify(right)
    } catch {
      return false
    }
  }
  return false
}

export const getEffectiveAuditChanges = (entry: AdminSettingsAuditEntry) =>
  entry.changed_keys
    .map((key) => ({ key, diff: entry.changes[key] }))
    .filter(({ diff }) => !isAuditValueEqual(diff?.old, diff?.new))

export const formatActorLabel = (actor?: string) => {
  if (!actor) return 'Unknown actor'
  const fingerprintPrefix = 'admin_key:sha256:'
  if (actor.startsWith(fingerprintPrefix)) return `Admin (${actor.slice(fingerprintPrefix.length)})`
  return actor
}

export const formatAuditTimestampUtc = (timestamp: string) =>
  new Date(timestamp).toISOString().replace('T', ' ').slice(0, 19) + ' UTC'

/** Descriptions for each setting field shown to users. */
export const SETTING_DESCRIPTIONS: Record<string, string> = {
  heal_mode:
    'Controls how aggressively PipelineHealer fixes failures. "safe" applies conservative fixes, "demo" is aggressive for demonstrations, "debug" adds verbose logging.',
  auto_create_pr:
    'When enabled, PipelineHealer automatically creates pull requests with proposed fixes for CI failures.',
  auto_create_tracking_issue_for_prs:
    'Creates a GitHub issue to track each PR-based remediation and auto-closes it when the PR merges.',
  max_remediation_attempts:
    'Maximum number of times PipelineHealer will retry fixing a single failure before giving up.',
  azure_openai_deployment_name:
    'The Azure OpenAI model deployment to use for AI analysis (e.g. gpt-4o, gpt-5-mini).',
  llm_provider:
    'Model backend selector. azure_openai is production-ready; openai_compatible and custom are scaffolded for future provider expansion.',
  pipeline_step_timeout_seconds:
    'Maximum seconds each pipeline step (analyze, diagnose, remediate) is allowed to run before timing out.',
  github_api_max_retries:
    'How many times to retry GitHub API calls that fail with rate-limit (429) or server errors (5xx).',
  github_api_retry_base_seconds:
    'Initial delay between GitHub API retries. Each retry doubles the wait (exponential backoff).',
  github_api_retry_max_seconds:
    'Upper limit on the delay between GitHub API retries, regardless of backoff.',
  log_prompt_max_chars:
    'Maximum total characters from CI logs sent to the AI model for analysis.',
  log_prompt_head_chars:
    'Characters kept from the beginning of CI logs when they need to be truncated.',
  log_prompt_tail_chars:
    'Characters kept from the end of CI logs when they need to be truncated (error messages are usually at the end).',
  gh_aw_tools_enabled:
    'Master switch for GitHub Agentic Workflows integration. When off, no external diagnostics are collected.',
  gh_aw_ingestion_mode:
    'How external diagnostics are collected. "passive" reads findings from GitHub issues. "disabled" turns collection off.',
  gh_aw_known_workflows:
    'Workflows to skip when polling ci-doctor (prevents circular self-diagnosis). ci-doctor is always included.',
  verify_webhook_signature_in_development:
    'Require GitHub webhook signature verification even in development mode. Usually off for local testing.',
  ph_allowed_repos:
    'Restrict PipelineHealer to only process CI failures from these repositories. Leave empty to allow all.',
}
