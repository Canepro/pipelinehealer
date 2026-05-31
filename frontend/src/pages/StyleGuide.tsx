import { useState } from "react";
import { Activity, Database, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { StatTile, StatusPill, StatusDot, type Tone } from "@/components/ui/status";
import { EmptyState } from "@/components/ui/empty-state";
import { useConfirm } from "@/components/ui/use-confirm";
import { CHART_PALETTE } from "@/components/charts/palette";

const TONES: Tone[] = ["ok", "warn", "bad", "info", "neutral"];
const SURFACES = [
  ["Page", "--ph-bg"],
  ["Elevated", "--ph-bg-elevated"],
  ["Surface", "--ph-surface"],
  ["Border", "--ph-border"],
  ["Accent", "--ph-accent"],
] as const;

function Swatch({ token, label }: { token: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-7 w-7 rounded-md border border-[var(--ph-border)]"
        style={{ background: `var(${token})` }}
      />
      <div className="text-xs">
        <div className="font-medium text-[var(--ph-text)]">{label}</div>
        <div className="font-mono text-[var(--ph-muted)]">{token}</div>
      </div>
    </div>
  );
}

export default function StyleGuide() {
  const { confirm, dialog } = useConfirm();
  const [confirmResult, setConfirmResult] = useState<string>("");

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10 sm:px-6">
      {dialog}
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ph-accent)]">
          Design system
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[var(--ph-text)]">
          PipelineHealer console styleguide
        </h1>
        <p className="mt-1 text-sm text-[var(--ph-muted)]">
          The shared primitives every operator surface is built from. Toggle your
          OS light/dark to check both themes.
        </p>
      </header>

      <Panel>
        <PanelHeader title="Surfaces and accent" />
        <PanelBody className="flex flex-wrap gap-5">
          {SURFACES.map(([label, token]) => (
            <Swatch key={token} token={token} label={label} />
          ))}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Data-viz palette" description="Categorical, theme-aware." />
        <PanelBody className="flex flex-wrap gap-3">
          {CHART_PALETTE.map((c, i) => (
            <div key={c} className="flex items-center gap-2">
              <span
                className="h-7 w-7 rounded-md"
                style={{ background: c }}
              />
              <span className="font-mono text-xs text-[var(--ph-muted)]">
                chart-{i + 1}
              </span>
            </div>
          ))}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Status language" description="One tone scale across dots, pills, and tiles." />
        <PanelBody className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            {TONES.map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5 text-xs text-[var(--ph-muted)]">
                <StatusDot tone={t} /> {t}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {TONES.map((t) => (
              <StatusPill key={t} tone={t}>
                {t}
              </StatusPill>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            <StatTile label="Heal mode" value="safe" tone="ok" />
            <StatTile label="Webhook signature" value="Off" tone="bad" />
            <StatTile label="Repo scope" value="Unrestricted" tone="warn" />
            <StatTile label="Safety gated" value="18" tone="info" />
            <StatTile label="GitHub App" value="Not set" tone="neutral" detail="Default" />
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Panel with header actions"
          description="Title, description, and right-aligned actions."
          icon={<Activity className="h-4 w-4" />}
          actions={
            <>
              <StatusPill tone="ok">Healthy</StatusPill>
              <Button size="sm" variant="secondary">
                Action
              </Button>
            </>
          }
        />
        <PanelBody>
          <p className="text-sm text-[var(--ph-muted)]">
            Panel body content sits here on the standard surface.
          </p>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Controls" />
        <PanelBody className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Destructive</Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge>Default</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="success">Success</Badge>
            <Badge variant="destructive">Destructive</Badge>
            <Badge variant="outline">Outline</Badge>
          </div>
          <Input placeholder="Themed input" className="max-w-sm" />
          <div className="flex items-center gap-3">
            <Button
              variant="destructive"
              size="sm"
              onClick={async () => {
                const ok = await confirm({
                  title: "Force-activate this playbook?",
                  description:
                    "This bypasses readiness gates and will be audit logged.",
                  confirmLabel: "Force activate",
                  destructive: true,
                });
                setConfirmResult(ok ? "confirmed" : "cancelled");
              }}
            >
              Open confirm dialog
            </Button>
            {confirmResult ? (
              <span className="text-sm text-[var(--ph-muted)]">
                Result: {confirmResult}
              </span>
            ) : null}
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Empty state" />
        <EmptyState
          icon={<GitBranch className="h-5 w-5" />}
          title="No activities yet"
          description="When PipelineHealer processes a run, it will appear here."
          action={
            <Button size="sm" variant="secondary">
              <Database className="h-4 w-4" />
              Open demo repo
            </Button>
          }
        />
      </Panel>
    </div>
  );
}
