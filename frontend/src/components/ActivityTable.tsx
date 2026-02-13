import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { ExternalLink, GitBranch } from 'lucide-react'
import type { Activity } from '../api/client'
import StatusBadge from './StatusBadge'
import FailureTypeBadge from './FailureTypeBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface ActivityTableProps {
  activities: Activity[]
  isLoading?: boolean
}

function getIssueProposalMeta(activity: Activity): {
  includesProposedFix: boolean
  reasonCode: string | null
  output: string | null
} {
  const details = activity.remediation_result?.details
  const includes = details?.includes_proposed_fix === true
  const reason =
    typeof details?.not_auto_reason_code === 'string'
      ? details.not_auto_reason_code
      : null
  const output =
    typeof activity.remediation_result?.action_taken === 'string'
      ? activity.remediation_result.action_taken.replace('_', ' ').toUpperCase()
      : null
  return { includesProposedFix: includes, reasonCode: reason, output }
}

export default function ActivityTable({ activities, isLoading }: ActivityTableProps) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="space-y-4">
            <Skeleton className="h-5 w-40" />
            {Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="grid grid-cols-6 gap-4">
                <Skeleton className="h-10 col-span-2" />
                <Skeleton className="h-10 col-span-1" />
                <Skeleton className="h-10 col-span-1" />
                <Skeleton className="h-10 col-span-1" />
                <Skeleton className="h-10 col-span-1" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (activities.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <GitBranch className="h-12 w-12 text-gray-400 mx-auto" />
          <p className="mt-4 text-gray-500">No activities found</p>
          <p className="text-sm text-gray-400">
            Activities will appear here when workflow failures are processed
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader className="bg-slate-100/70 dark:bg-slate-800/60">
          <TableRow>
            <TableHead className="pl-6">Repository</TableHead>
            <TableHead>Workflow</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Failure Type</TableHead>
            <TableHead>Time</TableHead>
            <TableHead className="pr-6">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
            {activities.map((activity) => {
              const meta = getIssueProposalMeta(activity)
              return (
              <TableRow key={activity.id}>
                <TableCell className="pl-6 whitespace-nowrap">
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
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <div className="text-sm text-gray-900 dark:text-white">
                    {activity.workflow_name}
                  </div>
                  <div className="text-xs text-gray-500">
                    Run #{activity.workflow_run_id}
                  </div>
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <StatusBadge status={activity.status} size="sm" />
                  <div className="mt-2 flex flex-wrap gap-1">
                    {meta.output && (
                      <Badge className="rounded-md text-[11px]" variant="secondary">
                        Output: {meta.output}
                      </Badge>
                    )}
                  </div>
                  {meta.includesProposedFix && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      <Badge className="rounded-md text-[11px]" variant="outline">
                        Includes Proposed Fix
                      </Badge>
                      {meta.reasonCode && (
                        <Badge className="rounded-md text-[11px]" variant="secondary">
                          {meta.reasonCode}
                        </Badge>
                      )}
                    </div>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  {activity.failure_type ? (
                    <FailureTypeBadge type={activity.failure_type} />
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm text-gray-500">
                  {formatDistanceToNow(new Date(activity.created_at), { addSuffix: true })}
                </TableCell>
                <TableCell className="pr-6 whitespace-nowrap text-sm">
                  <div className="flex items-center space-x-2">
                    <Button asChild variant="ghost" size="sm">
                      <Link to={`/activities/${activity.id}`}>View</Link>
                    </Button>
                    {activity.remediation_result?.pr_url && (
                      <Button asChild variant="ghost" size="icon">
                        <a
                          href={activity.remediation_result.pr_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </Button>
                      )}
                  </div>
                </TableCell>
              </TableRow>
            )})}
        </TableBody>
      </Table>
    </Card>
  )
}
