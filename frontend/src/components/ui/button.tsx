import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/utils/cn'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ph-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--ph-surface)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-[var(--ph-accent)] text-white hover:bg-[var(--ph-accent-hover)] active:bg-[var(--ph-accent-hover)]',
        secondary:
          'border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-[var(--ph-text)] hover:bg-[var(--ph-surface)] disabled:hover:bg-[var(--ph-bg-elevated)]',
        destructive: 'bg-[var(--ph-danger-solid)] text-white hover:bg-[var(--ph-danger-solid-hover)]',
        ghost:
          'text-[var(--ph-text)] hover:bg-[var(--ph-bg-elevated)] disabled:hover:bg-transparent',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-6',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    )
  }
)
Button.displayName = 'Button'

export { Button }
