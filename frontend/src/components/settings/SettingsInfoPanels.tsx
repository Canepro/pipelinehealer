import { Info, Shield, SlidersHorizontal, Wrench } from 'lucide-react'
import type { AppSettings } from '../../api/client'
import { Badge } from '@/components/ui/badge'

function BoolBadge({ value }: { value: boolean }) {
  return <Badge variant={value ? 'success' : 'destructive'}>{value ? 'Enabled' : 'Disabled'}</Badge>
}

interface Props {
  data: AppSettings
}

export default function SettingsInfoPanels({ data }: Props) {
  return (
    <>
      {/* Runtime + Security row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4 md:p-6">
          <div className="flex items-center gap-2 mb-4">
            <SlidersHorizontal className="h-5 w-5 text-azure-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Runtime</h2>
          </div>
          <dl className="space-y-3 text-sm">
            <Row label="Environment" value={data.environment} />
            <Row label="Storage backend" value={data.storage_backend} />
            <Row label="Heal mode" value={data.heal_mode} />
            <Row label="Max remediation attempts" value={data.max_remediation_attempts} />
          </dl>
        </div>

        <div className="card p-4 md:p-6">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="h-5 w-5 text-azure-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Security</h2>
          </div>
          <dl className="space-y-3 text-sm">
            <BoolRow label="API auth key" value={data.api_auth_enabled} />
            <BoolRow label="Admin key" value={data.admin_api_auth_enabled} />
            <BoolRow label="Webhook verification" value={data.verify_webhook_signature} />
            <BoolRow label="Verify in development" value={data.verify_webhook_signature_in_development} />
          </dl>
        </div>
      </div>

      {/* AI Provider + CORS row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4 md:p-6">
          <div className="flex items-center gap-2 mb-4">
            <Wrench className="h-5 w-5 text-azure-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">AI Provider</h2>
          </div>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500 dark:text-gray-400">Endpoint</dt>
              <dd className="text-right font-medium text-gray-900 dark:text-white break-all">
                {data.azure_openai_endpoint || 'Not set'}
              </dd>
            </div>
            <Row label="Deployment" value={data.azure_openai_deployment_name || 'Not set'} />
            <Row label="API version" value={data.azure_openai_api_version || 'Not set'} />
          </dl>
        </div>

        <div className="card p-4 md:p-6">
          <div className="flex items-center gap-2 mb-4">
            <Info className="h-5 w-5 text-azure-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">CORS</h2>
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

      {/* Reliability + GitHub Integration row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4 md:p-6">
          <div className="flex items-center gap-2 mb-4">
            <SlidersHorizontal className="h-5 w-5 text-azure-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Reliability Snapshot</h2>
          </div>
          <dl className="space-y-3 text-sm">
            <Row label="Step timeout (s)" value={data.pipeline_step_timeout_seconds} />
            <Row label="GitHub max retries" value={data.github_api_max_retries} />
            <Row
              label="Retry base / max (s)"
              value={`${data.github_api_retry_base_seconds} / ${data.github_api_retry_max_seconds}`}
            />
            <Row label="Prompt max chars" value={data.log_prompt_max_chars} />
          </dl>
        </div>

        <div className="card p-4 md:p-6">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="h-5 w-5 text-azure-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">GitHub Integration</h2>
          </div>
          <dl className="space-y-3 text-sm">
            <Row label="Auth mode" value={data.github_auth_mode} />
            <BoolRow label="PAT auth" value={data.github_pat_configured} />
            <BoolRow label="GitHub App auth" value={data.github_app_configured} />
            <Row
              label="Repo allowlist"
              value={
                data.ph_allowed_repos.length > 0
                  ? `${data.ph_allowed_repos.length} repos`
                  : 'All repos (unrestricted)'
              }
            />
            <BoolRow label="gh-aw tools" value={data.gh_aw_tools_enabled} />
            <Row label="gh-aw ingestion" value={data.gh_aw_ingestion_mode} />
          </dl>
          <div className="mt-3">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Allowed repositories</p>
            {data.ph_allowed_repos.length > 0 ? (
              <div className="space-y-1">
                {data.ph_allowed_repos.map((repo) => (
                  <div
                    key={repo}
                    className="px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 break-all text-xs"
                  >
                    {repo}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                No repo allowlist set. Backend is not restricted to specific repositories.
              </p>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 mb-1">Known gh-aw workflows</p>
            {data.gh_aw_known_workflows.length > 0 ? (
              <div className="space-y-1">
                {data.gh_aw_known_workflows.map((workflow) => (
                  <div
                    key={workflow}
                    className="px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 break-all text-xs"
                  >
                    {workflow}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                No known gh-aw workflows configured.
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

/* ---- tiny presentational helpers ---- */

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="font-medium text-gray-900 dark:text-white">{String(value)}</dd>
    </div>
  )
}

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd><BoolBadge value={value} /></dd>
    </div>
  )
}
