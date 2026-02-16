import { Link } from 'react-router-dom'
import { Zap, Activity, Shield, Sparkles, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function Landing() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 flex items-center justify-between px-4 sm:px-6 lg:px-8 h-16 border-b border-[var(--ph-border)] bg-[var(--ph-surface)]/80 backdrop-blur">
        <div className="flex items-center gap-2">
          <Zap className="h-7 w-7 text-azure-500" />
          <span className="text-lg font-semibold text-[var(--ph-text)] tracking-tight">
            PipelineHealer
          </span>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 py-16 sm:py-24">
        <div className="max-w-2xl mx-auto text-center space-y-8">
          <h1 className="text-4xl sm:text-5xl font-bold text-[var(--ph-text)] tracking-tight">
            AI-powered CI/CD self-healing
          </h1>
          <p className="text-lg sm:text-xl text-[var(--ph-muted)] leading-relaxed">
            Diagnose failures, suggest fixes, and integrate with GitHub Agentic Workflows — so you
            spend less time on red builds and more time shipping.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
            <Button asChild size="lg" className="text-base px-8">
              <Link to="/app">
                Enter dashboard
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>

        {/* Feature pills */}
        <div className="mt-16 grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl mx-auto">
          <FeaturePill
            icon={Activity}
            title="Failure analysis"
            text="Log analysis and root-cause diagnosis with configurable safety modes."
          />
          <FeaturePill
            icon={Sparkles}
            title="AI + Agentic Workflows"
            text="Azure OpenAI and optional gh-aw integration for richer diagnostics."
          />
          <FeaturePill
            icon={Shield}
            title="Safe by default"
            text="Issue-only or PR creation with repo allowlists and audit trail."
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="flex-shrink-0 py-6 px-4 border-t border-[var(--ph-border)] text-center text-sm text-[var(--ph-muted)]">
        <p>Built for AI Dev Days Hackathon · Microsoft Agent Framework</p>
      </footer>
    </div>
  )
}

function FeaturePill({
  icon: Icon,
  title,
  text,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  text: string
}) {
  return (
    <div className="rounded-xl border border-[var(--ph-border)] bg-[var(--ph-surface)] p-5 text-left shadow-sm">
      <Icon className="h-6 w-6 text-azure-500 mb-3" />
      <h3 className="font-semibold text-[var(--ph-text)] mb-1">{title}</h3>
      <p className="text-sm text-[var(--ph-muted)] leading-relaxed">{text}</p>
    </div>
  )
}
