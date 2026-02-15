import type { Dispatch, SetStateAction } from 'react'
import { RotateCcw, Save } from 'lucide-react'
import { toast } from 'sonner'
import type { AppSettings } from '../../api/client'
import type { SettingsFormState } from './types'
import { normalizeRepoInput, toSettingsForm } from './types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'

interface Props {
  data: AppSettings
  form: SettingsFormState
  setForm: Dispatch<SetStateAction<SettingsFormState>>
  hasUnsavedChanges: boolean
  newRepoInput: string
  setNewRepoInput: Dispatch<SetStateAction<string>>
  ghAwWorkflowsInput: string
  setGhAwWorkflowsInput: Dispatch<SetStateAction<string>>
  setLastSavedForm: Dispatch<SetStateAction<SettingsFormState | null>>
  savePending: boolean
  saveError: Error | null
  saveSuccess: boolean
  onSave: () => void
}

export default function AdminControlsForm({
  data,
  form,
  setForm,
  hasUnsavedChanges,
  newRepoInput,
  setNewRepoInput,
  ghAwWorkflowsInput,
  setGhAwWorkflowsInput,
  setLastSavedForm,
  savePending,
  saveError,
  saveSuccess,
  onSave,
}: Props) {
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

  return (
    <div className="card p-4 md:p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        Admin Controls
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-sm">
        {/* Heal mode */}
        <label className="space-y-1">
          <span className="text-gray-500 dark:text-gray-400">Heal mode</span>
          <select
            value={form.heal_mode}
            onChange={(e) => {
              const v = e.target.value
              setForm((prev) => ({
                ...prev,
                heal_mode: v === 'demo' ? 'demo' : v === 'debug' ? 'debug' : 'safe',
              }))
            }}
            className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
          >
            <option value="safe">safe</option>
            <option value="demo">demo</option>
            <option value="debug">debug</option>
          </select>
        </label>

        <NumberField label="Max remediation attempts" min={1} max={50} value={form.max_remediation_attempts} onChange={(v) => setForm((p) => ({ ...p, max_remediation_attempts: v }))} />

        <label className="space-y-1">
          <span className="text-gray-500 dark:text-gray-400">AI deployment name</span>
          <Input
            type="text"
            value={form.azure_openai_deployment_name}
            onChange={(e) => setForm((prev) => ({ ...prev, azure_openai_deployment_name: e.target.value }))}
            placeholder="gpt-5-mini"
          />
        </label>

        <NumberField label="Pipeline step timeout (s)" min={1} max={600} value={form.pipeline_step_timeout_seconds} onChange={(v) => setForm((p) => ({ ...p, pipeline_step_timeout_seconds: v }))} />
        <NumberField label="GitHub API max retries" min={0} max={10} value={form.github_api_max_retries} onChange={(v) => setForm((p) => ({ ...p, github_api_max_retries: v }))} />
        <NumberField label="Retry base seconds" min={0.1} max={30} step={0.1} value={form.github_api_retry_base_seconds} onChange={(v) => setForm((p) => ({ ...p, github_api_retry_base_seconds: v }))} />
        <NumberField label="Retry max seconds" min={0.1} max={120} step={0.1} value={form.github_api_retry_max_seconds} onChange={(v) => setForm((p) => ({ ...p, github_api_retry_max_seconds: v }))} />
        <NumberField label="Log prompt max chars" min={1000} max={200000} value={form.log_prompt_max_chars} onChange={(v) => setForm((p) => ({ ...p, log_prompt_max_chars: v }))} />
        <NumberField label="Log prompt head chars" min={100} max={200000} value={form.log_prompt_head_chars} onChange={(v) => setForm((p) => ({ ...p, log_prompt_head_chars: v }))} />
        <NumberField label="Log prompt tail chars" min={100} max={200000} value={form.log_prompt_tail_chars} onChange={(v) => setForm((p) => ({ ...p, log_prompt_tail_chars: v }))} />

        {/* gh-aw ingestion mode */}
        <label className="space-y-1">
          <span className="text-gray-500 dark:text-gray-400">gh-aw ingestion mode</span>
          <select
            value={form.gh_aw_ingestion_mode}
            onChange={(e) =>
              setForm((prev) => ({
                ...prev,
                gh_aw_ingestion_mode: e.target.value === 'passive' ? 'passive' : 'disabled',
              }))
            }
            className="w-full bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-3 py-2 focus:ring-2 focus:ring-azure-500"
          >
            <option value="disabled">disabled</option>
            <option value="passive">passive</option>
          </select>
        </label>

        <label className="space-y-1 lg:col-span-2">
          <span className="text-gray-500 dark:text-gray-400">Known gh-aw workflows (CSV)</span>
          <Input
            type="text"
            value={ghAwWorkflowsInput}
            onChange={(e) => {
              const raw = e.target.value
              setGhAwWorkflowsInput(raw)
              const normalized = raw
                .split(',')
                .map((item) => item.trim().toLowerCase())
                .filter(Boolean)
              setForm((prev) => ({
                ...prev,
                gh_aw_known_workflows: Array.from(new Set(normalized)),
              }))
            }}
            placeholder="ci-doctor,schema-consistency-checker,breaking-change-checker"
          />
        </label>

        <SwitchField label="Auto-create PRs" checked={form.auto_create_pr} onChange={(v) => setForm((p) => ({ ...p, auto_create_pr: v }))} />
        <SwitchField label="Auto-create tracking issue for PRs" checked={form.auto_create_tracking_issue_for_prs} onChange={(v) => setForm((p) => ({ ...p, auto_create_tracking_issue_for_prs: v }))} />
        <SwitchField label="Verify webhook signature in development" checked={form.verify_webhook_signature_in_development} onChange={(v) => setForm((p) => ({ ...p, verify_webhook_signature_in_development: v }))} />
        <SwitchField label="Enable gh-aw passive diagnostics" checked={form.gh_aw_tools_enabled} onChange={(v) => setForm((p) => ({ ...p, gh_aw_tools_enabled: v }))} />
      </div>

      {/* Allowed Repositories */}
      <div className="mt-6">
        <div className="flex items-center justify-between gap-2 mb-2">
          <p className="text-sm text-gray-500 dark:text-gray-400">Allowed repositories</p>
          <Badge variant={hasUnsavedChanges ? 'destructive' : 'success'}>
            {hasUnsavedChanges ? 'Draft changes pending save' : 'Draft is in sync'}
          </Badge>
        </div>
        <p className="text-xs text-gray-400 mb-2">
          Effective now: {data.ph_allowed_repos.length > 0 ? data.ph_allowed_repos.join(', ') : 'all repositories'}
        </p>
        <div className="flex flex-wrap gap-2 mb-2">
          {form.ph_allowed_repos.length === 0 && (
            <span className="text-xs text-gray-400 italic">All repos allowed (no restriction)</span>
          )}
          {form.ph_allowed_repos.map((repo) => (
            <Badge key={repo} variant="secondary" className="flex items-center gap-1">
              {repo}
              <button
                type="button"
                className="ml-1 text-gray-400 hover:text-red-500"
                onClick={() =>
                  setForm((prev) => ({
                    ...prev,
                    ph_allowed_repos: prev.ph_allowed_repos.filter((r) => r !== repo),
                  }))
                }
              >
                x
              </button>
            </Badge>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="owner/repo"
            value={newRepoInput}
            onChange={(e) => setNewRepoInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addAllowedRepo()
              }
            }}
            className="max-w-xs"
          />
          <Button type="button" variant="secondary" size="sm" onClick={addAllowedRepo}>
            Add
          </Button>
        </div>
        <p className="text-xs text-gray-400 mt-1">
          Format: owner/repo, https://github.com/owner/repo, or git@github.com:owner/repo.git.
          Click Save Settings to apply draft changes.
        </p>
      </div>

      {form.log_prompt_head_chars + form.log_prompt_tail_chars > form.log_prompt_max_chars && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">
          Head + tail prompt chars must be less than or equal to max prompt chars.
        </p>
      )}

      {saveError && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">
          {saveError.message || 'Failed to save settings'}
        </p>
      )}

      {saveSuccess && (
        <p className="mt-4 text-sm text-green-600 dark:text-green-400">
          Admin settings updated.
        </p>
      )}

      <div className="mt-4 flex justify-end gap-2">
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
          <RotateCcw className="h-4 w-4 mr-2" />
          Discard Draft
        </Button>
        <Button
          className="flex items-center"
          disabled={
            savePending ||
            !hasUnsavedChanges ||
            form.log_prompt_head_chars + form.log_prompt_tail_chars > form.log_prompt_max_chars
          }
          onClick={onSave}
        >
          <Save className="h-4 w-4 mr-2" />
          {savePending ? 'Saving...' : 'Save Settings'}
        </Button>
      </div>
    </div>
  )
}

/* ---- tiny presentational helpers ---- */

function NumberField({
  label,
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string
  min: number
  max: number
  step?: number
  value: number
  onChange: (v: number) => void
}) {
  return (
    <label className="space-y-1">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <Input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

function SwitchField({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2">
      <Switch checked={checked} onCheckedChange={onChange} />
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
    </label>
  )
}
