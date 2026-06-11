import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Bot,
  CheckCircle2,
  GitPullRequest,
  LockKeyhole,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  Workflow,
  Wrench,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const workflowStages = [
  { label: "Failed run", value: "workflow_run" },
  { label: "Evidence", value: "logs + checks" },
  { label: "Diagnosis", value: "root cause" },
  { label: "Healing path", value: "PR, retry, issue, handoff" },
  { label: "Proof", value: "labels + audit" },
];

const healingPaths = [
  {
    icon: GitPullRequest,
    title: "Open or reuse fix PRs",
    text: "Deterministic fixes become reviewable branches and pull requests against approved repositories.",
  },
  {
    icon: RefreshCw,
    title: "Rerun failed jobs",
    text: "Retryable failures can use GitHub's failed-job rerun path instead of creating noisy work.",
  },
  {
    icon: Bot,
    title: "Delegate to agents",
    text: "External agent runtimes can take the work while PipelineHealer keeps the record.",
  },
  {
    icon: ShieldCheck,
    title: "Verify and learn",
    text: "Every outcome keeps policy, labels, handoff events, verification, and operator trust signals attached.",
  },
];

const audienceRows = [
  {
    title: "Maintainers",
    text: "Get a fix PR or retry instead of a vague failure notification.",
  },
  {
    title: "Platform teams",
    text: "Keep repo allowlists, model routes, handoff targets, and secret provenance visible.",
  },
  {
    title: "Agent operators",
    text: "Hand work to external agents without losing callback history, GitHub proof, or audit ownership.",
  },
];

const capabilityRows = [
  { label: "Ingress", value: "GitHub Actions, Jenkins bridge" },
  { label: "Remediation", value: "PR, issue, retry, clean-check merge" },
  { label: "Agent runtime", value: "Codex App Server, OpenClaw, Hermes, custom webhooks" },
  { label: "Secrets", value: "Infisical, encrypted DB, Key Vault" },
  { label: "Cloud posture", value: "Provider-neutral core, container-first deploys" },
  { label: "Reference deploy", value: "Azure Container Apps today" },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-[var(--ph-bg)] text-[var(--ph-text)]">
      <header className="border-b border-[var(--ph-border-subtle)] bg-[var(--ph-surface)]/95 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-[1440px] items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]">
              <Zap className="h-5 w-5 text-[var(--ph-accent)]" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-base font-semibold">
                PipelineHealer
              </div>
              <div className="truncate text-xs text-[var(--ph-muted)]">
                Agent control plane for failed delivery pipelines
              </div>
            </div>
          </Link>
          <div className="flex shrink-0 items-center gap-2">
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
              <Link to="/app">Open control plane</Link>
            </Button>
          </div>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden border-b border-[var(--ph-border-subtle)] bg-[var(--ph-bg)]">
          <HeroBackdrop />
          <div className="relative mx-auto grid w-full max-w-[1440px] items-center gap-8 px-4 py-8 sm:px-6 sm:py-10 lg:grid-cols-[minmax(0,1fr)_minmax(360px,520px)] lg:py-12">
            <div className="max-w-4xl space-y-6">
              <div className="inline-flex items-center gap-2 rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)]/86 px-3 py-1 text-sm text-[var(--ph-muted)] shadow-[var(--ph-shadow-sm)]">
                <Activity className="h-4 w-4 text-[var(--ph-accent)]" />
                CI/CD failure control, remediation, and proof
              </div>
              <div className="space-y-4">
                <h1 className="max-w-4xl break-words text-4xl font-semibold leading-[1.05] min-[360px]:text-5xl sm:text-6xl">
                  Failed pipelines, fixed under policy
                </h1>
                <p className="max-w-3xl text-lg leading-8 text-[var(--ph-muted)] sm:text-xl">
                  PipelineHealer watches failed CI/CD runs, diagnoses the
                  cause, then takes the allowed recovery path: fix PR,
                  failed-job retry, review issue, or external agent handoff. It
                  keeps policy, labels, verification, and audit in one record.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link to="/app">
                    Open control plane
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button
                  asChild
                  className="hidden sm:inline-flex"
                  size="lg"
                  variant="secondary"
                >
                  <a
                    href="https://github.com/Canepro/pipelinehealer/blob/main/docs/runbooks/LOCAL_DEMO_RUNBOOK.md"
                    rel="noreferrer"
                    target="_blank"
                  >
                    Operator runbook
                  </a>
                </Button>
              </div>
              <div className="hidden max-w-4xl gap-3 sm:grid sm:grid-cols-3">
                <SignalStat label="Prod posture" value="Policy-driven fixes" />
                <SignalStat label="Runtime" value="External agents ready" />
                <SignalStat
                  label="Deploy model"
                  value="Cloud-agnostic core"
                />
              </div>
            </div>

            <div className="hidden rounded-lg border border-[var(--ph-border)] bg-[var(--ph-surface)]/92 p-4 shadow-[var(--ph-shadow-lg)] lg:block">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">Healing flow</div>
                  <div className="text-xs text-[var(--ph-muted)]">
                    One incident record from detection to proof
                  </div>
                </div>
                <div className="rounded-md border border-[var(--ph-success-border)] bg-[var(--ph-success-bg)] px-2.5 py-1 text-xs font-semibold text-[var(--ph-success)]">
                  Active
                </div>
              </div>
              <ol className="space-y-3">
                {workflowStages.map((stage, index) => (
                  <FlowStage
                    key={stage.label}
                    index={index + 1}
                    label={stage.label}
                    value={stage.value}
                  />
                ))}
              </ol>
            </div>
          </div>
        </section>

        <section className="mx-auto grid w-full max-w-[1440px] gap-6 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
          <div className="space-y-5">
            <SectionHeading
              icon={Wrench}
              title="Healing paths"
              text="PipelineHealer does not stop at diagnosis. It chooses the strongest action the evidence and policy allow."
            />
            <div className="grid gap-4 sm:grid-cols-2">
              {healingPaths.map((item) => (
                <Card key={item.title} className="min-h-[168px]">
                  <CardHeader className="pb-3">
                    <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]">
                      <item.icon className="h-5 w-5 text-[var(--ph-accent)]" />
                    </div>
                    <CardTitle className="text-base tracking-normal">
                      {item.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-6 text-[var(--ph-muted)]">
                      {item.text}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base tracking-normal">
                <LockKeyhole className="h-4 w-4 text-[var(--ph-accent)]" />
                Current capability map
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {capabilityRows.map((row) => (
                <CapabilityRow
                  key={row.label}
                  label={row.label}
                  value={row.value}
                />
              ))}
            </CardContent>
          </Card>
        </section>

        <section className="border-y border-[var(--ph-border-subtle)] bg-[var(--ph-surface-muted)]">
          <div className="mx-auto grid w-full max-w-[1440px] gap-6 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(320px,0.75fr)_minmax(0,1.25fr)]">
            <SectionHeading
              icon={SearchCheck}
              title="Built for the people who own the run"
              text="The product view is the same whether the work stays in PipelineHealer or moves to an external agent."
            />
            <div className="grid gap-4 md:grid-cols-3">
              {audienceRows.map((row) => (
                <Card key={row.title}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base tracking-normal">
                      {row.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-6 text-[var(--ph-muted)]">
                      {row.text}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto grid w-full max-w-[1440px] gap-6 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base tracking-normal">
                <Workflow className="h-4 w-4 text-[var(--ph-accent)]" />
                Operator surfaces
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SurfaceRow
                title="Dashboard"
                text="See failure mix, recent activity, safety gates, and system posture at a glance."
              />
              <SurfaceRow
                title="Activities"
                text="Trace diagnosis, remediation, handoff messages, external diagnostics, and verification on each incident."
              />
              <SurfaceRow
                title="Settings"
                text="Control repo scope, model routes, auto-fix policy, handoff targets, MCP policy, and write-only secrets."
              />
              <SurfaceRow
                title="Control Center"
                text="Inspect governance, runtime provenance, setup readiness, audit history, and learning signals."
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base tracking-normal">
                <CheckCircle2 className="h-4 w-4 text-[var(--ph-accent)]" />
                Product rules
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <PrincipleRow text="Fix when evidence and policy allow it." />
              <PrincipleRow text="Fall back to a review issue when confidence is weak." />
              <PrincipleRow text="Keep external agent work attached to the PipelineHealer record." />
              <PrincipleRow text="Run on a provider-neutral core; Azure is the reference deployment, not a dependency." />
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}

function HeroBackdrop() {
  return (
    <div aria-hidden className="absolute inset-0">
      <div className="absolute inset-0 opacity-[0.09] [background-image:linear-gradient(var(--ph-border)_1px,transparent_1px),linear-gradient(90deg,var(--ph-border)_1px,transparent_1px)] [background-size:48px_48px]" />
    </div>
  );
}

function SignalStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-surface)]/88 px-4 py-3 shadow-[var(--ph-shadow-sm)]">
      <div className="text-xs text-[var(--ph-muted)]">{label}</div>
      <div className="mt-1 text-sm font-semibold leading-5">{value}</div>
    </div>
  );
}

function FlowStage({
  index,
  label,
  value,
}: {
  index: number;
  label: string;
  value: string;
}) {
  return (
    <li className="flex items-center gap-3 rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/70 px-3 py-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--ph-accent-soft)] text-sm font-semibold text-[var(--ph-accent)]">
        {index}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold">{label}</div>
        <div className="truncate text-xs text-[var(--ph-muted)]">{value}</div>
      </div>
    </li>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  text,
}: {
  icon: typeof Wrench;
  title: string;
  text: string;
}) {
  return (
    <div className="space-y-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]">
        <Icon className="h-5 w-5 text-[var(--ph-accent)]" />
      </div>
      <div>
        <h2 className="text-2xl font-semibold leading-tight sm:text-3xl">
          {title}
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--ph-muted)] sm:text-base">
          {text}
        </p>
      </div>
    </div>
  );
}

function CapabilityRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[var(--ph-border-subtle)] pb-3 last:border-b-0 last:pb-0">
      <span className="text-sm text-[var(--ph-muted)]">{label}</span>
      <span className="max-w-[62%] text-right text-sm font-medium leading-6">
        {value}
      </span>
    </div>
  );
}

function SurfaceRow({ title, text }: { title: string; text: string }) {
  return (
    <div className="border-b border-[var(--ph-border-subtle)] pb-4 last:border-b-0 last:pb-0">
      <div className="font-medium">{title}</div>
      <p className="mt-1 text-sm leading-6 text-[var(--ph-muted)]">{text}</p>
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
