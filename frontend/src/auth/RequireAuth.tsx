import { useEffect, type ReactNode } from 'react'
import { InteractionStatus } from '@azure/msal-browser'
import { useMsal } from '@azure/msal-react'
import { LockKeyhole, ShieldAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  AUTH_ENABLED,
  authConfigErrors,
  loginScopes,
  resolvedAuthority,
} from './config'
import { appMsalInstance } from './msalInstance'

function AuthLoadingState() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-surface)] px-4 py-3 text-sm text-[var(--ph-muted)]">
        Initializing secure session...
      </div>
    </div>
  )
}

function AuthConfigError() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-2xl items-center justify-center px-4">
      <Card className="w-full border-rose-500/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-rose-400">
            <ShieldAlert className="h-5 w-5" />
            Login configuration is incomplete
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-[var(--ph-muted)]">
            Entra authentication is enabled but required frontend environment values are missing.
          </p>
          <ul className="list-disc space-y-1 pl-5 text-[var(--ph-muted)]">
            {authConfigErrors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
          <div className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/70 p-3 font-mono text-xs">
            Authority: {resolvedAuthority || '(unset)'}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function RequireAuthInner({ children }: { children: ReactNode }) {
  const { instance, accounts, inProgress } = useMsal()
  const activeAccount = instance.getActiveAccount() || accounts[0] || null

  useEffect(() => {
    if (!instance.getActiveAccount() && accounts.length > 0) {
      instance.setActiveAccount(accounts[0])
    }
  }, [instance, accounts])

  if (
    inProgress === InteractionStatus.Startup ||
    inProgress === InteractionStatus.HandleRedirect ||
    inProgress === InteractionStatus.AcquireToken
  ) {
    return <AuthLoadingState />
  }

  if (!activeAccount) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-md items-center justify-center px-4">
        <Card className="w-full">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <LockKeyhole className="h-5 w-5 text-azure-500" />
              Secure Access Required
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-[var(--ph-muted)]">
              Sign in with Microsoft Entra ID to access the PipelineHealer application.
            </p>
            <Badge variant="outline">Scopes: {loginScopes.join(', ')}</Badge>
            <Button
              className="w-full"
              onClick={() => {
                void instance.loginRedirect({ scopes: loginScopes })
              }}
            >
              Sign in with Microsoft
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return <>{children}</>
}

export default function RequireAuth({ children }: { children: ReactNode }) {
  if (!AUTH_ENABLED) {
    return <>{children}</>
  }
  if (appMsalInstance === null || authConfigErrors.length > 0) {
    return <AuthConfigError />
  }
  return <RequireAuthInner>{children}</RequireAuthInner>
}
