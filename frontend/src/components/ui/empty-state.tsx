import type { ReactNode } from "react";
import { cn } from "@/utils/cn";

// Consistent empty/zero-data state for panels and tables.
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-10 text-center",
        className,
      )}
    >
      {icon ? (
        <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-[var(--ph-muted)]">
          {icon}
        </span>
      ) : null}
      <div>
        <p className="text-sm font-medium text-[var(--ph-text)]">{title}</p>
        {description ? (
          <p className="mt-1 max-w-sm text-sm text-[var(--ph-muted)]">
            {description}
          </p>
        ) : null}
      </div>
      {action}
    </div>
  );
}
