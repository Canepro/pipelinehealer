import { useQuery } from '@tanstack/react-query'
import { Info, Shield, SlidersHorizontal, Wrench } from 'lucide-react'
import { api } from '../api/client'

function BoolBadge({ value }: { value: boolean }) {
  return (
    <span
      className={`status-badge ${
        value ? 'status-completed' : 'status-failed'
      }`}
    >
      {value ? 'Enabled' : 'Disabled'}
    </span>
  )
}

export default function SettingsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['app-settings'],
    queryFn: api.getSettings,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Settings
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Runtime configuration (read-only for now). Write actions come in a
          future admin release.
        </p>
      </div>

      {isLoading && (
        <div className="card p-6 text-sm text-gray-500 dark:text-gray-400">
          Loading settings...
        </div>
      )}

      {isError && (
        <div className="card p-6">
          <div className="flex items-start gap-3">
            <Info className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-600 dark:text-red-400">
                Failed to load settings
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {error instanceof Error ? error.message : 'Unknown error'}
              </p>
            </div>
          </div>
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card p-6">
              <div className="flex items-center gap-2 mb-4">
                <SlidersHorizontal className="h-5 w-5 text-azure-500" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Runtime
                </h2>
              </div>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Environment</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.environment}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Heal mode</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.heal_mode}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Max remediation attempts</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.max_remediation_attempts}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="card p-6">
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-5 w-5 text-azure-500" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Security
                </h2>
              </div>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">API auth key configured</dt>
                  <dd><BoolBadge value={data.api_auth_enabled} /></dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Webhook verification</dt>
                  <dd><BoolBadge value={data.verify_webhook_signature} /></dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Verify in development</dt>
                  <dd>
                    <BoolBadge
                      value={data.verify_webhook_signature_in_development}
                    />
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card p-6">
              <div className="flex items-center gap-2 mb-4">
                <Wrench className="h-5 w-5 text-azure-500" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  AI Provider
                </h2>
              </div>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Endpoint</dt>
                  <dd className="text-right font-medium text-gray-900 dark:text-white break-all">
                    {data.azure_openai_endpoint || 'Not set'}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Deployment</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.azure_openai_deployment_name || 'Not set'}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">API version</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.azure_openai_api_version || 'Not set'}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="card p-6">
              <div className="flex items-center gap-2 mb-4">
                <Info className="h-5 w-5 text-azure-500" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  CORS
                </h2>
              </div>
              <dl className="space-y-3 text-sm">
                <div>
                  <dt className="text-gray-500 dark:text-gray-400 mb-2">Allowed origins</dt>
                  <dd className="space-y-1">
                    {data.cors_allowed_origins.map((origin) => (
                      <div
                        key={origin}
                        className="px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 break-all"
                      >
                        {origin}
                      </div>
                    ))}
                  </dd>
                </div>
                <div className="pt-1">
                  <dt className="text-gray-500 dark:text-gray-400">Origin regex</dt>
                  <dd className="font-medium text-gray-900 dark:text-white break-all">
                    {data.cors_allow_origin_regex}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
