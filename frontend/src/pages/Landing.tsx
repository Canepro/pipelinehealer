import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  GitBranch,
  Layers,
  Search,
  Shield,
  ShieldCheck,
  Workflow,
  Wrench,
  Zap,
} from 'lucide-react'
import { motion, useInView } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

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

const operationalSignals = [
  {
    title: 'Deployment Modes',
    text: 'Local Docker workflow plus Azure Container Apps for production demo runs.',
  },
  {
    title: 'Model Portability',
    text: 'Azure OpenAI today, OpenAI-compatible provider path built in, task-level model routing included.',
  },
  {
    title: 'Governance Controls',
    text: 'Policy gates, repository allowlists, MCP tool policies, and durable settings audit trail.',
  },
]

const platformStats = [
  { value: 7, label: 'Failure Types', suffix: '' },
  { value: 3, label: 'Remediation Modes', suffix: '' },
  { value: 4, label: 'Agent Pipeline', suffix: '-stage' },
  { value: 100, label: 'Audit Trail', suffix: '%' },
]

const agentNodes = [
  { icon: Search, label: 'Log Analyst', desc: 'Parse & classify' },
  { icon: Bot, label: 'Diagnostician', desc: 'Root-cause analysis' },
  { icon: Wrench, label: 'Fixer', desc: 'Generate remediation' },
  { icon: Shield, label: 'Policy Gate', desc: 'Safety validation' },
]

/* ------------------------------------------------------------------ */
/*  Animation helpers                                                  */
/* ------------------------------------------------------------------ */

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
}

const staggerContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1 } },
}

function FadeSection({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })
  return (
    <motion.div
      ref={ref}
      initial="hidden"
      animate={inView ? 'visible' : 'hidden'}
      variants={fadeUp}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* Animated counter that counts up when scrolled into view */
function CountUp({ target, suffix = '' }: { target: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!inView) return
    let frame: number
    const duration = 1200
    const start = performance.now()
    function tick(now: number) {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setCount(Math.round(eased * target))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [inView, target])

  return (
    <span ref={ref}>
      {count}
      {suffix}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

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
              Hackathon Preview
            </Badge>
            <Button asChild size="sm" variant="secondary">
              <Link to="/app">Open App</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl space-y-14 px-4 py-12 sm:px-6 sm:py-16">
        {/* Hero */}
        <motion.section
          initial="hidden"
          animate="visible"
          variants={staggerContainer}
          className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-stretch"
        >
          <motion.div variants={fadeUp} transition={{ duration: 0.5 }}>
            <Card className="h-full border-azure-500/20 bg-[color:var(--ph-surface)]/95">
              <CardContent className="p-6 sm:p-8">
                <Badge variant="outline" className="mb-4">
                  CI/CD Reliability Platform
                </Badge>
                <h1 className="text-3xl font-bold tracking-tight text-[var(--ph-text)] sm:text-5xl">
                  Resolve CI failures faster with policy-aware AI remediation
                </h1>
                <p className="mt-4 max-w-2xl text-base leading-relaxed text-[var(--ph-muted)] sm:text-lg">
                  PipelineHealer helps engineering teams detect failures, diagnose root causes,
                  and propose safe corrective actions with full traceability, provider-aware model
                  telemetry, and policy-first guardrails.
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
                  <Button asChild size="lg" variant="secondary">
                    <a
                      href="https://github.com/Canepro/pipelinehealer/blob/main/docs/LOCAL_DEMO_RUNBOOK.md"
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      View Runbook
                    </a>
                  </Button>
                </div>
                <div className="mt-6 flex flex-wrap gap-2 text-xs">
                  <Badge variant="secondary">GitHub Actions</Badge>
                  <Badge variant="secondary">Azure OpenAI</Badge>
                  <Badge variant="secondary">Model Routing</Badge>
                  <Badge variant="secondary">MCP Governance</Badge>
                  <Badge variant="secondary">External Diagnostics</Badge>
                  <Badge variant="secondary">Audit Trail</Badge>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={fadeUp} transition={{ duration: 0.5, delay: 0.15 }}>
            <Card className="h-full">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Operational Snapshot</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                {operationalSignals.map((signal) => (
                  <div
                    key={signal.title}
                    className="rounded-lg border border-[var(--ph-border)] bg-slate-800/10 p-3"
                  >
                    <p className="font-semibold text-[var(--ph-text)]">{signal.title}</p>
                    <p className="mt-1 text-[var(--ph-muted)]">{signal.text}</p>
                  </div>
                ))}
                <div className="rounded-lg border border-azure-500/25 bg-azure-500/5 p-3">
                  <p className="font-semibold text-[var(--ph-text)]">Operator Experience</p>
                  <p className="mt-1 text-[var(--ph-muted)]">
                    Dashboard for triage, Activity Detail for root-cause evidence, and Control Center
                    for policy, audit, and investigation workflows.
                  </p>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </motion.section>

        {/* Platform capability counters */}
        <FadeSection>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {platformStats.map((stat) => (
              <div
                key={stat.label}
                className="rounded-xl border border-[var(--ph-border)] bg-[var(--ph-surface)] p-4 text-center"
              >
                <p className="text-3xl font-bold tracking-tight text-azure-500 sm:text-4xl">
                  <CountUp target={stat.value} suffix={stat.suffix} />
                </p>
                <p className="mt-1 text-sm text-[var(--ph-muted)]">{stat.label}</p>
              </div>
            ))}
          </div>
        </FadeSection>

        {/* Architecture diagram */}
        <FadeSection>
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <Layers className="h-5 w-5 text-azure-500" />
                <CardTitle className="text-base">Multi-Agent Pipeline</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-6 pt-2 sm:px-6">
              <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-between sm:gap-0">
                {agentNodes.map((node, i) => (
                  <div key={node.label} className="flex items-center gap-3 sm:flex-col sm:gap-0">
                    <div className="flex flex-col items-center">
                      <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-azure-500/30 bg-azure-500/10">
                        <node.icon className="h-6 w-6 text-azure-500" />
                      </div>
                      <p className="mt-2 text-sm font-semibold text-[var(--ph-text)]">{node.label}</p>
                      <p className="text-xs text-[var(--ph-muted)]">{node.desc}</p>
                    </div>
                    {i < agentNodes.length - 1 && (
                      <ArrowRight className="hidden h-5 w-5 shrink-0 text-[var(--ph-muted)] sm:block sm:mx-3" />
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </FadeSection>

        {/* Enterprise-Ready Capabilities */}
        <FadeSection>
          <section className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-xl font-semibold text-[var(--ph-text)] sm:text-2xl">
                Enterprise-Ready Capabilities
              </h2>
              <Badge variant="outline">Production-minded defaults</Badge>
            </div>
            <motion.div
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: '-40px' }}
              variants={staggerContainer}
              className="grid gap-4 md:grid-cols-3"
            >
              {capabilityCards.map((card) => (
                <motion.div key={card.title} variants={fadeUp} transition={{ duration: 0.4 }}>
                  <Card className="h-full">
                    <CardContent className="p-5">
                      <card.icon className="mb-3 h-6 w-6 text-azure-500" />
                      <h3 className="text-base font-semibold text-[var(--ph-text)]">{card.title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-[var(--ph-muted)]">{card.text}</p>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </motion.div>
          </section>
        </FadeSection>

        {/* How It Works */}
        <FadeSection>
          <section className="space-y-4">
            <h2 className="text-xl font-semibold text-[var(--ph-text)] sm:text-2xl">How It Works</h2>
            <motion.div
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: '-40px' }}
              variants={staggerContainer}
              className="grid gap-4 md:grid-cols-3"
            >
              {processSteps.map((step) => (
                <motion.div key={step.title} variants={fadeUp} transition={{ duration: 0.4 }}>
                  <Card className="h-full">
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
                </motion.div>
              ))}
            </motion.div>
          </section>
        </FadeSection>
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
