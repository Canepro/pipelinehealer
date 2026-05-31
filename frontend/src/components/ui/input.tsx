import * as React from 'react'

import { cn } from '@/utils/cn'

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          'flex h-10 w-full rounded-lg border border-[var(--ph-border-strong)] bg-[var(--ph-bg-elevated)] px-3 py-2 text-sm text-[var(--ph-text)] ring-offset-[var(--ph-surface)] file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-[var(--ph-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ph-accent)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = 'Input'

export { Input }
