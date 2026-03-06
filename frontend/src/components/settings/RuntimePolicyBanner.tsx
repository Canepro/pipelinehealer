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
            />
            <PolicyFact
              label="Repo scope"
              value={
                data.ph_allowed_repos.length > 0
                  ? `${data.ph_allowed_repos.length} repo${data.ph_allowed_repos.length !== 1 ? "s" : ""}`
                  : "Unrestricted"
              }
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
            />
            <PolicyFact
              label="External diagnostics"
              value={data.gh_aw_tools_enabled ? "Enabled" : "Off"}
            />
            <PolicyFact
              label="Receiver mode"
              value={handoffStatus.label.replace("Handoff: ", "")}
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--ph-muted)]">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>
              Save and Persist keeps mutable settings durable. Startup-only
              settings still require deployment updates.
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

function PolicyFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/45 px-3 py-2">
      <div className="text-xs text-[var(--ph-muted)]">{label}</div>
      <div className="mt-1 text-sm font-medium text-[var(--ph-text)]">
        {value}
      </div>
    </div>
  );
}
