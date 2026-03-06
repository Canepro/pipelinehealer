import { useEffect, useState, type ReactNode } from 'react'
import { InteractionRequiredAuthError } from '@azure/msal-browser'
import { MsalProvider, useMsal } from '@azure/msal-react'
import { configureApiAuthTokenProvider } from '../api/client'
import { ApiAuthReadyContext } from './apiAuthReady'
import {
  AUTH_ENABLED,
  loginScopes,
} from './config'
import { appMsalInstance } from './msalInstance'

function MsalTokenBridge({ children }: { children: ReactNode }) {
  const { instance, accounts } = useMsal()
  const [isApiAuthReady, setIsApiAuthReady] = useState(false)

  useEffect(() => {
    if (!instance.getActiveAccount() && accounts.length > 0) {
      instance.setActiveAccount(accounts[0])
    }
  }, [instance, accounts])

  useEffect(() => {
    configureApiAuthTokenProvider(async () => {
      const account = instance.getActiveAccount() || accounts[0]
      if (!account || loginScopes.length === 0) {
        return null
      }
      try {
        const response = await instance.acquireTokenSilent({
          account,
          scopes: loginScopes,
        })
        return response.accessToken || null
      } catch (error) {
        if (error instanceof InteractionRequiredAuthError) {
          return null
        }
        return null
      }
    })
    setIsApiAuthReady(true)

    return () => {
      setIsApiAuthReady(false)
      configureApiAuthTokenProvider(null)
    }
  }, [instance, accounts])

  return (
    <ApiAuthReadyContext.Provider value={isApiAuthReady}>
      {children}
    </ApiAuthReadyContext.Provider>
  )
}

export function AppAuthProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (!AUTH_ENABLED) {
      configureApiAuthTokenProvider(null)
    }
  }, [])

  if (!AUTH_ENABLED || appMsalInstance === null) {
    return (
      <ApiAuthReadyContext.Provider value={true}>
        {children}
      </ApiAuthReadyContext.Provider>
    )
  }

  return (
    <MsalProvider instance={appMsalInstance}>
      <MsalTokenBridge>{children}</MsalTokenBridge>
    </MsalProvider>
  )
}
