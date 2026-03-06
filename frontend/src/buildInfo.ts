import packageJson from '../package.json'

export const FRONTEND_VERSION = String(packageJson.version || '0.0.0')
export const FRONTEND_RELEASE_TAG = `v${FRONTEND_VERSION}`
