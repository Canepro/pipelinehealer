import { createContext, useContext } from "react";

export const ApiAuthReadyContext = createContext(false);

export function useApiAuthReady(): boolean {
  return useContext(ApiAuthReadyContext);
}
