import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Filter, RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import ActivityTable from '../components/ActivityTable'

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
  const [filters, setFilters] = useState({
    status: '',
    failure_type: '',
    limit: 50,
  })

  const { data: activities, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['activities', filters],
    queryFn: () => api.getActivities(filters),
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Activities
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            All CI/CD healing activities
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="btn-secondary flex items-center"
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`}
          />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="card p-4">
        <div className="flex items-center space-x-4">
          <Filter className="h-5 w-5 text-gray-400" />
          <select
            value={filters.status}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, status: e.target.value }))
            }
            className="bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-azure-500"
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
            className="bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-azure-500"
          >
            {failureTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Activities Table */}
      <ActivityTable activities={activities || []} isLoading={isLoading} />

      {/* Pagination info */}
      {activities && activities.length > 0 && (
        <div className="text-sm text-gray-500 dark:text-gray-400 text-center">
          Showing {activities.length} activities
        </div>
      )}
    </div>
  )
}
