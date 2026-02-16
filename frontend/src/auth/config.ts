export type AuthMode = 'none' | 'entra'

const rawMode = String(import.meta.env.VITE_AUTH_MODE || 'none')
  .trim()
  .toLowerCase()

export const AUTH_MODE: AuthMode = rawMode === 'entra' ? 'entra' : 'none'
export const AUTH_ENABLED = AUTH_MODE === 'entra'

export const ENTRA_TENANT_ID = String(import.meta.env.VITE_ENTRA_TENANT_ID || '').trim()
export const ENTRA_CLIENT_ID = String(import.meta.env.VITE_ENTRA_CLIENT_ID || '').trim()
export const ENTRA_AUTHORITY = String(import.meta.env.VITE_ENTRA_AUTHORITY || '').trim()
export const ENTRA_API_SCOPE = String(import.meta.env.VITE_ENTRA_API_SCOPE || '').trim()
export const ENTRA_REDIRECT_URI = String(import.meta.env.VITE_ENTRA_REDIRECT_URI || '').trim()
export const ENTRA_POST_LOGOUT_REDIRECT_URI = String(
  import.meta.env.VITE_ENTRA_POST_LOGOUT_REDIRECT_URI || ''
).trim()

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
