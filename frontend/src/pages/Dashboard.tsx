import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import {
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  TrendingUp,
  GitPullRequest,
  FileText,
  ShieldAlert,
} from 'lucide-react'
import { api } from '../api/client'
import StatsCard from '../components/StatsCard'
import ActivityTable from '../components/ActivityTable'

const COLORS = ['#2563eb', '#0ea5e9', '#14b8a6', '#16a34a', '#f59e0b', '#64748b']

export default function Dashboard() {
  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    error: statsErrorValue,
  } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    retry: 1,
  })

  const { data: activities, isLoading: activitiesLoading } = useQuery({
    queryKey: ['activities', { limit: 5 }],
    queryFn: () => api.getActivities({ limit: 5 }),
  })

  const { data: failureBreakdown } = useQuery({
    queryKey: ['failureBreakdown'],
    queryFn: () => api.getFailureBreakdown(30),
  })

  // Transform failure breakdown for pie chart
  const pieData = failureBreakdown
    ? Object.entries(failureBreakdown).map(([name, value]) => ({
        name: name.replace('_', ' '),
        value,
      }))
    : []

  // Transform repository data for bar chart
  const repoData = stats?.by_repository
    ? Object.entries(stats.by_repository)
        .slice(0, 5)
        .map(([name, value]) => ({
          name: name.split('/')[1] || name,
          count: value,
        }))
    : []

  const actionRate = stats
    ? stats.total_runs_processed > 0
      ? Math.round(
          (stats.actioned_remediations / stats.total_runs_processed) * 100
        )
      : 0
    : 0
  const autoPrRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round((stats.auto_pr_remediations / stats.actioned_remediations) * 100)
      : 0
    : 0
  const issueRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round((stats.issue_remediations / stats.actioned_remediations) * 100)
      : 0
    : 0
  const safetyBlockedRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round((stats.safety_blocked_remediations / stats.actioned_remediations) * 100)
      : 0
    : 0

  const showStatsLoading = statsLoading && !statsError
  const statsErrorMessage =
    statsError && statsErrorValue instanceof Error
      ? statsErrorValue.message
      : 'Stats temporarily unavailable'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Overview of CI/CD healing activities
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Total Processed"
          value={showStatsLoading ? '...' : stats?.total_runs_processed || 0}
          icon={Activity}
          color="blue"
        />
        <StatsCard
          title="Actioned"
          value={showStatsLoading ? '...' : stats?.actioned_remediations || 0}
          icon={CheckCircle}
          color="green"
        />
        <StatsCard
          title="Failed"
          value={showStatsLoading ? '...' : stats?.failed_remediations || 0}
          icon={XCircle}
          color="red"
        />
        <StatsCard
          title="Action Rate"
          value={showStatsLoading ? '...' : `${actionRate}%`}
          icon={TrendingUp}
          color="blue"
        />
      </div>

      {/* Outcome Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatsCard
          title="Auto PR Rate"
          value={showStatsLoading ? '...' : `${autoPrRate}% (${stats?.auto_pr_remediations || 0})`}
          icon={GitPullRequest}
          color="blue"
        />
        <StatsCard
          title="Issue Rate"
          value={showStatsLoading ? '...' : `${issueRate}% (${stats?.issue_remediations || 0})`}
          icon={FileText}
          color="yellow"
        />
        <StatsCard
          title="Safety-Blocked"
          value={
            showStatsLoading
              ? '...'
              : `${safetyBlockedRate}% (${stats?.safety_blocked_remediations || 0})`
          }
          icon={ShieldAlert}
          color="red"
        />
      </div>

      {statsError && (
        <div className="rounded-lg border border-amber-300/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Dashboard stats endpoint is unavailable: {statsErrorMessage}
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Failure Types Pie Chart */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Failure Types (Last 30 Days)
          </h2>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  fill="#8884d8"
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) =>
                    `${name} (${(percent * 100).toFixed(0)}%)`
                  }
                >
                  {pieData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-400">
              No failure data available
            </div>
          )}
        </div>

        {/* Top Repositories Bar Chart */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Top Repositories
          </h2>
          {repoData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={repoData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#9ca3af', fontSize: 12 }}
                />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: 'none',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-400">
              No repository data available
            </div>
          )}
        </div>
      </div>

      {/* Recent Activities */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Recent Activities
          </h2>
          <a
            href="/activities"
            className="text-sm text-azure-600 hover:text-azure-700 dark:text-azure-400"
          >
            View all
          </a>
        </div>
        <ActivityTable
          activities={activities || []}
          isLoading={activitiesLoading}
        />
      </div>

      {/* Average Resolution Time */}
      {stats && stats.average_resolution_time_seconds > 0 && (
        <div className="card p-6">
          <div className="flex items-center">
            <Clock className="h-8 w-8 text-azure-500" />
            <div className="ml-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Average Resolution Time
              </p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {Math.round(stats.average_resolution_time_seconds)}s
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
