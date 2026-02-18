import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { ExternalLink, GitBranch } from 'lucide-react'
import type { Activity } from '../api/client'
import { EMPTY_STATES } from '../constants/emptyStates'
import StatusBadge from './StatusBadge'
import FailureTypeBadge from './FailureTypeBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface ActivityTableProps {
  activities: Activity[]
  isLoading?: boolean
  focusedActivityId?: string | null
  highlightedActivityId?: string | null
}

type StatusTag = {
  label: string
  variant: 'success' | 'destructive' | 'secondary' | 'outline'
  title?: string
}

const MAX_STATUS_TAGS = 3
const REASON_LABELS: Record<string, string> = {
  OUTSIDE_ALLOWED_FILES: 'Touches files outside safe scope',
  LOW_CONFIDENCE: 'Confidence below safety threshold',
  MISSING_CONTEXT: 'Insufficient diagnostic context',
  REQUIRES_ENV_CONTEXT: 'Needs environment-specific context',
  SAFETY_BOUND: 'Blocked by active safety policy',
  OUTPUT_ISSUES_DISABLED: 'Issues are disabled in target repository',
}

function formatSourceLabel(source: string): string {
  const normalizedRaw = source.trim().toLowerCase()
  const knownLabels: Record<string, string> = {
    'ci-doctor': 'CI Doctor',
    'external-diagnostics': 'External Diagnostics',
    'github-mcp': 'GitHub MCP',
    'knowledge-mcp': 'Knowledge MCP',
    github: 'GitHub',
    gh_aw: 'GitHub Agentic Workflows',
    azure_monitor: 'Azure Monitor',
  }
  if (knownLabels[normalizedRaw]) {
    return knownLabels[normalizedRaw]
  }
  const normalized = normalizedRaw.replace(/[_-]+/g, ' ')
  if (!normalized) {
    return 'External'
  }
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase())
}

function getExternalDiagnosticsMeta(activity: Activity): {
  label: string
  variant: 'success' | 'destructive' | 'secondary' | 'outline'
  findingsUrl: string | null
} | null {
  const diagnostics = activity.external_diagnostics ?? []
  if (diagnostics.length === 0) {
    return null
  }

  const nonNoopDiagnostics = diagnostics.filter((item) => {
    const metadata = (item.metadata ?? {}) as Record<string, unknown>
    return metadata.noop !== true
  })

  const representative =
    nonNoopDiagnostics.find((item) => item.status === 'available') ??
    nonNoopDiagnostics.find((item) => item.status === 'error') ??
    nonNoopDiagnostics[0]

  if (!representative) {
    return null
  }

  const source = formatSourceLabel(representative.source)
  const findingsUrl = nonNoopDiagnostics.find((item) => item.url)?.url ?? null

  if (representative.status === 'available') {
    return {
      label: `${source} Signal`,
      variant: 'success',
      findingsUrl,
    }
  }

  if (representative.status === 'error') {
    return {
      label: `${source} Error`,
      variant: 'destructive',
      findingsUrl,
    }
  }

  if (representative.status === 'unavailable') {
    return {
      label: `${source} Unavailable`,
      variant: 'secondary',
      findingsUrl,
    }
  }

  return {
    label: `${source} ${representative.status || 'Signal'}`,
    variant: 'outline',
    findingsUrl,
  }
}

function getIssueProposalMeta(activity: Activity): {
  includesProposedFix: boolean
  reasonCode: string | null
  reasonLabel: string | null
  output: string | null
  reusedExistingPr: boolean
} {
  const details = activity.remediation_result?.details
  const includes = details?.includes_proposed_fix === true
  const reason =
    typeof details?.not_auto_reason_code === 'string'
      ? details.not_auto_reason_code
      : null
  const output =
    typeof activity.remediation_result?.action_taken === 'string'
      ? activity.remediation_result.action_taken.replace('_', ' ').toUpperCase()
      : null
  const reusedExistingPr = details?.reused_existing_pr === true
  const reasonLabel = reason ? REASON_LABELS[reason] || 'Manual review required' : null
  return { includesProposedFix: includes, reasonCode: reason, reasonLabel, output, reusedExistingPr }
}

function getMcpLabel(activity: Activity): { label: string; variant: 'success' | 'secondary' } | null {
  const path = activity.mcp_model_path
  if (!path || !path.enabled) return null
  const provider = formatSourceLabel(path.provider || 'mcp')
  if (path.available) {
    return null
  }
  return { label: `MCP ${provider}: unavailable`, variant: 'secondary' }
}

function getFailureContext(activity: Activity): string | null {
  const structured = activity.failure_context
  const contextParts: string[] = []
  if (structured?.failing_job) {
    contextParts.push(`Job: ${structured.failing_job}`)
  }
  if (structured?.failing_step) {
    contextParts.push(`Step: ${structured.failing_step}`)
  }
  if (structured?.failing_command) {
    contextParts.push(`Cmd: ${structured.failing_command}`)
  }
  if (structured?.signal) {
    contextParts.push(`Signal: ${structured.signal}`)
  }
  if (contextParts.length > 0) {
    const summary = contextParts.join(' | ')
    return summary.length > 120 ? `${summary.slice(0, 117)}...` : summary
  }

  const rootCause = activity.diagnosis?.root_cause?.trim()
  if (rootCause) {
    return rootCause.length > 80 ? `${rootCause.slice(0, 77)}...` : rootCause
  }
  const error = activity.error?.trim()
  if (error) {
    return error.length > 80 ? `${error.slice(0, 77)}...` : error
  }
  return null
}

function getStatusTags(activity: Activity): StatusTag[] {
  const meta = getIssueProposalMeta(activity)
  const externalMeta = getExternalDiagnosticsMeta(activity)
  const mcpLabel = getMcpLabel(activity)
  const tags: StatusTag[] = []

  if (meta.output) {
    tags.push({ label: `Output: ${meta.output}`, variant: 'secondary' })
  }
  if (externalMeta) {
    tags.push({ label: externalMeta.label, variant: externalMeta.variant })
  }
  if (meta.reasonCode && meta.reasonLabel) {
    tags.push({
      label: `Safety Gate: ${meta.reasonLabel}`,
      variant: 'outline',
      title: `raw: ${meta.reasonCode}`,
    })
  }
  if (meta.includesProposedFix) {
    tags.push({ label: 'Includes Proposed Fix', variant: 'outline' })
  }
  if (activity.llm_model_path?.fallback_used) {
    tags.push({ label: 'Fallback Used', variant: 'outline' })
  }
  if (mcpLabel) {
    tags.push({ label: mcpLabel.label, variant: 'secondary' })
  }
  if (meta.reusedExistingPr) {
    tags.push({ label: 'Reused Existing PR', variant: 'success' })
  }

  return tags
}

export default function ActivityTable({
  activities,
  isLoading,
  focusedActivityId,
  highlightedActivityId,
}: ActivityTableProps) {
  const desktopScrollRef = useRef<HTMLDivElement | null>(null)
  const desktopTopRailRef = useRef<HTMLDivElement | null>(null)
  const [desktopScrollWidth, setDesktopScrollWidth] = useState(0)
  const [desktopHasHorizontalOverflow, setDesktopHasHorizontalOverflow] = useState(false)

  useEffect(() => {
    const viewport = desktopScrollRef.current
    if (!viewport) return

    const syncDimensions = () => {
      setDesktopScrollWidth(viewport.scrollWidth)
      setDesktopHasHorizontalOverflow(viewport.scrollWidth > viewport.clientWidth + 1)
    }

    syncDimensions()
    if (typeof ResizeObserver === 'undefined') {
      return
    }
    const resizeObserver = new ResizeObserver(syncDimensions)
    resizeObserver.observe(viewport)
    const table = viewport.querySelector('table')
    if (table) {
      resizeObserver.observe(table)
    }
    return () => resizeObserver.disconnect()
  }, [activities.length, isLoading])

  useEffect(() => {
    const topRail = desktopTopRailRef.current
    const viewport = desktopScrollRef.current
    if (!topRail || !viewport) return

    let syncingFromTop = false
    let syncingFromViewport = false

    const onTopScroll = () => {
      if (syncingFromViewport) return
      syncingFromTop = true
      viewport.scrollLeft = topRail.scrollLeft
      syncingFromTop = false
    }

    const onViewportScroll = () => {
      if (syncingFromTop) return
      syncingFromViewport = true
      topRail.scrollLeft = viewport.scrollLeft
      syncingFromViewport = false
    }

    topRail.addEventListener('scroll', onTopScroll)
    viewport.addEventListener('scroll', onViewportScroll)
    return () => {
      topRail.removeEventListener('scroll', onTopScroll)
      viewport.removeEventListener('scroll', onViewportScroll)
    }
  }, [activities.length, desktopHasHorizontalOverflow])

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="space-y-4">
            <Skeleton className="h-5 w-40" />
            {Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="grid grid-cols-6 gap-4">
                <Skeleton className="col-span-2 h-11" />
                <Skeleton className="col-span-1 h-11" />
                <Skeleton className="col-span-1 h-11" />
                <Skeleton className="col-span-1 h-11" />
                <Skeleton className="col-span-1 h-11" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (activities.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <GitBranch className="h-12 w-12 text-gray-400 mx-auto" />
          <p className="mt-4 text-gray-500">{EMPTY_STATES.activities.title}</p>
          <p className="text-sm text-gray-400">
            {EMPTY_STATES.activities.body}
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="overflow-hidden">
      <div className="lg:hidden divide-y divide-[var(--ph-border)]">
        {activities.map((activity) => {
          const externalMeta = getExternalDiagnosticsMeta(activity)
          const statusTags = getStatusTags(activity)
          const visibleStatusTags = statusTags.slice(0, MAX_STATUS_TAGS)
          const hiddenStatusTagCount = Math.max(statusTags.length - visibleStatusTags.length, 0)
          return (
            <div
              key={activity.id}
              data-activity-id={activity.id}
              className={`space-y-3 p-4 transition-colors ${
                activity.id === highlightedActivityId ? 'bg-azure-500/10' : ''
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p
                    className="truncate text-sm font-medium text-gray-900 dark:text-white"
                    title={activity.repository_name}
                  >
                    {activity.repository_name}
                  </p>
                  <p className="text-xs text-gray-500">Run #{activity.workflow_run_id}</p>
                </div>
                <StatusBadge status={activity.status} size="sm" />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {activity.id === focusedActivityId && (
                  <Badge className="rounded-md text-[11px]" variant="success">
                    Focused View
                  </Badge>
                )}
                {activity.failure_type ? (
                  <FailureTypeBadge type={activity.failure_type} />
                ) : (
                  <span className="text-xs text-gray-400">No failure type</span>
                )}
                {visibleStatusTags.map((tag, index) => (
                  <Badge
                    key={`${tag.label}-${index}`}
                    className="max-w-full sm:max-w-[18rem] truncate rounded-md text-[11px]"
                    variant={tag.variant}
                    title={tag.title || tag.label}
                  >
                    {tag.label}
                  </Badge>
                ))}
                {hiddenStatusTagCount > 0 && (
                  <Badge className="max-w-full rounded-md text-[11px]" variant="outline">
                    +{hiddenStatusTagCount} more
                  </Badge>
                )}
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  {formatDistanceToNow(new Date(activity.created_at), { addSuffix: true })}
                </span>
                <div className="flex items-center space-x-2">
                  <Button asChild variant="ghost" size="sm">
                    <Link to={`/app/activities/${activity.id}`}>View</Link>
                  </Button>
                  {externalMeta?.findingsUrl && (
                    <Button asChild variant="ghost" size="sm">
                      <a
                        href={externalMeta.findingsUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label="Open external diagnostics findings"
                      >
                        Findings
                      </a>
                    </Button>
                  )}
                  {activity.remediation_result?.pr_url && (
                    <Button asChild variant="ghost" size="sm">
                      <a
                        href={activity.remediation_result.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label="Open pull request"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="hidden lg:block">
        {desktopHasHorizontalOverflow && (
          <div className="border-b border-[var(--ph-border)] bg-slate-800/10 px-6 py-3">
            <div className="mb-2 flex items-center justify-between gap-3 text-xs text-[var(--ph-muted)]">
              <span>Horizontal scroll</span>
              <span>Use this rail instead of scrolling to the bottom of the table.</span>
            </div>
            <div ref={desktopTopRailRef} className="overflow-x-auto overflow-y-hidden">
              <div style={{ width: desktopScrollWidth, height: 1 }} />
            </div>
          </div>
        )}

        <div ref={desktopScrollRef} className="overflow-x-auto">
          <table className="min-w-[1080px] w-full caption-bottom text-sm">
            <thead className="bg-slate-100/70 dark:bg-slate-800/60 [&_tr]:border-b [&_tr]:border-[var(--ph-border)]">
              <tr>
                <th className="h-12 pl-6 pr-4 text-left align-middle text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Repository
                </th>
                <th className="h-12 px-4 text-left align-middle text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Workflow
                </th>
                <th className="h-12 px-4 text-left align-middle text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Status
                </th>
                <th className="h-12 px-4 text-left align-middle text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Failure Type
                </th>
                <th className="h-12 px-4 text-left align-middle text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Time
                </th>
                <th className="h-12 px-4 pr-6 text-left align-middle text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="[&_tr:last-child]:border-0">
              {activities.map((activity) => {
                const externalMeta = getExternalDiagnosticsMeta(activity)
                const statusTags = getStatusTags(activity)
                const visibleStatusTags = statusTags.slice(0, MAX_STATUS_TAGS)
                const hiddenStatusTagCount = Math.max(statusTags.length - visibleStatusTags.length, 0)
                const failureContext = getFailureContext(activity)
                return (
                  <tr
                    key={activity.id}
                    data-activity-id={activity.id}
                    className={`border-b border-[var(--ph-border)] transition-colors hover:bg-slate-100/60 dark:hover:bg-slate-800/40 ${
                      activity.id === highlightedActivityId ? 'bg-azure-500/10' : ''
                    }`}
                  >
                    <td className="whitespace-nowrap p-4 pl-6 align-middle">
                      <div className="flex items-center">
                        <GitBranch className="mr-2 h-5 w-5 text-gray-400" />
                        <div>
                          <div
                            className="max-w-[180px] truncate text-sm font-medium text-gray-900 dark:text-white"
                            title={activity.repository_name.split('/')[1]}
                          >
                            {activity.repository_name.split('/')[1]}
                          </div>
                          <div className="text-xs text-gray-500">
                            {activity.repository_name.split('/')[0]}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="whitespace-nowrap p-4 align-middle">
                      <div
                        className="max-w-[220px] truncate text-sm text-gray-900 dark:text-white"
                        title={activity.workflow_name}
                      >
                        {activity.workflow_name}
                      </div>
                      <div className="text-xs text-gray-500">
                        Run #{activity.workflow_run_id}
                      </div>
                    </td>
                    <td className="whitespace-nowrap p-4 align-middle">
                      {activity.id === focusedActivityId && (
                        <div className="mb-2">
                          <Badge className="rounded-md text-[11px]" variant="success">
                            Focused View
                          </Badge>
                        </div>
                      )}
                      <StatusBadge status={activity.status} size="sm" />
                      <div className="mt-2 flex max-w-[18rem] flex-wrap gap-1">
                        {visibleStatusTags.map((tag, index) => (
                          <Badge
                            key={`${tag.label}-${index}`}
                            className="max-w-[18rem] truncate rounded-md text-[11px]"
                            variant={tag.variant}
                            title={tag.title || tag.label}
                          >
                            {tag.label}
                          </Badge>
                        ))}
                        {hiddenStatusTagCount > 0 && (
                          <Badge className="max-w-full rounded-md text-[11px]" variant="outline">
                            +{hiddenStatusTagCount} more
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="p-4 align-top">
                      {activity.failure_type ? (
                        <div className="space-y-1">
                          <FailureTypeBadge type={activity.failure_type} />
                          {failureContext && (
                            <p
                              className="max-w-[240px] truncate text-xs text-gray-500 dark:text-gray-400"
                              title={failureContext}
                            >
                              {failureContext}
                            </p>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap p-4 align-middle text-sm text-gray-500">
                      {formatDistanceToNow(new Date(activity.created_at), { addSuffix: true })}
                    </td>
                    <td className="whitespace-nowrap p-4 pr-6 align-middle text-sm">
                      <div className="flex items-center space-x-2">
                        <Button asChild variant="ghost" size="sm">
                          <Link to={`/app/activities/${activity.id}`}>View</Link>
                        </Button>
                        {externalMeta?.findingsUrl && (
                          <Button asChild variant="ghost" size="sm">
                            <a
                              href={externalMeta.findingsUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              Findings
                            </a>
                          </Button>
                        )}
                        {activity.remediation_result?.pr_url && (
                          <Button asChild variant="ghost" size="sm">
                            <a
                              href={activity.remediation_result.pr_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              aria-label="Open pull request"
                            >
                              <ExternalLink className="h-4 w-4" />
                            </a>
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  )
}
