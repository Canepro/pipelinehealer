import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  GitBranch,
  Workflow,
  Wrench,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const operatorSurfaceRows = [
  {
    title: "Settings",
    text: "Manage mutable runtime policy, understand provenance, and see which integration values are deployment-managed.",
  },
  {
    title: "Control Center",
    text: "Inspect governance posture, startup-managed dependencies, receiver health, and investigation paths.",
  },
  {
    title: "Activity Detail",
    text: "Trace evidence, diagnosis, remediation output, handoff audit, and external diagnostics on one activity.",
  },
];

const pipelineLifecycle = [
  {
    icon: GitBranch,
    title: "Provider-specific ingress",
    text: "GitHub Actions is native today. Jenkins can feed the same activity model through the signed bridge path.",
  },
  {
    icon: Workflow,
    title: "One normalized activity model",
    text: "Failure context, diagnostics, remediation, audit, and policy state are kept in one operator-facing record.",
  },
  {
    icon: Wrench,
    title: "Policy-aware outcomes",
    text: "Issue, PR, retry, or agent handoff paths stay explicit about what is allowed, blocked, or missing.",
  },
];

const platformFacts = [
  { label: "Ingress paths", value: "2" },
  { label: "Operator surfaces", value: "4" },
  { label: "Agent stages", value: "4" },
  { label: "Auditability", value: "100%" },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-[var(--ph-bg)]">
      <header className="border-b border-[var(--ph-border)] bg-[var(--ph-surface)]">
        <div className="mx-auto flex h-16 w-full max-w-[1440px] items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]">
              <Zap className="h-5 w-5 text-[var(--ph-accent)]" />
            </div>
            <div>
              <div className="text-base font-semibold tracking-tight text-[var(--ph-text)]">
                PipelineHealer
              </div>
              <div className="text-xs text-[var(--ph-muted)]">
                OSS-first pipeline remediation platform
              </div>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <Button asChild size="sm" variant="secondary">
              <a
                href="https://github.com/Canepro/pipelinehealer"
                rel="noreferrer"
                target="_blank"
              >
                Source
              </a>
            </Button>
            <Button asChild size="sm">
              <Link to="/app">Open App</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-10 px-4 py-10 sm:px-6 sm:py-12">
        <section className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_360px] lg:items-start">
          <div className="space-y-5">
            <div className="max-w-4xl space-y-3">
              <h1 className="text-4xl font-semibold tracking-tight text-[var(--ph-text)] sm:text-5xl">
                Pipeline remediation with visible policy boundaries
              </h1>
              <p className="max-w-3xl text-base leading-7 text-[var(--ph-muted)] sm:text-lg">
                PipelineHealer turns provider-specific pipeline failures into
                one governed activity flow. Operators can see what the system
                diagnosed, what remediation path was selected, what is blocked
                by policy, and which integrations still require
                deployment-managed wiring.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <Link to="/app">
                  Open control plane
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="secondary">
                <a
                  href="https://github.com/Canepro/pipelinehealer/blob/main/docs/runbooks/LOCAL_DEMO_RUNBOOK.md"
                  rel="noreferrer"
                  target="_blank"
                >
                  Operator runbook
                </a>
              </Button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {platformFacts.map((fact) => (
                <div
                  key={fact.label}
                  className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-surface)] px-4 py-3"
                >
                  <div className="text-2xl font-semibold tracking-tight text-[var(--ph-text)]">
                    {fact.value}
                  </div>
                  <div className="text-sm text-[var(--ph-muted)]">
                    {fact.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                Current platform scope
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="space-y-3">
                <ScopeRow label="Native path" value="GitHub Actions" />
                <ScopeRow label="Bridge path" value="Jenkins" />
                <ScopeRow label="Agent handoff" value="Copy-only or webhook" />
                <ScopeRow
                  label="Reference deployment"
                  value="Azure Container Apps"
                />
              </div>
              <div className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/55 p-3 text-[var(--ph-muted)]">
                Startup-only secrets stay deployment-managed. Runtime policy and
                non-secret controls stay in the product surface.
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                What operators can inspect now
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {operatorSurfaceRows.map((row) => (
                <div
                  key={row.title}
                  className="border-b border-[var(--ph-border)] pb-4 last:border-b-0 last:pb-0"
                >
                  <div className="font-medium text-[var(--ph-text)]">
                    {row.title}
                  </div>
                  <p className="mt-1 text-sm leading-6 text-[var(--ph-muted)]">
                    {row.text}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                How the platform flows
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {pipelineLifecycle.map((item) => (
                <div
                  key={item.title}
                  className="flex gap-3 border-b border-[var(--ph-border)] pb-4 last:border-b-0 last:pb-0"
                >
                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]">
                    <item.icon className="h-4 w-4 text-[var(--ph-accent)]" />
                  </div>
                  <div>
                    <div className="font-medium text-[var(--ph-text)]">
                      {item.title}
                    </div>
                    <p className="mt-1 text-sm leading-6 text-[var(--ph-muted)]">
                      {item.text}
                    </p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                Why the control plane matters
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-[var(--ph-muted)]">
              <p>
                The product is broader than CI log summarization. It is built
                around a normalized pipeline activity model, explicit policy
                gates, auditable remediation decisions, and deployment-neutral
                configuration rules.
              </p>
              <p>
                That is why the app distinguishes configured state, effective
                runtime behavior, startup-managed dependencies, and outbound
                integration health instead of collapsing everything into one
                vague “enabled” badge.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Design principles</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <PrincipleRow text="Explain why something is blocked, not just that it is blocked." />
              <PrincipleRow text="Keep deployment-managed secrets out of generic runtime persistence." />
              <PrincipleRow text="Show operator-ready evidence before decorative surface polish." />
              <PrincipleRow text="Treat Azure as a reference deployment, not the product boundary." />
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}

function ScopeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[var(--ph-border)] pb-3 last:border-b-0 last:pb-0">
      <span className="text-[var(--ph-muted)]">{label}</span>
      <span className="text-right font-medium text-[var(--ph-text)]">
        {value}
      </span>
    </div>
  );
}

function PrincipleRow({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/55 px-3 py-2.5">
      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--ph-accent)]" />
      <span className="leading-6 text-[var(--ph-text)]">{text}</span>
    </div>
  );
}
