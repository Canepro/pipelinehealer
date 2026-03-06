import type { AppSettingMetadata, AppSettingSource } from '../../api/client'

export type BadgeTone = 'success' | 'secondary' | 'destructive' | 'outline'
export type McpPolicyMode = 'disabled' | 'read_only' | 'write_with_approval' | 'auto'
export type McpEffectiveState = {
  status: 'allowed' | 'approval' | 'blocked' | 'inactive'
  summary: string
  detail: string
  tone: BadgeTone
}

export function formatSettingSource(source: AppSettingSource): string {
  switch (source) {
    case 'default':
      return 'Default'
    case 'env':
      return 'Startup config'
    case 'runtime_override':
      return 'Runtime override'
    case 'persisted_runtime_override':
      return 'Persisted override'
    case 'computed':
      return 'Computed'
    default:
      return source
  }
}

export function settingSourceTone(source: AppSettingSource): BadgeTone {
  switch (source) {
    case 'runtime_override':
      return 'secondary'
    case 'persisted_runtime_override':
      return 'success'
    case 'env':
      return 'outline'
    case 'computed':
      return 'secondary'
    default:
      return 'outline'
  }
}

export function getDurabilityLabel(metadata?: AppSettingMetadata): string | null {
  if (!metadata) return null
  if (metadata.requires_restart) return 'Restart required'
  if (!metadata.mutable) return null
  return metadata.durable ? 'Durable' : 'Runtime only'
}

export function getMcpEffectiveState({
  mcpEnabled,
  mcpProvider,
  readOnly,
  write,
  policy,
}: {
  mcpEnabled: boolean
  mcpProvider: string
  readOnly: boolean
  write: boolean
  policy: McpPolicyMode
}): McpEffectiveState {
  if (!mcpEnabled || mcpProvider === 'disabled') {
    return {
      status: 'inactive',
      summary: 'Inactive',
      detail: 'MCP is disabled globally.',
      tone: 'outline',
    }
  }
  if (policy === 'disabled') {
    return {
      status: 'blocked',
      summary: 'Blocked',
      detail: 'Tool policy is disabled.',
      tone: 'destructive',
    }
  }
  if (!write) {
    return {
      status: 'allowed',
      summary: 'Allowed (Read)',
      detail: 'Read context fetch is allowed.',
      tone: 'success',
    }
  }
  if (readOnly) {
    return {
      status: 'blocked',
      summary: 'Blocked',
      detail: 'Global read-only mode blocks write actions.',
      tone: 'destructive',
    }
  }
  if (policy === 'read_only') {
    return {
      status: 'blocked',
      summary: 'Blocked',
      detail: 'Tool policy is read_only.',
      tone: 'destructive',
    }
  }
  if (policy === 'write_with_approval') {
    return {
      status: 'approval',
      summary: 'Approval Required',
      detail: 'Write action needs explicit approval.',
      tone: 'secondary',
    }
  }
  return {
    status: 'allowed',
    summary: 'Allowed (Auto)',
    detail: 'Write action may run automatically.',
    tone: 'success',
  }
}
