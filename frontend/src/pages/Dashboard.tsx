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
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

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
    <div className="space-y-8">
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
      {showStatsLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={`stats-skeleton-${index}`}>
              <CardContent className="p-4 md:p-5 space-y-3">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-8 w-20" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <StatsCard
            title="Total Processed"
            value={stats?.total_runs_processed || 0}
            icon={Activity}
            color="blue"
          />
          <StatsCard
            title="Actioned"
            value={stats?.actioned_remediations || 0}
            icon={CheckCircle}
            color="green"
          />
          <StatsCard
            title="Failed"
            value={stats?.failed_remediations || 0}
            icon={XCircle}
            color="red"
          />
          <StatsCard
            title="Action Rate"
            value={`${actionRate}%`}
            icon={TrendingUp}
            color="blue"
          />
        </div>
      )}

      {/* Outcome Breakdown */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <StatsCard
          title="Auto PR Rate"
          value={`${autoPrRate}% (${stats?.auto_pr_remediations || 0})`}
          icon={GitPullRequest}
          color="blue"
        />
        <StatsCard
          title="Issue Rate"
          value={`${issueRate}% (${stats?.issue_remediations || 0})`}
          icon={FileText}
          color="yellow"
        />
        <StatsCard
          title="Safety-Blocked"
          value={`${safetyBlockedRate}% (${stats?.safety_blocked_remediations || 0})`}
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
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Failure Types Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Failure Types (Last 30 Days)</CardTitle>
          </CardHeader>
          <CardContent>
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
              <div className="flex h-[250px] items-center justify-center text-sm text-gray-400">
                No failure data yet. Trigger a workflow run to populate this chart.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top Repositories Bar Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Top Repositories</CardTitle>
          </CardHeader>
          <CardContent>
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
              <div className="flex h-[250px] items-center justify-center text-sm text-gray-400">
                No repository data yet. Trigger a workflow run to populate this chart.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Activities */}
      <section className="space-y-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Recent Activities
          </h2>
          <Button asChild size="sm" variant="ghost">
            <a href="/activities">View all</a>
          </Button>
        </div>
        <ActivityTable
          activities={activities || []}
          isLoading={activitiesLoading}
        />
      </section>

      {/* Average Resolution Time */}
      {stats && stats.average_resolution_time_seconds > 0 && (
        <Card>
          <CardContent className="p-4 md:p-6">
            <div className="flex items-center gap-4">
              <Clock className="h-8 w-8 text-azure-500" />
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Average Resolution Time
                </p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {Math.round(stats.average_resolution_time_seconds)}s
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
