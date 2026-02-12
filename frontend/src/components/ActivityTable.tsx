import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { ExternalLink, GitBranch } from 'lucide-react'
import type { Activity } from '../api/client'
import StatusBadge from './StatusBadge'
import FailureTypeBadge from './FailureTypeBadge'

interface ActivityTableProps {
  activities: Activity[]
  isLoading?: boolean
}

export default function ActivityTable({ activities, isLoading }: ActivityTableProps) {
  if (isLoading) {
    return (
      <div className="card">
        <div className="p-8 text-center">
          <div className="animate-spin h-8 w-8 border-4 border-azure-500 border-t-transparent rounded-full mx-auto"></div>
          <p className="mt-4 text-gray-500">Loading activities...</p>
        </div>
      </div>
    )
  }

  if (activities.length === 0) {
    return (
      <div className="card">
        <div className="p-8 text-center">
          <GitBranch className="h-12 w-12 text-gray-400 mx-auto" />
          <p className="mt-4 text-gray-500">No activities found</p>
          <p className="text-sm text-gray-400">
            Activities will appear here when workflow failures are processed
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-slate-100/70 dark:bg-slate-800/60">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Repository
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Workflow
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Failure Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Time
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-transparent divide-y divide-gray-200 dark:divide-gray-700">
            {activities.map((activity) => (
              <tr key={activity.id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center">
                    <GitBranch className="h-5 w-5 text-gray-400 mr-2" />
                    <div>
                      <div className="text-sm font-medium text-gray-900 dark:text-white">
                        {activity.repository_name.split('/')[1]}
                      </div>
                      <div className="text-xs text-gray-500">
                        {activity.repository_name.split('/')[0]}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900 dark:text-white">
                    {activity.workflow_name}
                  </div>
                  <div className="text-xs text-gray-500">
                    Run #{activity.workflow_run_id}
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <StatusBadge status={activity.status} size="sm" />
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  {activity.failure_type ? (
                    <FailureTypeBadge type={activity.failure_type} />
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {formatDistanceToNow(new Date(activity.created_at), { addSuffix: true })}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <div className="flex items-center space-x-2">
                    <Link
                      to={`/activities/${activity.id}`}
                      className="text-sky-600 hover:text-sky-700 dark:text-sky-400"
                    >
                      View
                    </Link>
                    {activity.remediation_result?.pr_url && (
                      <a
                        href={activity.remediation_result.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-400 hover:text-gray-500"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
