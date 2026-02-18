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

const RAW_EVIDENCE_KEYS = new Set([
  'key_log_lines',
  'relevant_log_lines',
  'log_messages',
  'evidence',
  'raw_log_lines',
  'error_lines',
])

const STRUCTURED_EVIDENCE_OMIT_KEYS = new Set([
  ...RAW_EVIDENCE_KEYS,
  'violations',
  'additional',
  'message',
  'raw_logs',
])

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
  reusedExistingPr: boolean
} {
  const includes = details?.includes_proposed_fix === true
  const reason = (
    typeof details?.not_auto_reason_code === 'string'
      ? details.not_auto_reason_code
      : typeof details?.reason_code === 'string'
        ? details.reason_code
        : null
  ) as string | null
  const reasonDetail =
    typeof details?.not_auto_reason_detail === 'string'
      ? details.not_auto_reason_detail
      : typeof details?.reason_detail === 'string'
        ? details.reason_detail
      : null
  const reusedExistingPr = details?.reused_existing_pr === true
  return { includesProposedFix: includes, reasonCode: reason, reasonDetail, reusedExistingPr }
}

function toEvidenceLabel(key: string): string {
  return key
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function normalizeEvidenceLines(value: unknown): string[] {
  if (typeof value === 'string') {
    const line = value.trim()
    return line ? [line] : []
  }
  if (!Array.isArray(value)) return []
  return value
    .filter((line): line is string => typeof line === 'string')
    .map((line) => line.trim())
    .filter(Boolean)
}

function collectRawEvidenceLines(details: Record<string, unknown> | undefined): string[] {
  if (!details) return []
  const seen = new Set<string>()
  const lines: string[] = []
  for (const key of RAW_EVIDENCE_KEYS) {
    const entries = normalizeEvidenceLines(details[key])
    for (const entry of entries) {
      if (seen.has(entry)) continue
      seen.add(entry)
      lines.push(entry)
      if (lines.length >= 40) return lines
    }
  }
  const fallbackMessage = typeof details.message === 'string' ? details.message.trim() : ''
  if (fallbackMessage && !seen.has(fallbackMessage)) {
    lines.push(fallbackMessage)
  }
  return lines
}

function formatStructuredEvidenceValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    const compact = value
      .map((item) => (typeof item === 'string' ? item : JSON.stringify(item)))
      .filter((item) => typeof item === 'string' && item.length > 0)
      .slice(0, 5)
    if (compact.length === 0) return ''
    return compact.join(', ')
  }
  if (value && typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return ''
    }
  }
  return ''
}

function collectStructuredEvidence(
  details: Record<string, unknown> | undefined,
): Array<{ key: string; label: string; value: string }> {
  if (!details) return []
  const rows: Array<{ key: string; label: string; value: string }> = []
  for (const [key, rawValue] of Object.entries(details)) {
    if (STRUCTURED_EVIDENCE_OMIT_KEYS.has(key)) continue
    const formatted = formatStructuredEvidenceValue(rawValue).trim()
    if (!formatted) continue
    rows.push({
      key,
      label: toEvidenceLabel(key),
      value: formatted,
    })
    if (rows.length >= 12) break
  }
  return rows
}

function aggregateConfidenceBySource(
  diagnostics: Array<{ source: string; confidence_delta: number; status: string }>,
): Array<{ source: string; delta: number; samples: number; available: number }> {
  const bySource = new Map<string, { delta: number; samples: number; available: number }>()
  for (const diagnostic of diagnostics) {
    const source = diagnostic.source || 'unknown'
    const current = bySource.get(source) ?? { delta: 0, samples: 0, available: 0 }
    current.delta += diagnostic.confidence_delta
    current.samples += 1
    if (diagnostic.status === 'available') {
      current.available += 1
    }
    bySource.set(source, current)
  }
  return Array.from(bySource.entries())
    .map(([source, value]) => ({ source, ...value }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
}

type ExternalSignalSource = {
  source: string
  delta: number
  reason: string
}

function parseExternalSignalSources(value: unknown): ExternalSignalSource[] {
  if (!Array.isArray(value)) return []
  const parsed: ExternalSignalSource[] = []
  for (const item of value) {
    if (!item || typeof item !== 'object') continue
    const source = typeof (item as Record<string, unknown>).source === 'string'
      ? ((item as Record<string, unknown>).source as string)
      : 'unknown'
    const deltaRaw = (item as Record<string, unknown>).delta
    const delta = typeof deltaRaw === 'number' ? deltaRaw : 0
    const reason = typeof (item as Record<string, unknown>).reason === 'string'
      ? ((item as Record<string, unknown>).reason as string)
      : ''
    parsed.push({ source, delta, reason })
  }
  return parsed
}

function formatMcpStatus(enabled: boolean, available: boolean): string {
  if (!enabled) return 'Disabled'
  return available ? 'Available' : 'Limited'
}

function formatMcpReason(reason: string): string {
  const normalized = reason.trim().toLowerCase()
  const labels: Record<string, string> = {
    ok: 'Healthy and available',
    disabled: 'Disabled by runtime settings',
    provider_not_github: 'Unsupported provider for this action path',
    provider_health_error: 'Provider health check failed',
    missing_github_token: 'Missing GitHub credential/token',
    repo_not_allowlisted: 'Repository is outside MCP allowlist',
    tool_policy_disabled: 'Tool is disabled by policy',
    tool_policy_read_only: 'Tool policy allows read-only actions only',
    blocked_by_read_only_mode: 'Blocked by global read-only mode',
    approval_required: 'Blocked pending manual approval',
    mcp_disabled: 'MCP is disabled',
  }
  if (labels[normalized]) return labels[normalized]
  if (normalized.startsWith('branch_protection_respected')) {
    return 'Blocked to respect protected branch constraints'
  }
  return reason || 'Unknown'
}

type McpActionOutcome = {
  kind: 'success' | 'blocked' | 'error' | 'timeout' | 'other'
  label: string
  detail: string
  code: string | null
}

function mcpOutcomeBadgeClass(kind: McpActionOutcome['kind']): string {
  switch (kind) {
    case 'success':
      return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
    case 'blocked':
      return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200'
    case 'error':
      return 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200'
    case 'timeout':
      return 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-200'
    default:
      return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200'
  }
}

function parseMcpActionResult(rawResult: string): McpActionOutcome {
  const value = (rawResult || '').trim()
  if (!value) {
    return {
      kind: 'other',
      label: 'Unknown',
      detail: 'No result string captured.',
      code: null,
    }
  }

  if (value.startsWith('success:')) {
    const attempt = value.split(':').slice(1).join(':')
    return {
      kind: 'success',
      label: 'Allowed',
      detail: attempt ? `Completed (${attempt.replace(/_/g, ' ')})` : 'Completed successfully',
      code: value,
    }
  }
  if (value.startsWith('blocked:')) {
    const code = value.slice('blocked:'.length)
    return {
      kind: 'blocked',
      label: 'Blocked',
      detail: formatMcpReason(code),
      code,
    }
  }
  if (value.startsWith('timeout:')) {
    const code = value.slice('timeout:'.length)
    return {
      kind: 'timeout',
      label: 'Timeout',
      detail: code ? `Timed out (${code.replace(/_/g, ' ')})` : 'Timed out',
      code,
    }
  }
  if (value.startsWith('error:')) {
    const rest = value.slice('error:'.length)
    const [errorType] = rest.split(':')
    return {
      kind: 'error',
      label: 'Error',
      detail: errorType ? `Execution error (${errorType})` : 'Execution error',
      code: rest || value,
    }
  }
  return {
    kind: 'other',
    label: 'Result',
    detail: value,
    code: value,
  }
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
  const [showRawEvidence, setShowRawEvidence] = useState(false)
  const [showMcpDetails, setShowMcpDetails] = useState(false)

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

  const backfillMutation = useMutation({
    mutationFn: () => api.backfillDiagnostics(24),
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
        <Link to="/app/activities" className="btn-primary mt-4 inline-block">
          Back to Activities
        </Link>
      </div>
    )
  }
  const remediationMeta = getIssueProposalMeta(activity.remediation_result?.details)
  const externalDiagnostics = activity.external_diagnostics ?? []
  const diagnosisDetails = activity.diagnosis?.error_details as Record<string, unknown> | undefined
  const sourceConfidenceImpact = aggregateConfidenceBySource(externalDiagnostics)
  const structuredEvidence = collectStructuredEvidence(diagnosisDetails)
  const rawEvidenceLines = collectRawEvidenceLines(diagnosisDetails)
  const externalSignalBefore =
    typeof diagnosisDetails?.external_signal_confidence_before === 'number'
      ? diagnosisDetails.external_signal_confidence_before
      : null
  const externalSignalAfter =
    typeof diagnosisDetails?.external_signal_confidence_after === 'number'
      ? diagnosisDetails.external_signal_confidence_after
      : null
  const externalSignalDelta =
    typeof diagnosisDetails?.external_signal_confidence_delta === 'number'
      ? diagnosisDetails.external_signal_confidence_delta
      : null
  const externalSignalSources = parseExternalSignalSources(
    diagnosisDetails?.external_signal_sources,
  )
  const mcpPath = activity.mcp_model_path
  const mcpSourceAttribution = Object.entries(mcpPath?.source_attribution ?? {}).sort(
    (a, b) => b[1] - a[1],
  )
  const mcpToolUsage = Object.entries(mcpPath?.tool_invocations ?? {}).sort((a, b) => b[1] - a[1])
  const mcpToolCallCount = mcpToolUsage.reduce((total, [, count]) => total + count, 0)
  const mcpActionAudit = [...(mcpPath?.action_audit ?? [])].slice(-8).reverse()
  const mcpReasonCode = (mcpPath?.reason || '').trim()
  const mcpReasonLabel = formatMcpReason(mcpReasonCode)
  const failureContext = activity.failure_context
  const hasFailureContext = Boolean(
    failureContext?.failing_job ||
      failureContext?.failing_step ||
      failureContext?.failing_command ||
      failureContext?.signal,
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/app/activities"
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
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            External Diagnostics
          </h2>
          {(activity.status === 'completed' || activity.status === 'failed') && (
            <button
              onClick={() => backfillMutation.mutate()}
              disabled={backfillMutation.isPending}
              className="inline-flex items-center text-sm font-medium text-azure-600 hover:text-azure-700 dark:text-azure-400 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 mr-1.5 ${backfillMutation.isPending ? 'animate-spin' : ''}`}
              />
              {backfillMutation.isPending ? 'Backfilling...' : 'Backfill Diagnostics'}
            </button>
          )}
        </div>
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
                  {typeof (diagnostic.metadata as Record<string, unknown>)?.confidence_reason === 'string' && (
                    <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      Signal rationale:{' '}
                      {(diagnostic.metadata as Record<string, unknown>).confidence_reason as string}
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
            {hasFailureContext && (
              <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Failure Context</p>
                <div className="mt-2 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Failing Job</p>
                    <p className="text-gray-900 dark:text-white break-words">
                      {failureContext?.failing_job || 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Failing Step</p>
                    <p className="text-gray-900 dark:text-white break-words">
                      {failureContext?.failing_step || 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Command</p>
                    <p className="text-gray-900 dark:text-white break-words">
                      {failureContext?.failing_command || 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Signal</p>
                    <p className="text-gray-900 dark:text-white break-words">
                      {failureContext?.signal || 'N/A'}
                    </p>
                  </div>
                </div>
              </div>
            )}
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Root Cause
              </p>
              <p className="mt-1 text-gray-900 dark:text-white">
                {activity.diagnosis.root_cause}
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Diagnosis Source
                </p>
                <p className="mt-1 text-gray-900 dark:text-white capitalize">
                  {activity.diagnosis.diagnosis_source || 'unknown'}
                </p>
              </div>
            </div>
            {externalSignalDelta !== null && (
              <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  External Signal Attribution
                </p>
                <div className="mt-2 grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Confidence Before</p>
                    <p className="text-gray-900 dark:text-white">
                      {externalSignalBefore !== null ? `${Math.round(externalSignalBefore * 100)}%` : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">External Delta</p>
                    <p
                      className={
                        externalSignalDelta >= 0
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-rose-600 dark:text-rose-400'
                      }
                    >
                      {formatConfidenceDelta(externalSignalDelta)}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Confidence After</p>
                    <p className="text-gray-900 dark:text-white">
                      {externalSignalAfter !== null ? `${Math.round(externalSignalAfter * 100)}%` : 'N/A'}
                    </p>
                  </div>
                </div>
                {externalSignalSources.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {externalSignalSources.map((signal, idx) => (
                      <div
                        key={`${signal.source}-${idx}`}
                        className="rounded-md border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 px-3 py-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-medium text-gray-900 dark:text-white">
                            {formatSourceLabel(signal.source)}
                          </p>
                          <span
                            className={`text-xs font-semibold ${signal.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}
                          >
                            {formatConfidenceDelta(signal.delta)}
                          </span>
                        </div>
                        {signal.reason && (
                          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{signal.reason}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {activity.llm_model_path && (
              <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Model Path</p>
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Provider</p>
                    <p className="text-gray-900 dark:text-white">{activity.llm_model_path.provider}</p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Model/Deployment</p>
                    <p className="text-gray-900 dark:text-white break-all">{activity.llm_model_path.model}</p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Fallback Used</p>
                    <p className="text-gray-900 dark:text-white">
                      {activity.llm_model_path.fallback_used ? 'Yes' : 'No'}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">LLM Calls</p>
                    <p className="text-gray-900 dark:text-white">{activity.llm_model_path.call_count}</p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Total Latency</p>
                    <p className="text-gray-900 dark:text-white">
                      {Math.round(activity.llm_model_path.total_latency_ms)} ms
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">LLM Errors</p>
                    <p className="text-gray-900 dark:text-white">{activity.llm_model_path.error_count}</p>
                  </div>
                </div>
              </div>
            )}
            {mcpPath && (
              <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    MCP Observability
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowMcpDetails((prev) => !prev)}
                    className="text-xs font-medium text-azure-600 hover:text-azure-700 dark:text-azure-400"
                  >
                    {showMcpDetails ? 'Hide details' : 'Show details'}
                  </button>
                </div>
                <div className="mt-2 grid grid-cols-1 gap-3 text-sm md:grid-cols-2 lg:grid-cols-6">
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Provider</p>
                    <p className="text-gray-900 dark:text-white">{mcpPath.provider}</p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Status</p>
                    <p className="text-gray-900 dark:text-white">
                      {formatMcpStatus(mcpPath.enabled, mcpPath.available)}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Read Only</p>
                    <p className="text-gray-900 dark:text-white">{mcpPath.read_only ? 'Yes' : 'No'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Reason</p>
                    <p className="text-gray-900 dark:text-white break-words">{mcpReasonLabel}</p>
                    {mcpReasonCode && (
                      <p
                        className="mt-1 break-all font-mono text-[11px] text-gray-500 dark:text-gray-400"
                        title={mcpReasonCode}
                      >
                        raw: {mcpReasonCode}
                      </p>
                    )}
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Tool Calls</p>
                    <p className="text-gray-900 dark:text-white">{mcpToolCallCount}</p>
                  </div>
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Total Latency</p>
                    <p className="text-gray-900 dark:text-white">
                      {Math.round(mcpPath.total_latency_ms || 0)} ms
                    </p>
                  </div>
                </div>

                {showMcpDetails && (
                  <div className="mt-4 border-t border-gray-200 pt-3 dark:border-gray-700">
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                          Configured Tools
                        </p>
                        {mcpPath.configured_tools.length > 0 ? (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {mcpPath.configured_tools.map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-mono text-gray-700 dark:bg-gray-900/70 dark:text-gray-200"
                              >
                                {tool}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                            No configured MCP tools for this provider.
                          </p>
                        )}
                      </div>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                          Source Attribution
                        </p>
                        {mcpSourceAttribution.length > 0 ? (
                          <ul className="mt-2 space-y-1">
                            {mcpSourceAttribution.map(([source, count]) => (
                              <li
                                key={source}
                                className="flex items-center justify-between rounded border border-gray-200 px-2 py-1 text-sm dark:border-gray-700"
                              >
                                <span className="min-w-0">
                                  <span className="block text-gray-700 dark:text-gray-200">
                                    {formatSourceLabel(source)}
                                  </span>
                                  <span className="block break-all font-mono text-[11px] text-gray-500 dark:text-gray-400">
                                    {source}
                                  </span>
                                </span>
                                <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
                                  {count}
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                            No external source attributions were recorded for this activity.
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="mt-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        Tool Usage
                      </p>
                      {mcpToolUsage.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {mcpToolUsage.map(([tool, count]) => (
                            <li
                              key={tool}
                              className="flex items-center justify-between rounded border border-gray-200 px-2 py-1 text-sm dark:border-gray-700"
                            >
                              <span className="font-mono text-xs text-gray-700 dark:text-gray-200">
                                {tool}
                              </span>
                              <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
                                {count}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                          No MCP tool invocations captured for this activity yet.
                        </p>
                      )}
                    </div>
                    <div className="mt-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        Action Audit
                      </p>
                      {mcpActionAudit.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {mcpActionAudit.map((entry, index) => {
                            const outcome = parseMcpActionResult(entry.result)
                            return (
                              <li
                                key={`${entry.request_id}-${entry.tool}-${entry.payload_hash}-${index}`}
                                className="rounded border border-gray-200 px-2 py-1 text-xs dark:border-gray-700"
                              >
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <p className="break-all font-mono text-gray-700 dark:text-gray-200">
                                    {entry.tool}
                                  </p>
                                  <span
                                    className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${mcpOutcomeBadgeClass(outcome.kind)}`}
                                  >
                                    {outcome.label}
                                  </span>
                                </div>
                                <p className="mt-1 break-words text-[11px] text-gray-700 dark:text-gray-200">
                                  {outcome.detail}
                                </p>
                                {outcome.code && (
                                  <p
                                    className="mt-0.5 break-all font-mono text-[11px] text-gray-500 dark:text-gray-400"
                                    title={outcome.code}
                                  >
                                    raw: {outcome.code}
                                  </p>
                                )}
                                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                                  actor: {entry.actor} • provider: {entry.provider} • request: {entry.request_id}
                                </p>
                                <p className="text-[11px] text-gray-500 dark:text-gray-400">
                                  payload: {entry.payload_hash} • latency: {Math.round(entry.latency_ms || 0)} ms
                                  {entry.error_class ? ` • error: ${entry.error_class}` : ''}
                                </p>
                              </li>
                            )
                          })}
                        </ul>
                      ) : (
                        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                          No MCP action audit entries captured for this activity.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            {(sourceConfidenceImpact.length > 0 ||
              structuredEvidence.length > 0 ||
              rawEvidenceLines.length > 0) && (
              <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Evidence Layers
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowRawEvidence((prev) => !prev)}
                    disabled={rawEvidenceLines.length === 0}
                    className="text-xs font-medium text-azure-600 hover:text-azure-700 dark:text-azure-400 disabled:text-gray-400 disabled:cursor-not-allowed"
                  >
                    {showRawEvidence ? 'Hide raw extracts' : 'Show raw extracts'}
                  </button>
                </div>
                <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Confidence Impact By Source
                    </p>
                    {sourceConfidenceImpact.length > 0 ? (
                      <div className="space-y-2">
                        {sourceConfidenceImpact.map((item) => (
                          <div
                            key={item.source}
                            className="rounded-md border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 px-3 py-2"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-medium text-gray-900 dark:text-white">
                                {formatSourceLabel(item.source)}
                              </p>
                              <span
                                className={`text-xs font-semibold ${item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}
                              >
                                {formatConfidenceDelta(item.delta)}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              Samples: {item.samples} • Available findings: {item.available}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        No external confidence signals recorded.
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Structured Context
                    </p>
                    {structuredEvidence.length > 0 ? (
                      <div className="space-y-2">
                        {structuredEvidence.map((item) => (
                          <div
                            key={item.key}
                            className="rounded-md border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 px-3 py-2"
                          >
                            <p className="text-xs text-gray-500 dark:text-gray-400">{item.label}</p>
                            <p className="mt-1 text-sm text-gray-900 dark:text-white break-words">
                              {item.value}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        No additional structured context in this activity.
                      </p>
                    )}
                  </div>
                </div>
                {showRawEvidence && (
                  <div className="mt-4 border-t border-gray-200 pt-3 dark:border-gray-700">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Raw Log Extracts
                    </p>
                    {rawEvidenceLines.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {rawEvidenceLines.map((line, index) => (
                          <li
                            key={`${line}-${index}`}
                            className="rounded bg-gray-100 px-2 py-1 text-xs font-mono text-gray-700 dark:bg-gray-900/70 dark:text-gray-200"
                          >
                            {line}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                        Raw extracts are not present in this diagnosis payload.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
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
            {(remediationMeta.includesProposedFix ||
              remediationMeta.reusedExistingPr ||
              remediationMeta.reasonCode ||
              remediationMeta.reasonDetail) && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Result Metadata
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {remediationMeta.includesProposedFix && (
                    <span className="inline-flex items-center rounded-md bg-sky-100 px-2 py-1 text-xs font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-200">
                      Includes Proposed Fix
                    </span>
                  )}
                  {remediationMeta.reusedExistingPr && (
                    <span className="inline-flex items-center rounded-md bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                      Reused Existing PR
                    </span>
                  )}
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
