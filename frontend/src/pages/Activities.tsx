import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Filter, RefreshCw, X } from 'lucide-react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import ActivityTable from '../components/ActivityTable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Panel, PanelHeader, PanelBody } from '@/components/ui/panel'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'pending', label: 'Pending' },
  { value: 'analyzing', label: 'Analyzing' },
  { value: 'skipped', label: 'Skipped' },
]

const failureTypeOptions = [
  { value: '', label: 'All Types' },
  { value: 'dependency', label: 'Dependency' },
  { value: 'test', label: 'Test' },
  { value: 'lint', label: 'Lint' },
  { value: 'build_config', label: 'Build Config' },
  { value: 'timeout', label: 'Timeout' },
]

export default function Activities() {
  const [searchParams, setSearchParams] = useSearchParams()
  const focusedActivityId = searchParams.get('focus')
  const repositoryParam = searchParams.get('repository') || ''
  const statusParam = searchParams.get('status') || ''
  const failureTypeParam = searchParams.get('failure_type') || ''
  const [filters, setFilters] = useState({
    repository: repositoryParam,
    status: statusParam,
    failure_type: failureTypeParam,
    limit: 50,
  })
  const [repositoryDraft, setRepositoryDraft] = useState(repositoryParam)
  const [highlightedActivityId, setHighlightedActivityId] = useState<string | null>(null)

  const { data: activities, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['activities', filters],
    queryFn: () => api.getActivities(filters),
  })
  const hasFocusedActivity = useMemo(
    () => !!focusedActivityId && !!activities?.some((activity) => activity.id === focusedActivityId),
    [activities, focusedActivityId]
  )

  useEffect(() => {
    setFilters((prev) => {
      if (
        prev.repository === repositoryParam &&
        prev.status === statusParam &&
        prev.failure_type === failureTypeParam
      ) {
        return prev
      }

      return {
        ...prev,
        repository: repositoryParam,
        status: statusParam,
        failure_type: failureTypeParam,
      }
    })
  }, [failureTypeParam, repositoryParam, statusParam])

  useEffect(() => {
    setRepositoryDraft(repositoryParam)
  }, [repositoryParam])

  useEffect(() => {
    if (repositoryDraft === filters.repository) {
      return
    }

    const timer = window.setTimeout(() => {
      setFilters((prev) => ({ ...prev, repository: repositoryDraft }))
      const nextParams = new URLSearchParams(searchParams)
      if (repositoryDraft) {
        nextParams.set('repository', repositoryDraft)
      } else {
        nextParams.delete('repository')
      }
      setSearchParams(nextParams, { replace: true })
    }, 300)

    return () => window.clearTimeout(timer)
  }, [filters.repository, repositoryDraft, searchParams, setSearchParams])

  useEffect(() => {
    if (!focusedActivityId || !activities || !hasFocusedActivity) return

    setHighlightedActivityId(focusedActivityId)
    const timer = window.setTimeout(() => setHighlightedActivityId(null), 3000)

    const target = document.querySelector<HTMLElement>(`[data-activity-id=\"${focusedActivityId}\"]`)
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }

    return () => window.clearTimeout(timer)
  }, [focusedActivityId, activities, hasFocusedActivity])

  const handleRefresh = async () => {
    try {
      await refetch({ cancelRefetch: false })
      toast.success('Activities refreshed')
    } catch (err) {
      toast.error('Refresh failed', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  }

  const updateFilter = (key: 'status' | 'failure_type', value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }))

    const nextParams = new URLSearchParams(searchParams)
    if (value) {
      nextParams.set(key, value)
    } else {
      nextParams.delete(key)
    }
    setSearchParams(nextParams, { replace: true })
  }

  const activeFilterCount = [
    filters.repository,
    filters.status,
    filters.failure_type,
  ].filter(Boolean).length

  const clearAllFilters = () => {
    setRepositoryDraft('')
    setFilters((prev) => ({ ...prev, status: '', failure_type: '' }))
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('status')
    nextParams.delete('failure_type')
    nextParams.delete('repository')
    setSearchParams(nextParams, { replace: true })
  }

  const statusLabel = statusOptions.find((o) => o.value === filters.status)?.label
  const failureTypeLabel = failureTypeOptions.find(
    (o) => o.value === filters.failure_type,
  )?.label

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3.5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]">
            <Activity className="h-5 w-5 text-[var(--ph-accent)]" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-[var(--ph-text)]">
              Activities
            </h1>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              Every CI/CD healing activity PipelineHealer has processed.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {focusedActivityId && (
            <>
              <Badge variant="secondary">Focused View</Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const nextParams = new URLSearchParams(searchParams)
                  nextParams.delete('focus')
                  setSearchParams(nextParams)
                }}
              >
                Clear focus
              </Button>
            </>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleRefresh()}
            disabled={isLoading}
            aria-busy={isFetching}
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            {isFetching ? 'Refreshing...' : 'Refresh'}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Panel>
        <PanelHeader
          title="Filters"
          icon={<Filter className="h-4 w-4" />}
          actions={
            activeFilterCount > 0 ? (
              <Button variant="ghost" size="sm" onClick={clearAllFilters}>
                Clear all
              </Button>
            ) : undefined
          }
        />
        <PanelBody className="space-y-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-4">
            <Input
              value={repositoryDraft}
              onChange={(event) => setRepositoryDraft(event.target.value)}
              className="lg:w-[22rem]"
              placeholder="Filter by repository (owner/repo)"
              aria-label="Filter by repository"
            />
            <Select
              value={filters.status || '__all__'}
              onValueChange={(value) => updateFilter('status', value === '__all__' ? '' : value)}
            >
              <SelectTrigger className="lg:w-52" aria-label="Filter by status">
                <SelectValue placeholder="All Statuses" />
              </SelectTrigger>
              <SelectContent>
                {statusOptions.map((option) => (
                  <SelectItem key={option.value || '__all__'} value={option.value || '__all__'}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={filters.failure_type || '__all__'}
              onValueChange={(value) =>
                updateFilter('failure_type', value === '__all__' ? '' : value)
              }
            >
              <SelectTrigger className="lg:w-52" aria-label="Filter by failure type">
                <SelectValue placeholder="All Types" />
              </SelectTrigger>
              <SelectContent>
                {failureTypeOptions.map((option) => (
                  <SelectItem key={option.value || '__all__'} value={option.value || '__all__'}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {activeFilterCount > 0 && (
            <div className="flex flex-wrap items-center gap-2 border-t border-[var(--ph-border)] pt-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--ph-muted)]">
                Active
              </span>
              {filters.repository && (
                <FilterChip
                  label={`Repo: ${filters.repository}`}
                  onClear={() => setRepositoryDraft('')}
                />
              )}
              {filters.status && (
                <FilterChip
                  label={`Status: ${statusLabel ?? filters.status}`}
                  onClear={() => updateFilter('status', '')}
                />
              )}
              {filters.failure_type && (
                <FilterChip
                  label={`Type: ${failureTypeLabel ?? filters.failure_type}`}
                  onClear={() => updateFilter('failure_type', '')}
                />
              )}
            </div>
          )}
        </PanelBody>
      </Panel>

      {/* Activities Table */}
      {!hasFocusedActivity && focusedActivityId && (
        <Card>
          <CardContent className="p-4 text-sm text-[var(--ph-warning)]">
            Focused activity not in the current page. Refresh or adjust filters.
          </CardContent>
        </Card>
      )}

      <ActivityTable
        activities={activities || []}
        isLoading={isLoading}
        focusedActivityId={focusedActivityId}
        highlightedActivityId={highlightedActivityId}
      />

      {/* Result count */}
      {activities && activities.length > 0 && (
        <div className="text-center text-sm text-[var(--ph-muted)]">
          {activities.length >= filters.limit
            ? `Showing the ${filters.limit} most recent matches. Refine the filters above to narrow results.`
            : `Showing ${activities.length} ${activities.length === 1 ? "activity" : "activities"}.`}
        </div>
      )}
    </div>
  )
}

function FilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] py-1 pl-2.5 pr-1 text-xs font-medium text-[var(--ph-text)]">
      {label}
      <button
        type="button"
        onClick={onClear}
        aria-label={`Clear ${label}`}
        className="flex h-4 w-4 items-center justify-center rounded-full text-[var(--ph-muted)] transition-colors hover:bg-[var(--ph-border)] hover:text-[var(--ph-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ph-accent)]"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}
