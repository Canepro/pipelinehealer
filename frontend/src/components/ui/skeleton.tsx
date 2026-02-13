import type { HTMLAttributes } from 'react'
import { cn } from '@/utils/cn'

function Skeleton({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-slate-200/70 dark:bg-slate-700/60', className)}
      {...props}
    />
  )
}

export { Skeleton }
