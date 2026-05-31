import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Copy } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import type { AdminSettingsAuditEntry } from '../../api/client'
import { EMPTY_STATES } from '../../constants/emptyStates'
import { formatActorLabel, formatAuditTimestampUtc, getEffectiveAuditChanges } from './types'
import { copyToClipboard } from '@/utils/copyToClipboard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

interface Props {
  canLoad: boolean
  entries: AdminSettingsAuditEntry[] | undefined
  isLoading: boolean
  isError: boolean
  error: Error | null
  onLoad: () => void
  title?: string
  description?: string
  defaultVisibleCount?: number
  pageSize?: number
  defaultExpanded?: boolean
  ctaHref?: string
  ctaLabel?: string
}

export default function AuditTrailPanel({
  canLoad,
  entries,
  isLoading,
  isError,
  error,
  onLoad,
  title = 'Admin Audit Trail',
  description = 'Latest admin setting changes with actor, request trace, and effective diff.',
  defaultVisibleCount = 5,
  pageSize = 5,
  defaultExpanded = true,
  ctaHref,
  ctaLabel,
}: Props) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [visibleCount, setVisibleCount] = useState(defaultVisibleCount)

  useEffect(() => {
    setVisibleCount(defaultVisibleCount)
  }, [defaultVisibleCount, entries?.length])

  const visibleEntries = useMemo(() => entries?.slice(0, visibleCount), [entries, visibleCount])
  const hasMore = (entries?.length || 0) > visibleCount

  const handleCopyTrace = async (entry: AdminSettingsAuditEntry) => {
    if (!entry.request_id) {
      toast.error('No trace id available for this entry')
      return
    }

    const tracePayload = [
      `X-Request-Id: ${entry.request_id}`,
      '',
      `Actor: ${entry.actor || 'unknown'}`,
      '',
      `When: ${new Date(entry.timestamp).toISOString()}`,
    ].join('\n')

    try {
      await copyToClipboard(tracePayload)
      toast.success('Trace copied')
    } catch {
      toast.error('Unable to copy trace')
    }
  }

  return (
    <Card className="p-4 md:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--ph-text)]">{title}</h2>
          <p className="mt-1 text-sm text-[var(--ph-muted)]">
            {description}
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          disabled={isLoading || !canLoad}
          onClick={onLoad}
        >
          {isLoading ? 'Refreshing...' : 'Refresh'}
        </Button>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="text-xs text-[var(--ph-muted)]">
          Showing {visibleEntries?.length || 0} of {entries?.length || 0} events.
        </p>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => setIsExpanded((prev) => !prev)}
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : 'rotate-0'}`} />
          {isExpanded ? 'Collapse' : 'Expand'}
        </Button>
      </div>

      {isError && (
        <p className="mt-4 text-sm text-[var(--ph-danger)]">
          {error instanceof Error ? error.message : 'Failed to load audit entries'}
        </p>
      )}

      {isExpanded && visibleEntries && visibleEntries.length > 0 && (
        <div className="mt-4 space-y-3">
          {visibleEntries.map((entry) => {
            const effectiveChanges = getEffectiveAuditChanges(entry)
            const effectiveChangeJson = Object.fromEntries(
              effectiveChanges.map(({ key, diff }) => [key, { old: diff?.old ?? null, new: diff?.new ?? null }])
            )
            return (
              <div
                key={`${entry.timestamp}-${entry.request_id ?? 'none'}`}
                className="rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/35 p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-1">
                    <p
                      className="font-mono text-[11px] text-[var(--ph-text)]"
                      title={entry.actor || 'unknown'}
                    >
                      {formatActorLabel(entry.actor)}
                    </p>
                    <p className="text-xs text-[var(--ph-muted)]">
                      {formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}
                      {' . '}
                      {formatAuditTimestampUtc(entry.timestamp)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="max-w-[260px] truncate font-mono text-[11px] text-[var(--ph-muted)]" title={entry.request_id || 'n/a'}>
                      {entry.request_id || 'n/a'}
                    </span>
                    {entry.request_id && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => void handleCopyTrace(entry)}
                        aria-label="Copy trace"
                      >
                        <Copy className="h-4 w-4" />
                        Copy Trace
                      </Button>
                    )}
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1">
                  {entry.changed_keys.map((key) => (
                    <Badge key={`${entry.timestamp}-${key}`} variant="outline" className="font-mono text-[11px]">
                      {key}
                    </Badge>
                  ))}
                </div>

                <details className="mt-3 rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)] p-2">
                  <summary className="cursor-pointer text-xs font-medium text-[var(--ph-muted)]">
                    View value changes ({effectiveChanges.length})
                  </summary>
                  {effectiveChanges.length > 0 ? (
                    <pre className="mt-2 overflow-x-auto rounded bg-slate-950/60 p-2 text-xs text-slate-200">
                      {JSON.stringify(effectiveChangeJson, null, 2)}
                    </pre>
                  ) : (
                    <p className="mt-2 text-xs text-[var(--ph-muted)]">No effective value changes recorded.</p>
                  )}
                </details>
              </div>
            )
          })}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            {hasMore && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => setVisibleCount((prev) => prev + pageSize)}
              >
                Load more
              </Button>
            )}
            {visibleCount > defaultVisibleCount && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setVisibleCount(defaultVisibleCount)}
              >
                Show less
              </Button>
            )}
          </div>

          {ctaHref && ctaLabel && (
            <div className="pt-1">
              <Button asChild size="sm" variant="secondary">
                <Link to={ctaHref}>{ctaLabel}</Link>
              </Button>
            </div>
          )}
        </div>
      )}

      {isExpanded && visibleEntries && visibleEntries.length === 0 && (
        <div className="mt-4 rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/20 p-4">
          <p className="text-sm font-medium text-[var(--ph-text)]">{EMPTY_STATES.audit.title}</p>
          <p className="mt-1 text-sm text-[var(--ph-muted)]">{EMPTY_STATES.audit.body}</p>
        </div>
      )}
    </Card>
  )
}
