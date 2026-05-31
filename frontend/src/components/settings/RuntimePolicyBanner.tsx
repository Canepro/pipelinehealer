import { AlertTriangle } from "lucide-react";
import type { AppSettings } from "../../api/client";
import {
  formatSettingSource,
  getDurabilityLabel,
  settingSourceTone,
} from "./runtimeSemantics";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  data: AppSettings;
}

export default function RuntimePolicyBanner({ data }: Props) {
  const handoffStatus = !data.agent_handoff_enabled
    ? { label: "Handoff: OFF", variant: "outline" as const }
    : data.agent_handoff_mode === "webhook"
      ? data.agent_handoff_webhook_configured
        ? { label: "Handoff: Webhook", variant: "success" as const }
        : {
            label: "Handoff: Webhook needs URL",
            variant: "destructive" as const,
          }
      : { label: "Handoff: Copy only", variant: "secondary" as const };
  const healModeMeta = data.settings_metadata?.heal_mode;
  const healModeDurability = getDurabilityLabel(healModeMeta);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="py-4 px-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-[var(--ph-text)]">
                Active policy
              </h2>
              <p className="mt-1 text-sm text-[var(--ph-muted)]">
                Current runtime posture, repo scope, and external wiring state.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">Mode: {data.heal_mode}</Badge>
              <Badge variant={handoffStatus.variant}>
                {handoffStatus.label}
              </Badge>
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <PolicyFact
              label="Automation"
              value={data.auto_apply_remediation ? "Enabled" : "Dry-run"}
              tone={data.auto_apply_remediation ? "ok" : "muted"}
            />
            <PolicyFact
              label="Outputs"
              value={
                [
                  data.auto_create_pr ? "PR" : null,
                  data.auto_create_issue ? "Issue" : null,
                  data.auto_retry_workflow ? "Retry" : null,
                ]
                  .filter(Boolean)
                  .join(", ") || "None"
              }
              tone={
                data.auto_create_pr ||
                data.auto_create_issue ||
                data.auto_retry_workflow
                  ? "ok"
                  : "muted"
              }
            />
            <PolicyFact
              label="Repo scope"
              value={
                data.ph_allowed_repos.length > 0
                  ? `${data.ph_allowed_repos.length} repo${data.ph_allowed_repos.length !== 1 ? "s" : ""}`
                  : "Unrestricted"
              }
              tone={data.ph_allowed_repos.length > 0 ? "ok" : "warn"}
            />
            <PolicyFact
              label="MCP posture"
              value={
                data.mcp_enabled
                  ? data.mcp_read_only
                    ? "Enabled · Read-only"
                    : "Enabled · Write-capable"
                  : "Disabled"
              }
              tone={data.mcp_enabled ? "ok" : "muted"}
            />
            <PolicyFact
              label="Jenkins bridge PRs"
              value={
                data.auto_create_pr && data.jenkins_bridge_allow_pr
                  ? "Allowed"
                  : "Issue-first"
              }
            />
            <PolicyFact
              label="Webhook signature"
              value={data.verify_webhook_signature ? "Required" : "Off"}
              tone={data.verify_webhook_signature ? "ok" : "bad"}
            />
            <PolicyFact
              label="External diagnostics"
              value={data.gh_aw_tools_enabled ? "Enabled" : "Off"}
              tone={data.gh_aw_tools_enabled ? "ok" : "muted"}
            />
            <PolicyFact
              label="Receiver mode"
              value={handoffStatus.label.replace("Handoff: ", "")}
              tone={
                handoffStatus.variant === "success"
                  ? "ok"
                  : handoffStatus.variant === "destructive"
                    ? "bad"
                    : "muted"
              }
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--ph-muted)]">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>
              Runtime settings save durably from the UI. Startup-only wiring still belongs in deployment configuration.
            </span>
            {healModeMeta && (
              <>
                <Badge variant={settingSourceTone(healModeMeta.source)}>
                  Heal mode source: {formatSettingSource(healModeMeta.source)}
                </Badge>
                {healModeDurability ? (
                  <Badge variant="outline">{healModeDurability}</Badge>
                ) : null}
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

type PolicyTone = "ok" | "warn" | "bad" | "info" | "muted";

const POLICY_DOT: Record<PolicyTone, string> = {
  ok: "bg-[var(--ph-success)]",
  warn: "bg-[var(--ph-warning)]",
  bad: "bg-[var(--ph-danger)]",
  info: "bg-[var(--ph-info)]",
  muted: "bg-[var(--ph-muted)]",
};

function PolicyFact({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string;
  tone?: PolicyTone;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/40 px-3.5 py-3">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${POLICY_DOT[tone]}`}
          aria-hidden="true"
        />
        <span className="truncate text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--ph-muted)]">
          {label}
        </span>
      </div>
      <span className="text-sm font-semibold text-[var(--ph-text)]">{value}</span>
    </div>
  );
}
