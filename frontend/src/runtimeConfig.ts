export type FrontendRuntimeConfigKey =
  | 'VITE_AUTH_MODE'
  | 'VITE_ENTRA_TENANT_ID'
  | 'VITE_ENTRA_CLIENT_ID'
  | 'VITE_ENTRA_AUTHORITY'
  | 'VITE_ENTRA_API_SCOPE'
  | 'VITE_ENTRA_REDIRECT_URI'
  | 'VITE_ENTRA_POST_LOGOUT_REDIRECT_URI'
  | 'VITE_API_URL'
  | 'VITE_API_AUTH_KEY'
  | 'VITE_API_TIMEOUT_MS'

type FrontendRuntimeConfig = Partial<Record<FrontendRuntimeConfigKey, string>>

declare global {
  interface Window {
    __PH_RUNTIME_CONFIG__?: FrontendRuntimeConfig
  }
}

function getRuntimeConfig(): FrontendRuntimeConfig {
  if (typeof window === 'undefined' || typeof window.__PH_RUNTIME_CONFIG__ !== 'object') {
    return {}
  }
  return window.__PH_RUNTIME_CONFIG__ || {}
}

// Keep explicit VITE_* references so Vite injects build-time fallbacks.
const BUILD_FRONTEND_CONFIG: FrontendRuntimeConfig = {
  VITE_AUTH_MODE: import.meta.env.VITE_AUTH_MODE,
  VITE_ENTRA_TENANT_ID: import.meta.env.VITE_ENTRA_TENANT_ID,
  VITE_ENTRA_CLIENT_ID: import.meta.env.VITE_ENTRA_CLIENT_ID,
  VITE_ENTRA_AUTHORITY: import.meta.env.VITE_ENTRA_AUTHORITY,
  VITE_ENTRA_API_SCOPE: import.meta.env.VITE_ENTRA_API_SCOPE,
  VITE_ENTRA_REDIRECT_URI: import.meta.env.VITE_ENTRA_REDIRECT_URI,
  VITE_ENTRA_POST_LOGOUT_REDIRECT_URI: import.meta.env.VITE_ENTRA_POST_LOGOUT_REDIRECT_URI,
  VITE_API_URL: import.meta.env.VITE_API_URL,
  VITE_API_AUTH_KEY: import.meta.env.VITE_API_AUTH_KEY,
  VITE_API_TIMEOUT_MS: import.meta.env.VITE_API_TIMEOUT_MS,
}

export function readFrontendConfig(key: FrontendRuntimeConfigKey, fallback = ''): string {
  const runtimeConfig = getRuntimeConfig()
  if (Object.prototype.hasOwnProperty.call(runtimeConfig, key)) {
    return String(runtimeConfig[key] ?? '').trim()
  }

  const buildValue = BUILD_FRONTEND_CONFIG[key]
  if (buildValue === undefined || buildValue === null) {
    return fallback
  }
  return String(buildValue).trim()
}

export function readFrontendConfigNumber(key: FrontendRuntimeConfigKey, fallback: number): number {
  const raw = readFrontendConfig(key, '')
  if (!raw) {
    return fallback
  }
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : fallback
}
