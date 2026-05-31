import type { AdminSettingsAuditEntry, AppSettings } from '../../api/client'

export type SettingsFormState = {
  llm_provider: 'azure_openai' | 'openai_compatible' | 'codex_app_server' | 'custom'
  openai_compatible_base_url: string
  openai_compatible_model: string
  codex_app_server_transport: 'stdio' | 'websocket'
  codex_app_server_command: string
  codex_app_server_model: string
  codex_app_server_turn_timeout_ms: number
  codex_app_server_ws_url: string
  codex_app_server_ws_allow_remote: boolean
  llm_model_analysis: string
  llm_model_diagnosis: string
  llm_model_remediation: string
  mcp_enabled: boolean
  mcp_provider: 'disabled' | 'github' | 'azure_monitor' | 'custom'
  mcp_read_only: boolean
  mcp_timeout_seconds: number
  mcp_max_retries: number
  mcp_tool_policies: Record<string, 'disabled' | 'read_only' | 'write_with_approval' | 'auto'>
  mcp_repo_allowlist: string[]
  heal_mode: 'safe' | 'demo' | 'freestyle' | 'debug'
  auto_apply_remediation: boolean
  auto_create_pr: boolean
  jenkins_bridge_allow_pr: boolean
  auto_create_issue: boolean
  auto_retry_workflow: boolean
  auto_create_tracking_issue_for_prs: boolean
  auto_merge_remediation_prs: boolean
  auto_merge_strategy: 'github_auto_merge' | 'merge_when_clean'
  auto_merge_poll_seconds: number
  auto_merge_require_clean_checks: boolean
  max_remediation_attempts: number
  verify_webhook_signature: boolean
  verify_webhook_signature_in_development: boolean
  pipeline_step_timeout_seconds: number
  github_api_max_retries: number
  github_api_retry_base_seconds: number
  github_api_retry_max_seconds: number
  log_prompt_max_chars: number
  log_prompt_head_chars: number
  log_prompt_tail_chars: number
  gh_aw_tools_enabled: boolean
  gh_aw_ingestion_mode: 'disabled' | 'passive' | 'hybrid'
  gh_aw_known_workflows: string[]
  agent_handoff_enabled: boolean
  agent_handoff_mode: 'copy_only' | 'webhook'
  agent_handoff_webhook_allowlist: string[]
  agent_handoff_timeout_seconds: number
  agent_handoff_max_retries: number
  agent_handoff_default_target: 'codex_app_server' | 'openclaw' | 'hermes' | 'custom'
  agent_handoff_enabled_targets: Array<'codex_app_server' | 'openclaw' | 'hermes' | 'custom'>
  ph_allowed_repos: string[]
  azure_openai_endpoint: string
  azure_openai_deployment_name: string
  azure_openai_api_version: string
  azure_openai_chat_api_version: string
  github_app_id: string
  jenkins_bridge_enabled: boolean
  jenkins_bridge_max_skew_seconds: number
  jenkins_bridge_replay_ttl_seconds: number
  jenkins_bridge_max_body_bytes: number
}

export const REPO_FULL_NAME_REGEX = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
export const HOSTNAME_REGEX = /^[a-z0-9.-]+$/

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

export const normalizeHostnameInput = (value: string): string | null => {
  const candidate = value.trim().toLowerCase()
  if (!candidate) return null
  if (candidate.includes('://') || candidate.includes('/') || candidate.includes(':')) return null
  if (!HOSTNAME_REGEX.test(candidate)) return null
  return candidate
}

export const toSettingsForm = (data: AppSettings): SettingsFormState => ({
  llm_provider:
    data.llm_provider === 'openai_compatible'
      ? 'openai_compatible'
      : data.llm_provider === 'codex_app_server'
        ? 'codex_app_server'
      : data.llm_provider === 'custom'
        ? 'custom'
        : 'azure_openai',
  openai_compatible_base_url: data.openai_compatible_base_url ?? '',
  openai_compatible_model: data.openai_compatible_model ?? '',
  codex_app_server_transport:
    data.codex_app_server_transport === 'websocket' ? 'websocket' : 'stdio',
  codex_app_server_command: data.codex_app_server_command ?? 'codex app-server',
  codex_app_server_model: data.codex_app_server_model ?? 'gpt-5.4',
  codex_app_server_turn_timeout_ms: data.codex_app_server_turn_timeout_ms ?? 120000,
  codex_app_server_ws_url: data.codex_app_server_ws_url ?? '',
  codex_app_server_ws_allow_remote: data.codex_app_server_ws_allow_remote ?? false,
  llm_model_analysis: data.llm_model_analysis ?? '',
  llm_model_diagnosis: data.llm_model_diagnosis ?? '',
  llm_model_remediation: data.llm_model_remediation ?? '',
  mcp_enabled: data.mcp_enabled ?? false,
  mcp_provider:
    data.mcp_provider === 'github'
      ? 'github'
      : data.mcp_provider === 'azure_monitor'
        ? 'azure_monitor'
        : data.mcp_provider === 'custom'
          ? 'custom'
          : 'disabled',
  mcp_read_only: data.mcp_read_only ?? true,
  mcp_timeout_seconds: data.mcp_timeout_seconds ?? 15,
  mcp_max_retries: data.mcp_max_retries ?? 1,
  mcp_tool_policies: {
    fetch_failure_context:
      data.mcp_tool_policies?.fetch_failure_context === 'disabled'
        ? 'disabled'
        : data.mcp_tool_policies?.fetch_failure_context === 'auto'
          ? 'auto'
          : data.mcp_tool_policies?.fetch_failure_context === 'write_with_approval'
            ? 'write_with_approval'
            : 'read_only',
    fetch_runbook_context:
      data.mcp_tool_policies?.fetch_runbook_context === 'disabled'
        ? 'disabled'
        : data.mcp_tool_policies?.fetch_runbook_context === 'auto'
          ? 'auto'
          : data.mcp_tool_policies?.fetch_runbook_context === 'write_with_approval'
            ? 'write_with_approval'
            : 'read_only',
    publish_artifact:
      data.mcp_tool_policies?.publish_artifact === 'disabled'
        ? 'disabled'
        : data.mcp_tool_policies?.publish_artifact === 'auto'
          ? 'auto'
          : data.mcp_tool_policies?.publish_artifact === 'read_only'
            ? 'read_only'
            : 'write_with_approval',
    rerun_pipeline:
      data.mcp_tool_policies?.rerun_pipeline === 'disabled'
        ? 'disabled'
        : data.mcp_tool_policies?.rerun_pipeline === 'auto'
          ? 'auto'
          : data.mcp_tool_policies?.rerun_pipeline === 'read_only'
            ? 'read_only'
            : 'write_with_approval',
  },
  mcp_repo_allowlist: data.mcp_repo_allowlist ?? [],
  heal_mode:
    data.heal_mode === 'demo'
      ? 'demo'
      : data.heal_mode === 'freestyle'
        ? 'freestyle'
        : data.heal_mode === 'debug'
          ? 'debug'
          : 'safe',
  auto_apply_remediation: data.auto_apply_remediation,
  auto_create_pr: data.auto_create_pr,
  jenkins_bridge_allow_pr: data.jenkins_bridge_allow_pr ?? false,
  auto_create_issue: data.auto_create_issue,
  auto_retry_workflow: data.auto_retry_workflow,
  auto_create_tracking_issue_for_prs: data.auto_create_tracking_issue_for_prs,
  auto_merge_remediation_prs: data.auto_merge_remediation_prs ?? false,
  auto_merge_strategy:
    data.auto_merge_strategy === 'github_auto_merge' ? 'github_auto_merge' : 'merge_when_clean',
  auto_merge_poll_seconds: data.auto_merge_poll_seconds ?? 90,
  auto_merge_require_clean_checks: data.auto_merge_require_clean_checks ?? true,
  max_remediation_attempts: data.max_remediation_attempts,
  verify_webhook_signature: data.verify_webhook_signature,
  verify_webhook_signature_in_development: data.verify_webhook_signature_in_development,
  pipeline_step_timeout_seconds: data.pipeline_step_timeout_seconds,
  github_api_max_retries: data.github_api_max_retries,
  github_api_retry_base_seconds: data.github_api_retry_base_seconds,
  github_api_retry_max_seconds: data.github_api_retry_max_seconds,
  log_prompt_max_chars: data.log_prompt_max_chars,
  log_prompt_head_chars: data.log_prompt_head_chars,
  log_prompt_tail_chars: data.log_prompt_tail_chars,
  gh_aw_tools_enabled: data.gh_aw_tools_enabled,
  gh_aw_ingestion_mode:
    data.gh_aw_ingestion_mode === 'hybrid'
      ? 'hybrid'
      : data.gh_aw_ingestion_mode === 'passive'
        ? 'passive'
        : 'disabled',
  gh_aw_known_workflows: data.gh_aw_known_workflows ?? [],
  agent_handoff_enabled: data.agent_handoff_enabled ?? false,
  agent_handoff_mode: data.agent_handoff_mode === 'webhook' ? 'webhook' : 'copy_only',
  agent_handoff_webhook_allowlist: data.agent_handoff_webhook_allowlist ?? [],
  agent_handoff_timeout_seconds: data.agent_handoff_timeout_seconds ?? 8,
  agent_handoff_max_retries: data.agent_handoff_max_retries ?? 1,
  agent_handoff_default_target:
    data.agent_handoff_default_target === 'openclaw'
      ? 'openclaw'
      : data.agent_handoff_default_target === 'hermes'
        ? 'hermes'
        : data.agent_handoff_default_target === 'custom'
          ? 'custom'
          : 'codex_app_server',
  agent_handoff_enabled_targets:
    data.agent_handoff_enabled_targets?.filter((target) =>
      ['codex_app_server', 'openclaw', 'hermes', 'custom'].includes(target),
    ) ?? ['codex_app_server'],
  ph_allowed_repos: data.ph_allowed_repos ?? [],
  azure_openai_endpoint: data.azure_openai_endpoint ?? '',
  azure_openai_deployment_name: data.azure_openai_deployment_name ?? '',
  azure_openai_api_version: data.azure_openai_api_version ?? '2025-04-01-preview',
  azure_openai_chat_api_version: data.azure_openai_chat_api_version ?? '2024-12-01-preview',
  github_app_id: data.github_app_id ?? '',
  jenkins_bridge_enabled: data.jenkins_bridge_enabled ?? false,
  jenkins_bridge_max_skew_seconds: data.jenkins_bridge_max_skew_seconds ?? 300,
  jenkins_bridge_replay_ttl_seconds: data.jenkins_bridge_replay_ttl_seconds ?? 86400,
  jenkins_bridge_max_body_bytes: data.jenkins_bridge_max_body_bytes ?? 524288,
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
    'Controls how aggressively PipelineHealer plans fixes. "safe" is conservative, "demo" is aggressive for demonstrations, "freestyle" is aggressive open-ended automation, and "debug" uses safe behavior with verbose logging.',
  auto_apply_remediation:
    'Global execution gate. When off, PipelineHealer runs in dry-run plan mode and does not publish PRs/issues or retry workflows.',
  auto_create_pr:
    'Allows PipelineHealer to publish pull request artifacts when remediation selects create_pr.',
  jenkins_bridge_allow_pr:
    'Jenkins bridge-specific PR gate. Requires Auto-Create PR to be enabled; when off, Jenkins bridge events stay issue-first.',
  auto_create_issue:
    'Allows PipelineHealer to publish issue artifacts when remediation selects create_issue or notify.',
  auto_retry_workflow:
    'Allows PipelineHealer to trigger retry of failed workflow jobs when remediation selects retry_workflow.',
  auto_create_tracking_issue_for_prs:
    'Creates a GitHub issue to track each PR-based remediation and auto-closes it when the PR merges (requires Auto-Create Issues).',
  auto_merge_remediation_prs:
    'Allows PipelineHealer to merge its own remediation PRs after GitHub reports them mergeable and checks are clean.',
  auto_merge_strategy:
    'github_auto_merge asks GitHub to merge when branch requirements pass; merge_when_clean polls checks and merges once the PR is clean.',
  auto_merge_poll_seconds:
    'Maximum time PipelineHealer waits for remediation PR checks before leaving the PR open with a traceable timeout.',
  auto_merge_require_clean_checks:
    'Requires at least one successful GitHub status/check run and no failing checks before PipelineHealer merges a remediation PR.',
  max_remediation_attempts:
    'Maximum number of times PipelineHealer will retry fixing a single failure before giving up.',
  azure_openai_deployment_name:
    'The Azure OpenAI deployment name to use for AI analysis.',
  llm_provider:
    'Model backend selector. azure_openai is production-ready, openai_compatible is available, codex_app_server uses the local Codex App Server runtime, and custom remains scaffolded.',
  openai_compatible_base_url:
    'Base URL for an OpenAI-compatible provider endpoint (example: https://api.openai.com/v1).',
  openai_compatible_model:
    'Model name used when llm_provider=openai_compatible.',
  codex_app_server_transport:
    'Transport for the Codex App Server runtime. stdio is the safest local default; websocket is for managed bridge deployments.',
  codex_app_server_command:
    'Executable used for stdio Codex App Server access.',
  codex_app_server_model:
    'Model label requested from Codex App Server for diagnosis and remediation work. Production defaults to gpt-5.4.',
  codex_app_server_turn_timeout_ms:
    'Timeout budget for one Codex App Server turn.',
  codex_app_server_ws_url:
    'WebSocket URL for a Codex App Server bridge when transport=websocket.',
  codex_app_server_ws_allow_remote:
    'Allow a non-localhost WebSocket bridge URL for Codex App Server.',
  llm_model_analysis:
    'Optional override model/deployment for analysis tasks. Leave empty to use provider default model.',
  llm_model_diagnosis:
    'Optional override model/deployment for diagnosis tasks. Leave empty to use provider default model.',
  llm_model_remediation:
    'Optional override model/deployment for remediation tasks. Leave empty to use provider default model.',
  mcp_enabled:
    'Enable MCP integration hooks for external tool-provider adapters.',
  mcp_provider:
    'MCP provider selector. disabled is safest; github is scaffolded for read-only integration first.',
  mcp_read_only:
    'Restrict MCP providers to read-only operations.',
  mcp_timeout_seconds:
    'Timeout budget for MCP provider requests.',
  mcp_max_retries:
    'Retry budget for transient MCP provider failures.',
  mcp_tool_policies:
    'Per-tool MCP policy: disabled, read_only, write_with_approval, or auto.',
  mcp_repo_allowlist:
    'Optional MCP-specific repository allowlist (owner/repo). Empty means MCP follows PH_ALLOWED_REPOS fallback.',
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
    'How external diagnostics are collected. "passive" reads GH-AW findings from GitHub issues, "hybrid" combines GH-AW + MCP context, and "disabled" turns collection off.',
  gh_aw_known_workflows:
    'Workflows to skip when polling ci-doctor (prevents circular self-diagnosis). ci-doctor is always included.',
  agent_handoff_enabled:
    'Enable the Assign-to-Agent integration path for operators. When off, no handoff requests are accepted.',
  agent_handoff_mode:
    'Choose between copy_only audit mode and outbound webhook delivery mode.',
  agent_handoff_webhook_allowlist:
    'Allowed destination hostnames for outbound Assign-to-Agent webhook delivery. Empty means any host is allowed, unless deployment policy adds stricter checks.',
  agent_handoff_timeout_seconds:
    'Timeout budget for outbound Assign-to-Agent webhook requests.',
  agent_handoff_max_retries:
    'Retry budget for transient outbound Assign-to-Agent webhook failures.',
  agent_handoff_default_target:
    'Default external-agent target for durable handoff sessions.',
  agent_handoff_enabled_targets:
    'Targets allowed for durable external-agent handoff sessions.',
  verify_webhook_signature_in_development:
    'Require GitHub webhook signature verification even in development mode. Usually off for local testing.',
  ph_allowed_repos:
    'Restrict PipelineHealer to only process CI failures from these repositories. Leave empty to allow all.',
}
