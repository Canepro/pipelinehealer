import { useCallback, useState } from "react";
import {
  ConfirmDialog,
  type ConfirmOptions,
} from "@/components/ui/confirm-dialog";

interface ConfirmState {
  open: boolean;
  options: ConfirmOptions | null;
  resolve: ((result: boolean) => void) | null;
}

// Promise-based confirm. Usage:
//   const { confirm, dialog } = useConfirm();
//   render {dialog};  then:  if (await confirm({ ... })) { ... }
// Replaces native window.confirm() with an on-brand, accessible dialog.
export function useConfirm() {
  const [state, setState] = useState<ConfirmState>({
    open: false,
    options: null,
    resolve: null,
  });

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setState({ open: true, options, resolve });
    });
  }, []);

  const handleResolve = useCallback((result: boolean) => {
    setState((current) => {
      current.resolve?.(result);
      return { open: false, options: current.options, resolve: null };
    });
  }, []);

  const dialog = (
    <ConfirmDialog
      open={state.open}
      options={state.options}
      onResolve={handleResolve}
    />
  );

  return { confirm, dialog };
}
