import clsx from 'clsx'
import { Package, TestTube, FileCode, Settings, Clock } from 'lucide-react'

interface FailureTypeBadgeProps {
  type: string
}

const typeConfig: Record<string, {
  label: string
  className: string
  icon: typeof Package
}> = {
  dependency: {
    label: 'Dependency',
    className: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200',
    icon: Package,
  },
  test: {
    label: 'Test',
    className: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
    icon: TestTube,
  },
  lint: {
    label: 'Lint',
    className: 'bg-teal-100 text-teal-800 dark:bg-teal-900/40 dark:text-teal-200',
    icon: FileCode,
  },
  build_config: {
    label: 'Config',
    className: 'bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-200',
    icon: Settings,
  },
  timeout: {
    label: 'Timeout',
    className: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
    icon: Clock,
  },
  unknown: {
    label: 'Unknown',
    className: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
    icon: Settings,
  },
}

export default function FailureTypeBadge({ type }: FailureTypeBadgeProps) {
  const config = typeConfig[type] || typeConfig.unknown
  const Icon = config.icon

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
        config.className
      )}
    >
      <Icon className="h-3 w-3 mr-1" />
      {config.label}
    </span>
  )
}
