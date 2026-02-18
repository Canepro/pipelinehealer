import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Copy,
  ExternalLink,
  KeyRound,
  ScrollText,
  ShieldCheck,
  TerminalSquare,
  Workflow,
} from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import { AuditTrailPanel } from '../components/settings'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

type ToolPolicy = 'disabled' | 'read_only' | 'write_with_approval' | 'auto'

const LOGS_RUNBOOK_URL =
  'https://github.com/Canepro/pipelinehealer/blob/main/docs/LOGS_AND_INVESTIGATION.md'

const TOOL_METADATA: Array<{ key: string; write: boolean; label: string }> = [
  { key: 'fetch_failure_context', write: false, label: 'Failure Context' },
  { key: 'fetch_runbook_context', write: false, label: 'Runbook Context' },
  { key: 'publish_artifact', write: true, label: 'Publish Artifact' },
  { key: 'rerun_pipeline', write: true, label: 'Rerun Pipeline' },
]

function formatToolPolicy(policy: ToolPolicy): string {
  switch (policy) {
    case 'disabled':
      return 'Disabled'
    case 'read_only':
      return 'Read only'
    case 'write_with_approval':
      return 'Write with approval'
    case 'auto':
      return 'Auto'
    default:
      return policy
  }
}

function getEffectiveToolState({
  mcpEnabled,
  provider,
  readOnly,
  write,
  policy,
}: {
  mcpEnabled: boolean
  provider: string
  readOnly: boolean
  write: boolean
  policy: ToolPolicy
}): { label: string; tone: 'ok' | 'warn' | 'bad' | 'muted' } {
  if (!mcpEnabled || provider === 'disabled') {
    return { label: 'Inactive', tone: 'muted' }
  }
  if (policy === 'disabled') {
    return { label: 'Blocked', tone: 'bad' }
  }
  if (!write) {
    return { label: 'Allowed (Read)', tone: 'ok' }
  }
  if (readOnly || policy === 'read_only') {
    return { label: 'Blocked', tone: 'bad' }
  }
  if (policy === 'write_with_approval') {
    return { label: 'Approval Required', tone: 'warn' }
  }
  return { label: 'Allowed (Auto)', tone: 'ok' }
}

function toneClass(tone: 'ok' | 'warn' | 'bad' | 'muted'): string {
  switch (tone) {
    case 'ok':
      return 'text-emerald-300'
    case 'warn':
      return 'text-amber-300'
    case 'bad':
      return 'text-rose-300'
    default:
      return 'text-slate-300'
  }
}

export default function ControlCenterPage() {
  const [adminKeyInput, setAdminKeyInput] = useState('')
  const [adminKey, setAdminKey] = useState('')
  const [useSessionAuth, setUseSessionAuth] = useState(false)
  const hasAuthAttempt = useSessionAuth || adminKey.length > 0
  const effectiveAdminKey = useSessionAuth ? undefined : adminKey

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    retry: 1,
  })

  const {
    data: recentActivities,
    isLoading: activitiesLoading,
  } = useQuery({
    queryKey: ['activities', { limit: 8 }],
    queryFn: () => api.getActivities({ limit: 8 }),
  })

  const {
    data: settings,
    isLoading: settingsLoading,
    isError: isSettingsError,
    error: settingsError,
  } = useQuery({
    queryKey: ['control-center-settings', adminKey, useSessionAuth],
    queryFn: () => api.getSettings(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  })

  const { data: llmHealth, isLoading: llmLoading } = useQuery({
    queryKey: ['control-center-llm-health', adminKey, useSessionAuth],
    queryFn: () => api.getLLMProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  })

  const { data: mcpHealth, isLoading: mcpLoading } = useQuery({
    queryKey: ['control-center-mcp-health', adminKey, useSessionAuth],
    queryFn: () => api.getMCPProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  })

  const {
    data: auditEntries,
    isLoading: auditLoading,
    isError: isAuditError,
    error: auditError,
    refetch: refetchAudit,
  } = useQuery({
    queryKey: ['control-center-audit', adminKey, useSessionAuth],
    queryFn: () => api.getSettingsAudit(effectiveAdminKey, 25),
    enabled: hasAuthAttempt,
    retry: false,
  })

  const settingsErrorMessage = settingsError instanceof Error ? settingsError.message : 'Unknown error'
  const showSessionRefreshHint =
    useSessionAuth &&
    isSettingsError &&
    (() => {
      const normalized = settingsErrorMessage.toLowerCase()
      return (
        normalized.includes('invalid or missing admin api key') ||
        normalized.includes('invalid bearer token') ||
        normalized.includes('missing credentials')
      )
    })()

  const latestActivity = recentActivities?.[0]
  const latestRunUrl =
    latestActivity?.repository_name && latestActivity?.workflow_run_id
      ? `https://github.com/${latestActivity.repository_name}/actions/runs/${latestActivity.workflow_run_id}`
      : null

  const mcpToolRows = useMemo(() => {
    if (!settings) return []
    return TOOL_METADATA.map((tool) => {
      const raw = settings.mcp_tool_policies?.[tool.key]
      const policy: ToolPolicy =
        raw === 'disabled' || raw === 'auto' || raw === 'write_with_approval' ? raw : 'read_only'
      const effective = getEffectiveToolState({
        mcpEnabled: settings.mcp_enabled,
        provider: settings.mcp_provider,
        readOnly: settings.mcp_read_only,
        write: tool.write,
        policy,
      })
      return { ...tool, policy, effective }
    })
  }, [settings])

  const writeToolRows = mcpToolRows.filter((row) => row.write)
  const mcpWriteAutoCount = writeToolRows.filter((row) => row.effective.label === 'Allowed (Auto)').length
  const mcpWriteApprovalCount = writeToolRows.filter(
    (row) => row.effective.label === 'Approval Required'
  ).length
  const mcpWriteBlockedCount = writeToolRows.filter((row) => row.effective.label === 'Blocked').length

  const remediationPolicySummary = (() => {
    if (!settings) return 'N/A'
    if (!settings.auto_create_pr) return 'Issue-only path (automatic PR creation is disabled).'
    if (settings.heal_mode === 'safe') return 'Safe mode: conservative PR path with policy gating.'
    if (settings.heal_mode === 'demo') return 'Demo mode: aggressive automation for demonstrations.'
    return 'Debug mode: safe behavior with increased diagnostic verbosity.'
  })()

  const mcpWriteSummary = (() => {
    if (!settings) return 'N/A'
    if (!settings.mcp_enabled || settings.mcp_provider === 'disabled') {
      return 'MCP write actions are inactive (provider disabled).'
    }
    if (settings.mcp_read_only) return 'Global read-only mode blocks all MCP write actions.'
    if (mcpWriteAutoCount > 0) {
      return `${mcpWriteAutoCount} write action(s) can run automatically under current policy.`
    }
    if (mcpWriteApprovalCount > 0) {
      return `${mcpWriteApprovalCount} write action(s) require explicit approval.`
    }
    return `${mcpWriteBlockedCount} write action(s) are blocked by policy.`
  })()

  const logCommands = [
    'bash scripts/ph.sh logs',
    'bash scripts/ph.sh logs:grep --pattern "error|timeout|traceback"',
    'bash scripts/ph.sh settings:check',
    'bash scripts/ph.sh settings:audit --limit 10',
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-[var(--ph-text)]">
          <ShieldCheck className="h-6 w-6 text-azure-400" />
          Control Center
        </h1>
        <p className="text-sm text-[var(--ph-muted)]">
          Operational governance view for policy posture, provider readiness, audit traceability, and
          investigation access.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-azure-500" />
            <CardTitle>Admin Access</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3 sm:flex-row">
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
              disabled={!adminKeyInput.trim() || settingsLoading}
            >
              {settingsLoading ? 'Loading...' : 'Load with Admin Key'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setUseSessionAuth(true)
                setAdminKey('')
              }}
              disabled={settingsLoading}
            >
              {settingsLoading ? 'Loading...' : 'Use Login Session'}
            </Button>
          </div>
          <p className="mt-2 text-xs text-[var(--ph-muted)]">
            Read-only page. Use Settings for configuration changes, then return here for governance checks.
          </p>
        </CardContent>
      </Card>

      {!hasAuthAttempt && (
        <Card>
          <CardContent className="py-6 text-sm text-[var(--ph-muted)]">
            Provide admin access above to load policy posture, provider health, and audit records.
          </CardContent>
        </Card>
      )}

      {hasAuthAttempt && settingsLoading && (
        <Card>
          <CardContent className="space-y-3 py-6">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      )}

      {hasAuthAttempt && isSettingsError && (
        <Card className="border-rose-500/30">
          <CardContent className="py-6">
            <p className="text-sm font-medium text-rose-500">Failed to load Control Center</p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">{settingsErrorMessage}</p>
            {showSessionRefreshHint && (
              <p className="mt-3 text-xs text-[var(--ph-muted)]">
                Session may be stale. Try signing out, signing in again, or clearing site data and retrying.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {settings && (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Runtime Posture</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-[var(--ph-muted)]">
                <p>
                  Heal mode: <span className="font-medium text-[var(--ph-text)]">{settings.heal_mode}</span>
                </p>
                <p>
                  Auto-create PR: <span className="font-medium text-[var(--ph-text)]">{settings.auto_create_pr ? 'Yes' : 'No'}</span>
                </p>
                <p>
                  Max attempts:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.max_remediation_attempts}</span>
                </p>
                <p>
                  Repo allowlist:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.ph_allowed_repos.length}</span>
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Auth Posture</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-[var(--ph-muted)]">
                <p>
                  Auth mode: <span className="font-medium text-[var(--ph-text)]">{settings.auth_mode}</span>
                </p>
                <p>
                  Entra enabled:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.entra_auth_enabled ? 'Yes' : 'No'}</span>
                </p>
                <p>
                  Admin roles:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.entra_admin_roles.length}</span>
                </p>
                <p>
                  Admin API auth:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.admin_api_auth_enabled ? 'On' : 'Off'}</span>
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Provider Readiness</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-[var(--ph-muted)]">
                <p>
                  LLM: <span className="font-medium text-[var(--ph-text)]">{llmLoading ? 'Checking...' : llmHealth?.available ? 'Available' : 'Unavailable'}</span>
                </p>
                <p>
                  MCP: <span className="font-medium text-[var(--ph-text)]">{mcpLoading ? 'Checking...' : mcpHealth?.available ? 'Available' : 'Unavailable'}</span>
                </p>
                <p>
                  MCP provider:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.mcp_provider}</span>
                </p>
                <p>
                  MCP read-only:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.mcp_read_only ? 'Yes' : 'No'}</span>
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Ops Snapshot</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-[var(--ph-muted)]">
                <p>
                  Runs processed:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{statsLoading ? '...' : stats?.total_runs_processed ?? 0}</span>
                </p>
                <p>
                  Safety gated:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{statsLoading ? '...' : stats?.safety_blocked_remediations ?? 0}</span>
                </p>
                <p>
                  Diagnostics wait:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.external_diagnostics_wait_seconds}s</span>
                </p>
                <p>
                  Poll interval:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{settings.external_diagnostics_poll_interval_seconds}s</span>
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Policy Impact Preview</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                <p>
                  Remediation path:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{remediationPolicySummary}</span>
                </p>
                <p>
                  Diagnostics cadence:{' '}
                  <span className="font-medium text-[var(--ph-text)]">
                    wait {settings.external_diagnostics_wait_seconds}s / poll{' '}
                    {settings.external_diagnostics_poll_interval_seconds}s
                  </span>
                </p>
                <p>
                  MCP write posture:{' '}
                  <span className="font-medium text-[var(--ph-text)]">{mcpWriteSummary}</span>
                </p>
                <p>
                  Repo scope:{' '}
                  <span className="font-medium text-[var(--ph-text)]">
                    {settings.ph_allowed_repos.length === 0
                      ? 'All repositories (no allowlist)'
                      : `${settings.ph_allowed_repos.length} allowlisted repository entries`}
                  </span>
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Learning Queue (Next Phase)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                <p>
                  This phase remains governance-first. Human-approved learning workflow is planned after
                  model portability.
                </p>
                <p>
                  Planned states:{' '}
                  <span className="font-medium text-[var(--ph-text)]">
                    observed {'->'} candidate {'->'} approved {'->'} active
                  </span>
                </p>
                <div className="pt-1">
                  <Button asChild size="sm" variant="ghost">
                    <a
                      href="https://github.com/Canepro/pipelinehealer/blob/main/docs/FUTURE_PLAN.md"
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      Open roadmap details
                      <ExternalLink className="ml-1 h-3.5 w-3.5" />
                    </a>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Workflow className="h-4 w-4 text-azure-400" />
                  MCP Tool Policy Effect
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {mcpToolRows.map((row) => (
                  <div
                    key={row.key}
                    className="grid grid-cols-1 gap-1 rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/30 p-3 text-sm md:grid-cols-3"
                  >
                    <div className="font-medium text-[var(--ph-text)]">{row.label}</div>
                    <div className="text-[var(--ph-muted)]">Configured: {formatToolPolicy(row.policy)}</div>
                    <div className={`${toneClass(row.effective.tone)} font-medium`}>Effective: {row.effective.label}</div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <TerminalSquare className="h-4 w-4 text-azure-400" />
                  Logs & Investigation Access
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Button asChild size="sm" variant="secondary">
                    <a href={LOGS_RUNBOOK_URL} rel="noopener noreferrer" target="_blank">
                      Logs Runbook
                      <ExternalLink className="ml-1 h-3.5 w-3.5" />
                    </a>
                  </Button>
                  {latestRunUrl && (
                    <Button asChild size="sm" variant="ghost">
                      <a href={latestRunUrl} rel="noopener noreferrer" target="_blank">
                        Latest Workflow Run
                        <ExternalLink className="ml-1 h-3.5 w-3.5" />
                      </a>
                    </Button>
                  )}
                </div>

                <div className="space-y-2">
                  {logCommands.map((command) => (
                    <div
                      key={command}
                      className="flex items-center justify-between gap-2 rounded-md border border-[var(--ph-border)] bg-slate-900/30 px-3 py-2"
                    >
                      <code className="min-w-0 truncate text-xs text-slate-200" title={command}>
                        {command}
                      </code>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(command)
                            toast.success('Command copied')
                          } catch {
                            toast.error('Copy failed')
                          }
                        }}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>

                <div className="text-xs text-[var(--ph-muted)]">
                  UI log links are safe and read-only. Deep runtime/container log streaming is planned as a later
                  phase to avoid exposing infrastructure-specific credentials in-browser.
                </div>
              </CardContent>
            </Card>
          </div>

          <AuditTrailPanel
            canLoad={hasAuthAttempt}
            entries={auditEntries}
            isLoading={auditLoading}
            isError={isAuditError}
            error={isAuditError ? (auditError as Error) : null}
            onLoad={() => {
              void refetchAudit()
            }}
            title="Audit Timeline"
            description="Recent settings changes with actor and request trace. Use this as the primary governance feed."
            defaultVisibleCount={5}
            pageSize={5}
            defaultExpanded={true}
          />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <ScrollText className="h-4 w-4 text-azure-400" />
                Next Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <Link to="/app/settings">Open Settings</Link>
              </Button>
              <Button asChild size="sm" variant="secondary">
                <Link to="/app/activities">Review Activities</Link>
              </Button>
            </CardContent>
          </Card>
        </>
      )}

      {!settings && hasAuthAttempt && activitiesLoading && (
        <Card>
          <CardContent className="py-6">
            <Skeleton className="h-5 w-64" />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
