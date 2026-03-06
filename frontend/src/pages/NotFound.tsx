import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 text-center">
      <AlertTriangle className="h-12 w-12 text-[var(--ph-warning)]" />
      <h1 className="text-2xl font-semibold text-[var(--ph-text)]">
        Page not found
      </h1>
      <p className="max-w-md text-sm text-[var(--ph-muted)]">
        The page you are looking for does not exist or has been moved.
      </p>
      <Button asChild>
        <Link to="/app">Back to Dashboard</Link>
      </Button>
    </div>
  )
}
