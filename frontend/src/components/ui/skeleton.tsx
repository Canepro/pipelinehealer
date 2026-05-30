import type { HTMLAttributes } from 'react'
import { cn } from '@/utils/cn'

function Skeleton({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-[var(--ph-border)]', className)}
      {...props}
    />
  )
}

export { Skeleton }
