import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info, LockKeyhole, Save, Shield, SlidersHorizontal, Wrench } from 'lucide-react'
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
  const queryClient = useQueryClient()
  const [adminKeyInput, setAdminKeyInput] = useState('')
  const [adminKey, setAdminKey] = useState('')
  const [form, setForm] = useState({
    heal_mode: 'safe' as 'safe' | 'demo',
    auto_create_pr: true,
    auto_create_tracking_issue_for_prs: true,
    max_remediation_attempts: 3,
    verify_webhook_signature_in_development: false,
    pipeline_step_timeout_seconds: 120,
    github_api_max_retries: 3,
    github_api_retry_base_seconds: 0.5,
    github_api_retry_max_seconds: 8,
    log_prompt_max_chars: 18000,
    log_prompt_head_chars: 9000,
    log_prompt_tail_chars: 9000,
  })

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['app-settings', adminKey],
    queryFn: () => api.getSettings(adminKey),
    enabled: adminKey.length > 0,
    retry: false,
  })

  useEffect(() => {
    if (!data) {
      return
    }
    setForm({
      heal_mode: data.heal_mode === 'demo' ? 'demo' : 'safe',
      auto_create_pr: data.auto_create_pr,
      auto_create_tracking_issue_for_prs: data.auto_create_tracking_issue_for_prs,
      max_remediation_attempts: data.max_remediation_attempts,
      verify_webhook_signature_in_development: data.verify_webhook_signature_in_development,
      pipeline_step_timeout_seconds: data.pipeline_step_timeout_seconds,
      github_api_max_retries: data.github_api_max_retries,
      github_api_retry_base_seconds: data.github_api_retry_base_seconds,
      github_api_retry_max_seconds: data.github_api_retry_max_seconds,
      log_prompt_max_chars: data.log_prompt_max_chars,
      log_prompt_head_chars: data.log_prompt_head_chars,
      log_prompt_tail_chars: data.log_prompt_tail_chars,
    })
  }, [data])

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateSettings(adminKey, {
        heal_mode: form.heal_mode,
        auto_create_pr: form.auto_create_pr,
        auto_create_tracking_issue_for_prs: form.auto_create_tracking_issue_for_prs,
        max_remediation_attempts: form.max_remediation_attempts,
        verify_webhook_signature_in_development: form.verify_webhook_signature_in_development,
        pipeline_step_timeout_seconds: form.pipeline_step_timeout_seconds,
        github_api_max_retries: form.github_api_max_retries,
        github_api_retry_base_seconds: form.github_api_retry_base_seconds,
        github_api_retry_max_seconds: form.github_api_retry_max_seconds,
        log_prompt_max_chars: form.log_prompt_max_chars,
        log_prompt_head_chars: form.log_prompt_head_chars,
        log_prompt_tail_chars: form.log_prompt_tail_chars,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['app-settings', adminKey] })
    },
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Settings
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Admin-only runtime configuration. Changes apply immediately and remain
          active until backend restart.
        </p>
      </div>

      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <LockKeyhole className="h-5 w-5 text-azure-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Admin Access
          </h2>
        </div>
        <div className="flex flex-col md:flex-row gap-3">
          <input
            type="password"
            value={adminKeyInput}
            onChange={(e) => setAdminKeyInput(e.target.value)}
            placeholder="Enter X-Admin-Key"
            className="flex-1 bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-azure-500"
          />
          <button
            className="btn-primary"
            onClick={() => setAdminKey(adminKeyInput.trim())}
            disabled={!adminKeyInput.trim() || isLoading}
          >
            Load Settings
          </button>
        </div>
        <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
          Uses header <code>X-Admin-Key</code>. Keep this key private.
        </p>
      </div>

      {adminKey && isLoading && (
        <div className="card p-6 text-sm text-gray-500 dark:text-gray-400">
          Loading admin settings...
        </div>
      )}

      {adminKey && isError && (
        <div className="card p-6">
          <div className="flex items-start gap-3">
            <Info className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-600 dark:text-red-400">
                Failed to load admin settings
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
                  <dt className="text-gray-500 dark:text-gray-400">Storage backend</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.storage_backend}
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
                  <dt className="text-gray-500 dark:text-gray-400">Admin key configured</dt>
                  <dd><BoolBadge value={data.admin_api_auth_enabled} /></dd>
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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card p-6">
              <div className="flex items-center gap-2 mb-4">
                <SlidersHorizontal className="h-5 w-5 text-azure-500" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Reliability Snapshot
                </h2>
              </div>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Step timeout (s)</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.pipeline_step_timeout_seconds}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">GitHub max retries</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.github_api_max_retries}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Retry base / max (s)</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.github_api_retry_base_seconds} / {data.github_api_retry_max_seconds}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Prompt max chars</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.log_prompt_max_chars}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="card p-6">
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-5 w-5 text-azure-500" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  GitHub Integration
                </h2>
              </div>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">Auth mode</dt>
                  <dd className="font-medium text-gray-900 dark:text-white">
                    {data.github_auth_mode}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">PAT configured</dt>
                  <dd><BoolBadge value={data.github_pat_configured} /></dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-500 dark:text-gray-400">GitHub App configured</dt>
                  <dd><BoolBadge value={data.github_app_configured} /></dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="card p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Admin Controls
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-sm">
              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Heal mode</span>
                <select
                  value={form.heal_mode}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      heal_mode: e.target.value === 'demo' ? 'demo' : 'safe',
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                >
                  <option value="safe">safe</option>
                  <option value="demo">demo</option>
                </select>
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Max remediation attempts</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={form.max_remediation_attempts}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      max_remediation_attempts: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Pipeline step timeout (s)</span>
                <input
                  type="number"
                  min={1}
                  max={600}
                  value={form.pipeline_step_timeout_seconds}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      pipeline_step_timeout_seconds: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">GitHub API max retries</span>
                <input
                  type="number"
                  min={0}
                  max={10}
                  value={form.github_api_max_retries}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      github_api_max_retries: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Retry base seconds</span>
                <input
                  type="number"
                  min={0.1}
                  max={30}
                  step={0.1}
                  value={form.github_api_retry_base_seconds}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      github_api_retry_base_seconds: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Retry max seconds</span>
                <input
                  type="number"
                  min={0.1}
                  max={120}
                  step={0.1}
                  value={form.github_api_retry_max_seconds}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      github_api_retry_max_seconds: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Log prompt max chars</span>
                <input
                  type="number"
                  min={1000}
                  max={200000}
                  value={form.log_prompt_max_chars}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      log_prompt_max_chars: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Log prompt head chars</span>
                <input
                  type="number"
                  min={100}
                  max={200000}
                  value={form.log_prompt_head_chars}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      log_prompt_head_chars: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="space-y-1">
                <span className="text-gray-500 dark:text-gray-400">Log prompt tail chars</span>
                <input
                  type="number"
                  min={100}
                  max={200000}
                  value={form.log_prompt_tail_chars}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      log_prompt_tail_chars: Number(e.target.value),
                    }))
                  }
                  className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
                />
              </label>

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.auto_create_pr}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, auto_create_pr: e.target.checked }))
                  }
                />
                <span className="text-gray-500 dark:text-gray-400">Auto-create PRs</span>
              </label>

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.auto_create_tracking_issue_for_prs}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      auto_create_tracking_issue_for_prs: e.target.checked,
                    }))
                  }
                />
                <span className="text-gray-500 dark:text-gray-400">
                  Auto-create tracking issue for PRs
                </span>
              </label>

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.verify_webhook_signature_in_development}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      verify_webhook_signature_in_development: e.target.checked,
                    }))
                  }
                />
                <span className="text-gray-500 dark:text-gray-400">
                  Verify webhook signature in development
                </span>
              </label>
            </div>

            {form.log_prompt_head_chars + form.log_prompt_tail_chars >
              form.log_prompt_max_chars && (
              <p className="mt-4 text-sm text-red-600 dark:text-red-400">
                Head + tail prompt chars must be less than or equal to max prompt chars.
              </p>
            )}

            {saveMutation.isError && (
              <p className="mt-4 text-sm text-red-600 dark:text-red-400">
                {saveMutation.error instanceof Error
                  ? saveMutation.error.message
                  : 'Failed to save settings'}
              </p>
            )}

            {saveMutation.isSuccess && (
              <p className="mt-4 text-sm text-green-600 dark:text-green-400">
                Admin settings updated.
              </p>
            )}

            <div className="mt-4 flex justify-end">
              <button
                className="btn-primary flex items-center"
                disabled={
                  saveMutation.isPending ||
                  form.log_prompt_head_chars + form.log_prompt_tail_chars >
                    form.log_prompt_max_chars
                }
                onClick={() => saveMutation.mutate()}
              >
                <Save className="h-4 w-4 mr-2" />
                {saveMutation.isPending ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
