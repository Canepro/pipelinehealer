import {
  BrowserCacheLocation,
  EventType,
  PublicClientApplication,
  type AuthenticationResult,
} from '@azure/msal-browser'
import {
  AUTH_ENABLED,
  ENTRA_CLIENT_ID,
  authConfigErrors,
  resolvedAuthority,
  resolvedPostLogoutRedirectUri,
  resolvedRedirectUri,
} from './config'

function createMsalInstance(): PublicClientApplication | null {
  if (!AUTH_ENABLED || authConfigErrors.length > 0) {
    return null
  }

  const instance = new PublicClientApplication({
    auth: {
      clientId: ENTRA_CLIENT_ID,
      authority: resolvedAuthority,
      redirectUri: resolvedRedirectUri,
      postLogoutRedirectUri: resolvedPostLogoutRedirectUri,
    },
    cache: {
      cacheLocation: BrowserCacheLocation.SessionStorage,
    },
  })

  instance.addEventCallback((event) => {
    if (
      event.eventType === EventType.LOGIN_SUCCESS ||
      event.eventType === EventType.ACQUIRE_TOKEN_SUCCESS
    ) {
      const payload = event.payload as AuthenticationResult | null
      if (payload?.account) {
        instance.setActiveAccount(payload.account)
      }
    }
  })

  return instance
}

export const appMsalInstance = createMsalInstance()
