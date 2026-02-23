import { useState, type Dispatch, type SetStateAction } from 'react'
import {
  ChevronDown,
  HelpCircle,
  RotateCcw,
  Save,
  Settings2,
  Shield,
  Sparkles,
  Wrench,
  X,
  Zap,
} from 'lucide-react'
import { toast } from 'sonner'
import type { AppSettings, LLMProviderHealth, MCPProviderHealth } from '../../api/client'
import type { SettingsFormState } from './types'
import { normalizeRepoInput, SETTING_DESCRIPTIONS, toSettingsForm } from './types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface Props {
  data: AppSettings
  form: SettingsFormState
  setForm: Dispatch<SetStateAction<SettingsFormState>>
  llmProviderHealth?: LLMProviderHealth
  isLlmHealthLoading?: boolean
  mcpProviderHealth?: MCPProviderHealth
  isMcpHealthLoading?: boolean
  hasUnsavedChanges: boolean
  newRepoInput: string
  setNewRepoInput: Dispatch<SetStateAction<string>>
  newMcpRepoInput: string
  setNewMcpRepoInput: Dispatch<SetStateAction<string>>
  setGhAwWorkflowsInput: Dispatch<SetStateAction<string>>
  setLastSavedForm: Dispatch<SetStateAction<SettingsFormState | null>>
  savePending: boolean
  saveError: Error | null
  saveSuccess: boolean
  onSave: () => void
}

type SettingsSection = 'runtime' | 'intelligence' | 'security'
type McpPolicyMode = 'disabled' | 'read_only' | 'write_with_approval' | 'auto'
type McpEffectiveState = {
  status: 'allowed' | 'approval' | 'blocked' | 'inactive'
  summary: string
  detail: string
}
type McpToolDefinition = {
  key: 'fetch_failure_context' | 'fetch_runbook_context' | 'publish_artifact' | 'rerun_pipeline'
  label: string
  description: string
  write: boolean
}

const MCP_TOOL_DEFINITIONS: McpToolDefinition[] = [
  {
    key: 'fetch_failure_context',
    label: 'fetch_failure_context',
    description: 'Read failure/job context from provider APIs.',
    write: false,
  },
  {
    key: 'fetch_runbook_context',
    label: 'fetch_runbook_context',
    description: 'Read runbook and troubleshooting markdown context from repositories.',
    write: false,
  },
  {
    key: 'publish_artifact',
    label: 'publish_artifact',
    description: 'Publish issue/PR-like artifacts through provider tools.',
    write: true,
  },
  {
    key: 'rerun_pipeline',
    label: 'rerun_pipeline',
    description: 'Trigger pipeline/job reruns through provider tools.',
    write: true,
  },
]

function formatMcpPolicyLabel(policy: McpPolicyMode): string {
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

function getMcpEffectiveState({
  mcpEnabled,
  mcpProvider,
  readOnly,
  tool,
  policy,
}: {
  mcpEnabled: boolean
  mcpProvider: SettingsFormState['mcp_provider']
  readOnly: boolean
  tool: McpToolDefinition
  policy: McpPolicyMode
}): McpEffectiveState {
  if (!mcpEnabled || mcpProvider === 'disabled') {
    return {
      status: 'inactive',
      summary: 'Inactive',
      detail: 'MCP is disabled globally.',
    }
  }
  if (policy === 'disabled') {
    return {
      status: 'blocked',
      summary: 'Blocked',
      detail: 'Tool policy is disabled.',
    }
  }
  if (!tool.write) {
    return {
      status: 'allowed',
      summary: 'Allowed (Read)',
      detail: 'Read context fetch is allowed.',
    }
  }
  if (readOnly) {
    return {
      status: 'blocked',
      summary: 'Blocked',
      detail: 'Global read-only mode blocks write actions.',
    }
  }
  if (policy === 'read_only') {
    return {
      status: 'blocked',
      summary: 'Blocked',
      detail: 'Tool policy is read_only.',
    }
  }
  if (policy === 'write_with_approval') {
    return {
      status: 'approval',
      summary: 'Approval Required',
      detail: 'Write action needs explicit approval.',
    }
  }
  return {
    status: 'allowed',
    summary: 'Allowed (Auto)',
    detail: 'Write action may run automatically.',
  }
}

export default function AdminControlsForm({
  data,
  form,
  setForm,
  llmProviderHealth,
  isLlmHealthLoading,
  mcpProviderHealth,
  isMcpHealthLoading,
  hasUnsavedChanges,
  newRepoInput,
  setNewRepoInput,
  newMcpRepoInput,
  setNewMcpRepoInput,
  setGhAwWorkflowsInput,
  setLastSavedForm,
  savePending,
  saveError,
  saveSuccess,
  onSave,
}: Props) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [workflowInput, setWorkflowInput] = useState('')
  const [activeSection, setActiveSection] = useState<SettingsSection>('runtime')
  const mcpEffectivePolicies = MCP_TOOL_DEFINITIONS.map((tool) => {
    const raw = form.mcp_tool_policies[tool.key]
    const policy: McpPolicyMode =
      raw === 'disabled' || raw === 'auto' || raw === 'write_with_approval'
        ? raw
        : 'read_only'
    return {
      tool,
      policy,
      effective: getMcpEffectiveState({
        mcpEnabled: form.mcp_enabled,
        mcpProvider: form.mcp_provider,
        readOnly: form.mcp_read_only,
        tool,
        policy,
      }),
    }
  })
  const mcpAllowedCount = mcpEffectivePolicies.filter((row) => row.effective.status === 'allowed').length
  const mcpApprovalCount = mcpEffectivePolicies.filter((row) => row.effective.status === 'approval').length
  const mcpBlockedCount = mcpEffectivePolicies.filter((row) => row.effective.status === 'blocked').length
  const providerDefaultModel =
    form.llm_provider === 'azure_openai'
      ? form.azure_openai_deployment_name.trim()
      : form.openai_compatible_model.trim()
  const taskModelPreview = [
    { key: 'analysis', label: 'Analysis', override: form.llm_model_analysis.trim() },
    { key: 'diagnosis', label: 'Diagnosis', override: form.llm_model_diagnosis.trim() },
    { key: 'remediation', label: 'Remediation', override: form.llm_model_remediation.trim() },
  ]

  const addAllowedRepo = () => {
    const normalized = normalizeRepoInput(newRepoInput)
    if (!normalized) {
      toast.error('Invalid repository format', {
        description: "Use 'owner/repo' or 'https://github.com/owner/repo'.",
      })
      return
    }
    if (form.ph_allowed_repos.includes(normalized)) {
      toast.error('Repository already in allowlist')
      return
    }
    setForm((prev) => ({
      ...prev,
      ph_allowed_repos: [...prev.ph_allowed_repos, normalized],
    }))
    setNewRepoInput('')
  }

  const addMcpAllowedRepo = () => {
    const normalized = normalizeRepoInput(newMcpRepoInput)
    if (!normalized) {
      toast.error('Invalid repository format', {
        description: "Use 'owner/repo' or 'https://github.com/owner/repo'.",
      })
      return
    }
    if (form.mcp_repo_allowlist.includes(normalized)) {
      toast.error('Repository already in MCP allowlist')
      return
    }
    setForm((prev) => ({
      ...prev,
      mcp_repo_allowlist: [...prev.mcp_repo_allowlist, normalized],
    }))
    setNewMcpRepoInput('')
  }

  const addWorkflow = () => {
    const name = workflowInput.trim().toLowerCase()
    if (!name) return
    if (form.gh_aw_known_workflows.includes(name)) {
      toast.error('Workflow already in list')
      return
    }
    const next = [...form.gh_aw_known_workflows, name]
    setForm((prev) => ({ ...prev, gh_aw_known_workflows: next }))
    setGhAwWorkflowsInput(next.join(','))
    setWorkflowInput('')
  }

  const removeWorkflow = (name: string) => {
    const next = form.gh_aw_known_workflows.filter((w) => w !== name)
    setForm((prev) => ({ ...prev, gh_aw_known_workflows: next }))
    setGhAwWorkflowsInput(next.join(','))
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-8">
        <Card>
          <CardContent className="py-5">
            <Tabs
              value={activeSection}
              onValueChange={(value) => setActiveSection(value as SettingsSection)}
              className="w-full"
            >
              <TabsList className="grid h-auto w-full grid-cols-1 gap-1 rounded-xl border border-[var(--ph-border)] bg-slate-800/20 p-1 sm:grid-cols-3">
                <TabsTrigger
                  value="runtime"
                  className="flex items-center justify-center gap-2 py-3 text-sm font-semibold text-slate-300 data-[state=active]:bg-azure-600 data-[state=active]:text-white data-[state=active]:shadow-sm data-[state=active]:ring-1 data-[state=active]:ring-azure-300/40"
                >
                  <Zap className="h-4 w-4" />
                  1. Runtime Controls
                </TabsTrigger>
                <TabsTrigger
                  value="intelligence"
                  className="flex items-center justify-center gap-2 py-3 text-sm font-semibold text-slate-300 data-[state=active]:bg-azure-600 data-[state=active]:text-white data-[state=active]:shadow-sm data-[state=active]:ring-1 data-[state=active]:ring-azure-300/40"
                >
                  <Sparkles className="h-4 w-4" />
                  2. AI & Integrations
                </TabsTrigger>
                <TabsTrigger
                  value="security"
                  className="flex items-center justify-center gap-2 py-3 text-sm font-semibold text-slate-300 data-[state=active]:bg-azure-600 data-[state=active]:text-white data-[state=active]:shadow-sm data-[state=active]:ring-1 data-[state=active]:ring-azure-300/40"
                >
                  <Shield className="h-4 w-4" />
                  3. Security & Advanced
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <p className="mt-3 text-sm text-[var(--ph-muted)]">
              {activeSection === 'runtime' &&
                'Runtime Controls: set remediation behavior, repo scope, and operation mode first.'}
              {activeSection === 'intelligence' &&
                'AI & Integrations: configure model providers, external diagnostics, and MCP policies.'}
              {activeSection === 'security' &&
                'Security & Advanced: adjust auth posture, retries, limits, and low-level safeguards.'}
            </p>
          </CardContent>
        </Card>

        {/* ── Section 1: Healing Behavior ── */}
        {activeSection === 'runtime' && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-azure-500" />
                <CardTitle>Healing Behavior</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                Controls how PipelineHealer responds to CI failures.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup label="Heal Mode" field="heal_mode">
                  <Select
                    value={form.heal_mode}
                    onValueChange={(v) =>
                      setForm((prev) => ({
                        ...prev,
                        heal_mode: v as SettingsFormState['heal_mode'],
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="safe">Safe — Conservative fixes</SelectItem>
                      <SelectItem value="demo">Demo — Aggressive for demonstrations</SelectItem>
                      <SelectItem value="freestyle">
                        Freestyle — Aggressive open-ended automation
                      </SelectItem>
                      <SelectItem value="debug">Debug — Safe + verbose logging</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>

                <FieldGroup label="Max Remediation Attempts" field="max_remediation_attempts">
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    value={form.max_remediation_attempts}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, max_remediation_attempts: Number(e.target.value) }))
                    }
                  />
                </FieldGroup>
              </div>

              <Separator />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <SwitchField
                  label="Auto-Apply Remediation"
                  field="auto_apply_remediation"
                  checked={form.auto_apply_remediation}
                  onChange={(v) => setForm((p) => ({ ...p, auto_apply_remediation: v }))}
                />
                <SwitchField
                  label="Auto-Create Pull Requests"
                  field="auto_create_pr"
                  checked={form.auto_create_pr}
                  onChange={(v) => setForm((p) => ({ ...p, auto_create_pr: v }))}
                />
                <SwitchField
                  label="Auto-Create Issues"
                  field="auto_create_issue"
                  checked={form.auto_create_issue}
                  onChange={(v) => setForm((p) => ({ ...p, auto_create_issue: v }))}
                />
                <SwitchField
                  label="Auto-Retry Workflows"
                  field="auto_retry_workflow"
                  checked={form.auto_retry_workflow}
                  onChange={(v) => setForm((p) => ({ ...p, auto_retry_workflow: v }))}
                />
                <SwitchField
                  label="Auto-Create Tracking Issues"
                  field="auto_create_tracking_issue_for_prs"
                  checked={form.auto_create_tracking_issue_for_prs}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, auto_create_tracking_issue_for_prs: v }))
                  }
                />
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Section 2: AI Configuration ── */}
        {activeSection === 'intelligence' && (
          <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-azure-500" />
              <CardTitle>AI Configuration</CardTitle>
            </div>
            <p className="text-sm text-[var(--ph-muted)]">
              Configure model provider and deployment for log analysis and diagnosis.
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <FieldGroup label="LLM Provider" field="llm_provider">
                <Select
                  value={form.llm_provider}
                  onValueChange={(v) =>
                    setForm((prev) => ({
                      ...prev,
                      llm_provider: v as SettingsFormState['llm_provider'],
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select provider" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="azure_openai">azure_openai (recommended)</SelectItem>
                    <SelectItem value="openai_compatible">openai_compatible (scaffold)</SelectItem>
                    <SelectItem value="custom">custom (scaffold)</SelectItem>
                  </SelectContent>
                </Select>
              </FieldGroup>
              <FieldGroup
                label={form.llm_provider === 'azure_openai' ? 'Model Deployment Name' : 'Model Name'}
                field={
                  form.llm_provider === 'azure_openai'
                    ? 'azure_openai_deployment_name'
                    : 'openai_compatible_model'
                }
              >
                <Input
                  type="text"
                  value={
                    form.llm_provider === 'azure_openai'
                      ? form.azure_openai_deployment_name
                      : form.openai_compatible_model
                  }
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      ...(form.llm_provider === 'azure_openai'
                        ? { azure_openai_deployment_name: e.target.value }
                        : { openai_compatible_model: e.target.value }),
                    }))
                  }
                  placeholder={
                    form.llm_provider === 'azure_openai'
                      ? 'e.g. gpt-4o, gpt-5-mini'
                      : 'e.g. gpt-4o-mini, claude-compatible-model'
                  }
                />
              </FieldGroup>
              {form.llm_provider === 'azure_openai' ? (
                <div className="space-y-1.5">
                  <Label className="text-[var(--ph-muted)]">Endpoint</Label>
                  <p className="text-sm font-medium text-[var(--ph-text)] break-words py-2 font-mono leading-relaxed">
                    {data.azure_openai_endpoint || (
                      <span className="text-[var(--ph-muted)] italic">Not configured</span>
                    )}
                  </p>
                </div>
              ) : (
                <FieldGroup label="Provider Base URL" field="openai_compatible_base_url">
                  <Input
                    type="text"
                    value={form.openai_compatible_base_url}
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        openai_compatible_base_url: e.target.value,
                      }))
                    }
                    placeholder="https://api.openai.com/v1"
                  />
                </FieldGroup>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <ReadOnlyField label="API Version" value={data.azure_openai_api_version} />
              <ReadOnlyField label="Chat API Version" value={data.azure_openai_chat_api_version} />
            </div>
            {form.llm_provider === 'openai_compatible' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <ReadOnlyField
                  label="OpenAI-Compatible Key"
                  value={data.openai_compatible_api_key_configured ? 'Configured' : 'Not configured'}
                />
                <ReadOnlyField
                  label="Provider Endpoint"
                  value={data.openai_compatible_base_url || 'Not configured'}
                />
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <ReadOnlyField
                label="Provider Health"
                value={
                  isLlmHealthLoading
                    ? 'Checking...'
                    : llmProviderHealth
                      ? `${llmProviderHealth.available ? 'Available' : 'Unavailable'} (${llmProviderHealth.reason})`
                      : 'Unavailable'
                }
              />
              <ReadOnlyField
                label="Provider Status"
                value={
                  llmProviderHealth
                    ? llmProviderHealth.implemented
                      ? 'Implemented'
                      : 'Scaffolded only'
                    : 'Unknown'
                }
              />
            </div>
            <Separator />
            <div className="space-y-3">
              <p className="text-sm font-medium text-[var(--ph-text)]">
                Task Model Routing (Optional Overrides)
              </p>
              <p className="text-xs text-[var(--ph-muted)]">
                Leave blank to use the provider default model/deployment.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <FieldGroup label="Analysis Model" field="llm_model_analysis">
                  <Input
                    type="text"
                    value={form.llm_model_analysis}
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        llm_model_analysis: e.target.value,
                      }))
                    }
                    placeholder={providerDefaultModel || 'Uses provider default'}
                  />
                </FieldGroup>
                <FieldGroup label="Diagnosis Model" field="llm_model_diagnosis">
                  <Input
                    type="text"
                    value={form.llm_model_diagnosis}
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        llm_model_diagnosis: e.target.value,
                      }))
                    }
                    placeholder={providerDefaultModel || 'Uses provider default'}
                  />
                </FieldGroup>
                <FieldGroup label="Remediation Model" field="llm_model_remediation">
                  <Input
                    type="text"
                    value={form.llm_model_remediation}
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        llm_model_remediation: e.target.value,
                      }))
                    }
                    placeholder={providerDefaultModel || 'Uses provider default'}
                  />
                </FieldGroup>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                {taskModelPreview.map((task) => (
                  <ReadOnlyField
                    key={task.key}
                    label={`Effective ${task.label}`}
                    value={task.override || providerDefaultModel || 'Not configured'}
                  />
                ))}
              </div>
            </div>
          </CardContent>
          </Card>
        )}

        {/* ── Section 3: MCP Integration (preview) ── */}
        {activeSection === 'intelligence' && (
          <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Wrench className="h-5 w-5 text-azure-500" />
              <CardTitle>MCP Integration (Preview)</CardTitle>
            </div>
            <p className="text-sm text-[var(--ph-muted)]">
              Foundation controls for provider-agnostic MCP tool integration.
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <SwitchField
                label="Enable MCP"
                field="mcp_enabled"
                checked={form.mcp_enabled}
                onChange={(v) => setForm((p) => ({ ...p, mcp_enabled: v }))}
              />
              <SwitchField
                label="Read-Only Mode"
                field="mcp_read_only"
                checked={form.mcp_read_only}
                onChange={(v) => setForm((p) => ({ ...p, mcp_read_only: v }))}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <FieldGroup label="MCP Provider" field="mcp_provider">
                <Select
                  value={form.mcp_provider}
                  onValueChange={(v) =>
                    setForm((prev) => ({
                      ...prev,
                      mcp_provider: v as SettingsFormState['mcp_provider'],
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="disabled">disabled</SelectItem>
                    <SelectItem value="github">github (recommended first)</SelectItem>
                    <SelectItem value="azure_monitor">azure_monitor (scaffold)</SelectItem>
                    <SelectItem value="custom">custom (scaffold)</SelectItem>
                  </SelectContent>
                </Select>
              </FieldGroup>
              <FieldGroup label="Timeout (seconds)" field="mcp_timeout_seconds">
                <Input
                  type="number"
                  min={1}
                  max={120}
                  step={0.5}
                  value={form.mcp_timeout_seconds}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, mcp_timeout_seconds: Number(e.target.value) }))
                  }
                />
              </FieldGroup>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <FieldGroup label="Max Retries" field="mcp_max_retries">
                <Input
                  type="number"
                  min={0}
                  max={10}
                  value={form.mcp_max_retries}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, mcp_max_retries: Number(e.target.value) }))
                  }
                />
              </FieldGroup>
              <ReadOnlyField
                label="MCP Provider Health"
                value={
                  isMcpHealthLoading
                    ? 'Checking...'
                    : mcpProviderHealth
                      ? `${mcpProviderHealth.available ? 'Available' : 'Unavailable'} (${mcpProviderHealth.reason})`
                      : 'Unavailable'
                }
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
              <StatusChip label="Allowed Actions" value={String(mcpAllowedCount)} ok={mcpAllowedCount > 0} />
              <StatusChip label="Approval Needed" value={String(mcpApprovalCount)} ok={mcpApprovalCount > 0} />
              <StatusChip label="Blocked Actions" value={String(mcpBlockedCount)} ok={mcpBlockedCount === 0 ? true : false} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
              <FieldGroup label="Policy: fetch_failure_context" field="mcp_tool_policies">
                <Select
                  value={form.mcp_tool_policies.fetch_failure_context}
                  onValueChange={(value) =>
                    setForm((prev) => ({
                      ...prev,
                      mcp_tool_policies: {
                        ...prev.mcp_tool_policies,
                        fetch_failure_context: value as
                          | 'disabled'
                          | 'read_only'
                          | 'write_with_approval'
                          | 'auto',
                      },
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="disabled">disabled</SelectItem>
                    <SelectItem value="read_only">read_only</SelectItem>
                    <SelectItem value="write_with_approval">write_with_approval</SelectItem>
                    <SelectItem value="auto">auto</SelectItem>
                  </SelectContent>
                </Select>
              </FieldGroup>
              <FieldGroup label="Policy: fetch_runbook_context" field="mcp_tool_policies">
                <Select
                  value={form.mcp_tool_policies.fetch_runbook_context}
                  onValueChange={(value) =>
                    setForm((prev) => ({
                      ...prev,
                      mcp_tool_policies: {
                        ...prev.mcp_tool_policies,
                        fetch_runbook_context: value as
                          | 'disabled'
                          | 'read_only'
                          | 'write_with_approval'
                          | 'auto',
                      },
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="disabled">disabled</SelectItem>
                    <SelectItem value="read_only">read_only</SelectItem>
                    <SelectItem value="write_with_approval">write_with_approval</SelectItem>
                    <SelectItem value="auto">auto</SelectItem>
                  </SelectContent>
                </Select>
              </FieldGroup>
              <FieldGroup label="Policy: publish_artifact" field="mcp_tool_policies">
                <Select
                  value={form.mcp_tool_policies.publish_artifact}
                  onValueChange={(value) =>
                    setForm((prev) => ({
                      ...prev,
                      mcp_tool_policies: {
                        ...prev.mcp_tool_policies,
                        publish_artifact: value as
                          | 'disabled'
                          | 'read_only'
                          | 'write_with_approval'
                          | 'auto',
                      },
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="disabled">disabled</SelectItem>
                    <SelectItem value="read_only">read_only</SelectItem>
                    <SelectItem value="write_with_approval">write_with_approval</SelectItem>
                    <SelectItem value="auto">auto</SelectItem>
                  </SelectContent>
                </Select>
              </FieldGroup>
              <FieldGroup label="Policy: rerun_pipeline" field="mcp_tool_policies">
                <Select
                  value={form.mcp_tool_policies.rerun_pipeline}
                  onValueChange={(value) =>
                    setForm((prev) => ({
                      ...prev,
                      mcp_tool_policies: {
                        ...prev.mcp_tool_policies,
                        rerun_pipeline: value as
                          | 'disabled'
                          | 'read_only'
                          | 'write_with_approval'
                          | 'auto',
                      },
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="disabled">disabled</SelectItem>
                    <SelectItem value="read_only">read_only</SelectItem>
                    <SelectItem value="write_with_approval">write_with_approval</SelectItem>
                    <SelectItem value="auto">auto</SelectItem>
                  </SelectContent>
                </Select>
              </FieldGroup>
            </div>
            <div className="space-y-3">
              <Label className="text-[var(--ph-text)]">Effective Tool Actions</Label>
              <p className="text-xs text-[var(--ph-muted)]">
                This view combines global MCP toggles and per-tool policy to show what will happen at runtime.
              </p>
              <div className="space-y-2">
                {mcpEffectivePolicies.map(({ tool, policy, effective }) => (
                  <div
                    key={tool.key}
                    className="rounded-md border border-gray-200 dark:border-gray-700 bg-white/60 dark:bg-gray-900/40 px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="font-mono text-xs text-[var(--ph-text)]">{tool.label}</p>
                        <p className="text-xs text-[var(--ph-muted)]">{tool.description}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{formatMcpPolicyLabel(policy)}</Badge>
                        <Badge
                          variant={
                            effective.status === 'allowed'
                              ? 'success'
                              : effective.status === 'approval'
                                ? 'secondary'
                                : effective.status === 'inactive'
                                  ? 'outline'
                                  : 'destructive'
                          }
                        >
                          {effective.summary}
                        </Badge>
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-[var(--ph-muted)]">{effective.detail}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <span className="text-[var(--ph-muted)]">MCP repo allowlist:</span>
                {form.mcp_repo_allowlist.length > 0 ? (
                  <span className="font-medium text-[var(--ph-text)]">
                    {form.mcp_repo_allowlist.length} repo
                    {form.mcp_repo_allowlist.length !== 1 ? 's' : ''}
                  </span>
                ) : (
                  <Badge variant="outline">Fallback to PH allowlist</Badge>
                )}
              </div>
              <div className="flex flex-wrap gap-2 min-h-[2rem]">
                {form.mcp_repo_allowlist.length === 0 && (
                  <span className="text-sm text-[var(--ph-muted)] italic py-1">
                    Empty list means MCP uses PH_ALLOWED_REPOS fallback.
                  </span>
                )}
                {form.mcp_repo_allowlist.map((repo) => (
                  <Badge key={repo} variant="secondary" className="gap-1 pr-1">
                    {repo}
                    <button
                      type="button"
                      className="ml-1 rounded-full p-0.5 hover:bg-gray-300 dark:hover:bg-gray-500 transition-colors"
                      onClick={() =>
                        setForm((prev) => ({
                          ...prev,
                          mcp_repo_allowlist: prev.mcp_repo_allowlist.filter((r) => r !== repo),
                        }))
                      }
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="owner/repo or https://github.com/owner/repo"
                  value={newMcpRepoInput}
                  onChange={(e) => setNewMcpRepoInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addMcpAllowedRepo()
                    }
                  }}
                  className="max-w-md"
                />
                <Button type="button" variant="secondary" size="sm" onClick={addMcpAllowedRepo}>
                  Add
                </Button>
              </div>
            </div>
            {mcpProviderHealth?.configured_tools?.length ? (
              <div className="space-y-1">
                <Label className="text-[var(--ph-muted)]">Configured Tools</Label>
                <div className="flex flex-wrap gap-2">
                  {mcpProviderHealth.configured_tools.map((tool) => (
                    <Badge key={tool} variant="secondary" className="font-mono text-xs">
                      {tool}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
          </Card>
        )}

        {/* ── Section 4: Repository Scope ── */}
        {activeSection === 'runtime' && (
          <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-azure-500" />
              <CardTitle>Repository Scope</CardTitle>
            </div>
            <p className="text-sm text-[var(--ph-muted)]">
              {SETTING_DESCRIPTIONS.ph_allowed_repos}
            </p>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex items-center gap-3 text-sm">
              <span className="text-[var(--ph-muted)]">Effective now:</span>
              {data.ph_allowed_repos.length > 0 ? (
                <span className="font-medium text-[var(--ph-text)]">
                  {data.ph_allowed_repos.length} repo{data.ph_allowed_repos.length !== 1 ? 's' : ''}
                </span>
              ) : (
                <Badge variant="outline">All repositories (unrestricted)</Badge>
              )}
            </div>

            <div className="flex flex-wrap gap-2 min-h-[2rem]">
              {form.ph_allowed_repos.length === 0 && (
                <span className="text-sm text-[var(--ph-muted)] italic py-1">
                  No restrictions — all repositories are processed
                </span>
              )}
              {form.ph_allowed_repos.map((repo) => (
                <Badge key={repo} variant="secondary" className="gap-1 pr-1">
                  {repo}
                  <button
                    type="button"
                    className="ml-1 rounded-full p-0.5 hover:bg-gray-300 dark:hover:bg-gray-500 transition-colors"
                    onClick={() =>
                      setForm((prev) => ({
                        ...prev,
                        ph_allowed_repos: prev.ph_allowed_repos.filter((r) => r !== repo),
                      }))
                    }
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>

            <div className="flex gap-2">
              <Input
                placeholder="owner/repo or https://github.com/owner/repo"
                value={newRepoInput}
                onChange={(e) => setNewRepoInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addAllowedRepo()
                  }
                }}
                className="max-w-md"
              />
              <Button type="button" variant="secondary" size="sm" onClick={addAllowedRepo}>
                Add
              </Button>
            </div>
          </CardContent>
          </Card>
        )}

        {/* ── Section 5: External Diagnostics (gh-aw) ── */}
        {activeSection === 'intelligence' && (
          <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Wrench className="h-5 w-5 text-azure-500" />
              <CardTitle>External Diagnostics</CardTitle>
            </div>
            <p className="text-sm text-[var(--ph-muted)]">
              GitHub Agentic Workflows integration for enhanced CI failure analysis.
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <SwitchField
                label="Enable External Diagnostics"
                field="gh_aw_tools_enabled"
                checked={form.gh_aw_tools_enabled}
                onChange={(v) => setForm((p) => ({ ...p, gh_aw_tools_enabled: v }))}
              />

              <FieldGroup label="Ingestion Mode" field="gh_aw_ingestion_mode">
                <Select
                  value={form.gh_aw_ingestion_mode}
                  onValueChange={(v) =>
                    setForm((prev) => ({
                      ...prev,
                      gh_aw_ingestion_mode: v as SettingsFormState['gh_aw_ingestion_mode'],
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="disabled">Disabled</SelectItem>
                    <SelectItem value="passive">Passive — Read from GitHub Issues</SelectItem>
                    <SelectItem value="hybrid">Hybrid — GH-AW + GitHub MCP</SelectItem>
                  </SelectContent>
                </Select>
              </FieldGroup>
            </div>

            <Separator />

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Label className="text-[var(--ph-text)]">CI-Doctor Skip List</Label>
                <InfoTip text={SETTING_DESCRIPTIONS.gh_aw_known_workflows} />
              </div>
              <p className="text-xs text-[var(--ph-muted)]">
                Workflows listed here will not be polled by ci-doctor (prevents circular
                self-diagnosis). ci-doctor itself should always be in this list.
              </p>

              <div className="flex flex-wrap gap-2 min-h-[2rem]">
                {form.gh_aw_known_workflows.length === 0 && (
                  <span className="text-sm text-[var(--ph-muted)] italic py-1">
                    No skip list — ci-doctor will poll for all workflows
                  </span>
                )}
                {form.gh_aw_known_workflows.map((wf) => (
                  <Badge key={wf} variant="secondary" className="gap-1 pr-1 font-mono text-xs">
                    {wf}
                    <button
                      type="button"
                      className="ml-1 rounded-full p-0.5 hover:bg-gray-300 dark:hover:bg-gray-500 transition-colors"
                      onClick={() => removeWorkflow(wf)}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>

              <div className="flex gap-2">
                <Input
                  placeholder="workflow-name"
                  value={workflowInput}
                  onChange={(e) => setWorkflowInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addWorkflow()
                    }
                  }}
                  className="max-w-xs font-mono text-sm"
                />
                <Button type="button" variant="secondary" size="sm" onClick={addWorkflow}>
                  Add
                </Button>
              </div>
            </div>

            {/* Read-only status summary */}
            <Separator />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <StatusChip label="Auth Mode" value={data.github_auth_mode} />
              <StatusChip label="PAT" value={data.github_pat_configured ? 'Configured' : 'Not set'} ok={data.github_pat_configured} />
              <StatusChip label="GitHub App" value={data.github_app_configured ? 'Configured' : 'Not set'} ok={data.github_app_configured} />
              <StatusChip label="gh-aw" value={data.gh_aw_tools_enabled ? 'Active' : 'Off'} ok={data.gh_aw_tools_enabled} />
            </div>
          </CardContent>
          </Card>
        )}

        {/* ── Section 6: Security ── */}
        {activeSection === 'security' && (
          <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-azure-500" />
              <CardTitle>Security</CardTitle>
            </div>
            <p className="text-sm text-[var(--ph-muted)]">
              Authentication and webhook verification status.
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <StatusChip label="API Auth" value={data.api_auth_enabled ? 'Enabled' : 'Disabled'} ok={data.api_auth_enabled} />
              <StatusChip label="Admin Auth" value={data.admin_api_auth_enabled ? 'Enabled' : 'Disabled'} ok={data.admin_api_auth_enabled} />
              <StatusChip label="Webhook Sig" value={data.verify_webhook_signature ? 'Required' : 'Off'} ok={data.verify_webhook_signature} />
              <StatusChip label="Environment" value={data.environment} />
            </div>

            <Separator />

            <SwitchField
              label="Verify Webhook Signature in Development"
              field="verify_webhook_signature_in_development"
              checked={form.verify_webhook_signature_in_development}
              onChange={(v) =>
                setForm((p) => ({ ...p, verify_webhook_signature_in_development: v }))
              }
            />

            {/* CORS read-only */}
            <Separator />
            <div className="space-y-2">
              <Label className="text-[var(--ph-muted)]">CORS Allowed Origins</Label>
              <div className="flex flex-wrap gap-2">
                {data.cors_allowed_origins.map((origin) => (
                  <Badge key={origin} variant="outline" className="font-mono text-xs">
                    {origin}
                  </Badge>
                ))}
              </div>
              {data.cors_allow_origin_regex && (
                <p className="text-xs text-[var(--ph-muted)]">
                  Regex: <code className="font-mono">{data.cors_allow_origin_regex}</code>
                </p>
              )}
            </div>
          </CardContent>
          </Card>
        )}

        {/* ── Section 7: Advanced (collapsed by default) ── */}
        {activeSection === 'security' && (
          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <Card>
              <CollapsibleTrigger asChild>
                <CardHeader className="cursor-pointer select-none hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition-colors rounded-t-xl pb-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Settings2 className="h-5 w-5 text-azure-500" />
                      <CardTitle>Advanced</CardTitle>
                    </div>
                    <ChevronDown
                      className={`h-5 w-5 text-[var(--ph-muted)] transition-transform duration-200 ${advancedOpen ? 'rotate-180' : ''}`}
                    />
                  </div>
                  <p className="text-sm text-[var(--ph-muted)]">
                    Pipeline timeouts, retry policies, and log prompt tuning. Usually safe to leave
                    at defaults.
                  </p>
                </CardHeader>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <CardContent className="space-y-5 pt-0">
                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">Pipeline Timeouts</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <FieldGroup label="Step Timeout (seconds)" field="pipeline_step_timeout_seconds">
                      <Input
                        type="number"
                        min={1}
                        max={600}
                        value={form.pipeline_step_timeout_seconds}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            pipeline_step_timeout_seconds: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                  </div>

                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">
                    GitHub API Retry Policy
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <FieldGroup label="Max Retries" field="github_api_max_retries">
                      <Input
                        type="number"
                        min={0}
                        max={10}
                        value={form.github_api_max_retries}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            github_api_max_retries: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup label="Retry Base (seconds)" field="github_api_retry_base_seconds">
                      <Input
                        type="number"
                        min={0.1}
                        max={30}
                        step={0.1}
                        value={form.github_api_retry_base_seconds}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            github_api_retry_base_seconds: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup label="Retry Max (seconds)" field="github_api_retry_max_seconds">
                      <Input
                        type="number"
                        min={0.1}
                        max={120}
                        step={0.1}
                        value={form.github_api_retry_max_seconds}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            github_api_retry_max_seconds: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                  </div>

                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">Log Prompt Tuning</h4>
                  <p className="text-xs text-[var(--ph-muted)]">
                    Controls how much of the CI log is sent to the AI model. Larger values give
                    more context but cost more tokens.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <FieldGroup label="Max Total Chars" field="log_prompt_max_chars">
                      <Input
                        type="number"
                        min={1000}
                        max={200000}
                        value={form.log_prompt_max_chars}
                        onChange={(e) =>
                          setForm((p) => ({ ...p, log_prompt_max_chars: Number(e.target.value) }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup label="Head Chars (start of log)" field="log_prompt_head_chars">
                      <Input
                        type="number"
                        min={100}
                        max={200000}
                        value={form.log_prompt_head_chars}
                        onChange={(e) =>
                          setForm((p) => ({ ...p, log_prompt_head_chars: Number(e.target.value) }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup label="Tail Chars (end of log)" field="log_prompt_tail_chars">
                      <Input
                        type="number"
                        min={100}
                        max={200000}
                        value={form.log_prompt_tail_chars}
                        onChange={(e) =>
                          setForm((p) => ({ ...p, log_prompt_tail_chars: Number(e.target.value) }))
                        }
                      />
                    </FieldGroup>
                  </div>

                  {form.log_prompt_head_chars + form.log_prompt_tail_chars >
                    form.log_prompt_max_chars && (
                    <p className="text-sm text-rose-500 dark:text-rose-400">
                      Head + tail chars ({form.log_prompt_head_chars + form.log_prompt_tail_chars})
                      exceeds max ({form.log_prompt_max_chars}). The log will be over-truncated.
                    </p>
                  )}

                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">Runtime Info</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <StatusChip label="Environment" value={data.environment} />
                    <StatusChip label="Storage" value={data.storage_backend} />
                    <StatusChip label="Heal Mode" value={data.heal_mode} />
                    <StatusChip
                      label="Max Attempts"
                      value={String(data.max_remediation_attempts)}
                    />
                  </div>
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>
        )}

        {/* ── Save / Discard Bar ── */}
        <Card>
          <CardContent className="py-4 px-6">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <Badge variant={hasUnsavedChanges ? 'destructive' : 'success'}>
                  {hasUnsavedChanges ? 'Unsaved changes' : 'In sync'}
                </Badge>
                {saveError && (
                  <span className="text-sm text-rose-500">
                    {saveError.message || 'Failed to save'}
                  </span>
                )}
                {saveSuccess && !hasUnsavedChanges && (
                  <span className="text-sm text-emerald-500">Settings saved</span>
                )}
              </div>

              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={savePending || !hasUnsavedChanges || !data}
                  onClick={() => {
                    const reset = toSettingsForm(data)
                    setForm(reset)
                    setLastSavedForm(reset)
                    setNewRepoInput('')
                    setGhAwWorkflowsInput(reset.gh_aw_known_workflows.join(','))
                  }}
                >
                  <RotateCcw className="h-4 w-4" />
                  Discard
                </Button>
                <Button
                  disabled={
                    savePending ||
                    !hasUnsavedChanges ||
                    form.log_prompt_head_chars + form.log_prompt_tail_chars >
                      form.log_prompt_max_chars
                  }
                  onClick={onSave}
                >
                  <Save className="h-4 w-4" />
                  {savePending ? 'Saving...' : 'Save & Persist'}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  )
}

/* ── Presentational helpers ── */

function InfoTip({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <HelpCircle className="h-3.5 w-3.5 text-[var(--ph-muted)] cursor-help" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs">
        {text}
      </TooltipContent>
    </Tooltip>
  )
}

function FieldGroup({
  label,
  field,
  children,
}: {
  label: string
  field: string
  children: React.ReactNode
}) {
  const desc = SETTING_DESCRIPTIONS[field]
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label className="text-[var(--ph-text)]">{label}</Label>
        {desc && <InfoTip text={desc} />}
      </div>
      {children}
    </div>
  )
}

function SwitchField({
  label,
  field,
  checked,
  onChange,
}: {
  label: string
  field: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  const desc = SETTING_DESCRIPTIONS[field]
  return (
    <div className="flex items-start gap-3 py-1">
      <Switch checked={checked} onCheckedChange={onChange} className="mt-0.5" />
      <div>
        <Label className="text-[var(--ph-text)] cursor-pointer" onClick={() => onChange(!checked)}>
          {label}
        </Label>
        {desc && <p className="text-xs text-[var(--ph-muted)] mt-0.5">{desc}</p>}
      </div>
    </div>
  )
}

function ReadOnlyField({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[var(--ph-muted)]">{label}</Label>
      <p className="text-sm font-medium text-[var(--ph-text)] py-2">
        {value || <span className="text-[var(--ph-muted)] italic">Not set</span>}
      </p>
    </div>
  )
}

function StatusChip({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-[var(--ph-muted)]">{label}</p>
      <Badge variant={ok === undefined ? 'outline' : ok ? 'success' : 'destructive'}>
        {value}
      </Badge>
    </div>
  )
}
