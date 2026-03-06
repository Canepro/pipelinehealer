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
    className: 'bg-[var(--ph-info-bg)] text-[var(--ph-info)] border border-[var(--ph-info-border)]',
    icon: Package,
  },
  test: {
    label: 'Test',
    className: 'bg-[var(--ph-warning-bg)] text-[var(--ph-warning)] border border-[var(--ph-warning-border)]',
    icon: TestTube,
  },
  lint: {
    label: 'Lint',
    className: 'bg-[var(--ph-success-bg)] text-[var(--ph-success)] border border-[var(--ph-success-border)]',
    icon: FileCode,
  },
  build_config: {
    label: 'Config',
    className: 'bg-[var(--ph-bg-elevated)] text-[var(--ph-text)] border border-[var(--ph-border)]',
    icon: Settings,
  },
  timeout: {
    label: 'Timeout',
    className: 'bg-[var(--ph-warning-bg)] text-[var(--ph-warning)] border border-[var(--ph-warning-border)]',
    icon: Clock,
  },
  unknown: {
    label: 'Unknown',
    className: 'bg-[var(--ph-bg-elevated)] text-[var(--ph-muted)] border border-[var(--ph-border)]',
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
