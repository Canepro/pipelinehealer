import type {
  AgentHandoffIntegrationStatus,
  AppSettingMetadata,
  AppSettingSource,
} from '../../api/client'

export type BadgeTone = 'success' | 'secondary' | 'destructive' | 'outline'
export type McpPolicyMode = 'disabled' | 'read_only' | 'write_with_approval' | 'auto'
export type McpEffectiveState = {
  status: 'allowed' | 'approval' | 'blocked' | 'inactive'
  summary: string
  detail: string
  tone: BadgeTone
}

export type IntegrationTone = 'ok' | 'warn' | 'bad' | 'muted'

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

export function describeAgentHandoffIntegrationStatus(
  status?: AgentHandoffIntegrationStatus
): { summary: string; detail: string; tone: IntegrationTone } {
  if (!status) {
    return {
      summary: 'Status unavailable',
      detail: 'Receiver health has not been loaded yet.',
      tone: 'muted',
    }
  }

  switch (status.receiver_status) {
    case 'not_required':
      return {
        summary: status.mode === 'copy_only' ? 'Copy-only mode' : 'Disabled',
        detail:
          status.reason === 'copy_only_mode'
            ? 'No external receiver is required while Assign-to-Agent stays in copy-only mode.'
            : 'Assign-to-Agent is disabled by runtime configuration.',
        tone: 'muted',
      }
    case 'missing_configuration':
      return {
        summary: 'Missing receiver URL',
        detail: 'Webhook mode is enabled, but no startup receiver URL is configured.',
        tone: 'warn',
      }
    case 'invalid_configuration':
      if (status.reason === 'destination_not_allowlisted') {
        return {
          summary: 'Receiver blocked by allowlist',
          detail: 'The configured receiver host is outside the webhook allowlist used for real delivery.',
          tone: 'bad',
        }
      }
      return {
        summary: 'Invalid receiver URL',
        detail: 'The configured startup receiver URL is not a valid http(s) endpoint.',
        tone: 'bad',
      }
    case 'unreachable':
      return {
        summary: 'Receiver unreachable',
        detail: 'The configured receiver health endpoint could not be reached from the backend.',
        tone: 'bad',
      }
    case 'invalid_response':
      return {
        summary: 'Receiver health invalid',
        detail: 'The receiver responded, but not with the expected notification health summary.',
        tone: 'warn',
      }
    case 'degraded':
      return {
        summary: 'Receiver degraded',
        detail: 'The receiver is reachable, but one or more notification targets are invalid.',
        tone: 'warn',
      }
    default:
      return {
        summary: status.notifications?.configured_targets
          ? 'Receiver available'
          : 'Receiver available (no targets)',
        detail: status.notifications?.configured_targets
          ? 'Receiver health is available and notification targets are configured.'
          : 'Receiver health is available, but no notification targets are configured yet.',
        tone: 'ok',
      }
  }
}

export function formatIntegrationQueryState(args: {
  status?: AgentHandoffIntegrationStatus
  isError: boolean
  error?: Error | null
}): { summary: string; detail: string; tone: IntegrationTone } {
  if (args.isError) {
    return {
      summary: 'Probe failed',
      detail: args.error?.message || 'Integration status request failed.',
      tone: 'bad',
    }
  }
  return describeAgentHandoffIntegrationStatus(args.status)
}
