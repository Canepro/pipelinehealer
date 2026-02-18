import { AlertTriangle } from 'lucide-react'
import type { AppSettings } from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

interface Props {
  data: AppSettings
}

export default function RuntimePolicyBanner({
  data,
}: Props) {
  return (
    <div className="space-y-4">
      {/* Policy summary strip */}
      <Card>
        <CardContent className="py-4 px-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <h2 className="text-sm font-semibold text-[var(--ph-text)]">Active Policy</h2>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">Mode: {data.heal_mode}</Badge>
              <Badge variant={data.auto_create_pr ? 'destructive' : 'success'}>
                PR Creation: {data.auto_create_pr ? 'ON' : 'OFF'}
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
                      : 'destructive'
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
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-[var(--ph-muted)]">
            <AlertTriangle className="h-3.5 w-3.5" />
            Save Settings applies changes and persists them for restart/redeploy durability.
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
