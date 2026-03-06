import { AUTH_ENABLED } from "./config";
import { appMsalInstance } from "./msalInstance";

export function detectCachedAdminSession(): boolean {
  if (!AUTH_ENABLED || appMsalInstance === null) {
    return false;
  }

  return Boolean(
    appMsalInstance.getActiveAccount() || appMsalInstance.getAllAccounts()[0],
  );
}
