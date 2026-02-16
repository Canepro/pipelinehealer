import { Link } from 'react-router-dom'
import { ArrowRight, BarChart3, Bot, CheckCircle2, GitBranch, ShieldCheck, Workflow, Zap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const capabilityCards = [
  {
    icon: Workflow,
    title: 'Automated Failure Triage',
    text: 'Correlates workflow logs, classifies failure type, and surfaces root-cause evidence quickly.',
  },
  {
    icon: Bot,
    title: 'AI-Assisted Diagnosis',
    text: 'Uses configurable AI models with deterministic safeguards to avoid risky false positives.',
  },
  {
    icon: ShieldCheck,
    title: 'Governed Remediation',
    text: 'Supports issue-only mode, PR mode, allowlists, and policy-aware safety gates.',
  },
]

const processSteps = [
  {
    step: '01',
    title: 'Detect',
    text: 'Ingest CI failures from GitHub Actions and normalize activity context.',
  },
  {
    step: '02',
    title: 'Diagnose',
    text: 'Combine pattern matching, AI analysis, and external diagnostics for confidence scoring.',
  },
  {
    step: '03',
    title: 'Remediate',
    text: 'Generate safe actions: issue, PR, or no-op with clear reasoning and auditability.',
  },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-[radial-gradient(1200px_500px_at_20%_-10%,rgba(53,111,174,0.18),transparent_55%),radial-gradient(1000px_420px_at_90%_0%,rgba(53,111,174,0.14),transparent_50%)]">
      <header className="sticky top-0 z-20 border-b border-[var(--ph-border)] bg-[var(--ph-surface)]/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2 rounded-lg px-1 py-1 hover:bg-slate-800/5">
            <Zap className="h-7 w-7 text-azure-500" />
            <span className="text-lg font-semibold tracking-tight text-[var(--ph-text)]">PipelineHealer</span>
          </Link>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="hidden md:inline-flex">
              Enterprise Preview
            </Badge>
            <Button asChild size="sm" variant="secondary">
              <Link to="/app">Open App</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl space-y-14 px-4 py-12 sm:px-6 sm:py-16">
        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-stretch">
          <Card className="border-azure-500/20 bg-[color:var(--ph-surface)]/95">
            <CardContent className="p-6 sm:p-8">
              <Badge variant="outline" className="mb-4">
                CI/CD Reliability Platform
              </Badge>
              <h1 className="text-3xl font-bold tracking-tight text-[var(--ph-text)] sm:text-5xl">
                Resolve CI failures faster with policy-aware AI remediation
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-[var(--ph-muted)] sm:text-lg">
                PipelineHealer helps engineering teams detect failures, diagnose root causes,
                and propose safe corrective actions with full traceability.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Button asChild size="lg" className="px-6">
                  <Link to="/app">
                    Enter Dashboard
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="secondary">
                  <a href="https://github.com/Canepro/pipelinehealer" rel="noopener noreferrer" target="_blank">
                    View Source
                  </a>
                </Button>
              </div>
              <div className="mt-6 flex flex-wrap gap-2 text-xs">
                <Badge variant="secondary">GitHub Actions</Badge>
                <Badge variant="secondary">Azure OpenAI</Badge>
                <Badge variant="secondary">External Diagnostics</Badge>
                <Badge variant="secondary">Audit Trail</Badge>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Operational Snapshot</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg border border-[var(--ph-border)] bg-slate-800/10 p-3">
                <p className="font-semibold text-[var(--ph-text)]">Deployment Modes</p>
                <p className="mt-1 text-[var(--ph-muted)]">Local Docker workflow and Azure Container Apps.</p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-slate-800/10 p-3">
                <p className="font-semibold text-[var(--ph-text)]">Safety Controls</p>
                <p className="mt-1 text-[var(--ph-muted)]">Issue-only mode, PR gate controls, repository allowlisting.</p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-slate-800/10 p-3">
                <p className="font-semibold text-[var(--ph-text)]">Diagnostics Depth</p>
                <p className="mt-1 text-[var(--ph-muted)]">Primary diagnosis + optional gh-aw enrichment + no-op signals.</p>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-xl font-semibold text-[var(--ph-text)] sm:text-2xl">
              Enterprise-Ready Capabilities
            </h2>
            <Badge variant="outline">Production-minded defaults</Badge>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {capabilityCards.map((card) => (
              <Card key={card.title}>
                <CardContent className="p-5">
                  <card.icon className="mb-3 h-6 w-6 text-azure-500" />
                  <h3 className="text-base font-semibold text-[var(--ph-text)]">{card.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[var(--ph-muted)]">{card.text}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-[var(--ph-text)] sm:text-2xl">How It Works</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {processSteps.map((step) => (
              <Card key={step.title}>
                <CardContent className="p-5">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono">
                      {step.step}
                    </Badge>
                    {step.title === 'Detect' && <GitBranch className="h-4 w-4 text-azure-400" />}
                    {step.title === 'Diagnose' && <BarChart3 className="h-4 w-4 text-azure-400" />}
                    {step.title === 'Remediate' && <CheckCircle2 className="h-4 w-4 text-azure-400" />}
                  </div>
                  <h3 className="mt-3 text-base font-semibold text-[var(--ph-text)]">{step.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[var(--ph-muted)]">{step.text}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-[var(--ph-border)] py-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-4 text-sm text-[var(--ph-muted)] sm:flex-row sm:px-6">
          <p>PipelineHealer · AI Dev Days Hackathon 2026</p>
          <p>Microsoft Agent Framework · GitHub Actions · Azure OpenAI</p>
        </div>
      </footer>
    </div>
  )
}
