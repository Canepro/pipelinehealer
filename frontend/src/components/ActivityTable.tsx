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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface ActivityTableProps {
  activities: Activity[]
  isLoading?: boolean
  focusedActivityId?: string | null
  highlightedActivityId?: string | null
}

type StatusTag = {
  label: string
  variant: 'success' | 'destructive' | 'secondary' | 'outline'
}

const MAX_STATUS_TAGS = 4

function formatSourceLabel(source: string): string {
  const normalizedRaw = source.trim().toLowerCase()
  const knownLabels: Record<string, string> = {
    'ci-doctor': 'CI Doctor',
    'external-diagnostics': 'External Diagnostics',
    'github-mcp': 'GitHub MCP',
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
  return { includesProposedFix: includes, reasonCode: reason, output, reusedExistingPr }
}

function getDiagnosisSourceLabel(activity: Activity): string | null {
  const source = activity.diagnosis?.diagnosis_source
  if (source === 'llm') return 'LLM'
  if (source === 'pattern') return 'Pattern'
  return null
}

function getModelPathLabel(activity: Activity): string | null {
  const path = activity.llm_model_path
  if (!path) return null
  const provider = path.provider || 'unknown'
  const model = path.model || 'unknown'
  return `${provider}:${model}`
}

function getMcpLabel(activity: Activity): { label: string; variant: 'success' | 'secondary' } | null {
  const path = activity.mcp_model_path
  if (!path || !path.enabled) return null
  const provider = formatSourceLabel(path.provider || 'mcp')
  if (path.available) {
    return { label: `MCP: ${provider}`, variant: 'success' }
  }
  return { label: `MCP: ${provider} (limited)`, variant: 'secondary' }
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
  const diagnosisSourceLabel = getDiagnosisSourceLabel(activity)
  const modelPathLabel = getModelPathLabel(activity)
  const mcpLabel = getMcpLabel(activity)
  const tags: StatusTag[] = []

  if (meta.output) {
    tags.push({ label: `Output: ${meta.output}`, variant: 'secondary' })
  }
  if (meta.includesProposedFix) {
    tags.push({ label: 'Includes Proposed Fix', variant: 'outline' })
  }
  if (meta.reasonCode) {
    tags.push({ label: meta.reasonCode, variant: 'secondary' })
  }
  if (externalMeta) {
    tags.push({ label: externalMeta.label, variant: externalMeta.variant })
  }
  // Only highlight diagnosis source when LLM path was used to reduce visual noise.
  if (diagnosisSourceLabel === 'LLM') {
    tags.push({ label: `Diagnosis: ${diagnosisSourceLabel}`, variant: 'secondary' })
  }
  if (diagnosisSourceLabel === 'LLM' && modelPathLabel) {
    tags.push({ label: `Model: ${modelPathLabel}`, variant: 'secondary' })
  }
  if (activity.llm_model_path?.fallback_used) {
    tags.push({ label: 'Fallback Used', variant: 'outline' })
  }
  // Show MCP tag only when limited to keep status focused.
  if (mcpLabel?.variant === 'secondary') {
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
                  <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
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
                    className="max-w-full break-all rounded-md text-[11px]"
                    variant={tag.variant}
                  >
                    {tag.label}
                  </Badge>
                ))}
                {hiddenStatusTagCount > 0 && (
                  <Badge className="max-w-full break-all rounded-md text-[11px]" variant="outline">
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
        <Table>
          <TableHeader className="bg-slate-100/70 dark:bg-slate-800/60">
            <TableRow>
              <TableHead className="pl-6">Repository</TableHead>
              <TableHead>Workflow</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Failure Type</TableHead>
              <TableHead>Time</TableHead>
              <TableHead className="pr-6">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {activities.map((activity) => {
              const externalMeta = getExternalDiagnosticsMeta(activity)
              const statusTags = getStatusTags(activity)
              const visibleStatusTags = statusTags.slice(0, MAX_STATUS_TAGS)
              const hiddenStatusTagCount = Math.max(statusTags.length - visibleStatusTags.length, 0)
              const failureContext = getFailureContext(activity)
              return (
                <TableRow
                  key={activity.id}
                  data-activity-id={activity.id}
                  className={`transition-colors ${
                    activity.id === highlightedActivityId ? 'bg-azure-500/10' : ''
                  }`}
                >
                  <TableCell className="pl-6 whitespace-nowrap">
                    <div className="flex items-center">
                      <GitBranch className="mr-2 h-5 w-5 text-gray-400" />
                      <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                          {activity.repository_name.split('/')[1]}
                        </div>
                        <div className="text-xs text-gray-500">
                          {activity.repository_name.split('/')[0]}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    <div className="text-sm text-gray-900 dark:text-white">
                      {activity.workflow_name}
                    </div>
                    <div className="text-xs text-gray-500">
                      Run #{activity.workflow_run_id}
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {activity.id === focusedActivityId && (
                      <div className="mb-2">
                        <Badge className="rounded-md text-[11px]" variant="success">
                          Focused View
                        </Badge>
                      </div>
                    )}
                    <StatusBadge status={activity.status} size="sm" />
                    <div className="mt-2 flex flex-wrap gap-1">
                      {visibleStatusTags.map((tag, index) => (
                        <Badge
                          key={`${tag.label}-${index}`}
                          className="max-w-full break-all rounded-md text-[11px]"
                          variant={tag.variant}
                        >
                          {tag.label}
                        </Badge>
                      ))}
                      {hiddenStatusTagCount > 0 && (
                        <Badge className="max-w-full break-all rounded-md text-[11px]" variant="outline">
                          +{hiddenStatusTagCount} more
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="align-top">
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
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm text-gray-500">
                    {formatDistanceToNow(new Date(activity.created_at), { addSuffix: true })}
                  </TableCell>
                  <TableCell className="pr-6 whitespace-nowrap text-sm">
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
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </Card>
  )
}
