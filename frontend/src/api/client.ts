const API_BASE = import.meta.env.VITE_API_URL || ''
const API_AUTH_KEY = import.meta.env.VITE_API_AUTH_KEY || ''
const API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || '15000')

type AuthTokenProvider = () => Promise<string | null>
let authTokenProvider: AuthTokenProvider | null = null

export function configureApiAuthTokenProvider(provider: AuthTokenProvider | null): void {
  authTokenProvider = provider
}

export interface DashboardStats {
  total_runs_processed: number
  actioned_remediations: number
  successful_remediations: number
  failed_remediations: number
  pending_remediations: number
  auto_pr_remediations: number
  issue_remediations: number
  safety_blocked_remediations: number
  mcp_enabled_runs_30d: number
  llm_fallback_rate_30d: number
  by_failure_type: Record<string, number>
  by_repository: Record<string, number>
  average_resolution_time_seconds: number
  last_updated: string
}

export interface Diagnosis {
  failure_type: string
  diagnosis_source?: 'pattern' | 'llm'
  confidence: number
  root_cause: string
  affected_files: string[]
  is_auto_fixable: boolean
  suggested_fix: string
  error_details: Record<string, unknown>
}

export interface RemediationResult {
  success: boolean
  action_taken: string
  pr_url?: string
  issue_url?: string
  error_message?: string
  details: Record<string, unknown>
}

export interface Activity {
  id: string
  repositoryId: string
  repository_name: string
  workflow_run_id: number
  workflow_name: string
  status: string
  failure_type?: string
  diagnosis?: Diagnosis
  llm_model_path?: {
    provider: string
    model: string
    fallback_used: boolean
    call_count: number
    total_latency_ms: number
    error_count: number
  }
  mcp_model_path?: {
    provider: string
    enabled: boolean
    available: boolean
    read_only: boolean
    reason: string
    configured_tools: string[]
    tool_invocations: Record<string, number>
    source_attribution: Record<string, number>
    error_count: number
  }
  remediation_result?: RemediationResult
  created_at: string
  updated_at: string
  duration_seconds?: number
  error?: string
  external_diagnostics?: Array<{
    source: string
    status: string
    summary: string
    url?: string
    matched_run_id?: number
    confidence_delta: number
    metadata: Record<string, unknown>
    collected_at: string
  }>
}

export interface TimelineData {
  data: Record<string, Record<string, number>>
  since: string
}

export interface AppSettings {
  environment: string
  storage_backend: string
  heal_mode: string
  auto_create_pr: boolean
  auto_create_tracking_issue_for_prs: boolean
  max_remediation_attempts: number
  pipeline_step_timeout_seconds: number
  github_api_max_retries: number
  github_api_retry_base_seconds: number
  github_api_retry_max_seconds: number
  log_prompt_max_chars: number
  log_prompt_head_chars: number
  log_prompt_tail_chars: number
  verify_webhook_signature: boolean
  verify_webhook_signature_in_development: boolean
  api_auth_enabled: boolean
  admin_api_auth_enabled: boolean
  auth_mode: string
  entra_auth_enabled: boolean
  entra_admin_roles: string[]
  github_pat_configured: boolean
  github_app_configured: boolean
  github_auth_mode: string
  gh_aw_tools_enabled: boolean
  gh_aw_ingestion_mode: string
  gh_aw_known_workflows: string[]
  external_diagnostics_wait_seconds: number
  external_diagnostics_poll_interval_seconds: number
  ph_allowed_repos: string[]
  cors_allowed_origins: string[]
  cors_allow_origin_regex: string
  llm_provider: 'azure_openai' | 'openai_compatible' | 'custom'
  openai_compatible_base_url: string
  openai_compatible_model: string
  openai_compatible_api_key_configured: boolean
  mcp_enabled: boolean
  mcp_provider: 'disabled' | 'github' | 'azure_monitor' | 'custom'
  mcp_read_only: boolean
  mcp_timeout_seconds: number
  mcp_max_retries: number
  azure_openai_endpoint: string
  azure_openai_deployment_name: string
  azure_openai_api_version: string
  azure_openai_chat_api_version: string
}

export interface LLMProviderHealth {
  provider: string
  implemented: boolean
  available: boolean
  reason: string
  message: string
  endpoint?: string
  deployment_name?: string
  api_version?: string
}

export interface MCPProviderHealth {
  provider: string
  enabled: boolean
  read_only: boolean
  available: boolean
  reason: string
  message: string
  configured_tools: string[]
}

export interface AdminSettingsAuditEntry {
  timestamp: string
  changed_keys: string[]
  changes: Record<string, { old: unknown; new: unknown }>
  actor?: string
  request_id?: string
  client_ip?: string
  user_agent?: string
}

export interface AdminSettingsUpdate {
  heal_mode?: 'safe' | 'demo' | 'debug'
  auto_create_pr?: boolean
  auto_create_tracking_issue_for_prs?: boolean
  max_remediation_attempts?: number
  verify_webhook_signature_in_development?: boolean
  pipeline_step_timeout_seconds?: number
  github_api_max_retries?: number
  github_api_retry_base_seconds?: number
  github_api_retry_max_seconds?: number
  log_prompt_max_chars?: number
  log_prompt_head_chars?: number
  log_prompt_tail_chars?: number
  gh_aw_tools_enabled?: boolean
  gh_aw_ingestion_mode?: 'disabled' | 'passive'
  gh_aw_known_workflows?: string[]
  ph_allowed_repos?: string[]
  llm_provider?: 'azure_openai' | 'openai_compatible' | 'custom'
  openai_compatible_base_url?: string
  openai_compatible_model?: string
  mcp_enabled?: boolean
  mcp_provider?: 'disabled' | 'github' | 'azure_monitor' | 'custom'
  mcp_read_only?: boolean
  mcp_timeout_seconds?: number
  mcp_max_retries?: number
  azure_openai_deployment_name?: string
}

export interface AdminSettingsPersistResponse {
  env_file: string
  persisted_keys: string[]
  redeploy_attempted: boolean
  redeploy_started: boolean
  redeploy_message: string
}

type ApiRequestOptions = RequestInit & {
  adminKey?: string
}

function getApiErrorMessage(status: number, statusText: string, bodyText: string): string {
  const trimmed = bodyText.trim()
  if (!trimmed) {
    return `API error: ${status} ${statusText}`
  }
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; message?: unknown; error?: unknown }
    const detail =
      typeof parsed.detail === 'string'
        ? parsed.detail
        : typeof parsed.message === 'string'
          ? parsed.message
          : typeof parsed.error === 'string'
            ? parsed.error
            : ''
    if (detail) {
      return `API error: ${status} ${statusText} - ${detail}`
    }
  } catch {
    // Non-JSON upstream errors (for example an HTML proxy page) should surface clearly.
  }
  return `API error: ${status} ${statusText} - ${trimmed.slice(0, 300)}`
}

async function fetchJson<T>(path: string, options?: ApiRequestOptions): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS)
  let bearerToken: string | null = null
  if (authTokenProvider) {
    try {
      bearerToken = await authTokenProvider()
    } catch {
      bearerToken = null
    }
  }
  const upstreamSignal = options?.signal
  if (upstreamSignal) {
    if (upstreamSignal.aborted) {
      controller.abort()
    } else {
      upstreamSignal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {}),
        ...(API_AUTH_KEY ? { 'X-API-Key': API_AUTH_KEY } : {}),
        ...(options?.adminKey ? { 'X-Admin-Key': options.adminKey } : {}),
        ...options?.headers,
      },
    })

    const rawText = await response.text()
    if (!response.ok) {
      throw new Error(getApiErrorMessage(response.status, response.statusText, rawText))
    }
    if (!rawText.trim()) {
      throw new Error(`API error: ${response.status} ${response.statusText} - empty response body`)
    }
    try {
      return JSON.parse(rawText) as T
    } catch {
      throw new Error(
        `API error: ${response.status} ${response.statusText} - expected JSON response body`
      )
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`API timeout after ${API_TIMEOUT_MS}ms`)
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

export const api = {
  getStats: () => fetchJson<DashboardStats>('/api/stats'),
  getSettings: (adminKey?: string) =>
    fetchJson<AppSettings>('/api/settings', { adminKey }),
  // Intentionally not auto-loaded.
  // Admin audit access is gated and activated via explicit UI action.
  getSettingsAudit: (adminKey: string | undefined, limit = 50) =>
    fetchJson<AdminSettingsAuditEntry[]>(
      `/api/settings/audit?limit=${Math.max(1, Math.min(limit, 200))}`,
      { adminKey }
    ),
  getLLMProviderHealth: (adminKey: string | undefined) =>
    fetchJson<LLMProviderHealth>('/api/settings/llm/provider-health', { adminKey }),
  getMCPProviderHealth: (adminKey: string | undefined) =>
    fetchJson<MCPProviderHealth>('/api/settings/mcp/provider-health', { adminKey }),
  updateSettings: (adminKey: string | undefined, payload: AdminSettingsUpdate) =>
    fetchJson<AppSettings>('/api/settings', {
      method: 'PATCH',
      adminKey,
      body: JSON.stringify(payload),
    }),
  persistSettings: (adminKey: string | undefined, skipRedeploy = false) =>
    fetchJson<AdminSettingsPersistResponse>('/api/settings/persist', {
      method: 'POST',
      adminKey,
      body: JSON.stringify({ skip_redeploy: skipRedeploy }),
    }),
  
  getActivities: (params?: {
    repository?: string
    status?: string
    failure_type?: string
    limit?: number
    offset?: number
  }) => {
    const searchParams = new URLSearchParams()
    if (params?.repository) searchParams.set('repository', params.repository)
    if (params?.status) searchParams.set('status', params.status)
    if (params?.failure_type) searchParams.set('failure_type', params.failure_type)
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    
    const query = searchParams.toString()
    return fetchJson<Activity[]>(`/api/activities${query ? `?${query}` : ''}`)
  },
  
  getActivity: (id: string) => fetchJson<Activity>(`/api/activities/${id}`),
  
  getTimeline: (days = 7) => fetchJson<TimelineData>(`/api/timeline?days=${days}`),
  
  getFailureBreakdown: (days = 30) => 
    fetchJson<Record<string, number>>(`/api/failure-breakdown?days=${days}`),
  
  retryActivity: (id: string) => 
    fetchJson<{ status: string; activity_id: string }>(`/api/activities/${id}/retry`, {
      method: 'POST',
    }),

  backfillDiagnostics: (maxAgeHours = 24) =>
    fetchJson<{ status: string; backfilled: number; max_age_hours: number }>(
      `/api/backfill-diagnostics?max_age_hours=${maxAgeHours}`,
      { method: 'POST' },
    ),
}
