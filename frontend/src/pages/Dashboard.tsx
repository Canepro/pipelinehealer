import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import {
  Activity,
  ArrowRight,
  CheckCircle,
  Clock,
  FileText,
  ShieldAlert,
  SearchCheck,
  Copy,
  ExternalLink,
} from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import type { Activity as ActivityItem } from '../api/client'
import { EMPTY_STATES } from '../constants/emptyStates'
import StatsCard from '../components/StatsCard'
import ActivityTable from '../components/ActivityTable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

const COLORS = ['#2563eb', '#0ea5e9', '#14b8a6', '#16a34a', '#f59e0b', '#64748b']
const REASON_LABELS: Record<string, string> = {
  OUTSIDE_ALLOWED_FILES: 'Touches non-allowlisted files.',
  LOW_CONFIDENCE: 'Model confidence below threshold.',
  MISSING_CONTEXT: 'Insufficient logs or stack trace.',
  REQUIRES_ENV_CONTEXT: 'Needs repo/environment context not available.',
  SAFETY_BOUND: 'Blocked by configured safety policy.',
}

function getEvidenceLines(activity: ActivityItem | null): string[] {
  if (!activity?.diagnosis?.error_details) return []
  const details = activity.diagnosis.error_details as Record<string, unknown>
  const listKeys = ['key_log_lines', 'relevant_log_lines', 'log_messages', 'evidence']
  for (const key of listKeys) {
    const value = details[key]
    if (Array.isArray(value)) {
      return value
        .filter((line): line is string => typeof line === 'string' && line.trim().length > 0)
        .slice(0, 2)
    }
  }
  const message = details.message
  if (typeof message === 'string' && message.trim().length > 0) {
    return [message]
  }
  return []
}

export default function Dashboard() {
  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    error: statsErrorValue,
  } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    retry: 1,
  })

  const { data: activities, isLoading: activitiesLoading } = useQuery({
    queryKey: ['activities', { limit: 50 }],
    queryFn: () => api.getActivities({ limit: 50 }),
  })

  const { data: failureBreakdown } = useQuery({
    queryKey: ['failureBreakdown'],
    queryFn: () => api.getFailureBreakdown(30),
  })

  // Transform failure breakdown for pie chart
  const pieData = failureBreakdown
    ? Object.entries(failureBreakdown).map(([name, value]) => ({
        name: name.replace('_', ' '),
        value,
      }))
    : []
  const totalFailures = pieData.reduce((sum, item) => sum + item.value, 0)

  // Transform repository data for bar chart
  const repoData = stats?.by_repository
    ? Object.entries(stats.by_repository)
        .slice(0, 5)
        .map(([name, value]) => ({
          name: name.split('/')[1] || name,
          count: value,
        }))
    : []
  const topRepository = repoData[0]

  const safetyGatedRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round((stats.safety_blocked_remediations / stats.actioned_remediations) * 100)
      : 0
    : 0
  const issueRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round((stats.issue_remediations / stats.actioned_remediations) * 100)
      : 0
    : 0
  const successRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round((stats.successful_remediations / stats.actioned_remediations) * 100)
      : 0
    : 0
  const llmFallbackRate30d = stats ? Math.round(stats.llm_fallback_rate_30d) : 0
  const recentActivities = (activities || []).slice(0, 5)
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedActivityId && recentActivities.length > 0) {
      setSelectedActivityId(recentActivities[0].id)
    }
  }, [recentActivities, selectedActivityId])

  const selectedActivity = useMemo(() => {
    if (recentActivities.length === 0) return null
    return (
      recentActivities.find((activity) => activity.id === selectedActivityId) ||
      recentActivities[0]
    )
  }, [recentActivities, selectedActivityId])

  const selectedReasonCode =
    typeof selectedActivity?.remediation_result?.details?.not_auto_reason_code === 'string'
      ? selectedActivity.remediation_result.details.not_auto_reason_code
      : null
  const selectedActionTaken =
    typeof selectedActivity?.remediation_result?.action_taken === 'string'
      ? selectedActivity.remediation_result.action_taken.replace('_', ' ').toUpperCase()
      : 'N/A'
  const selectedConfidence =
    typeof selectedActivity?.diagnosis?.confidence === 'number'
      ? `${Math.round(selectedActivity.diagnosis.confidence * 100)}%`
      : 'N/A'
  const selectedDiagnosisSource =
    selectedActivity?.diagnosis?.diagnosis_source === 'llm'
      ? 'LLM'
      : selectedActivity?.diagnosis?.diagnosis_source === 'pattern'
        ? 'Pattern'
        : 'Unknown'
  const selectedModelPath = selectedActivity?.llm_model_path
    ? `${selectedActivity.llm_model_path.provider}:${selectedActivity.llm_model_path.model}`
    : 'N/A'
  const selectedFallbackUsed = selectedActivity?.llm_model_path?.fallback_used ? 'Yes' : 'No'
  const selectedLlmCalls = selectedActivity?.llm_model_path?.call_count ?? 0
  const selectedFailureType = selectedActivity?.failure_type || 'unknown'
  const selectedArtifactUrl =
    selectedActivity?.remediation_result?.pr_url || selectedActivity?.remediation_result?.issue_url || null
  const selectedRunUrl =
    selectedActivity?.repository_name && selectedActivity?.workflow_run_id
      ? `https://github.com/${selectedActivity.repository_name}/actions/runs/${selectedActivity.workflow_run_id}`
      : null
  const evidenceLines = useMemo(() => getEvidenceLines(selectedActivity), [selectedActivity])

  const safetyGateReasonCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const activity of activities || []) {
      const reason = activity?.remediation_result?.details?.not_auto_reason_code
      if (typeof reason === 'string' && reason.length > 0) {
        counts.set(reason, (counts.get(reason) || 0) + 1)
      }
    }
    return Array.from(counts.entries())
      .map(([code, count]) => ({ code, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 4)
  }, [activities])
  const externalSignalCount = useMemo(
    () =>
      (activities || []).filter((activity) =>
        (activity.external_diagnostics || []).some((item) => item.status === 'available')
      ).length,
    [activities]
  )
  const lastUpdatedLabel = stats?.last_updated
    ? new Date(stats.last_updated).toLocaleString()
    : 'Unavailable'

  const showStatsLoading = statsLoading && !statsError
  const statsErrorMessage =
    statsError && statsErrorValue instanceof Error
      ? statsErrorValue.message
      : 'Stats temporarily unavailable'

  return (
    <div className="space-y-8">
      {/* Executive header */}
      <Card className="border-azure-500/20 bg-[radial-gradient(120%_100%_at_0%_0%,rgba(53,111,174,0.25),transparent_52%),var(--ph-surface)]">
        <CardContent className="p-5 md:p-6">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-center xl:justify-between">
            <div className="max-w-2xl">
              <Badge variant="outline">Operations Command Center</Badge>
              <h1 className="mt-3 text-2xl font-bold tracking-tight text-[var(--ph-text)] sm:text-3xl">
                Pipeline Reliability Dashboard
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-[var(--ph-muted)] sm:text-base">
                Track remediation throughput, safety posture, and external diagnostic signals from one place.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button asChild size="sm">
                  <Link to="/app/activities">
                    Review Activities
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="sm" variant="secondary">
                  <Link to="/app/settings">Runtime Settings</Link>
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:min-w-[360px] lg:grid-cols-3">
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">Success Rate</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">{successRate}%</p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">External Signals</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">{externalSignalCount}</p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">MCP Runs (30d)</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {stats?.mcp_enabled_runs_30d ?? 0}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">LLM Fallback (30d)</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {llmFallbackRate30d}%
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">Avg Resolution</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {stats?.average_resolution_time_seconds
                    ? `${Math.round(stats.average_resolution_time_seconds)}s`
                    : 'N/A'}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">Last Updated</p>
                <p className="mt-1 truncate text-sm font-medium text-[var(--ph-text)]">{lastUpdatedLabel}</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-[var(--ph-text)]">Healing Throughput</h2>
          <Badge variant="outline">Last 30 days</Badge>
        </div>
        {showStatsLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Card key={`stats-skeleton-${index}`}>
                <CardContent className="p-4 md:p-5 space-y-3">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-8 w-20" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatsCard
              title="Processed"
              value={stats?.total_runs_processed || 0}
              icon={Activity}
              color="blue"
            />
            <StatsCard
              title="Actioned"
              value={stats?.actioned_remediations || 0}
              icon={CheckCircle}
              color="green"
            />
            <StatsCard
              title="Safety Gated"
              value={`${stats?.safety_blocked_remediations || 0} (${safetyGatedRate}%)`}
              icon={ShieldAlert}
              color="red"
            />
            <StatsCard
              title="Issue-Only"
              value={`${stats?.issue_remediations || 0} (${issueRate}%)`}
              icon={FileText}
              color="yellow"
            />
          </div>
        )}
      </section>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Why Safety Gated</CardTitle>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            We create review-ready proposals when changes touch non-allowlisted paths or require
            extra context.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 pt-0">
          {safetyGateReasonCounts.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {safetyGateReasonCounts.map((item) => (
                <div
                  key={item.code}
                  className="rounded-md border border-[var(--ph-border)] bg-slate-800/40 px-3 py-2 text-xs text-slate-200"
                >
                  <div className="font-semibold">
                    {item.code} ({item.count})
                  </div>
                  <div className="mt-1 text-gray-400">
                    {REASON_LABELS[item.code] || 'Manual review required.'}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div>
              <p className="text-sm font-medium text-[var(--ph-text)]">{EMPTY_STATES.safetyGated.title}</p>
              <p className="mt-1 text-sm text-gray-400">{EMPTY_STATES.safetyGated.body}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {statsError && (
        <div className="rounded-lg border border-amber-300/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Dashboard stats endpoint is unavailable: {statsErrorMessage}
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Failure Types Pie Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Failure Types (Last 30 Days)</CardTitle>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Total failures observed: <span className="font-semibold text-[var(--ph-text)]">{totalFailures}</span>
            </p>
          </CardHeader>
          <CardContent>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  fill="#8884d8"
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                  fontSize={12}
                >
                    {pieData.map((_, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={COLORS[index % COLORS.length]}
                      />
                    ))}
                </Pie>
                  <Tooltip
                    formatter={(value: number, _name, item) => [
                      `${value} case${value === 1 ? '' : 's'}`,
                      item.payload.name,
                    ]}
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '8px',
                      color: '#e2e8f0',
                      fontSize: '12px',
                      padding: '8px 10px',
                    }}
                    labelStyle={{ color: '#e2e8f0', fontWeight: 500 }}
                    itemStyle={{ color: '#e2e8f0' }}
                    wrapperStyle={{ maxWidth: 'min(90vw, 320px)' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] flex-col items-center justify-center gap-3 text-sm text-gray-400">
                <p>{EMPTY_STATES.activities.body}</p>
                <Button asChild size="sm" variant="secondary">
                  <a
                    href="https://github.com/Canepro/pipelinehealer-demo"
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Open demo repo
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top Repositories Bar Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Top Repositories</CardTitle>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Most active repo: <span className="font-semibold text-[var(--ph-text)]">{topRepository?.name || 'N/A'}</span>{' '}
              <span className="text-gray-400">({topRepository?.count || 0} runs)</span>
            </p>
          </CardHeader>
          <CardContent>
            {repoData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={repoData}>
                  <CartesianGrid
                    strokeDasharray="2 4"
                    stroke="#334155"
                    strokeOpacity={0.25}
                    vertical={false}
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: '#e2e8f0', fontSize: 12 }}
                    interval={0}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: '#e2e8f0', fontSize: 12 }}
                    tickCount={5}
                    axisLine={false}
                    tickLine={false}
                    width={40}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '8px',
                      color: '#e2e8f0',
                      fontSize: '12px',
                      padding: '8px 10px',
                    }}
                    labelStyle={{ color: '#e2e8f0', fontWeight: 500 }}
                    itemStyle={{ color: '#e2e8f0' }}
                    formatter={(value: number) => [`${value} run${value === 1 ? '' : 's'}`, 'Runs']}
                    wrapperStyle={{ maxWidth: 'min(90vw, 320px)' }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] flex-col items-center justify-center gap-3 text-sm text-gray-400">
                <p>{EMPTY_STATES.activities.body}</p>
                <Button asChild size="sm" variant="secondary">
                  <a
                    href="https://github.com/Canepro/pipelinehealer-demo"
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Open demo repo
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Explainability Snapshot */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <SearchCheck className="h-4 w-4 text-azure-400" />
            Explainability Snapshot
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {recentActivities.length > 0 ? (
            <>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-xs uppercase tracking-wide text-gray-400">
                    Selected Activity
                  </span>
                  <select
                    value={selectedActivity?.id || ''}
                    onChange={(e) => setSelectedActivityId(e.target.value)}
                    className="h-10 w-full rounded-lg border border-[var(--ph-border)] bg-gray-100 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-azure-500 dark:bg-gray-700 dark:text-gray-100"
                  >
                    {recentActivities.map((activity) => (
                      <option key={activity.id} value={activity.id}>
                        Run #{activity.workflow_run_id} · {activity.failure_type || 'unknown'}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="flex flex-wrap items-end gap-2">
                  <Button asChild variant="secondary" size="sm">
                    <Link to={`/app/activities?focus=${selectedActivity?.id || ''}`}>View activity</Link>
                  </Button>
                  {selectedArtifactUrl && (
                    <Button asChild variant="ghost" size="sm">
                      <a href={selectedArtifactUrl} rel="noopener noreferrer" target="_blank">
                        Open Issue/PR
                      </a>
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => {
                      const traceId = selectedActivity?.id || ''
                      try {
                        await navigator.clipboard.writeText(traceId)
                        toast.success('Activity ID copied')
                      } catch {
                        toast.error('Copy failed')
                      }
                    }}
                  >
                    <Copy className="mr-1 h-4 w-4" />
                    Copy ID
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-7">
                <div className="rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Failure Type</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">{selectedFailureType}</p>
                </div>
                <div className="rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Confidence</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">{selectedConfidence}</p>
                </div>
                <div className="rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Diagnosis Source</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">{selectedDiagnosisSource}</p>
                </div>
                <div className="rounded-lg border border-[var(--ph-border)] p-3 lg:col-span-2">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Model Path</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)] break-all">{selectedModelPath}</p>
                  {selectedActivity?.llm_model_path && (
                    <p className="mt-1 text-xs text-gray-400">
                      Calls: {selectedLlmCalls} • Fallback used: {selectedFallbackUsed}
                    </p>
                  )}
                </div>
                <div className="rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Proposed Action</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">{selectedActionTaken}</p>
                </div>
                <div className="rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Reason Code</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">{selectedReasonCode || 'N/A'}</p>
                </div>
              </div>

              <div className="rounded-lg border border-[var(--ph-border)] p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Evidence</p>
                  <div className="flex items-center gap-2">
                    {selectedRunUrl && (
                      <Button asChild size="sm" variant="ghost">
                        <a href={selectedRunUrl} rel="noopener noreferrer" target="_blank">
                          Workflow run
                          <ExternalLink className="ml-1 h-3.5 w-3.5" />
                        </a>
                      </Button>
                    )}
                    {selectedActivity?.id && (
                      <Badge variant="secondary" className="font-mono text-[11px]">
                        {selectedActivity.id}
                      </Badge>
                    )}
                  </div>
                </div>
                {evidenceLines.length > 0 ? (
                  <ul className="space-y-1 text-sm text-[var(--ph-text)]">
                    {evidenceLines.map((line, index) => (
                      <li key={index} className="truncate">
                        {line}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-400">No structured evidence lines available.</p>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400">
              {EMPTY_STATES.activities.body}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Recent Activities */}
      <section className="space-y-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Recent Activities
          </h2>
          <Button asChild size="sm" variant="ghost">
            <Link to="/app/activities">View all</Link>
          </Button>
        </div>
        <ActivityTable
          activities={recentActivities}
          isLoading={activitiesLoading}
        />
      </section>

      {/* Average Resolution Time */}
      {stats && stats.average_resolution_time_seconds > 0 && (
        <Card>
          <CardContent className="p-4 md:p-6">
            <div className="flex items-center gap-4">
              <Clock className="h-8 w-8 text-azure-500" />
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Average Resolution Time
                </p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {Math.round(stats.average_resolution_time_seconds)}s
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
