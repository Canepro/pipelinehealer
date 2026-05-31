import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/utils/cn";

// Shared status language for the operator console: one tone scale, one dot,
// one pill, one stat tile. Used by Dashboard, Control Center, and Settings.
export type Tone = "ok" | "warn" | "bad" | "info" | "neutral";

const DOT: Record<Tone, string> = {
  ok: "bg-[var(--ph-success)]",
  warn: "bg-[var(--ph-warning)]",
  bad: "bg-[var(--ph-danger)]",
  info: "bg-[var(--ph-info)]",
  neutral: "bg-[var(--ph-muted)]",
};

const TEXT: Record<Tone, string> = {
  ok: "text-[var(--ph-success)]",
  warn: "text-[var(--ph-warning)]",
  bad: "text-[var(--ph-danger)]",
  info: "text-[var(--ph-text)]",
  neutral: "text-[var(--ph-muted)]",
};

const PILL: Record<Tone, string> = {
  ok: "border-[var(--ph-success-border)] bg-[var(--ph-success-bg)] text-[var(--ph-success)]",
  warn: "border-[var(--ph-warning-border)] bg-[var(--ph-warning-bg)] text-[var(--ph-warning)]",
  bad: "border-[var(--ph-danger-border)] bg-[var(--ph-danger-bg)] text-[var(--ph-danger)]",
  info: "border-[var(--ph-info-border)] bg-[var(--ph-info-bg)] text-[var(--ph-info)]",
  neutral: "border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] text-[var(--ph-muted)]",
};

export function StatusDot({
  tone,
  className,
}: {
  tone: Tone;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn("h-2 w-2 shrink-0 rounded-full", DOT[tone], className)}
    />
  );
}

export function StatusPill({
  tone,
  children,
  className,
}: {
  tone: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        PILL[tone],
        className,
      )}
    >
      <StatusDot tone={tone} className="h-1.5 w-1.5" />
      {children}
    </span>
  );
}

export function StatTile({
  label,
  value,
  tone = "neutral",
  detail,
  className,
  ...rest
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  detail?: ReactNode;
} & Omit<HTMLAttributes<HTMLDivElement>, "title">) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-xl border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/40 px-3.5 py-3",
        className,
      )}
      {...rest}
    >
      <div className="flex items-center gap-2">
        <StatusDot tone={tone} />
        <span className="truncate text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--ph-muted)]">
          {label}
        </span>
      </div>
      <span className={cn("text-sm font-semibold", TEXT[tone])}>{value}</span>
      {detail ? (
        <span className="text-xs leading-4 text-[var(--ph-muted)]">{detail}</span>
      ) : null}
    </div>
  );
}
