import { AlertTriangle } from 'lucide-react'
import type { AppSettings } from '../../api/client'
import {
  formatSettingSource,
  getDurabilityLabel,
  settingSourceTone,
} from './runtimeSemantics'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

interface Props {
  data: AppSettings
}

export default function RuntimePolicyBanner({
  data,
}: Props) {
  const handoffStatus = !data.agent_handoff_enabled
    ? { label: 'Handoff: OFF', variant: 'outline' as const }
    : data.agent_handoff_mode === 'webhook'
      ? data.agent_handoff_webhook_configured
        ? { label: 'Handoff: Webhook', variant: 'success' as const }
        : { label: 'Handoff: Webhook needs URL', variant: 'destructive' as const }
      : { label: 'Handoff: Copy only', variant: 'secondary' as const }
  const healModeMeta = data.settings_metadata?.heal_mode
  const healModeDurability = getDurabilityLabel(healModeMeta)

  return (
    <div className="space-y-4">
      {/* Policy summary strip */}
      <Card>
        <CardContent className="py-4 px-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <h2 className="text-sm font-semibold text-[var(--ph-text)]">Active Policy</h2>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">Mode: {data.heal_mode}</Badge>
              <Badge variant={data.auto_apply_remediation ? 'success' : 'secondary'}>
                Apply: {data.auto_apply_remediation ? 'ON' : 'DRY-RUN'}
              </Badge>
              <Badge variant={data.auto_create_pr ? 'secondary' : 'outline'}>
                PR: {data.auto_create_pr ? 'ON' : 'OFF'}
              </Badge>
              <Badge
                variant={
                  data.auto_create_pr && data.jenkins_bridge_allow_pr ? 'secondary' : 'outline'
                }
              >
                Jenkins Bridge PR:{' '}
                {data.auto_create_pr && data.jenkins_bridge_allow_pr ? 'ON' : 'Issue-first'}
              </Badge>
              <Badge variant={data.auto_create_issue ? 'secondary' : 'outline'}>
                Issue: {data.auto_create_issue ? 'ON' : 'OFF'}
              </Badge>
              <Badge variant={data.auto_retry_workflow ? 'secondary' : 'outline'}>
                Retry: {data.auto_retry_workflow ? 'ON' : 'OFF'}
              </Badge>
              <Badge
                variant={data.ph_allowed_repos.length > 0 ? 'success' : 'destructive'}
              >
                Scope:{' '}
                {data.ph_allowed_repos.length > 0
                  ? `${data.ph_allowed_repos.length} repo${data.ph_allowed_repos.length !== 1 ? 's' : ''}`
                  : 'Unrestricted'}
              </Badge>
              <Badge variant={data.verify_webhook_signature ? 'success' : 'destructive'}>
                Webhook Sig: {data.verify_webhook_signature ? 'ON' : 'OFF'}
              </Badge>
              <Badge variant={data.gh_aw_tools_enabled ? 'success' : 'outline'}>
                External Diag: {data.gh_aw_tools_enabled ? 'ON' : 'OFF'}
              </Badge>
              <Badge
                variant={
                  data.mcp_enabled
                    ? data.mcp_read_only
                      ? 'success'
                      : 'secondary'
                    : 'outline'
                }
              >
                MCP:{' '}
                {data.mcp_enabled
                  ? data.mcp_read_only
                    ? 'ON (Read-only)'
                    : 'ON (Write-capable)'
                  : 'OFF'}
              </Badge>
              <Badge variant={handoffStatus.variant}>{handoffStatus.label}</Badge>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--ph-muted)]">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>Save &amp; Persist keeps mutable settings durable. Startup-only settings still require deployment updates.</span>
            {healModeMeta && (
              <>
                <Badge variant={settingSourceTone(healModeMeta.source)}>
                  Heal mode source: {formatSettingSource(healModeMeta.source)}
                </Badge>
                {healModeDurability ? <Badge variant="outline">{healModeDurability}</Badge> : null}
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
