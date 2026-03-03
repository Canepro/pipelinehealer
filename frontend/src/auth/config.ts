import { readFrontendConfig } from '@/runtimeConfig'

export type AuthMode = 'none' | 'entra'

const rawMode = readFrontendConfig('VITE_AUTH_MODE', 'none').toLowerCase()

export const AUTH_MODE: AuthMode = rawMode === 'entra' ? 'entra' : 'none'
export const AUTH_ENABLED = AUTH_MODE === 'entra'

export const ENTRA_TENANT_ID = readFrontendConfig('VITE_ENTRA_TENANT_ID')
export const ENTRA_CLIENT_ID = readFrontendConfig('VITE_ENTRA_CLIENT_ID')
export const ENTRA_AUTHORITY = readFrontendConfig('VITE_ENTRA_AUTHORITY')
export const ENTRA_API_SCOPE = readFrontendConfig('VITE_ENTRA_API_SCOPE')
export const ENTRA_REDIRECT_URI = readFrontendConfig('VITE_ENTRA_REDIRECT_URI')
export const ENTRA_POST_LOGOUT_REDIRECT_URI = readFrontendConfig(
  'VITE_ENTRA_POST_LOGOUT_REDIRECT_URI'
)

export const resolvedAuthority =
  ENTRA_AUTHORITY || (ENTRA_TENANT_ID ? `https://login.microsoftonline.com/${ENTRA_TENANT_ID}` : '')

export const resolvedRedirectUri =
  ENTRA_REDIRECT_URI || (typeof window !== 'undefined' ? `${window.location.origin}/app` : '/app')

export const resolvedPostLogoutRedirectUri =
  ENTRA_POST_LOGOUT_REDIRECT_URI || (typeof window !== 'undefined' ? `${window.location.origin}/` : '/')

export const authConfigErrors: string[] = AUTH_ENABLED
  ? [
      !resolvedAuthority ? 'Missing VITE_ENTRA_TENANT_ID or VITE_ENTRA_AUTHORITY' : '',
      !ENTRA_CLIENT_ID ? 'Missing VITE_ENTRA_CLIENT_ID' : '',
      !ENTRA_API_SCOPE ? 'Missing VITE_ENTRA_API_SCOPE (API access token scope)' : '',
    ].filter(Boolean)
  : []

export const loginScopes = ENTRA_API_SCOPE ? [ENTRA_API_SCOPE] : ['openid', 'profile']
