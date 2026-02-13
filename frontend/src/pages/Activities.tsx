import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Filter, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import ActivityTable from '../components/ActivityTable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

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
  const [filters, setFilters] = useState({
    status: '',
    failure_type: '',
    limit: 50,
  })
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Activities
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            All CI/CD healing activities
          </p>
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
            onClick={() => void handleRefresh()}
            disabled={isLoading}
            aria-busy={isFetching}
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`}
            />
            {isFetching ? 'Refreshing...' : 'Refresh'}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4 md:p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-4">
            <Filter className="h-5 w-5 text-gray-400" />
            <select
              value={filters.status}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, status: e.target.value }))
              }
              className="h-10 w-full rounded-lg border border-[var(--ph-border)] bg-gray-100 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-azure-500 dark:bg-gray-700 dark:text-gray-100 lg:w-52"
            >
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              value={filters.failure_type}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, failure_type: e.target.value }))
              }
              className="h-10 w-full rounded-lg border border-[var(--ph-border)] bg-gray-100 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-azure-500 dark:bg-gray-700 dark:text-gray-100 lg:w-52"
            >
              {failureTypeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Activities Table */}
      {!hasFocusedActivity && focusedActivityId && (
        <Card>
          <CardContent className="p-4 text-sm text-amber-300">
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

      {/* Pagination info */}
      {activities && activities.length > 0 && (
        <div className="text-sm text-gray-500 dark:text-gray-400 text-center">
          Showing {activities.length} activities
        </div>
      )}
    </div>
  )
}
