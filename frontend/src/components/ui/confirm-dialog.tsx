import type { ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ConfirmOptions {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
}

// Presentational confirm dialog. Drive it with useConfirm() for promise-based flows.
export function ConfirmDialog({
  open,
  options,
  onResolve,
}: {
  open: boolean;
  options: ConfirmOptions | null;
  onResolve: (result: boolean) => void;
}) {
  if (!options) return null;
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onResolve(false);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-surface)] p-5 shadow-[var(--ph-shadow-lg)] focus:outline-none">
          <div className="flex items-start gap-3">
            {options.destructive ? (
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--ph-danger-border)] bg-[var(--ph-danger-bg)] text-[var(--ph-danger)]">
                <TriangleAlert className="h-5 w-5" />
              </span>
            ) : null}
            <div className="min-w-0">
              <Dialog.Title className="text-base font-semibold text-[var(--ph-text)]">
                {options.title}
              </Dialog.Title>
              {options.description ? (
                <Dialog.Description className="mt-1.5 text-sm leading-relaxed text-[var(--ph-muted)]">
                  {options.description}
                </Dialog.Description>
              ) : null}
            </div>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => onResolve(false)}>
              {options.cancelLabel ?? "Cancel"}
            </Button>
            <Button
              variant={options.destructive ? "destructive" : "default"}
              size="sm"
              onClick={() => onResolve(true)}
            >
              {options.confirmLabel ?? "Confirm"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
