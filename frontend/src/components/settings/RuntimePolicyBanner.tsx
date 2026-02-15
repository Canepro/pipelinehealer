import { AlertTriangle } from 'lucide-react'
import type { AppSettings } from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

interface Props {
  data: AppSettings
  hasUnsavedChanges: boolean
  isPersisting: boolean
  onPersist: () => void
}

export default function RuntimePolicyBanner({ data, hasUnsavedChanges, isPersisting, onPersist }: Props) {
  return (
    <>
      <Card className="p-4 md:p-6 border border-amber-500/30 bg-amber-500/10">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 mt-0.5" />
            <div>
              <h2 className="text-base font-semibold text-amber-200">
                Runtime only (lost on redeploy)
              </h2>
              <p className="mt-1 text-sm text-amber-100/90">
                Settings saved here update the running backend process. Redeploy or revision replacement restores values from
                <code className="mx-1">backend/.env</code> and Azure Container App env.
              </p>
              <p className="mt-2 text-xs text-amber-100/80">
                Use Persist Settings to write all mutable runtime settings to durable storage.
                In Azure, redeploy is not required because persisted values are applied on startup.
                When local <code className="mx-1">backend/.env</code> exists, the action also updates it.
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={onPersist}
            disabled={hasUnsavedChanges || isPersisting}
          >
            {isPersisting ? 'Persisting...' : 'Persist Settings'}
          </Button>
        </div>
      </Card>

      <Card className="p-4 md:p-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Effective Runtime Policy
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Current operational guardrails applied by the backend.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">Mode: {data.heal_mode}</Badge>
            <Badge variant={data.auto_create_pr ? 'destructive' : 'success'}>
              PR Creation: {data.auto_create_pr ? 'ON' : 'OFF'}
            </Badge>
            <Badge variant={data.ph_allowed_repos.length > 0 ? 'success' : 'destructive'}>
              Scope: {data.ph_allowed_repos.length > 0 ? `Allowlist (${data.ph_allowed_repos.length})` : 'Unrestricted'}
            </Badge>
            <Badge variant={data.verify_webhook_signature ? 'success' : 'destructive'}>
              Signature: {data.verify_webhook_signature ? 'ON' : 'OFF'}
            </Badge>
          </div>
        </div>
      </Card>
    </>
  )
}
