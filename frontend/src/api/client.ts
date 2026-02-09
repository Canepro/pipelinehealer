const API_BASE = import.meta.env.VITE_API_URL || ''

export interface DashboardStats {
  total_runs_processed: number
  successful_remediations: number
  failed_remediations: number
  pending_remediations: number
  by_failure_type: Record<string, number>
  by_repository: Record<string, number>
  average_resolution_time_seconds: number
  last_updated: string
}

export interface Diagnosis {
  failure_type: string
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
  remediation_result?: RemediationResult
  created_at: string
  updated_at: string
  duration_seconds?: number
  error?: string
}

export interface TimelineData {
  data: Record<string, Record<string, number>>
  since: string
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

export const api = {
  getStats: () => fetchJson<DashboardStats>('/api/stats'),
  
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
}
