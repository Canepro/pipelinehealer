import { Copy } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { toast } from 'sonner'
import type { AdminSettingsAuditEntry } from '../../api/client'
import { EMPTY_STATES } from '../../constants/emptyStates'
import {
  formatActorLabel,
  formatAuditTimestampUtc,
  formatAuditValue,
  getEffectiveAuditChanges,
} from './types'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Props {
  canLoad: boolean
  entries: AdminSettingsAuditEntry[] | undefined
  isLoading: boolean
  isError: boolean
  error: Error | null
  onLoad: () => void
}

export default function AuditTrailPanel({
  canLoad,
  entries,
  isLoading,
  isError,
  error,
  onLoad,
}: Props) {
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
      await navigator.clipboard.writeText(tracePayload)
      toast.success('Trace copied')
    } catch {
      toast.error('Unable to copy trace')
    }
  }

  return (
    <Card className="p-4 md:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Admin Audit Trail
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Intentionally not auto-loaded. Audit access is gated and pulled only on explicit admin action.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          disabled={isLoading || !canLoad}
          onClick={onLoad}
        >
          {isLoading ? 'Loading...' : 'Load Audit'}
        </Button>
      </div>

      {isError && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">
          {error instanceof Error ? error.message : 'Failed to load audit entries'}
        </p>
      )}

      {entries && entries.length > 0 && (
        <div className="mt-4 rounded-md border border-[var(--ph-border)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>What Changed</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Trace</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => {
                const effectiveChanges = getEffectiveAuditChanges(entry)
                return (
                  <TableRow key={`${entry.timestamp}-${entry.request_id ?? 'none'}`}>
                    <TableCell className="text-xs text-gray-700 dark:text-gray-200">
                      <div className="space-y-1">
                        {effectiveChanges.map(({ key, diff }) => (
                          <p key={key}>
                            <span className="font-medium">{key}</span>: {formatAuditValue(diff?.old)} {'->'}{' '}
                            {formatAuditValue(diff?.new)}
                          </p>
                        ))}
                        {effectiveChanges.length === 0 && (
                          <p className="text-gray-500 dark:text-gray-400">No effective value changes recorded.</p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell
                      className="font-mono text-[11px] text-gray-600 dark:text-gray-300"
                      title={entry.actor || 'unknown'}
                    >
                      {formatActorLabel(entry.actor)}
                    </TableCell>
                    <TableCell className="text-xs text-gray-600 dark:text-gray-300">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px]">{entry.request_id || 'n/a'}</span>
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
                    </TableCell>
                    <TableCell className="text-xs text-gray-600 dark:text-gray-300">
                      <span
                        className="cursor-help"
                        title={new Date(entry.timestamp).toISOString()}
                      >
                        {formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}
                        {' . '}
                        {formatAuditTimestampUtc(entry.timestamp)}
                      </span>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {entries && entries.length === 0 && (
        <div className="mt-4 rounded-lg border border-[var(--ph-border)] p-4">
          <p className="text-sm font-medium text-gray-200">{EMPTY_STATES.audit.title}</p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{EMPTY_STATES.audit.body}</p>
        </div>
      )}
    </Card>
  )
}
