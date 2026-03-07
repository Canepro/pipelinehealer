import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import {
  Copy,
  ExternalLink,
  KeyRound,
  ScrollText,
  ShieldCheck,
  TerminalSquare,
  Workflow,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "../api/client";
import type {
  AppSettingMetadata,
  LearningQueueItem,
  LearningQueueStatus,
} from "../api/client";
import { detectCachedAdminSession } from "../auth/adminSession";
import { useApiAuthReady } from "../auth/apiAuthReady";
import { AUTH_ENABLED } from "../auth/config";
import { AuditTrailPanel } from "../components/settings";
import {
  formatSettingSource,
  formatIntegrationQueryState,
  getDurabilityLabel,
  getMcpEffectiveState,
  type McpPolicyMode,
} from "../components/settings/runtimeSemantics";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type ControlCenterSection = "overview" | "learning_ops" | "audit";
type PostureItem = { label: string; value: string | number };
type SummaryRow = {
  label: string;
  value: string;
  detail?: string;
  mono?: boolean;
  tone?: "default" | "ok" | "warn" | "bad" | "muted";
};

const LOGS_RUNBOOK_URL =
  "https://github.com/Canepro/pipelinehealer/blob/main/docs/LOGS_AND_INVESTIGATION.md";

type InvestigationCommandScope = "Azure" | "Local/Docker";
type InvestigationCommandItem = {
  label: string;
  scope: InvestigationCommandScope;
  command: string;
  note: string;
};

const INVESTIGATION_COMMANDS: InvestigationCommandItem[] = [
  {
    label: "Backend status",
    scope: "Azure",
    command: "bash scripts/ph.sh status",
    note: "Requires Azure CLI login and target resource configuration.",
  },
  {
    label: "Filtered backend logs",
    scope: "Azure",
    command: "bash scripts/ph.sh logs",
    note: "Best default in deployed environments.",
  },
  {
    label: "Search error signatures",
    scope: "Azure",
    command:
      'bash scripts/ph.sh logs:grep --pattern "error|timeout|traceback|401|403"',
    note: "Fast triage path for auth/runtime failures.",
  },
  {
    label: "Settings snapshot",
    scope: "Azure",
    command: "bash scripts/ph.sh settings:check",
    note: "Confirms live effective settings from backend API.",
  },
  {
    label: "Audit timeline",
    scope: "Azure",
    command: "bash scripts/ph.sh settings:audit --limit 10",
    note: "Shows recent settings changes with actor and request id.",
  },
  {
    label: "Filtered backend logs",
    scope: "Local/Docker",
    command: "PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh logs",
    note: "Runs without Azure CLI when backend is local.",
  },
  {
    label: "Search error signatures",
    scope: "Local/Docker",
    command:
      'PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh logs:grep --pattern "error|timeout|traceback"',
    note: "Use same troubleshooting flow for local backend.",
  },
  {
    label: "Settings snapshot",
    scope: "Local/Docker",
    command:
      "PH_BACKEND_URL=http://127.0.0.1:8000 bash scripts/ph.sh settings:check",
    note: "Useful when testing local docker/compose stack.",
  },
];

const TOOL_METADATA: Array<{ key: string; write: boolean; label: string }> = [
  { key: "fetch_failure_context", write: false, label: "Failure Context" },
  { key: "fetch_runbook_context", write: false, label: "Runbook Context" },
  { key: "publish_artifact", write: true, label: "Publish Artifact" },
  { key: "rerun_pipeline", write: true, label: "Rerun Pipeline" },
];

function formatToolPolicy(policy: McpPolicyMode): string {
  switch (policy) {
    case "disabled":
      return "Disabled";
    case "read_only":
      return "Read only";
    case "write_with_approval":
      return "Write with approval";
    case "auto":
      return "Auto";
    default:
      return policy;
  }
}

function toneClass(
  tone:
    | "success"
    | "secondary"
    | "destructive"
    | "outline"
    | "ok"
    | "warn"
    | "bad"
    | "muted",
): string {
  switch (tone) {
    case "success":
    case "ok":
      return "text-[var(--ph-success)]";
    case "secondary":
    case "warn":
      return "text-[var(--ph-warning)]";
    case "destructive":
    case "bad":
      return "text-[var(--ph-danger)]";
    default:
      return "text-[var(--ph-muted)]";
  }
}

function learningStatusTone(
  status: LearningQueueStatus,
): "ok" | "warn" | "bad" | "muted" {
  switch (status) {
    case "active":
      return "ok";
    case "approved":
      return "warn";
    case "rejected":
    case "retired":
      return "bad";
    default:
      return "muted";
  }
}

function learningStatusLabel(status: LearningQueueStatus): string {
  switch (status) {
    case "candidate":
      return "Candidate";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "active":
      return "Active";
    case "retired":
      return "Retired";
    default:
      return status;
  }
}

function learningReadinessReasonLabel(reason: string): string {
  switch (reason) {
    case "status_candidate_requires_approval":
      return "Needs approval before activation";
    case "status_rejected":
      return "Rejected candidate";
    case "status_retired":
      return "Retired candidate";
    case "status_not_approved":
      return "Not approved for activation";
    case "occurrence_below_threshold":
      return "Insufficient recurring occurrences";
    case "success_rate_below_threshold":
      return "Success rate below threshold";
    case "sample_size_below_threshold":
      return "Not enough sample runs";
    default:
      return reason.replace(/_/g, " ");
  }
}

function learningReadinessTone(
  item: LearningQueueItem,
): "ok" | "warn" | "bad" | "muted" {
  const readiness = item.promotion_readiness;
  if (!readiness) return "muted";
  if (readiness.ready) return "ok";
  if (readiness.requires_force_activate) return "warn";
  return "bad";
}

function learningReadinessLabel(item: LearningQueueItem): string {
  const readiness = item.promotion_readiness;
  if (!readiness) return "Readiness unknown";
  if (readiness.ready) return "Promotion ready";
  if (readiness.requires_force_activate) return "Needs review / force activate";
  return "Not ready";
}

function formatMetadataSummary(metadata?: AppSettingMetadata): string {
  if (!metadata) return "No provenance metadata";
  const parts: string[] = [formatSettingSource(metadata.source)];
  if (metadata.sensitive) parts.push("Sensitive");
  const durability = getDurabilityLabel(metadata);
  if (durability) parts.push(durability);
  return parts.join(" · ");
}

function OverviewBlock({
  title,
  items,
}: {
  title: string;
  items: PostureItem[];
}) {
  return (
    <div>
      <div className="mb-3 text-sm font-semibold text-[var(--ph-text)]/90">
        {title}
      </div>
      <div>
        {items.map((item) => (
          <div
            key={`${title}-${item.label}`}
            className="grid min-h-[44px] grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b border-[var(--ph-border)]/55 py-3 last:border-b-0 last:pb-0 first:pt-0"
          >
            <span className="text-sm text-[var(--ph-muted)]">{item.label}</span>
            <span className="text-right text-sm font-semibold text-[var(--ph-text)]/90">
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SummaryRows({
  rows,
  compact = false,
}: {
  rows: SummaryRow[];
  compact?: boolean;
}) {
  return (
    <div>
      {rows.map((row) => (
        <div
          key={`${row.label}-${row.value}`}
          className={
            compact
              ? "grid grid-cols-1 gap-2 border-b border-[var(--ph-border)]/55 py-3 text-sm last:border-b-0 last:pb-0 first:pt-0 sm:grid-cols-[minmax(0,128px)_minmax(0,1fr)]"
              : "grid grid-cols-1 gap-2 border-b border-[var(--ph-border)]/55 py-3 text-sm last:border-b-0 last:pb-0 first:pt-0 sm:grid-cols-[minmax(0,180px)_minmax(0,1fr)]"
          }
        >
          <span className="pt-0.5 text-xs font-medium uppercase tracking-[0.06em] text-[var(--ph-muted)]/90">
            {row.label}
          </span>
          <div
            className={
              compact
                ? "min-w-0 space-y-1"
                : "min-w-0 space-y-1 sm:text-right"
            }
          >
            <span
              className={`block font-medium ${
                row.mono ? "break-all font-mono text-xs" : "break-words"
              } ${
                row.tone === "ok"
                  ? "text-[var(--ph-success)]"
                  : row.tone === "warn"
                    ? "text-[var(--ph-warning)]"
                    : row.tone === "bad"
                      ? "text-[var(--ph-danger)]"
                      : row.tone === "muted"
                        ? "text-[var(--ph-muted)]"
                        : "text-[var(--ph-text)]/90"
              }`}
            >
              {row.value}
            </span>
            {row.detail ? (
              <div className="break-words text-xs leading-5 text-[var(--ph-muted)]">
                {row.detail}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ControlCenterPage() {
  const queryClient = useQueryClient();
  const isApiAuthReady = useApiAuthReady();
  const [adminKeyInput, setAdminKeyInput] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [useSessionAuth, setUseSessionAuth] = useState(false);
  const [activeSection, setActiveSection] =
    useState<ControlCenterSection>("overview");
  const hasAuthAttempt =
    adminKey.length > 0 || (isApiAuthReady && useSessionAuth);
  const effectiveAdminKey = useSessionAuth ? undefined : adminKey;

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: api.getStats,
    retry: 1,
  });

  const { data: recentActivities, isLoading: activitiesLoading } = useQuery({
    queryKey: ["activities", { limit: 8 }],
    queryFn: () => api.getActivities({ limit: 8 }),
  });

  const {
    data: settings,
    isLoading: settingsLoading,
    isError: isSettingsError,
    error: settingsError,
  } = useQuery({
    queryKey: ["control-center-settings", adminKey, useSessionAuth],
    queryFn: () => api.getSettings(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const { data: llmHealth, isLoading: llmLoading } = useQuery({
    queryKey: ["control-center-llm-health", adminKey, useSessionAuth],
    queryFn: () => api.getLLMProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const { data: mcpHealth, isLoading: mcpLoading } = useQuery({
    queryKey: ["control-center-mcp-health", adminKey, useSessionAuth],
    queryFn: () => api.getMCPProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const {
    data: auditEntries,
    isLoading: auditLoading,
    isError: isAuditError,
    error: auditError,
    refetch: refetchAudit,
  } = useQuery({
    queryKey: ["control-center-audit", adminKey, useSessionAuth],
    queryFn: () => api.getSettingsAudit(effectiveAdminKey, 25),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const {
    data: learningQueue,
    isLoading: learningLoading,
    isError: learningError,
    error: learningErrorDetail,
  } = useQuery({
    queryKey: ["control-center-learning-queue", adminKey, useSessionAuth],
    queryFn: () => api.getLearningQueue(effectiveAdminKey, { limit: 20 }),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const {
    data: handoffIntegrationStatus,
    isError: isHandoffIntegrationError,
    error: handoffIntegrationError,
  } = useQuery({
    queryKey: ["control-center-handoff-integration-status", hasAuthAttempt],
    queryFn: () => api.getAgentHandoffIntegrationStatus(),
    enabled: hasAuthAttempt,
    retry: false,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!AUTH_ENABLED || !isApiAuthReady || adminKey.length > 0) {
      return;
    }
    if (detectCachedAdminSession()) {
      setUseSessionAuth(true);
    }
  }, [adminKey.length, isApiAuthReady]);

  const refreshLearningMutation = useMutation({
    mutationFn: () =>
      api.refreshLearningQueue(effectiveAdminKey, {
        lookback_hours: 24 * 14,
        min_occurrences: 2,
        max_scan: 600,
        max_candidates: 120,
      }),
    onSuccess: (result) => {
      toast.success(
        `Learning queue refreshed: ${result.generated_candidates} generated, ${result.upserted_candidates} upserted`,
      );
      void queryClient.invalidateQueries({
        queryKey: ["control-center-learning-queue", adminKey, useSessionAuth],
      });
    },
    onError: (error) => {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to refresh learning queue",
      );
    },
  });

  const decideLearningMutation = useMutation({
    mutationFn: (args: {
      candidateId: string;
      action: "approve" | "reject" | "activate" | "retire" | "reset_candidate";
      forceActivate?: boolean;
    }) =>
      api.decideLearningQueueItem(effectiveAdminKey, args.candidateId, {
        action: args.action,
        force_activate: args.forceActivate,
      }),
    onSuccess: (_item, vars) => {
      toast.success(
        vars.forceActivate
          ? `Learning item updated: ${vars.action} (forced)`
          : `Learning item updated: ${vars.action}`,
      );
      void queryClient.invalidateQueries({
        queryKey: ["control-center-learning-queue", adminKey, useSessionAuth],
      });
      void queryClient.invalidateQueries({
        queryKey: ["control-center-audit", adminKey, useSessionAuth],
      });
    },
    onError: (error) => {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to update learning item",
      );
    },
  });

  const settingsErrorMessage =
    settingsError instanceof Error ? settingsError.message : "Unknown error";
  const sessionAuthActive = AUTH_ENABLED && useSessionAuth;
  const sessionBootstrapPending =
    AUTH_ENABLED && !isApiAuthReady && adminKey.length === 0;
  const sessionAuthDisabledByConfig = useSessionAuth && !AUTH_ENABLED;
  const showSessionRefreshHint =
    useSessionAuth &&
    AUTH_ENABLED &&
    isSettingsError &&
    (() => {
      const normalized = settingsErrorMessage.toLowerCase();
      return (
        normalized.includes("invalid or missing admin api key") ||
        normalized.includes("invalid bearer token") ||
        normalized.includes("missing credentials")
      );
    })();

  const latestActivity = recentActivities?.[0];
  const latestRunUrl =
    latestActivity?.repository_name && latestActivity?.workflow_run_id
      ? `https://github.com/${latestActivity.repository_name}/actions/runs/${latestActivity.workflow_run_id}`
      : null;

  const mcpToolRows = useMemo(() => {
    if (!settings) return [];
    return TOOL_METADATA.map((tool) => {
      const raw = settings.mcp_tool_policies?.[tool.key];
      const policy: McpPolicyMode =
        raw === "disabled" || raw === "auto" || raw === "write_with_approval"
          ? raw
          : "read_only";
      const effective = getMcpEffectiveState({
        mcpEnabled: settings.mcp_enabled,
        mcpProvider: settings.mcp_provider,
        readOnly: settings.mcp_read_only,
        write: tool.write,
        policy,
      });
      return { ...tool, policy, effective };
    });
  }, [settings]);

  const learningQueueSummary = useMemo(() => {
    const items = learningQueue ?? [];
    const counts = {
      candidate: 0,
      approved: 0,
      rejected: 0,
      active: 0,
      retired: 0,
      ready: 0,
    };
    for (const item of items) {
      if (item.status in counts) {
        counts[item.status] += 1;
      }
      if (item.promotion_readiness?.ready) {
        counts.ready += 1;
      }
    }
    return counts;
  }, [learningQueue]);

  const writeToolRows = mcpToolRows.filter((row) => row.write);
  const mcpWriteAutoCount = writeToolRows.filter(
    (row) => row.policy === "auto" && row.effective.status === "allowed",
  ).length;
  const mcpWriteApprovalCount = writeToolRows.filter(
    (row) => row.effective.status === "approval",
  ).length;
  const mcpWriteBlockedCount = writeToolRows.filter(
    (row) => row.effective.status === "blocked",
  ).length;

  const remediationPolicySummary = (() => {
    if (!settings) return "N/A";
    if (!settings.auto_apply_remediation) {
      return "Plan-only mode: remediation actions are generated but not executed.";
    }
    const enabledActions: string[] = [];
    if (settings.auto_create_pr) enabledActions.push("PR");
    if (settings.auto_create_issue) enabledActions.push("Issue");
    if (settings.auto_retry_workflow) enabledActions.push("Retry");
    const actionsLabel =
      enabledActions.length > 0 ? enabledActions.join(", ") : "none";
    if (settings.heal_mode === "safe") {
      return `Safe mode: conservative planning with execution enabled for [${actionsLabel}].`;
    }
    if (settings.heal_mode === "demo") {
      return `Demo mode: aggressive planning with execution enabled for [${actionsLabel}].`;
    }
    if (settings.heal_mode === "freestyle") {
      return `Freestyle mode: aggressive open-ended planning with execution enabled for [${actionsLabel}].`;
    }
    return `Debug mode: safe planning with verbose diagnostics; execution enabled for [${actionsLabel}].`;
  })();

  const mcpWriteSummary = (() => {
    if (!settings) return "N/A";
    if (!settings.mcp_enabled || settings.mcp_provider === "disabled") {
      return "MCP write actions are inactive (provider disabled).";
    }
    if (settings.mcp_read_only)
      return "Global read-only mode blocks all MCP write actions.";
    if (mcpWriteAutoCount > 0) {
      return `${mcpWriteAutoCount} write action(s) can run automatically under current policy.`;
    }
    if (mcpWriteApprovalCount > 0) {
      return `${mcpWriteApprovalCount} write action(s) require explicit approval.`;
    }
    return `${mcpWriteBlockedCount} write action(s) are blocked by policy.`;
  })();

  const providerDefaultModel = (() => {
    if (!settings) return "";
    return settings.llm_provider === "azure_openai"
      ? settings.azure_openai_deployment_name
      : settings.openai_compatible_model;
  })();

  const taskModelPreview = settings
    ? [
        {
          key: "analysis",
          label: "Analysis",
          model:
            settings.llm_model_analysis ||
            providerDefaultModel ||
            "Not configured",
        },
        {
          key: "diagnosis",
          label: "Diagnosis",
          model:
            settings.llm_model_diagnosis ||
            providerDefaultModel ||
            "Not configured",
        },
        {
          key: "remediation",
          label: "Remediation",
          model:
            settings.llm_model_remediation ||
            providerDefaultModel ||
            "Not configured",
        },
      ]
    : [];

  const handoffIntegrationSummary = formatIntegrationQueryState({
    status: handoffIntegrationStatus,
    isError: isHandoffIntegrationError,
    error:
      handoffIntegrationError instanceof Error ? handoffIntegrationError : null,
  });

  const startupDependencyRows: SummaryRow[] = settings
    ? [
        {
          label: "GitHub PAT",
          value: settings.github_pat_configured ? "Configured" : "Not set",
          detail: formatMetadataSummary(
            settings.settings_metadata?.github_pat_configured,
          ),
          tone: settings.github_pat_configured ? "ok" : "muted",
        },
        {
          label: "GitHub App",
          value: settings.github_app_configured ? "Configured" : "Not set",
          detail: formatMetadataSummary(
            settings.settings_metadata?.github_app_configured,
          ),
          tone: settings.github_app_configured ? "ok" : "muted",
        },
        {
          label: "Assign-to-Agent Webhook",
          value: settings.agent_handoff_webhook_configured
            ? settings.agent_handoff_webhook_host || "Configured"
            : "Not configured",
          detail: formatMetadataSummary(
            settings.settings_metadata?.agent_handoff_webhook_host,
          ),
          mono: Boolean(settings.agent_handoff_webhook_host),
          tone: settings.agent_handoff_webhook_configured ? "ok" : "warn",
        },
        {
          label: "OpenAI-Compatible Key",
          value: settings.openai_compatible_api_key_configured
            ? "Configured"
            : "Not set",
          detail: formatMetadataSummary(
            settings.settings_metadata?.openai_compatible_api_key_configured,
          ),
          tone: settings.openai_compatible_api_key_configured ? "ok" : "muted",
        },
      ]
    : [];

  const azureCommands = INVESTIGATION_COMMANDS.filter(
    (item) => item.scope === "Azure",
  );
  const localCommands = INVESTIGATION_COMMANDS.filter(
    (item) => item.scope === "Local/Docker",
  );

  const copyCommand = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      toast.success("Command copied");
    } catch {
      toast.error("Copy failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-[var(--ph-text)]">
          <ShieldCheck className="h-6 w-6 text-[var(--ph-accent)]" />
          Control Center
        </h1>
        <p className="text-sm text-[var(--ph-muted)]">
          Operational governance view for policy posture, provider readiness,
          audit traceability, and investigation access.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-[var(--ph-accent)]" />
            <CardTitle>Admin Access</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Input
              type="password"
              value={adminKeyInput}
              onChange={(e) => setAdminKeyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && adminKeyInput.trim()) {
                  e.preventDefault();
                  setUseSessionAuth(false);
                  setAdminKey(adminKeyInput.trim());
                }
              }}
              placeholder="Enter admin key (X-Admin-Key)"
              className="flex-1"
            />
            <Button
              onClick={() => {
                setUseSessionAuth(false);
                setAdminKey(adminKeyInput.trim());
              }}
              disabled={!adminKeyInput.trim() || settingsLoading}
            >
              {settingsLoading ? "Loading..." : "Load with Admin Key"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setUseSessionAuth(true);
                setAdminKey("");
              }}
              disabled={
                settingsLoading ||
                !AUTH_ENABLED ||
                !isApiAuthReady ||
                sessionAuthActive
              }
            >
              {settingsLoading
                ? "Loading..."
                : sessionAuthActive
                  ? "Using Login Session"
                  : "Use Login Session"}
            </Button>
          </div>
          <p className="mt-2 text-xs text-[var(--ph-muted)]">
            {AUTH_ENABLED ? (
              <>
                {sessionAuthActive ? (
                  <>
                    Signed-in Entra session detected. Control Center is already
                    using it. Enter
                    <code className="mx-1 font-mono">X-Admin-Key</code>
                    only if you need an explicit override.
                  </>
                ) : (
                  <>
                    Read-only page. Use your signed-in Entra session or enter
                    <code className="mx-1 font-mono">X-Admin-Key</code>
                    for troubleshooting. Use Settings for configuration changes,
                    then return here for governance checks.
                  </>
                )}
              </>
            ) : (
              "Session login is disabled in this deployment (VITE_AUTH_MODE=none). Use X-Admin-Key or set VITE_AUTH_MODE=entra in frontend runtime env and redeploy env."
            )}
          </p>
        </CardContent>
      </Card>

      {sessionBootstrapPending && (
        <Card>
          <CardContent className="py-6 text-sm text-[var(--ph-muted)]">
            Preparing your signed-in admin session...
          </CardContent>
        </Card>
      )}

      {!hasAuthAttempt && (
        <Card>
          <CardContent className="py-6 text-sm text-[var(--ph-muted)]">
            Provide an admin key above to load policy posture, provider health,
            and audit records.
          </CardContent>
        </Card>
      )}

      {hasAuthAttempt && settingsLoading && (
        <Card>
          <CardContent className="space-y-3 py-6">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      )}

      {hasAuthAttempt && isSettingsError && (
        <Card className="border-rose-500/30">
          <CardContent className="py-6">
            <p className="text-sm font-medium text-rose-500">
              Failed to load Control Center
            </p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              {settingsErrorMessage}
            </p>
            {showSessionRefreshHint && (
              <p className="mt-3 text-xs text-[var(--ph-muted)]">
                Session may be stale. Try signing out, signing in again, or
                clearing site data and retrying.
              </p>
            )}
            {sessionAuthDisabledByConfig && (
              <p className="mt-3 text-xs text-[var(--ph-muted)]">
                Session tokens are disabled by runtime config. Set
                <code className="mx-1 font-mono">VITE_AUTH_MODE=entra</code> and
                required
                <code className="mx-1 font-mono">VITE_ENTRA_*</code> env vars,
                then redeploy env.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {settings && (
        <>
          <Card>
            <CardContent className="py-5">
              <Tabs
                value={activeSection}
                onValueChange={(value) =>
                  setActiveSection(value as ControlCenterSection)
                }
                className="w-full"
              >
                <TabsList className="grid h-auto w-full grid-cols-1 gap-4 sm:grid-cols-3">
                  <TabsTrigger
                    value="overview"
                    className="py-3 text-sm font-semibold"
                  >
                    Governance Overview
                  </TabsTrigger>
                  <TabsTrigger
                    value="learning_ops"
                    className="py-3 text-sm font-semibold"
                  >
                    Learning & Ops
                  </TabsTrigger>
                  <TabsTrigger
                    value="audit"
                    className="py-3 text-sm font-semibold"
                  >
                    Audit & Trace
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <p className="mt-3 text-sm text-[var(--ph-muted)]">
                {activeSection === "overview" &&
                  "Overview: runtime posture, policy impact, model routing, and MCP policy effect."}
                {activeSection === "learning_ops" &&
                  "Learning & Ops: candidate governance actions and investigation command runbooks."}
                {activeSection === "audit" &&
                  "Audit & Trace: recent settings changes with actor and request-id traceability."}
              </p>
            </CardContent>
          </Card>

          {activeSection === "overview" && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_360px]">
              <div className="space-y-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Governance summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-3 md:grid-cols-2">
                    <OverviewBlock
                      title="Runtime posture"
                      items={[
                        { label: "Heal mode", value: settings.heal_mode },
                        {
                          label: "Auto-apply remediation",
                          value: settings.auto_apply_remediation ? "Yes" : "No",
                        },
                        {
                          label: "Auto-create PR",
                          value: settings.auto_create_pr ? "Yes" : "No",
                        },
                        {
                          label: "Auto-create issue",
                          value: settings.auto_create_issue ? "Yes" : "No",
                        },
                        {
                          label: "Auto-retry workflow",
                          value: settings.auto_retry_workflow ? "Yes" : "No",
                        },
                        {
                          label: "Max attempts",
                          value: settings.max_remediation_attempts,
                        },
                      ]}
                    />
                    <OverviewBlock
                      title="Auth posture"
                      items={[
                        { label: "Auth mode", value: settings.auth_mode },
                        {
                          label: "Entra enabled",
                          value: settings.entra_auth_enabled ? "Yes" : "No",
                        },
                        {
                          label: "Admin roles",
                          value: settings.entra_admin_roles.length,
                        },
                        {
                          label: "Admin API auth",
                          value: settings.admin_api_auth_enabled ? "On" : "Off",
                        },
                        {
                          label: "Webhook signature",
                          value: settings.verify_webhook_signature
                            ? "Required"
                            : "Off",
                        },
                      ]}
                    />
                    <OverviewBlock
                      title="Provider readiness"
                      items={[
                        {
                          label: "LLM",
                          value: llmLoading
                            ? "Checking..."
                            : llmHealth?.available
                              ? "Available"
                              : "Unavailable",
                        },
                        {
                          label: "MCP",
                          value: mcpLoading
                            ? "Checking..."
                            : mcpHealth?.available
                              ? "Available"
                              : "Unavailable",
                        },
                        { label: "MCP provider", value: settings.mcp_provider },
                        {
                          label: "MCP read-only",
                          value: settings.mcp_read_only ? "Yes" : "No",
                        },
                      ]}
                    />
                    <OverviewBlock
                      title="Ops snapshot"
                      items={[
                        {
                          label: "Runs processed",
                          value: statsLoading
                            ? "..."
                            : (stats?.total_runs_processed ?? 0),
                        },
                        {
                          label: "Safety gated",
                          value: statsLoading
                            ? "..."
                            : (stats?.safety_blocked_remediations ?? 0),
                        },
                        {
                          label: "Diagnostics wait",
                          value: `${settings.external_diagnostics_wait_seconds}s`,
                        },
                        {
                          label: "Poll interval",
                          value: `${settings.external_diagnostics_poll_interval_seconds}s`,
                        },
                      ]}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Policy impact preview
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                    <SummaryRows
                      rows={[
                        {
                          label: "Remediation path",
                          value: remediationPolicySummary,
                        },
                        {
                          label: "Diagnostics cadence",
                          value: `wait ${settings.external_diagnostics_wait_seconds}s / poll ${settings.external_diagnostics_poll_interval_seconds}s`,
                        },
                        {
                          label: "MCP write posture",
                          value: mcpWriteSummary,
                        },
                        {
                          label: "Repo scope",
                          value:
                            settings.ph_allowed_repos.length === 0
                              ? "All repositories (no allowlist)"
                              : `${settings.ph_allowed_repos.length} allowlisted repository entries`,
                        },
                      ]}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Workflow className="h-4 w-4 text-[var(--ph-accent)]" />
                      MCP tool policy effect
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {mcpToolRows.map((row) => (
                      <div
                        key={row.key}
                        className="grid grid-cols-1 gap-2 rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/30 p-3 text-sm lg:grid-cols-[180px_minmax(0,1fr)_160px]"
                      >
                        <div className="font-medium text-[var(--ph-text)]">
                          {row.label}
                        </div>
                        <div className="text-[var(--ph-muted)]">
                          Configured: {formatToolPolicy(row.policy)}
                        </div>
                        <div
                          className={`${toneClass(row.effective.tone)} font-medium`}
                        >
                          Effective: {row.effective.summary}
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              <div className="flex flex-col gap-4">
                <Card className="overflow-hidden">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Task model routing
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                    <SummaryRows
                      rows={[
                        { label: "Provider", value: settings.llm_provider },
                        {
                          label: "Default model",
                          value: providerDefaultModel || "Not configured",
                        },
                      ]}
                    />
                    <div className="space-y-2">
                      {taskModelPreview.map((task) => (
                        <div
                          key={task.key}
                          className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/30 p-3"
                        >
                          <div className="text-sm font-medium text-[var(--ph-text)]">
                            {task.label}
                          </div>
                          <div className="mt-1 break-words font-mono text-xs text-[var(--ph-muted)]">
                            {task.model}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <Card className="overflow-hidden">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Integration gateway status
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                    <SummaryRows
                      compact
                      rows={[
                        {
                          label: "Receiver",
                          value: handoffIntegrationSummary.summary,
                          detail: handoffIntegrationSummary.detail,
                          tone: handoffIntegrationSummary.tone,
                        },
                        {
                          label: "Webhook host",
                          value:
                            handoffIntegrationStatus?.webhook_host ||
                            "Not configured",
                          mono: Boolean(handoffIntegrationStatus?.webhook_host),
                          tone: handoffIntegrationStatus?.webhook_host
                            ? "ok"
                            : "muted",
                        },
                        {
                          label: "Notification targets",
                          value: handoffIntegrationStatus?.notifications
                            ? `${handoffIntegrationStatus.notifications.enabled_targets} enabled · ${handoffIntegrationStatus.notifications.invalid_targets} invalid`
                            : "No receiver probe data",
                          detail: handoffIntegrationStatus?.notifications
                            ?.supported_target_types.length
                            ? `Supported sinks: ${handoffIntegrationStatus.notifications.supported_target_types.join(
                                ", ",
                              )}`
                            : undefined,
                          tone: handoffIntegrationStatus?.notifications
                            ?.invalid_targets
                            ? "warn"
                            : handoffIntegrationStatus?.notifications
                              ? "ok"
                              : "muted",
                        },
                      ]}
                    />
                  </CardContent>
                </Card>

                <Card className="overflow-hidden">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Startup-managed dependencies
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                    <SummaryRows compact rows={startupDependencyRows} />
                    <p className="text-xs text-[var(--ph-muted)]">
                      Portable provenance rule: the UI reports startup-managed
                      config and sensitive presence signals, but it does not
                      assume a platform-specific secret adapter.
                    </p>
                  </CardContent>
                </Card>

                <Card className="overflow-hidden">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ScrollText className="h-4 w-4 text-[var(--ph-accent)]" />
                      Next actions
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-2">
                    <Button asChild size="sm">
                      <Link to="/app/settings">Open Settings</Link>
                    </Button>
                    <Button asChild size="sm" variant="secondary">
                      <Link to="/app/activities">Review Activities</Link>
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {activeSection === "learning_ops" && (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.15fr)_420px]">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Learning queue</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-[var(--ph-muted)]">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={refreshLearningMutation.isPending}
                      onClick={() => refreshLearningMutation.mutate()}
                    >
                      {refreshLearningMutation.isPending
                        ? "Refreshing..."
                        : "Refresh candidates"}
                    </Button>
                    <Badge variant="outline">
                      Candidate: {learningQueueSummary.candidate}
                    </Badge>
                    <Badge variant="outline">
                      Approved: {learningQueueSummary.approved}
                    </Badge>
                    <Badge variant="outline">
                      Active: {learningQueueSummary.active}
                    </Badge>
                    <Badge variant="outline">
                      Ready: {learningQueueSummary.ready}
                    </Badge>
                  </div>

                  {learningLoading && <p>Loading learning queue...</p>}
                  {learningError && (
                    <p className="text-rose-400">
                      {learningErrorDetail instanceof Error
                        ? learningErrorDetail.message
                        : "Failed to load learning queue"}
                    </p>
                  )}
                  {!learningLoading &&
                    !learningError &&
                    (learningQueue?.length ?? 0) === 0 && (
                      <p>
                        No learning candidates yet. Use{" "}
                        <span className="font-medium text-[var(--ph-text)]">
                          Refresh candidates
                        </span>{" "}
                        after successful runs to generate governance-reviewed
                        candidates.
                      </p>
                    )}

                  <div className="space-y-3">
                    {(learningQueue ?? []).slice(0, 8).map((item) => (
                      <LearningQueueItemRow
                        key={item.id}
                        item={item}
                        decidePending={decideLearningMutation.isPending}
                        onApprove={() =>
                          decideLearningMutation.mutate({
                            candidateId: item.id,
                            action: "approve",
                          })
                        }
                        onActivate={() =>
                          decideLearningMutation.mutate({
                            candidateId: item.id,
                            action: "activate",
                          })
                        }
                        onForceActivate={() => {
                          const ok = window.confirm(
                            "Force-activate this playbook candidate? This bypasses readiness gates and will be audit logged.",
                          );
                          if (!ok) return;
                          decideLearningMutation.mutate({
                            candidateId: item.id,
                            action: "activate",
                            forceActivate: true,
                          });
                        }}
                        onReject={() =>
                          decideLearningMutation.mutate({
                            candidateId: item.id,
                            action: "reject",
                          })
                        }
                        onRetire={() =>
                          decideLearningMutation.mutate({
                            candidateId: item.id,
                            action: "retire",
                          })
                        }
                      />
                    ))}
                  </div>
                </CardContent>
              </Card>

              <div className="space-y-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Integration gateway status
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                    <SummaryRows
                      compact
                      rows={[
                        {
                          label: "Receiver",
                          value: handoffIntegrationSummary.summary,
                          detail: handoffIntegrationSummary.detail,
                          tone: handoffIntegrationSummary.tone,
                        },
                        {
                          label: "Webhook host",
                          value:
                            handoffIntegrationStatus?.webhook_host ||
                            "Not configured",
                          mono: Boolean(handoffIntegrationStatus?.webhook_host),
                          tone: handoffIntegrationStatus?.webhook_host
                            ? "ok"
                            : "muted",
                        },
                        {
                          label: "Notification targets",
                          value: handoffIntegrationStatus?.notifications
                            ? `${handoffIntegrationStatus.notifications.enabled_targets} enabled · ${handoffIntegrationStatus.notifications.invalid_targets} invalid`
                            : "No receiver probe data",
                          detail: handoffIntegrationStatus?.notifications
                            ?.supported_target_types.length
                            ? `Supported sinks: ${handoffIntegrationStatus.notifications.supported_target_types.join(
                                ", ",
                              )}`
                            : undefined,
                          tone: handoffIntegrationStatus?.notifications
                            ?.invalid_targets
                            ? "warn"
                            : handoffIntegrationStatus?.notifications
                              ? "ok"
                              : "muted",
                        },
                      ]}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <TerminalSquare className="h-4 w-4 text-[var(--ph-accent)]" />
                      Logs and investigation access
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Button asChild size="sm" variant="secondary">
                        <a
                          href={LOGS_RUNBOOK_URL}
                          rel="noopener noreferrer"
                          target="_blank"
                        >
                          Logs Runbook
                          <ExternalLink className="ml-1 h-3.5 w-3.5" />
                        </a>
                      </Button>
                      {latestRunUrl && (
                        <Button asChild size="sm" variant="ghost">
                          <a
                            href={latestRunUrl}
                            rel="noopener noreferrer"
                            target="_blank"
                          >
                            Latest Workflow Run
                            <ExternalLink className="ml-1 h-3.5 w-3.5" />
                          </a>
                        </Button>
                      )}
                    </div>

                    <div className="space-y-3">
                      <CommandScopeBlock
                        title="Azure deployment commands"
                        description="Use these when your backend is deployed to Azure Container Apps."
                        commands={azureCommands}
                        onCopy={copyCommand}
                      />
                      <CommandScopeBlock
                        title="Local and Docker commands"
                        description="Use these when testing with a local backend and no Azure CLI."
                        commands={localCommands}
                        onCopy={copyCommand}
                      />
                    </div>

                    <div className="text-xs text-[var(--ph-muted)]">
                      Commands stay grouped by execution scope so operators can
                      avoid Azure-only paths during local troubleshooting.
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {activeSection === "audit" && (
            <div className="space-y-4">
              <AuditTrailPanel
                canLoad={hasAuthAttempt}
                entries={auditEntries}
                isLoading={auditLoading}
                isError={isAuditError}
                error={isAuditError ? (auditError as Error) : null}
                onLoad={() => {
                  void refetchAudit();
                }}
                title="Audit Timeline"
                description="Recent settings changes with actor and request trace. Use this as the primary governance feed."
                defaultVisibleCount={5}
                pageSize={5}
                defaultExpanded={true}
              />
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <ScrollText className="h-4 w-4 text-[var(--ph-accent)]" />
                    Next Actions
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                  <Button asChild size="sm">
                    <Link to="/app/settings">Open Settings</Link>
                  </Button>
                  <Button asChild size="sm" variant="secondary">
                    <Link to="/app/activities">Review Activities</Link>
                  </Button>
                </CardContent>
              </Card>
            </div>
          )}
        </>
      )}

      {!settings && hasAuthAttempt && activitiesLoading && (
        <Card>
          <CardContent className="py-6">
            <Skeleton className="h-5 w-64" />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function CommandScopeBlock({
  title,
  description,
  commands,
  onCopy,
}: {
  title: string;
  description: string;
  commands: InvestigationCommandItem[];
  onCopy: (command: string) => void;
}) {
  return (
    <div className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/20 p-3">
      <div className="mb-2">
        <p className="text-sm font-medium text-[var(--ph-text)]">{title}</p>
        <p className="text-xs text-[var(--ph-muted)]">{description}</p>
      </div>
      <div className="space-y-2">
        {commands.map((item) => (
          <div
            key={`${item.scope}-${item.label}-${item.command}`}
            className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)] px-3 py-2"
          >
            <div className="mb-1 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-[var(--ph-text)]">
                  {item.label}
                </span>
                <Badge variant="outline" className="text-[10px]">
                  {item.scope}
                </Badge>
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onCopy(item.command)}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
            <code className="block overflow-x-auto text-xs text-[var(--ph-text)]">
              {item.command}
            </code>
            <p className="mt-1 text-[11px] text-[var(--ph-muted)]">
              {item.note}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function LearningQueueItemRow({
  item,
  decidePending,
  onApprove,
  onActivate,
  onForceActivate,
  onReject,
  onRetire,
}: {
  item: LearningQueueItem;
  decidePending: boolean;
  onApprove: () => void;
  onActivate: () => void;
  onForceActivate: () => void;
  onReject: () => void;
  onRetire: () => void;
}) {
  return (
    <div className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/25 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="break-words font-medium text-[var(--ph-text)]">
            {item.title}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge variant="outline">Runs: {item.occurrence_count}</Badge>
            <Badge variant="outline">
              Success: {item.success_count}/{item.occurrence_count}
            </Badge>
            <Badge variant="outline">Action: {item.proposed_action}</Badge>
            <Badge
              variant="outline"
              className={toneClass(learningReadinessTone(item))}
            >
              {learningReadinessLabel(item)}
            </Badge>
          </div>
        </div>
        <Badge
          variant="outline"
          className={toneClass(learningStatusTone(item.status))}
        >
          {learningStatusLabel(item.status)}
        </Badge>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="space-y-2 text-xs text-[var(--ph-muted)]">
          <p className="break-words">{item.suggested_playbook}</p>
          {item.promotion_readiness && (
            <>
              <p>
                {item.promotion_readiness.occurrence_count}/
                {item.promotion_readiness.min_occurrences} runs
                {" · "}
                {(item.promotion_readiness.success_rate * 100).toFixed(0)}%/
                {(item.promotion_readiness.min_success_rate * 100).toFixed(0)}%
                success
              </p>
              {item.promotion_readiness.reasons.length > 0 && (
                <p className="break-words">
                  {item.promotion_readiness.reasons
                    .map((reason) => learningReadinessReasonLabel(reason))
                    .join(" · ")}
                </p>
              )}
            </>
          )}
        </div>

        {/* Keep actions grouped so the queue reads as an operator worklist, not a card gallery. */}
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <Button
            size="sm"
            variant="ghost"
            disabled={
              decidePending ||
              item.status === "approved" ||
              item.status === "active"
            }
            onClick={onApprove}
          >
            Approve
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={
              decidePending ||
              item.status === "active" ||
              !item.promotion_readiness?.ready
            }
            onClick={onActivate}
          >
            Activate
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={
              decidePending ||
              item.status === "active" ||
              !item.promotion_readiness?.requires_force_activate
            }
            onClick={onForceActivate}
          >
            Force Activate
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={
              decidePending ||
              item.status === "rejected" ||
              item.status === "retired"
            }
            onClick={onReject}
          >
            Reject
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={decidePending || item.status === "retired"}
            onClick={onRetire}
          >
            Retire
          </Button>
        </div>
      </div>
    </div>
  );
}
