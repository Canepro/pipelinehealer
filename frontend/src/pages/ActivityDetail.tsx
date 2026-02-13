import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow, format } from 'date-fns'
import {
  ArrowLeft,
  ExternalLink,
  GitBranch,
  RefreshCw,
  FileCode,
  AlertTriangle,
} from 'lucide-react'
import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import FailureTypeBadge from '../components/FailureTypeBadge'

function getIssueProposalMeta(details: Record<string, unknown> | undefined): {
  includesProposedFix: boolean
  reasonCode: string | null
  reasonDetail: string | null
} {
  const includes = details?.includes_proposed_fix === true
  const reason =
    typeof details?.not_auto_reason_code === 'string'
      ? details.not_auto_reason_code
      : null
  const reasonDetail =
    typeof details?.not_auto_reason_detail === 'string'
      ? details.not_auto_reason_detail
      : null
  return { includesProposedFix: includes, reasonCode: reason, reasonDetail }
}

export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

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
        <Link to="/activities" className="btn-primary mt-4 inline-block">
          Back to Activities
        </Link>
      </div>
    )
  }
  const remediationMeta = getIssueProposalMeta(activity.remediation_result?.details)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/activities"
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

      {/* Diagnosis Card */}
      {activity.diagnosis && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Diagnosis
          </h2>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Root Cause
              </p>
              <p className="mt-1 text-gray-900 dark:text-white">
                {activity.diagnosis.root_cause}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
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
            </div>
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
                <p className="mt-1 text-gray-900 dark:text-white capitalize">
                  {activity.remediation_result.action_taken.replace('_', ' ')}
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
            {remediationMeta.includesProposedFix && (
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Issue Metadata
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="inline-flex items-center rounded-md bg-sky-100 px-2 py-1 text-xs font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-200">
                    Includes Proposed Fix
                  </span>
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
