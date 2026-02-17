import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Settings2 } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import {
  AdminControlsForm,
  AuditTrailPanel,
  RuntimePolicyBanner,
  toSettingsForm,
} from '../components/settings'
import type { SettingsFormState } from '../components/settings'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [adminKeyInput, setAdminKeyInput] = useState('')
  const [adminKey, setAdminKey] = useState('')
  const [useSessionAuth, setUseSessionAuth] = useState(false)
  const [form, setForm] = useState<SettingsFormState>({
    llm_provider: 'azure_openai',
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
    gh_aw_known_workflows: ['ci-doctor'],
    ph_allowed_repos: [],
    azure_openai_deployment_name: '',
  })
  const [lastSavedForm, setLastSavedForm] = useState<SettingsFormState | null>(null)
  const [newRepoInput, setNewRepoInput] = useState('')
  const [, setGhAwWorkflowsInput] = useState('')
  const hasAuthAttempt = useSessionAuth || adminKey.length > 0
  const effectiveAdminKey = useSessionAuth ? undefined : adminKey

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['app-settings', adminKey, useSessionAuth],
    queryFn: () => api.getSettings(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  })

  const {
    data: auditEntries,
    refetch: refetchAudit,
    isFetching: isAuditLoading,
    isError: isAuditError,
    error: auditError,
  } = useQuery({
    queryKey: ['settings-audit', adminKey, useSessionAuth],
    queryFn: () => api.getSettingsAudit(effectiveAdminKey, 20),
    enabled: false,
    retry: false,
  })

  const {
    data: llmProviderHealth,
    isLoading: isLlmHealthLoading,
  } = useQuery({
    queryKey: ['llm-provider-health', adminKey, useSessionAuth],
    queryFn: () => api.getLLMProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
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
        llm_provider: form.llm_provider,
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
      return api.updateSettings(effectiveAdminKey, payload)
    },
    onSuccess: async (updated) => {
      const next = toSettingsForm(updated)
      setForm(next)
      setLastSavedForm(next)
      setGhAwWorkflowsInput(next.gh_aw_known_workflows.join(','))
      queryClient.setQueryData(['app-settings', adminKey, useSessionAuth], updated)
      await queryClient.invalidateQueries({ queryKey: ['app-settings', adminKey, useSessionAuth] })
      toast.success('Settings saved', {
        description: 'Runtime settings updated. Changes are active immediately.',
      })
    },
    onError: (err) => {
      toast.error('Failed to save settings', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    },
  })

  const persistMutation = useMutation({
    mutationFn: () => api.persistSettings(effectiveAdminKey),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['app-settings', adminKey, useSessionAuth] })
      if (result.redeploy_attempted && !result.redeploy_started) {
        toast.error('Settings persisted but redeploy did not start', {
          description: result.redeploy_message,
        })
        return
      }
      toast.success(
        result.redeploy_attempted
          ? 'Settings persisted and redeploy started'
          : 'Settings persisted',
        { description: result.redeploy_message }
      )
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
        description: 'Persist uses effective saved values only.',
      })
      return
    }
    persistMutation.mutate()
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Settings2 className="h-7 w-7 text-azure-500" />
        <div>
          <h1 className="text-2xl font-bold text-[var(--ph-text)]">Settings</h1>
          <p className="text-sm text-[var(--ph-muted)]">
            Admin-only runtime configuration for PipelineHealer.
          </p>
        </div>
      </div>

      {/* Admin access */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-azure-500" />
            <CardTitle>Admin Access</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <Input
              type="password"
              value={adminKeyInput}
              onChange={(e) => setAdminKeyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && adminKeyInput.trim()) {
                  e.preventDefault()
                  setUseSessionAuth(false)
                  setAdminKey(adminKeyInput.trim())
                }
              }}
              placeholder="Enter admin key (X-Admin-Key)"
              className="flex-1"
            />
            <Button
              onClick={() => {
                setUseSessionAuth(false)
                setAdminKey(adminKeyInput.trim())
              }}
              disabled={!adminKeyInput.trim() || isLoading}
            >
              {isLoading ? 'Loading...' : 'Load with Admin Key'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setUseSessionAuth(true)
                setAdminKey('')
              }}
              disabled={isLoading}
            >
              {isLoading ? 'Loading...' : 'Use Login Session'}
            </Button>
          </div>
          <p className="mt-2 text-xs text-[var(--ph-muted)]">
            Use either <code className="font-mono">X-Admin-Key</code> or a signed-in Entra role
            with admin permissions.
          </p>
        </CardContent>
      </Card>

      {/* Loading skeleton */}
      {hasAuthAttempt && isLoading && (
        <Card>
          <CardContent className="py-6">
            <div className="space-y-4">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-2/3" />
              <Skeleton className="h-10 w-full" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error state */}
      {hasAuthAttempt && isError && (
        <Card className="border-rose-500/30">
          <CardContent className="py-6">
            <p className="text-sm font-medium text-rose-500">Failed to load settings</p>
            <p className="text-sm text-[var(--ph-muted)] mt-1">
              {error instanceof Error ? error.message : 'Unknown error'}
            </p>
          </CardContent>
        </Card>
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

          <AdminControlsForm
            data={data}
            form={form}
            setForm={setForm}
            llmProviderHealth={llmProviderHealth}
            isLlmHealthLoading={isLlmHealthLoading}
            hasUnsavedChanges={hasUnsavedChanges}
            newRepoInput={newRepoInput}
            setNewRepoInput={setNewRepoInput}
            setGhAwWorkflowsInput={setGhAwWorkflowsInput}
            setLastSavedForm={setLastSavedForm}
            savePending={saveMutation.isPending}
            saveError={saveMutation.isError ? (saveMutation.error as Error) : null}
            saveSuccess={saveMutation.isSuccess}
            onSave={() => saveMutation.mutate()}
          />

          <AuditTrailPanel
            canLoad={hasAuthAttempt}
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
