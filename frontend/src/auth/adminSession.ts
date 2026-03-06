import { AUTH_ENABLED } from "./config";
import { appMsalInstance } from "./msalInstance";

export function detectCachedAdminSession(): boolean {
  if (!AUTH_ENABLED || appMsalInstance === null) {
    return false;
  }

  if (appMsalInstance.getActiveAccount()) {
    return true;
  }

  const accounts = appMsalInstance.getAllAccounts();
  if (accounts.length === 0) {
    return false;
  }

  // Keep admin pages aligned with the already-signed-in browser session.
  appMsalInstance.setActiveAccount(accounts[0]);
  return true;
}
