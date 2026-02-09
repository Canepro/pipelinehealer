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
    className: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    icon: Package,
  },
  test: {
    label: 'Test',
    className: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    icon: TestTube,
  },
  lint: {
    label: 'Lint',
    className: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
    icon: FileCode,
  },
  build_config: {
    label: 'Config',
    className: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
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
