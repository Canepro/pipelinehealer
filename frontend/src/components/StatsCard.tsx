import clsx from 'clsx'
import { LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

interface StatsCardProps {
  title: string
  value: string | number
  icon: LucideIcon
  trend?: {
    value: number
    isPositive: boolean
  }
  color?: 'blue' | 'green' | 'red' | 'yellow'
}

const colorClasses = {
  blue: 'bg-sky-500/15 text-sky-600 dark:text-sky-300 border border-sky-500/30',
  green: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border border-emerald-500/30',
  red: 'bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-500/30',
  yellow: 'bg-amber-500/15 text-amber-600 dark:text-amber-300 border border-amber-500/30',
}

export default function StatsCard({
  title,
  value,
  icon: Icon,
  trend,
  color = 'blue',
}: StatsCardProps) {
  return (
    <Card>
      <CardContent className="p-4 md:p-5">
        <div className="flex items-center gap-3">
          <div className={clsx('rounded-lg border p-2.5', colorClasses[color])}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {title}
            </p>
            <div className="mt-1 flex items-baseline gap-2">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {value}
              </p>
              {trend && (
                <Badge className="ml-0" variant={trend.isPositive ? 'success' : 'destructive'}>
                  {trend.isPositive ? '+' : '-'}
                  {Math.abs(trend.value)}%
                </Badge>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
