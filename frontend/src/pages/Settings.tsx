import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { KeyRound, Settings2 } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import { AUTH_ENABLED } from '../auth/config'
import {
  AdminControlsForm,
  RuntimePolicyBanner,
  toSettingsForm,
} from '../components/settings'
import type { SettingsFormState } from '../components/settings'
import { describeAgentHandoffIntegrationStatus } from '../components/settings/runtimeSemantics'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [adminKeyInput, setAdminKeyInput] = useState('')
  const [adminKey, setAdminKey] = useState('')
  const [useSessionAuth, setUseSessionAuth] = useState(false)
  const [newMcpRepoInput, setNewMcpRepoInput] = useState('')
  const [newHandoffHostInput, setNewHandoffHostInput] = useState('')
  const [form, setForm] = useState<SettingsFormState>({
    llm_provider: 'azure_openai',
    openai_compatible_base_url: '',
    openai_compatible_model: '',
    llm_model_analysis: '',
    llm_model_diagnosis: '',
    llm_model_remediation: '',
    mcp_enabled: false,
    mcp_provider: 'disabled',
    mcp_read_only: true,
    mcp_timeout_seconds: 15,
    mcp_max_retries: 1,
    mcp_tool_policies: {
      fetch_failure_context: 'read_only',
      fetch_runbook_context: 'read_only',
      publish_artifact: 'write_with_approval',
      rerun_pipeline: 'write_with_approval',
    },
    mcp_repo_allowlist: [],
    heal_mode: 'safe',
    auto_apply_remediation: true,
    auto_create_pr: true,
    jenkins_bridge_allow_pr: false,
    auto_create_issue: true,
    auto_retry_workflow: true,
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
    agent_handoff_enabled: false,
    agent_handoff_mode: 'copy_only',
    agent_handoff_webhook_allowlist: [],
    agent_handoff_timeout_seconds: 8,
    agent_handoff_max_retries: 1,
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
    data: llmProviderHealth,
    isLoading: isLlmHealthLoading,
  } = useQuery({
    queryKey: ['llm-provider-health', adminKey, useSessionAuth],
    queryFn: () => api.getLLMProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  })

  const {
    data: mcpProviderHealth,
    isLoading: isMcpHealthLoading,
  } = useQuery({
    queryKey: ['mcp-provider-health', adminKey, useSessionAuth],
    queryFn: () => api.getMCPProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  })

  const { data: handoffIntegrationStatus } = useQuery({
    queryKey: ['agent-handoff-integration-status', hasAuthAttempt],
    queryFn: () => api.getAgentHandoffIntegrationStatus(),
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
  const settingsErrorMessage = error instanceof Error ? error.message : 'Unknown error'
  const sessionAuthDisabledByConfig = useSessionAuth && !AUTH_ENABLED
  const showSessionRefreshHint =
    useSessionAuth &&
    AUTH_ENABLED &&
    isError &&
    (() => {
      const normalized = settingsErrorMessage.toLowerCase()
      return (
        normalized.includes('invalid or missing admin api key') ||
        normalized.includes('invalid bearer token') ||
        normalized.includes('missing credentials')
      )
    })()
  const handoffIntegrationSummary = describeAgentHandoffIntegrationStatus(handoffIntegrationStatus)

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        llm_provider: form.llm_provider,
        openai_compatible_base_url: form.openai_compatible_base_url.trim(),
        openai_compatible_model: form.openai_compatible_model.trim(),
        llm_model_analysis: form.llm_model_analysis.trim(),
        llm_model_diagnosis: form.llm_model_diagnosis.trim(),
        llm_model_remediation: form.llm_model_remediation.trim(),
        mcp_enabled: form.mcp_enabled,
        mcp_provider: form.mcp_provider,
        mcp_read_only: form.mcp_read_only,
        mcp_timeout_seconds: form.mcp_timeout_seconds,
        mcp_max_retries: form.mcp_max_retries,
        mcp_tool_policies: form.mcp_tool_policies,
        mcp_repo_allowlist: form.mcp_repo_allowlist,
        heal_mode: form.heal_mode,
        auto_apply_remediation: form.auto_apply_remediation,
        auto_create_pr: form.auto_create_pr,
        jenkins_bridge_allow_pr: form.jenkins_bridge_allow_pr,
        auto_create_issue: form.auto_create_issue,
        auto_retry_workflow: form.auto_retry_workflow,
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
        agent_handoff_enabled: form.agent_handoff_enabled,
        agent_handoff_mode: form.agent_handoff_mode,
        agent_handoff_webhook_allowlist: form.agent_handoff_webhook_allowlist,
        agent_handoff_timeout_seconds: form.agent_handoff_timeout_seconds,
        agent_handoff_max_retries: form.agent_handoff_max_retries,
        ph_allowed_repos: form.ph_allowed_repos,
      }
      const deploymentName = form.azure_openai_deployment_name.trim()
      if (deploymentName) {
        payload.azure_openai_deployment_name = deploymentName
      }
      const updated = await api.updateSettings(effectiveAdminKey, payload)
      try {
        const persist = await api.persistSettings(effectiveAdminKey)
        return { updated, persist, persistError: null as string | null }
      } catch (error) {
        const persistError =
          error instanceof Error ? error.message : 'Persist step failed after runtime save'
        return { updated, persist: null, persistError }
      }
    },
    onSuccess: async ({ updated, persist, persistError }) => {
      const next = toSettingsForm(updated)
      setForm(next)
      setLastSavedForm(next)
      setGhAwWorkflowsInput(next.gh_aw_known_workflows.join(','))
      queryClient.setQueryData(['app-settings', adminKey, useSessionAuth], updated)
      await queryClient.invalidateQueries({ queryKey: ['app-settings', adminKey, useSessionAuth] })
      if (persistError) {
        toast.warning('Settings saved but persist step failed', {
          description: persistError,
        })
        return
      }
      if (persist && persist.redeploy_attempted && !persist.redeploy_started) {
        toast.warning('Settings saved and persisted; redeploy did not start', {
          description: persist.redeploy_message,
        })
        return
      }
      toast.success('Settings saved and persisted', {
        description:
          persist?.redeploy_message || 'Changes are active and durable across restarts/redeploy.',
      })
    },
    onError: (err) => {
      toast.error('Failed to save settings', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    },
  })

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Settings2 className="h-7 w-7 text-azure-500" />
        <div>
          <h1 className="text-2xl font-bold text-[var(--ph-text)]">Settings</h1>
          <p className="text-sm text-[var(--ph-muted)]">
            Operator control surface for runtime policy, startup-managed dependencies, and durable settings.
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
              disabled={isLoading || !AUTH_ENABLED}
            >
              {isLoading ? 'Loading...' : 'Use Login Session'}
            </Button>
          </div>
          <p className="mt-2 text-xs text-[var(--ph-muted)]">
            {AUTH_ENABLED ? (
              <>
                Use either <code className="font-mono">X-Admin-Key</code> or a signed-in Entra role
                with admin permissions.
              </>
            ) : (
              <>
                Session login is disabled in this deployment
                (<code className="font-mono">VITE_AUTH_MODE=none</code>). Use
                <code className="font-mono">X-Admin-Key</code> or set frontend runtime
                <code className="font-mono">VITE_ENTRA_*</code> values and redeploy env.
              </>
            )}
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
            <p className="text-sm text-[var(--ph-muted)] mt-1">{settingsErrorMessage}</p>
            {showSessionRefreshHint && (
              <p className="text-xs text-[var(--ph-muted)] mt-3">
                Session may be stale. Try signing out, signing in again, or clearing site data and
                retrying.
              </p>
            )}
            {sessionAuthDisabledByConfig && (
              <p className="text-xs text-[var(--ph-muted)] mt-3">
                Session tokens are disabled by runtime config. Set
                <code className="mx-1 font-mono">VITE_AUTH_MODE=entra</code> and required
                <code className="mx-1 font-mono">VITE_ENTRA_*</code> env vars, then redeploy env.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Main settings content */}
      {data && (
        <>
          <RuntimePolicyBanner
            data={data}
          />

          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
              <p className="text-sm text-[var(--ph-muted)]">
                Use section tabs below for changes, then verify outcomes in Control Center.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm" variant="secondary">
                  <Link to="/app/control-center">Open Control Center</Link>
                </Button>
                <Button asChild size="sm" variant="ghost">
                  <Link to="/app/activities">Review Activities</Link>
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Operator Workflow</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
                <WorkflowStep
                  step={1}
                  title="Authenticate"
                  detail="Load admin access key or use active login session."
                />
                <WorkflowStep
                  step={2}
                  title="Edit Policy"
                  detail="Adjust runtime, model, and MCP settings in section tabs."
                />
                <WorkflowStep
                  step={3}
                  title="Save & Persist"
                  detail="Use one save action to apply runtime + durable configuration."
                />
                <WorkflowStep
                  step={4}
                  title="Verify"
                  detail="Confirm outcomes in Control Center and Activity evidence."
                />
              </div>
            </CardContent>
          </Card>

          <div
            className="grid gap-4"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}
          >
            <SettingsSummaryCard
              title="Runtime Posture"
              items={[
                { label: 'Heal mode', value: data.heal_mode },
                {
                  label: 'Auto-apply remediation',
                  value: data.auto_apply_remediation ? 'Yes' : 'No',
                },
                { label: 'Auto-create PR', value: data.auto_create_pr ? 'Yes' : 'No' },
                {
                  label: 'Jenkins bridge PRs',
                  value: data.jenkins_bridge_allow_pr ? 'Allowed' : 'Issue-first',
                },
                { label: 'Auto-create Issue', value: data.auto_create_issue ? 'Yes' : 'No' },
                {
                  label: 'Auto-retry workflow',
                  value: data.auto_retry_workflow ? 'Yes' : 'No',
                },
                { label: 'Max attempts', value: data.max_remediation_attempts },
              ]}
            />
            <SettingsSummaryCard
              title="Scope"
              items={[
                {
                  label: 'Repo scope',
                  value:
                    data.ph_allowed_repos.length > 0
                      ? `${data.ph_allowed_repos.length} allowlisted repos`
                      : 'All repositories',
                },
                {
                  label: 'MCP allowlist',
                  value:
                    data.mcp_repo_allowlist.length > 0
                      ? `${data.mcp_repo_allowlist.length} repos`
                      : 'Fallback to PH scope',
                },
              ]}
            />
            <SettingsSummaryCard
              title="Assign-to-Agent"
              items={[
                {
                  label: 'Runtime',
                  value: data.agent_handoff_enabled ? 'Enabled' : 'Disabled',
                },
                {
                  label: 'Mode',
                  value:
                    data.agent_handoff_mode === 'webhook'
                      ? data.agent_handoff_webhook_configured
                        ? 'Webhook'
                        : 'Webhook (missing startup URL)'
                      : 'Copy only',
                },
                {
                  label: 'Destination',
                  value: data.agent_handoff_webhook_host || 'Startup URL not configured',
                },
                {
                  label: 'Receiver',
                  value: handoffIntegrationSummary.summary,
                },
                {
                  label: 'Notifications',
                  value: handoffIntegrationStatus?.notifications
                    ? `${handoffIntegrationStatus.notifications.enabled_targets} enabled / ${handoffIntegrationStatus.notifications.invalid_targets} invalid`
                    : 'No receiver probe data',
                },
              ]}
            />
            <SettingsSummaryCard
              title="Integration Status"
              items={[
                {
                  label: 'Receiver detail',
                  value: handoffIntegrationSummary.detail,
                },
                {
                  label: 'Health endpoint',
                  value: handoffIntegrationStatus?.receiver_health_url || 'Not probed',
                },
                {
                  label: 'Supported sinks',
                  value: handoffIntegrationStatus?.notifications?.supported_target_types.length
                    ? handoffIntegrationStatus.notifications.supported_target_types.join(', ')
                    : 'No receiver probe data',
                },
              ]}
            />
            <SettingsSummaryCard
              title="AI Provider"
              items={[
                { label: 'Provider', value: data.llm_provider },
                {
                  label: 'Default model',
                  value:
                    data.llm_provider === 'azure_openai'
                      ? data.azure_openai_deployment_name || 'Not configured'
                      : data.openai_compatible_model || 'Not configured',
                },
              ]}
            />
            <SettingsSummaryCard
              title="Security"
              items={[
                { label: 'Auth mode', value: data.auth_mode },
                {
                  label: 'Admin auth',
                  value: data.admin_api_auth_enabled ? 'Enabled' : 'Disabled',
                },
                {
                  label: 'Webhook signature',
                  value: data.verify_webhook_signature ? 'Required' : 'Off',
                },
              ]}
            />
          </div>

            <AdminControlsForm
              data={data}
              form={form}
              setForm={setForm}
            llmProviderHealth={llmProviderHealth}
            isLlmHealthLoading={isLlmHealthLoading}
            mcpProviderHealth={mcpProviderHealth}
            isMcpHealthLoading={isMcpHealthLoading}
            hasUnsavedChanges={hasUnsavedChanges}
            newRepoInput={newRepoInput}
            setNewRepoInput={setNewRepoInput}
              newMcpRepoInput={newMcpRepoInput}
              setNewMcpRepoInput={setNewMcpRepoInput}
              newHandoffHostInput={newHandoffHostInput}
              setNewHandoffHostInput={setNewHandoffHostInput}
              setGhAwWorkflowsInput={setGhAwWorkflowsInput}
            setLastSavedForm={setLastSavedForm}
            savePending={saveMutation.isPending}
            saveError={saveMutation.isError ? (saveMutation.error as Error) : null}
            saveSuccess={saveMutation.isSuccess}
            onSave={() => saveMutation.mutate()}
          />
        </>
      )}
    </div>
  )
}

function WorkflowStep({
  step,
  title,
  detail,
}: {
  step: number
  title: string
  detail: string
}) {
  return (
    <div className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/25 p-3">
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-azure-600/90 text-[11px] font-semibold text-white">
          {step}
        </span>
        <span className="text-sm font-medium text-[var(--ph-text)]">{title}</span>
      </div>
      <p className="mt-1 text-xs text-[var(--ph-muted)]">{detail}</p>
    </div>
  )
}

function SettingsSummaryCard({
  title,
  items,
}: {
  title: string
  items: Array<{ label: string; value: string | number }>
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        {items.map((item) => (
          <div key={`${title}-${item.label}`} className="flex items-center justify-between gap-3">
            <span className="text-[var(--ph-muted)]">{item.label}</span>
            <span className="break-words text-right font-medium text-[var(--ph-text)]">
              {item.value}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
