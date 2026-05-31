import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/utils/cn";

// The console's standard surface: a panel with an optional header row
// (title + description on the left, status/actions on the right) and a body.
export function Panel({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-surface)] shadow-[var(--ph-shadow-md)]",
        className,
      )}
      {...props}
    />
  );
}

export function PanelHeader({
  title,
  description,
  icon,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-3 border-b border-[var(--ph-border-subtle)] px-5 py-3.5",
        className,
      )}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        {icon ? (
          <span className="mt-0.5 text-[var(--ph-accent)]">{icon}</span>
        ) : null}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold tracking-tight text-[var(--ph-text)]">
            {title}
          </h3>
          {description ? (
            <p className="mt-0.5 text-xs leading-5 text-[var(--ph-muted)]">
              {description}
            </p>
          ) : null}
        </div>
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

export function PanelBody({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...props} />;
}
