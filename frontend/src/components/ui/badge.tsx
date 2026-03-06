import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/utils/cn'

const badgeVariants = cva(
  'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-[var(--ph-accent)] text-white',
        secondary:
          'border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]',
        success: 'border-[var(--ph-success-border)] bg-[var(--ph-success-bg)] text-[var(--ph-success)]',
        destructive: 'border-[var(--ph-danger-border)] bg-[var(--ph-danger-bg)] text-[var(--ph-danger)]',
        outline: 'border-[var(--ph-border)] text-[var(--ph-muted)]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge }
