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

export function readFrontendConfig(key: FrontendRuntimeConfigKey, fallback = ''): string {
  const runtimeConfig = getRuntimeConfig()
  if (Object.prototype.hasOwnProperty.call(runtimeConfig, key)) {
    return String(runtimeConfig[key] ?? '').trim()
  }

  const buildValue = (import.meta.env as Record<string, unknown>)[key]
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
