import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info, LockKeyhole } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import {
  AdminControlsForm,
  AuditTrailPanel,
  RuntimePolicyBanner,
  SettingsInfoPanels,
  toSettingsForm,
} from '../components/settings'
import type { SettingsFormState } from '../components/settings'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [adminKeyInput, setAdminKeyInput] = useState('')
  const [adminKey, setAdminKey] = useState('')
  const [form, setForm] = useState<SettingsFormState>({
    heal_mode: 'safe',
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
    gh_aw_tools_enabled: false,
    gh_aw_ingestion_mode: 'disabled',
    gh_aw_known_workflows: ['ci-doctor', 'schema-consistency-checker', 'breaking-change-checker'],
    ph_allowed_repos: [],
    azure_openai_deployment_name: '',
  })
  const [lastSavedForm, setLastSavedForm] = useState<SettingsFormState | null>(null)
  const [newRepoInput, setNewRepoInput] = useState('')
  const [ghAwWorkflowsInput, setGhAwWorkflowsInput] = useState('')

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['app-settings', adminKey],
    queryFn: () => api.getSettings(adminKey),
    enabled: adminKey.length > 0,
    retry: false,
  })

  const {
    data: auditEntries,
    refetch: refetchAudit,
    isFetching: isAuditLoading,
    isError: isAuditError,
    error: auditError,
  } = useQuery({
    queryKey: ['settings-audit', adminKey],
    queryFn: () => api.getSettingsAudit(adminKey, 20),
    enabled: false,
    retry: false,
  })

  useEffect(() => {
    if (!data) return
    const next = toSettingsForm(data)
    setForm(next)
    setLastSavedForm(next)
    setGhAwWorkflowsInput(next.gh_aw_known_workflows.join(','))
  }, [data])

  const hasUnsavedChanges =
    lastSavedForm !== null && JSON.stringify(form) !== JSON.stringify(lastSavedForm)

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
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
        gh_aw_tools_enabled: form.gh_aw_tools_enabled,
        gh_aw_ingestion_mode: form.gh_aw_ingestion_mode,
        gh_aw_known_workflows: form.gh_aw_known_workflows,
        ph_allowed_repos: form.ph_allowed_repos,
      }
      const deploymentName = form.azure_openai_deployment_name.trim()
      if (deploymentName) {
        payload.azure_openai_deployment_name = deploymentName
      }
      return api.updateSettings(adminKey, payload)
    },
    onSuccess: async (updated) => {
      const next = toSettingsForm(updated)
      setForm(next)
      setLastSavedForm(next)
      setGhAwWorkflowsInput(next.gh_aw_known_workflows.join(','))
      queryClient.setQueryData(['app-settings', adminKey], updated)
      await queryClient.invalidateQueries({ queryKey: ['app-settings', adminKey] })
      toast.success('Settings saved', {
        description: 'Runtime settings were updated successfully.',
      })
    },
    onError: (err) => {
      toast.error('Failed to save settings', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    },
  })

  const persistMutation = useMutation({
    mutationFn: () => api.persistSettings(adminKey),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['app-settings', adminKey] })
      if (result.redeploy_attempted && !result.redeploy_started) {
        toast.error('Settings persisted but redeploy did not start', {
          description: result.redeploy_message,
        })
        return
      }
      toast.success(result.redeploy_attempted ? 'Settings persisted and redeploy started' : 'Settings persisted', {
        description: result.redeploy_message,
      })
    },
    onError: (err) => {
      toast.error('Failed to persist settings', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    },
  })

  const handleLoadAudit = async () => {
    try {
      await refetchAudit()
      toast.success('Audit log loaded')
    } catch (err) {
      toast.error('Failed to load audit log', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  }

  const handlePersistAndRedeploy = () => {
    if (!data) return
    if (hasUnsavedChanges) {
      toast.error('Save settings first', {
        description: 'Persist and redeploy uses effective saved values only.',
      })
      return
    }
    persistMutation.mutate()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Admin-only runtime configuration. Edit draft values, then save to make them effective.
          Saved values apply immediately and remain active until backend restart.
        </p>
      </div>

      {/* Admin access card */}
      <Card className="p-4 md:p-6">
        <div className="flex items-center gap-2 mb-4">
          <LockKeyhole className="h-5 w-5 text-azure-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Admin Access</h2>
        </div>
        <div className="flex flex-col md:flex-row gap-3">
          <Input
            type="password"
            value={adminKeyInput}
            onChange={(e) => setAdminKeyInput(e.target.value)}
            placeholder="Enter X-Admin-Key"
            className="flex-1"
          />
          <Button
            onClick={() => setAdminKey(adminKeyInput.trim())}
            disabled={!adminKeyInput.trim() || isLoading}
          >
            Load Settings
          </Button>
        </div>
        <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
          Uses header <code>X-Admin-Key</code>. Keep this key private.
        </p>
      </Card>

      {/* Loading state */}
      {adminKey && isLoading && (
        <Card className="p-4 md:p-6">
          <div className="space-y-3">
            <Skeleton className="h-4 w-44" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        </Card>
      )}

      {/* Error state */}
      {adminKey && isError && (
        <div className="card p-4 md:p-6">
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

      {/* Main settings content */}
      {data && (
        <>
          <RuntimePolicyBanner
            data={data}
            hasUnsavedChanges={hasUnsavedChanges}
            isPersisting={persistMutation.isPending}
            onPersist={handlePersistAndRedeploy}
          />

          <SettingsInfoPanels data={data} />

          <AdminControlsForm
            data={data}
            form={form}
            setForm={setForm}
            hasUnsavedChanges={hasUnsavedChanges}
            newRepoInput={newRepoInput}
            setNewRepoInput={setNewRepoInput}
            ghAwWorkflowsInput={ghAwWorkflowsInput}
            setGhAwWorkflowsInput={setGhAwWorkflowsInput}
            setLastSavedForm={setLastSavedForm}
            savePending={saveMutation.isPending}
            saveError={saveMutation.isError ? (saveMutation.error as Error) : null}
            saveSuccess={saveMutation.isSuccess}
            onSave={() => saveMutation.mutate()}
          />

          <AuditTrailPanel
            adminKey={adminKey}
            entries={auditEntries}
            isLoading={isAuditLoading}
            isError={isAuditError}
            error={isAuditError ? (auditError as Error) : null}
            onLoad={() => void handleLoadAudit()}
          />
        </>
      )}
    </div>
  )
}
