import { AlertTriangle, CloudUpload } from 'lucide-react'
import type { AppSettings } from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

interface Props {
  data: AppSettings
  hasUnsavedChanges: boolean
  isPersisting: boolean
  onPersist: () => void
}

export default function RuntimePolicyBanner({
  data,
  hasUnsavedChanges,
  isPersisting,
  onPersist,
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
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Persist warning */}
      <Card className="border-amber-500/20 bg-amber-500/5">
        <CardContent className="py-4 px-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-amber-200">
                  Runtime-only — changes are lost on redeploy
                </p>
                <p className="text-xs text-amber-100/70">
                  Saved settings update the running process immediately. Use{' '}
                  <strong>Persist</strong> to write them to durable storage so they survive
                  restarts.
                </p>
              </div>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={onPersist}
              disabled={hasUnsavedChanges || isPersisting}
            >
              <CloudUpload className="h-4 w-4" />
              {isPersisting ? 'Persisting...' : 'Persist'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
