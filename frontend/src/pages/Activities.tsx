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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[var(--ph-text)]">
            Activities
          </h1>
          <p className="mt-1 text-sm text-[var(--ph-muted)]">
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
          {filters.repository && <Badge variant="outline">Repo: {filters.repository}</Badge>}
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
            <Filter className="h-5 w-5 text-[var(--ph-muted)]" />
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
            {filters.repository && (
              <Button variant="ghost" size="sm" onClick={() => setRepositoryDraft('')}>
                Clear repo
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

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

      {/* Pagination info */}
      {activities && activities.length > 0 && (
        <div className="text-sm text-[var(--ph-muted)] text-center">
          Showing {activities.length} activities
        </div>
      )}
    </div>
  )
}
