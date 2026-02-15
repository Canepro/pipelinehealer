import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow, format } from 'date-fns'
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  GitBranch,
  RefreshCw,
  FileCode,
  AlertTriangle,
} from 'lucide-react'
import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import FailureTypeBadge from '../components/FailureTypeBadge'

function formatSourceLabel(source: string): string {
  const normalized = source.trim().replace(/[_-]+/g, ' ')
  if (!normalized) {
    return 'External Tool'
  }
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase())
}

function getExternalDiagnosticStatusMeta(status: string): {
  label: string
  className: string
} {
  switch (status) {
    case 'available':
      return {
        label: 'Available',
        className:
          'inline-flex items-center rounded-md bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200',
      }
    case 'error':
      return {
        label: 'Error',
        className:
          'inline-flex items-center rounded-md bg-rose-100 px-2 py-1 text-xs font-medium text-rose-700 dark:bg-rose-900/40 dark:text-rose-200',
      }
    case 'unavailable':
      return {
        label: 'Unavailable',
        className:
          'inline-flex items-center rounded-md bg-amber-100 px-2 py-1 text-xs font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-200',
      }
    case 'disabled':
      return {
        label: 'Disabled',
        className:
          'inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200',
      }
    default:
      return {
        label: status || 'Unknown',
        className:
          'inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200',
      }
  }
}

function formatConfidenceDelta(delta: number): string {
  if (delta === 0) {
    return 'No confidence change'
  }
  const sign = delta > 0 ? '+' : '-'
  const pct = Math.round(Math.abs(delta) * 100)
  return `${sign}${pct}% confidence`
}

function getIssueProposalMeta(details: Record<string, unknown> | undefined): {
  includesProposedFix: boolean
  reasonCode: string | null
  reasonDetail: string | null
} {
  const includes = details?.includes_proposed_fix === true
  const reason =
    typeof details?.not_auto_reason_code === 'string'
      ? details.not_auto_reason_code
      : null
  const reasonDetail =
    typeof details?.not_auto_reason_detail === 'string'
      ? details.not_auto_reason_detail
      : null
  return { includesProposedFix: includes, reasonCode: reason, reasonDetail }
}

const DETAIL_SECTIONS: Array<{ key: string; label: string }> = [
  { key: 'summary', label: 'Summary' },
  { key: 'root_cause', label: 'Root Cause' },
  { key: 'failed_jobs', label: 'Failed Jobs' },
  { key: 'investigation_findings', label: 'Investigation Findings' },
  { key: 'recommended_actions', label: 'Recommended Actions' },
  { key: 'prevention_strategies', label: 'Prevention Strategies' },
  { key: 'historical_context', label: 'Historical Context' },
  { key: 'ai_self_improvement', label: 'AI Self-Improvement' },
]

/** Maximum visible lines before truncation with "Show more". */
const SECTION_LINE_LIMIT = 6

/**
 * Lightweight inline markdown renderer.
 *
 * Handles:
 * - `**bold**`
 * - `` `code` ``
 * - `[text](url)` links
 *
 * Returns an array of React nodes suitable for inline rendering.
 */
function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = []
  // Regex alternation: bold | code | link
  const re = /\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  let key = 0

  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    if (match[1] != null) {
      parts.push(
        <strong key={key++} className="font-semibold">
          {match[1]}
        </strong>,
      )
    } else if (match[2] != null) {
      parts.push(
        <code
          key={key++}
          className="bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded text-xs font-mono"
        >
          {match[2]}
        </code>,
      )
    } else if (match[3] != null && match[4] != null) {
      parts.push(
        <a
          key={key++}
          href={match[4]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-azure-600 hover:text-azure-700 dark:text-azure-400 underline"
        >
          {match[3]}
        </a>,
      )
    }
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  return parts
}

/**
 * Render a section body string as structured content.
 *
 * Detects bullet lists (- item, * item) vs plain paragraphs and renders
 * them with appropriate styling instead of raw whitespace-pre-wrap.
 */
function MarkdownBody({ text }: { text: string }) {
  const lines = text.split('\n')
  const groups: Array<{ type: 'paragraph' | 'bullet'; lines: string[] }> = []

  for (const raw of lines) {
    const trimmed = raw.trim()
    if (!trimmed) {
      // Blank line — start a fresh group on next non-empty line.
      continue
    }
    const isBullet = /^[-*]\s|^- \[[ x]\]\s/i.test(trimmed)
    const last = groups[groups.length - 1]
    if (last && last.type === (isBullet ? 'bullet' : 'paragraph')) {
      last.lines.push(trimmed)
    } else {
      groups.push({ type: isBullet ? 'bullet' : 'paragraph', lines: [trimmed] })
    }
  }

  return (
    <>
      {groups.map((group, gi) =>
        group.type === 'bullet' ? (
          <ul key={gi} className="list-disc list-inside space-y-1 ml-1">
            {group.lines.map((line, li) => {
              // Strip leading - / * / - [x]
              const content = line.replace(/^[-*]\s+(\[[ x]\]\s+)?/i, '')
              const checked = /^- \[x\]/i.test(line)
              return (
                <li key={li} className="text-sm text-gray-900 dark:text-white leading-relaxed">
                  {checked && (
                    <span className="text-emerald-600 dark:text-emerald-400 mr-1">&#10003;</span>
                  )}
                  {renderInlineMarkdown(content)}
                </li>
              )
            })}
          </ul>
        ) : (
          <p key={gi} className="text-sm text-gray-900 dark:text-white leading-relaxed">
            {group.lines.map((line, li) => (
              <span key={li}>
                {li > 0 && ' '}
                {renderInlineMarkdown(line)}
              </span>
            ))}
          </p>
        ),
      )}
    </>
  )
}

/**
 * Renders a section with optional "Show more / Show less" truncation.
 */
function CollapsibleSection({ label, text }: { label: string; text: string }) {
  const lines = text.split('\n').filter((l) => l.trim())
  const needsTruncation = lines.length > SECTION_LINE_LIMIT
  const [showAll, setShowAll] = useState(false)

  const displayText = needsTruncation && !showAll
    ? lines.slice(0, SECTION_LINE_LIMIT).join('\n')
    : text

  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
        {label}
      </p>
      <div className="space-y-2">
        <MarkdownBody text={displayText} />
      </div>
      {needsTruncation && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-1 text-xs font-medium text-azure-600 hover:text-azure-700 dark:text-azure-400 dark:hover:text-azure-300"
        >
          {showAll ? 'Show less' : `Show more (${lines.length - SECTION_LINE_LIMIT} more lines)`}
        </button>
      )}
    </div>
  )
}

function ExternalFindingsPanel({ details, defaultOpen = false }: { details: Record<string, unknown>; defaultOpen?: boolean }) {
  const [expanded, setExpanded] = useState(defaultOpen)

  const hasSections = DETAIL_SECTIONS.some(
    (s) => typeof details[s.key] === 'string' && (details[s.key] as string).trim(),
  )
  if (!hasSections) return null

  const doctorRunUrl = typeof details.doctor_run_url === 'string' ? details.doctor_run_url : null
  const doctorEngine = typeof details.doctor_engine === 'string' ? details.doctor_engine : null
  const doctorModel = typeof details.doctor_model === 'string' ? details.doctor_model : null
  const trigger = typeof details.trigger === 'string' ? details.trigger : null

  return (
    <div className="mt-3 w-full">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-azure-600 dark:hover:text-azure-400 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        External Findings Details
      </button>
      {expanded && (
        <div className="mt-3 space-y-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
          {(doctorEngine || doctorModel || trigger) && (
            <div className="flex flex-wrap items-center gap-2 pb-3 border-b border-gray-200 dark:border-gray-700">
              {doctorEngine && (
                <span className="inline-flex items-center rounded-md bg-violet-100 px-2 py-1 text-xs font-medium text-violet-700 dark:bg-violet-900/40 dark:text-violet-200">
                  Engine: {doctorEngine}
                </span>
              )}
              {doctorModel && (
                <span className="inline-flex items-center rounded-md bg-violet-100 px-2 py-1 text-xs font-medium text-violet-700 dark:bg-violet-900/40 dark:text-violet-200">
                  Model: {doctorModel}
                </span>
              )}
              {trigger && (
                <span className="inline-flex items-center rounded-md bg-gray-200 px-2 py-1 text-xs font-medium text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                  Trigger: {trigger}
                </span>
              )}
              {doctorRunUrl && (
                <a
                  href={doctorRunUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center text-xs text-azure-600 hover:text-azure-700 dark:text-azure-400"
                >
                  Doctor workflow run
                  <ExternalLink className="h-3 w-3 ml-1" />
                </a>
              )}
            </div>
          )}
          {DETAIL_SECTIONS.map(({ key, label }) => {
            const value = details[key]
            if (typeof value !== 'string' || !value.trim()) return null
            return <CollapsibleSection key={key} label={label} text={value} />
          })}
        </div>
      )}
    </div>
  )
}

export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

  const { data: activity, isLoading, error } = useQuery({
    queryKey: ['activity', id],
    queryFn: () => api.getActivity(id!),
    enabled: !!id,
  })

  const retryMutation = useMutation({
    mutationFn: () => api.retryActivity(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['activity', id] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-azure-500 border-t-transparent rounded-full"></div>
      </div>
    )
  }

  if (error || !activity) {
    return (
      <div className="card p-8 text-center">
        <AlertTriangle className="h-12 w-12 text-red-500 mx-auto" />
        <h2 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">
          Activity Not Found
        </h2>
        <p className="mt-2 text-gray-500">
          The requested activity could not be found.
        </p>
        <Link to="/activities" className="btn-primary mt-4 inline-block">
          Back to Activities
        </Link>
      </div>
    )
  }
  const remediationMeta = getIssueProposalMeta(activity.remediation_result?.details)
  const externalDiagnostics = activity.external_diagnostics ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/activities"
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Activity Details
            </h1>
            <p className="text-sm text-gray-500">{activity.id}</p>
          </div>
        </div>
        {(activity.status === 'failed' || activity.status === 'skipped') && (
          <button
            onClick={() => retryMutation.mutate()}
            disabled={retryMutation.isPending}
            className="btn-primary flex items-center"
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${
                retryMutation.isPending ? 'animate-spin' : ''
              }`}
            />
            Retry
          </button>
        )}
      </div>

      {/* Overview Card */}
      <div className="card p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Repository
            </p>
            <div className="flex items-center mt-1">
              <GitBranch className="h-5 w-5 text-gray-400 mr-2" />
              <a
                href={`https://github.com/${activity.repository_name}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-azure-600 hover:text-azure-700 dark:text-azure-400 font-medium"
              >
                {activity.repository_name}
                <ExternalLink className="h-3 w-3 inline ml-1" />
              </a>
            </div>
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Workflow</p>
            <p className="mt-1 font-medium text-gray-900 dark:text-white">
              {activity.workflow_name}
            </p>
            <p className="text-xs text-gray-500">
              Run #{activity.workflow_run_id}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Status</p>
            <div className="mt-1">
              <StatusBadge status={activity.status} />
            </div>
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Failure Type
            </p>
            <div className="mt-1">
              {activity.failure_type ? (
                <FailureTypeBadge type={activity.failure_type} />
              ) : (
                <span className="text-gray-400">Not determined</span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Created</p>
            <p className="mt-1 text-gray-900 dark:text-white">
              {format(new Date(activity.created_at), 'PPpp')}
            </p>
            <p className="text-xs text-gray-500">
              {formatDistanceToNow(new Date(activity.created_at), {
                addSuffix: true,
              })}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Updated</p>
            <p className="mt-1 text-gray-900 dark:text-white">
              {format(new Date(activity.updated_at), 'PPpp')}
            </p>
          </div>
          {activity.duration_seconds && (
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Duration
              </p>
              <p className="mt-1 text-gray-900 dark:text-white">
                {Math.round(activity.duration_seconds)}s
              </p>
            </div>
          )}
        </div>
      </div>

      {/* External Diagnostics Card */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          External Diagnostics
        </h2>
        {externalDiagnostics.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No external diagnostics available. PipelineHealer used built-in
            analysis only.
          </p>
        ) : (
          <div className="space-y-4">
            {externalDiagnostics.map((diagnostic, index) => {
              const statusMeta = getExternalDiagnosticStatusMeta(diagnostic.status)
              return (
                <div
                  key={`${diagnostic.source}-${diagnostic.collected_at}-${index}`}
                  className="rounded-lg border border-gray-200 dark:border-gray-700 p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center rounded-md bg-sky-100 px-2 py-1 text-xs font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-200">
                      {formatSourceLabel(diagnostic.source)}
                    </span>
                    <span className={statusMeta.className}>{statusMeta.label}</span>
                    {typeof diagnostic.matched_run_id === 'number' && (
                      <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                        Run #{diagnostic.matched_run_id}
                      </span>
                    )}
                    <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                      {formatConfidenceDelta(diagnostic.confidence_delta)}
                    </span>
                  </div>

                  {diagnostic.summary && (
                    <p className="mt-3 text-sm text-gray-900 dark:text-white">
                      {diagnostic.summary}
                    </p>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    {diagnostic.url && (
                      <a
                        href={diagnostic.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center text-sm text-azure-600 hover:text-azure-700 dark:text-azure-400"
                      >
                        Open findings
                        <ExternalLink className="h-4 w-4 ml-1" />
                      </a>
                    )}
                    {typeof (diagnostic.metadata as Record<string, unknown>)?.details === 'object' &&
                      (diagnostic.metadata as Record<string, unknown>).details !== null && (
                        <ExternalFindingsPanel details={(diagnostic.metadata as Record<string, unknown>).details as Record<string, unknown>} defaultOpen={diagnostic.status === 'available'} />
                      )}
                  </div>
                  {!diagnostic.url && typeof (diagnostic.metadata as Record<string, unknown>)?.details !== 'object' && (
                    <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                      No findings link published by the external workflow.
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Diagnosis Card */}
      {activity.diagnosis && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Diagnosis
          </h2>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Root Cause
              </p>
              <p className="mt-1 text-gray-900 dark:text-white">
                {activity.diagnosis.root_cause}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Confidence
                </p>
                <div className="mt-1 flex items-center">
                  <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2 mr-2">
                    <div
                      className="bg-azure-500 h-2 rounded-full"
                      style={{
                        width: `${activity.diagnosis.confidence * 100}%`,
                      }}
                    />
                  </div>
                  <span className="text-sm font-medium text-gray-900 dark:text-white">
                    {Math.round(activity.diagnosis.confidence * 100)}%
                  </span>
                </div>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Auto-Fixable
                </p>
                <p className="mt-1 text-gray-900 dark:text-white">
                  {activity.diagnosis.is_auto_fixable ? 'Yes' : 'No'}
                </p>
              </div>
            </div>
            {activity.diagnosis.suggested_fix && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Suggested Fix
                </p>
                <p className="mt-1 text-gray-900 dark:text-white">
                  {activity.diagnosis.suggested_fix}
                </p>
              </div>
            )}
            {activity.diagnosis.affected_files.length > 0 && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Affected Files
                </p>
                <div className="mt-2 space-y-1">
                  {activity.diagnosis.affected_files.map((file) => (
                    <div
                      key={file}
                      className="flex items-center text-sm text-gray-900 dark:text-white"
                    >
                      <FileCode className="h-4 w-4 text-gray-400 mr-2" />
                      <code className="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                        {file}
                      </code>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Remediation Result Card */}
      {activity.remediation_result && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Remediation Result
          </h2>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Action Taken
                </p>
                <p className="mt-1 text-gray-900 dark:text-white">
                  {activity.remediation_result.action_taken
                    .replace(/_/g, ' ')
                    .replace(/\b\w/g, (c) => c.toUpperCase())
                    .replace(/\bPr\b/, 'PR')}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Success
                </p>
                <p className="mt-1">
                  {activity.remediation_result.success ? (
                    <span className="text-green-600 font-medium">Yes</span>
                  ) : (
                    <span className="text-red-600 font-medium">No</span>
                  )}
                </p>
              </div>
            </div>
            {activity.remediation_result.pr_url && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Pull Request
                </p>
                <a
                  href={activity.remediation_result.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 text-azure-600 hover:text-azure-700 dark:text-azure-400 flex items-center"
                >
                  {activity.remediation_result.pr_url}
                  <ExternalLink className="h-4 w-4 ml-1" />
                </a>
              </div>
            )}
            {activity.remediation_result.issue_url && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Issue Created
                </p>
                <a
                  href={activity.remediation_result.issue_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 text-azure-600 hover:text-azure-700 dark:text-azure-400 flex items-center"
                >
                  {activity.remediation_result.issue_url}
                  <ExternalLink className="h-4 w-4 ml-1" />
                </a>
              </div>
            )}
            {remediationMeta.includesProposedFix && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Issue Metadata
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="inline-flex items-center rounded-md bg-sky-100 px-2 py-1 text-xs font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-200">
                    Includes Proposed Fix
                  </span>
                  {remediationMeta.reasonCode && (
                    <span className="inline-flex items-center rounded-md bg-amber-100 px-2 py-1 text-xs font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-200">
                      {remediationMeta.reasonCode}
                    </span>
                  )}
                </div>
                {remediationMeta.reasonDetail && (
                  <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
                    {remediationMeta.reasonDetail}
                  </p>
                )}
              </div>
            )}
            {activity.remediation_result.error_message && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Error
                </p>
                <p className="mt-1 text-red-600">
                  {activity.remediation_result.error_message}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Error Card */}
      {activity.error && (
        <div className="card p-6 border-red-200 dark:border-red-800">
          <h2 className="text-lg font-semibold text-red-600 mb-2">Error</h2>
          <p className="text-gray-900 dark:text-white">{activity.error}</p>
        </div>
      )}
    </div>
  )
}
