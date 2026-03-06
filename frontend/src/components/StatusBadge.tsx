import clsx from 'clsx'
import { CheckCircle, XCircle, Clock, Loader, AlertTriangle } from 'lucide-react'

interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

const statusConfig: Record<string, {
  label: string
  className: string
  icon: typeof CheckCircle
}> = {
  completed: {
    label: 'Completed',
    className: 'status-completed',
    icon: CheckCircle,
  },
  failed: {
    label: 'Failed',
    className: 'status-failed',
    icon: XCircle,
  },
  pending: {
    label: 'Pending',
    className: 'status-pending',
    icon: Clock,
  },
  analyzing: {
    label: 'Analyzing',
    className: 'status-analyzing',
    icon: Loader,
  },
  diagnosing: {
    label: 'Diagnosing',
    className: 'status-analyzing',
    icon: Loader,
  },
  remediating: {
    label: 'Remediating',
    className: 'status-analyzing',
    icon: Loader,
  },
  skipped: {
    label: 'Skipped',
    className: 'bg-[var(--ph-bg-elevated)] text-[var(--ph-muted)] border border-[var(--ph-border)]',
    icon: AlertTriangle,
  },
}

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status] || {
    label: status,
    className: 'bg-[var(--ph-bg-elevated)] text-[var(--ph-muted)]',
    icon: Clock,
  }

  const Icon = config.icon

  return (
    <span
      className={clsx(
        'status-badge',
        config.className,
        size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1'
      )}
    >
      <Icon className={clsx(
        'mr-1',
        size === 'sm' ? 'h-3 w-3' : 'h-4 w-4',
        status === 'analyzing' || status === 'diagnosing' || status === 'remediating'
          ? 'animate-spin'
          : ''
      )} />
      {config.label}
    </span>
  )
}
