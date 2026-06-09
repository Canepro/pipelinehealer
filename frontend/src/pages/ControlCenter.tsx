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
  TriangleAlert,
  Workflow,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "../api/client";
import { getActivitySourceInfo } from "../utils/activitySource";
import { copyToClipboard } from "../utils/copyToClipboard";
import type {
  Activity,
  AppSettingMetadata,
  DashboardStats,
  LearningQueueItem,
  LearningQueueStatus,
} from "../api/client";
import { detectCachedAdminSession } from "../auth/adminSession";
import { useApiAuthReady } from "../auth/apiAuthReady";
import { AUTH_ENABLED } from "../auth/config";
import { AuditTrailPanel } from "../components/settings";
import {
  describeLlmCapability,
  formatSettingSource,
  formatLlmValidationLabel,
  formatIntegrationQueryState,
  getDurabilityLabel,
  getMcpEffectiveState,
  type McpPolicyMode,
} from "../components/settings/runtimeSemantics";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile, type Tone } from "@/components/ui/status";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useConfirm } from "@/components/ui/use-confirm";

type ControlCenterSection =
  | "overview"
  | "learning_ops"
  | "trust_ops"
  | "audit";
type PostureItem = { label: string; value: string | number };
type SummaryRow = {
  label: string;
  value: string;
  detail?: string;
  mono?: boolean;
  tone?: "default" | "ok" | "warn" | "bad" | "muted";
};

type TrustMetric = {
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "ok" | "warn" | "bad" | "muted";
};

type ReviewQueueItem = {
  activity: Activity;
  title: string;
  reason: string;
  detail: string;
  priority: "high" | "medium";
  tone: "warn" | "bad" | "muted";
};

const LOGS_RUNBOOK_URL =
  "https://github.com/Canepro/pipelinehealer/blob/main/docs/runbooks/LOGS_AND_INVESTIGATION.md";

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

function normalizeVerificationOutcome(value: unknown): string | null {
  return value === "pass" || value === "partial" || value === "fail"
    ? value
    : null;
}

function normalizeGuidanceEffectiveness(value: unknown): string | null {
  return value === "helped" || value === "neutral" || value === "hurt"
    ? value
    : null;
}

function extractActivityVerification(
  activity: Activity,
): Record<string, unknown> | null {
  const payload = activity.remediation_result?.details?.verification;
  return payload && typeof payload === "object"
    ? (payload as Record<string, unknown>)
    : null;
}

function extractAppliedLearningContext(
  activity: Activity,
): Record<string, unknown> | null {
  const payload = activity.remediation_result?.details?.applied_learning_context;
  return payload && typeof payload === "object"
    ? (payload as Record<string, unknown>)
    : null;
}

function formatActionLabel(value: string | undefined): string {
  if (!value) return "Unknown";
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .replace(/\bPr\b/, "PR");
}

function createReviewQueue(
  activities: Activity[] | undefined,
): ReviewQueueItem[] {
  if (!activities) return [];
  const queue: ReviewQueueItem[] = [];
  for (const activity of activities) {
    const verification = extractActivityVerification(activity);
    const appliedLearning = extractAppliedLearningContext(activity);
    const overall = normalizeVerificationOutcome(verification?.overall);
    const guidanceEffectiveness = normalizeGuidanceEffectiveness(
      verification?.guidance_effectiveness,
    );
    const confidence = activity.diagnosis?.confidence ?? 0;
    const remediation = activity.remediation_result;

    if (guidanceEffectiveness === "hurt") {
      queue.push({
        activity,
        title: "Guidance was rated harmful",
        reason: "Operator feedback says the promoted playbook created noise or regression risk.",
        detail:
          typeof verification?.notes === "string" && verification.notes.trim()
            ? verification.notes
            : "Review this incident and consider retiring or demoting the linked learning candidate.",
        priority: "high",
        tone: "bad",
      });
    }

    if (
      remediation &&
      !remediation.success &&
      remediation.action_taken !== "skip"
    ) {
      queue.push({
        activity,
        title: "Remediation publish failed",
        reason: `${formatActionLabel(remediation.action_taken)} did not complete successfully.`,
        detail:
          remediation.error_message ||
          "Inspect the remediation result and related artifact publication path.",
        priority: "high",
        tone: "bad",
      });
    }

    if (remediation?.action_taken === "create_issue" && confidence < 0.85) {
      queue.push({
        activity,
        title: "Issue-only low-confidence diagnosis",
        reason: `Diagnosis confidence is ${Math.round(confidence * 100)}% and the run stayed review-only.`,
        detail:
          activity.diagnosis?.root_cause ||
          "Review the underlying evidence before acting on this issue.",
        priority: "medium",
        tone: "warn",
      });
    }

    const remediationDetails =
      remediation?.details && typeof remediation.details === "object"
        ? (remediation.details as Record<string, unknown>)
        : null;
    if (remediationDetails?.reused_existing_issue === true) {
      queue.push({
        activity,
        title: "Reused existing review issue",
        reason:
          "PipelineHealer deduplicated this failure against an already-open generated issue.",
        detail:
          typeof remediation.issue_url === "string"
            ? remediation.issue_url
            : "Inspect the linked issue for current status.",
        priority: "medium",
        tone: "warn",
      });
    }
    if (
      Array.isArray(remediationDetails?.linked_pull_request_numbers) &&
      remediationDetails.linked_pull_request_numbers.length > 0
    ) {
      queue.push({
        activity,
        title: "Generated issue linked to active PR",
        reason:
          "A human or automated PR was linked for auto-close when it merges.",
        detail: `#${remediationDetails.linked_pull_request_numbers.join(", #")}`,
        priority: "medium",
        tone: "warn",
      });
    }

    if (appliedLearning && !overall) {
      queue.push({
        activity,
        title: "Applied guidance still needs verification",
        reason: "A promoted playbook influenced remediation, but no operator verification has been recorded yet.",
        detail:
          typeof appliedLearning.title === "string"
            ? appliedLearning.title
            : typeof appliedLearning.id === "string"
              ? appliedLearning.id
              : "Review this guided run and record whether the guidance helped.",
        priority: "medium",
        tone: "warn",
      });
    }

    if (
      activity.diagnosis &&
      confidence < 0.7 &&
      remediation &&
      remediation.action_taken !== "create_issue" &&
      remediation.action_taken !== "skip"
    ) {
      queue.push({
        activity,
        title: "Very low-confidence automated handling",
        reason: `Diagnosis confidence is ${Math.round(confidence * 100)}%.`,
        detail:
          "This run crossed into automated handling despite a weak diagnosis. Check whether the artifact was appropriate.",
        priority: "high",
        tone: "bad",
      });
    }
  }

  return queue
    .sort((a, b) => {
      const priorityDelta =
        (a.priority === "high" ? 0 : 1) - (b.priority === "high" ? 0 : 1);
      if (priorityDelta !== 0) return priorityDelta;
      return (
        Date.parse(b.activity.updated_at) - Date.parse(a.activity.updated_at)
      );
    })
    .slice(0, 10);
}

function buildTrustMetrics(
  stats: DashboardStats | undefined,
  activities: Activity[] | undefined,
  learningQueue: LearningQueueItem[] | undefined,
): TrustMetric[] {
  const items = activities ?? [];
  let identificationVerified = 0;
  let identificationPass = 0;
  let diagnosisVerified = 0;
  let diagnosisPass = 0;
  let remediationVerified = 0;
  let remediationPass = 0;
  let guidanceFeedbackCount = 0;
  let guidanceHelpedCount = 0;
  let guidanceHurtCount = 0;

  for (const activity of items) {
    const verification = extractActivityVerification(activity);
    const identification = normalizeVerificationOutcome(
      verification?.identification,
    );
    const diagnosis = normalizeVerificationOutcome(verification?.diagnosis);
    const remediation = normalizeVerificationOutcome(verification?.remediation);
    const guidance = normalizeGuidanceEffectiveness(
      verification?.guidance_effectiveness,
    );

    if (identification) {
      identificationVerified += 1;
      if (identification === "pass") identificationPass += 1;
    }
    if (diagnosis) {
      diagnosisVerified += 1;
      if (diagnosis === "pass") diagnosisPass += 1;
    }
    if (remediation) {
      remediationVerified += 1;
      if (remediation === "pass") remediationPass += 1;
    }
    if (guidance) {
      guidanceFeedbackCount += 1;
      if (guidance === "helped") guidanceHelpedCount += 1;
      if (guidance === "hurt") guidanceHurtCount += 1;
    }
  }

  const activeCandidates = (learningQueue ?? []).filter(
    (item) => item.status === "active",
  );
  const activeGuidanceApplications = activeCandidates.reduce(
    (total, item) => total + item.guidance_application_count,
    0,
  );
  const activeGuidanceFeedback = activeCandidates.reduce(
    (total, item) => total + item.guidance_feedback_count,
    0,
  );

  const topFailureType = stats
    ? Object.entries(stats.by_failure_type ?? {}).sort((a, b) => b[1] - a[1])[0]
    : null;

  const pct = (pass: number, total: number): string =>
    total > 0 ? `${Math.round((pass / total) * 100)}%` : "N/A";

  return [
    {
      label: "Identification accuracy",
      value: pct(identificationPass, identificationVerified),
      detail:
        identificationVerified > 0
          ? `${identificationPass}/${identificationVerified} verified incidents marked identification as correct.`
          : "No operator identification feedback recorded in the current activity window.",
      tone:
        identificationVerified === 0
          ? "muted"
          : identificationPass / identificationVerified >= 0.8
            ? "ok"
            : "warn",
    },
    {
      label: "Diagnosis accuracy",
      value: pct(diagnosisPass, diagnosisVerified),
      detail:
        diagnosisVerified > 0
          ? `${diagnosisPass}/${diagnosisVerified} verified incidents marked diagnosis as correct.`
          : "No diagnosis verification data is available yet.",
      tone:
        diagnosisVerified === 0
          ? "muted"
          : diagnosisPass / diagnosisVerified >= 0.75
            ? "ok"
            : "warn",
    },
    {
      label: "Remediation usefulness",
      value: pct(remediationPass, remediationVerified),
      detail:
        remediationVerified > 0
          ? `${remediationPass}/${remediationVerified} verified incidents rated the remediation outcome as correct.`
          : "No remediation verification data is available yet.",
      tone:
        remediationVerified === 0
          ? "muted"
          : remediationPass / remediationVerified >= 0.7
            ? "ok"
            : "warn",
    },
    {
      label: "Guidance help rate",
      value:
        guidanceFeedbackCount > 0
          ? `${Math.round((guidanceHelpedCount / guidanceFeedbackCount) * 100)}%`
          : "N/A",
      detail:
        guidanceFeedbackCount > 0
          ? `${guidanceHelpedCount} helped, ${guidanceHurtCount} hurt, across ${guidanceFeedbackCount} operator-rated guided runs.`
          : "No operator guidance feedback has been recorded yet.",
      tone:
        guidanceFeedbackCount === 0
          ? "muted"
          : guidanceHurtCount > guidanceHelpedCount
            ? "bad"
            : "ok",
    },
    {
      label: "Guided run coverage",
      value: `${activeGuidanceFeedback}/${activeGuidanceApplications}`,
      detail:
        activeGuidanceApplications > 0
          ? `${activeGuidanceFeedback} of ${activeGuidanceApplications} active-playbook runs have explicit operator guidance feedback.`
          : "No active playbook guidance applications have been recorded yet.",
      tone:
        activeGuidanceApplications === 0
          ? "muted"
          : activeGuidanceFeedback / activeGuidanceApplications >= 0.6
            ? "ok"
            : "warn",
    },
    {
      label: "Noisiest failure class",
      value: topFailureType
        ? `${topFailureType[0]} (${topFailureType[1]})`
        : "N/A",
      detail: topFailureType
        ? "Use this to decide which failure class needs better heuristics, guidance, or operator runbooks next."
        : "No failure breakdown is available.",
      tone: topFailureType ? "default" : "muted",
    },
  ];
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
    <div className="space-y-2.5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--ph-muted)]">
        {title}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {items.map((item) => (
          <div
            key={`${title}-${item.label}`}
            className="rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/35 px-3 py-2.5"
          >
            <div className="text-[11px] leading-tight text-[var(--ph-muted)]">
              {item.label}
            </div>
            <div className="mt-1 text-sm font-semibold text-[var(--ph-text)]">
              {item.value}
            </div>
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
    <div className={compact ? "space-y-2.5" : "space-y-3"}>
      {rows.map((row) => (
        <div
          key={`${row.label}-${row.value}`}
          className="rounded-md bg-[var(--ph-bg-elevated)]/24 px-3 py-2.5 shadow-[inset_0_0_0_1px_var(--ph-border-subtle)]"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--ph-muted)]">
            {row.label}
          </span>
          <div className="mt-1 min-w-0">
            <span
              className={`block font-medium ${
                row.mono ? "break-all font-mono text-xs" : "break-words text-sm"
              } ${
                row.tone === "ok"
                  ? "text-[var(--ph-success)]"
                  : row.tone === "warn"
                    ? "text-[var(--ph-warning)]"
                    : row.tone === "bad"
                      ? "text-[var(--ph-danger)]"
                      : row.tone === "muted"
                        ? "text-[var(--ph-muted)]"
                        : "text-[var(--ph-text)]"
              }`}
            >
              {row.value}
            </span>
            {row.detail ? (
              <div className="mt-1 break-words text-xs leading-5 text-[var(--ph-muted)]">
                {row.detail}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function toHealthTone(
  tone: "default" | "ok" | "warn" | "bad" | "muted" | undefined,
): Tone {
  if (tone === "ok" || tone === "warn" || tone === "bad") return tone;
  return "neutral";
}

export default function ControlCenterPage() {
  const queryClient = useQueryClient();
  const { confirm, dialog: confirmDialog } = useConfirm();
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
    queryKey: ["activities", { limit: 40 }],
    queryFn: () => api.getActivities({ limit: 40 }),
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
    queryFn: () => api.getLearningQueue(effectiveAdminKey, { limit: 40 }),
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

  const loadWithAdminKey = () => {
    const trimmed = adminKeyInput.trim();
    if (!trimmed) {
      return;
    }
    setUseSessionAuth(false);
    setAdminKey(trimmed);
    setAdminKeyInput("");
  };

  const latestActivity = recentActivities?.[0];
  const latestActivitySourceInfo = latestActivity
    ? getActivitySourceInfo(latestActivity)
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

  const reviewQueue = useMemo(
    () => createReviewQueue(recentActivities),
    [recentActivities],
  );

  const trustMetrics = useMemo(
    () => buildTrustMetrics(stats, recentActivities, learningQueue),
    [learningQueue, recentActivities, stats],
  );

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

  const jenkinsBridgeSummary = (() => {
    if (!settings) return "N/A";
    if (!settings.jenkins_bridge_enabled) return "Disabled";
    if (settings.auto_create_pr && settings.jenkins_bridge_allow_pr) {
      return "Enabled, PR-capable after policy checks";
    }
    return "Enabled, issue-first";
  })();

  const providerDefaultModel = (() => {
    if (!settings) return "";
    if (settings.llm_provider === "azure_openai") {
      return settings.azure_openai_deployment_name;
    }
    if (settings.llm_provider === "codex_app_server") {
      return settings.codex_app_server_model;
    }
    return settings.openai_compatible_model;
  })();
  const codexRuntimeSelected = settings?.llm_provider === "codex_app_server";

  const taskModelPreview = settings
    ? [
        {
          key: "analysis",
          label: "Analysis",
          model:
            (codexRuntimeSelected ? "" : settings.llm_model_analysis) ||
            providerDefaultModel ||
            "Not configured",
        },
        {
          key: "diagnosis",
          label: "Diagnosis",
          model:
            (codexRuntimeSelected ? "" : settings.llm_model_diagnosis) ||
            providerDefaultModel ||
            "Not configured",
        },
        {
          key: "remediation",
          label: "Remediation",
          model:
            (codexRuntimeSelected ? "" : settings.llm_model_remediation) ||
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
  const llmCapabilitySummary = describeLlmCapability(llmHealth);
  const llmValidationLabel = formatLlmValidationLabel(llmHealth);

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
      await copyToClipboard(command);
      toast.success("Command copied");
    } catch {
      toast.error("Copy failed");
    }
  };

  return (
    <div className="space-y-6">
      {confirmDialog}
      <div className="flex items-start gap-3.5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]">
          <ShieldCheck className="h-5 w-5 text-[var(--ph-accent)]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--ph-text)]">
            Control Center
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--ph-muted)]">
            Operational governance view for policy posture, provider readiness,
            audit traceability, and investigation access.
          </p>
        </div>
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
                  loadWithAdminKey();
                }
              }}
              placeholder="Enter admin key (X-Admin-Key)"
              className="flex-1"
            />
            <Button onClick={loadWithAdminKey} disabled={!adminKeyInput.trim() || settingsLoading}>
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
              <>
                Session login is disabled in this deployment (
                <code className="font-mono">VITE_AUTH_MODE=none</code>). Use{" "}
                <code className="font-mono">X-Admin-Key</code> or set{" "}
                <code className="font-mono">VITE_AUTH_MODE=entra</code> in
                frontend runtime env and redeploy env.
              </>
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
        <Card className="border-[var(--ph-danger-border)]">
          <CardContent className="py-6">
            <p className="text-sm font-medium text-[var(--ph-danger)]">
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
                <TabsList className="inline-flex h-auto min-h-0 w-full flex-wrap gap-1 rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/40 p-1 sm:w-auto">
                  {[
                    { value: "overview", label: "Governance Overview" },
                    { value: "learning_ops", label: "Learning & Ops" },
                    { value: "trust_ops", label: "Trust Ops" },
                    { value: "audit", label: "Audit & Trace" },
                  ].map((tab) => (
                    <TabsTrigger
                      key={tab.value}
                      value={tab.value}
                      className="flex-1 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium text-[var(--ph-muted)] data-[state=active]:bg-[var(--ph-surface)] data-[state=active]:font-semibold data-[state=active]:shadow-sm sm:flex-none"
                    >
                      {tab.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <p className="mt-3 text-sm text-[var(--ph-muted)]">
                {activeSection === "overview" &&
                  "Overview: runtime posture, policy impact, model routing, and MCP policy effect."}
                {activeSection === "learning_ops" &&
                  "Learning & Ops: candidate governance actions, readiness evidence, and investigation runbooks."}
                {activeSection === "trust_ops" &&
                  "Trust Ops: operator review queue and compact trust metrics derived from recent activity and guided runs."}
                {activeSection === "audit" &&
                  "Audit & Trace: recent settings changes with actor and request-id traceability."}
              </p>
            </CardContent>
          </Card>

          {activeSection === "overview" && (
            <div className="space-y-4">
              <Card>
                <CardContent className="grid grid-cols-2 gap-3 py-4 sm:grid-cols-3 xl:grid-cols-6">
                  <StatTile
                    label="Heal mode"
                    value={settings.heal_mode}
                    tone={settings.heal_mode === "safe" ? "ok" : "warn"}
                  />
                  <StatTile
                    label="Remediation"
                    value={settings.auto_apply_remediation ? "Automated" : "Plan-only"}
                    tone={settings.auto_apply_remediation ? "ok" : "neutral"}
                  />
                  <StatTile
                    label="LLM"
                    value={llmLoading ? "Checking..." : llmCapabilitySummary.summary}
                    tone={llmLoading ? "neutral" : toHealthTone(llmCapabilitySummary.tone)}
                  />
                  <StatTile
                    label="MCP"
                    value={
                      mcpLoading
                        ? "Checking..."
                        : mcpHealth?.available
                          ? "Available"
                          : "Unavailable"
                    }
                    tone={
                      mcpLoading ? "neutral" : mcpHealth?.available ? "ok" : "bad"
                    }
                  />
                  <StatTile
                    label="Receiver"
                    value={handoffIntegrationSummary.summary}
                    tone={toHealthTone(handoffIntegrationSummary.tone)}
                  />
                  <StatTile
                    label="Safety gated"
                    value={
                      statsLoading
                        ? "..."
                        : String(stats?.safety_blocked_remediations ?? 0)
                    }
                    tone="info"
                  />
                </CardContent>
              </Card>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_360px]">
                <div className="space-y-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Governance summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-5">
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
                          label: "Auto-merge PRs",
                          value: settings.auto_merge_remediation_prs
                            ? settings.auto_merge_strategy
                            : "No",
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
                          label: "LLM state",
                          value: llmLoading
                            ? "Checking..."
                            : llmCapabilitySummary.summary,
                        },
                        {
                          label: "LLM validation",
                          value: llmLoading
                            ? "Checking..."
                            : llmValidationLabel,
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
                        {
                          label: "Jenkins bridge",
                          value: jenkinsBridgeSummary,
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
                        {
                          label: "Jenkins ingress",
                          value: jenkinsBridgeSummary,
                          detail: settings.jenkins_bridge_enabled
                            ? `Signed webhook: skew ${settings.jenkins_bridge_max_skew_seconds}s, replay TTL ${settings.jenkins_bridge_replay_ttl_seconds}s.`
                            : "Enable the signed bridge in Settings before connecting Jenkins jobs.",
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
                        className="grid grid-cols-1 gap-2 rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/28 p-3 text-sm lg:grid-cols-[180px_minmax(0,1fr)_160px]"
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
                        {
                          label: "Capability",
                          value: llmCapabilitySummary.summary,
                          detail: llmCapabilitySummary.detail,
                          tone: llmCapabilitySummary.tone,
                        },
                        {
                          label: "Last validation",
                          value: llmValidationLabel,
                          detail: llmHealth?.last_validated_at
                            ? new Date(llmHealth.last_validated_at).toLocaleString()
                            : "Run one real canary activity to prove the current routing.",
                          tone: llmHealth?.last_validated_at ? "default" : "muted",
                        },
                      ]}
                    />
                    <div className="space-y-2">
                      {taskModelPreview.map((task) => (
                        <div
                          key={task.key}
                          className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/28 p-3"
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
                    <Badge variant="outline">
                      Rejected: {learningQueueSummary.rejected}
                    </Badge>
                  </div>

                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/28 p-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-[var(--ph-muted)]">
                        Active playbooks
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-[var(--ph-text)]">
                        {learningQueueSummary.active}
                      </p>
                      <p className="mt-1 text-xs text-[var(--ph-muted)]">
                        Candidate guidance currently eligible for live injection.
                      </p>
                    </div>
                    <div className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/28 p-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-[var(--ph-muted)]">
                        Promotion ready
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-[var(--ph-text)]">
                        {learningQueueSummary.ready}
                      </p>
                      <p className="mt-1 text-xs text-[var(--ph-muted)]">
                        Candidates already meeting activation gates.
                      </p>
                    </div>
                    <div className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/28 p-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-[var(--ph-muted)]">
                        Pending review
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-[var(--ph-text)]">
                        {learningQueueSummary.candidate + learningQueueSummary.approved}
                      </p>
                      <p className="mt-1 text-xs text-[var(--ph-muted)]">
                        Candidate and approved items still needing explicit operator governance action.
                      </p>
                    </div>
                  </div>

                  {learningLoading && <p>Loading learning queue...</p>}
                  {learningError && (
                    <p className="text-[var(--ph-danger)]">
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
                    {(learningQueue ?? []).slice(0, 10).map((item) => (
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
                        onForceActivate={async () => {
                          const ok = await confirm({
                            title: "Force-activate this playbook?",
                            description:
                              "This bypasses readiness gates and will be audit logged.",
                            confirmLabel: "Force activate",
                            destructive: true,
                          });
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
                      Learning queue explainability
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                    <SummaryRows
                      compact
                      rows={[
                        {
                          label: "Activation rule",
                          value: "Status + readiness gates",
                          detail:
                            "Candidates become safely activatable only after status approval and readiness thresholds for recurrence, success, and verification evidence.",
                        },
                        {
                          label: "Verification signal",
                          value: "Operator feedback weighted",
                          detail:
                            "Verification pass rate and guidance helped/hurt counts are treated as operator-trust signals, not just activity counters.",
                        },
                        {
                          label: "Sample provenance",
                          value: "Recent incident IDs attached",
                          detail:
                            "Each candidate carries sample activity IDs so you can inspect the incidents behind the proposed playbook before approving or activating it.",
                        },
                      ]}
                    />
                  </CardContent>
                </Card>

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
                      {latestActivitySourceInfo?.runUrl && (
                        <Button asChild size="sm" variant="ghost">
                          <a
                            href={latestActivitySourceInfo.runUrl}
                            rel="noopener noreferrer"
                            target="_blank"
                          >
                            Latest {latestActivitySourceInfo.runLabel}
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

          {activeSection === "trust_ops" && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_420px]">
              <div className="space-y-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <TriangleAlert className="h-4 w-4 text-[var(--ph-accent)]" />
                      Review queue
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm text-[var(--ph-muted)]">
                    <p>
                      Items that need human follow-up now: harmful guidance, failed remediation publication, review-only low-confidence runs, or guided runs that still lack verification.
                    </p>
                    {activitiesLoading ? <p>Loading recent activity window...</p> : null}
                    {!activitiesLoading && reviewQueue.length === 0 ? (
                      <p>
                        No urgent trust-ops items in the current activity window.
                      </p>
                    ) : null}
                    <div className="space-y-3">
                      {reviewQueue.map((item) => (
                        <div
                          key={`${item.activity.id}-${item.title}`}
                          className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 p-4"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <p className="font-medium text-[var(--ph-text)]">
                                {item.title}
                              </p>
                              <p className="mt-1 text-sm text-[var(--ph-muted)]">
                                {item.reason}
                              </p>
                            </div>
                            <Badge
                              variant="outline"
                              className={toneClass(
                                item.tone === "bad" ? "bad" : "warn",
                              )}
                            >
                              {item.priority === "high" ? "High Priority" : "Review"}
                            </Badge>
                          </div>
                          <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
                            <div className="space-y-1">
                              <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                                Incident
                              </p>
                              <p className="text-sm text-[var(--ph-text)]">
                                {item.activity.repository_name} · {item.activity.workflow_name}
                              </p>
                              <p className="text-xs text-[var(--ph-muted)]">
                                {item.detail}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2 md:justify-end">
                              <Button asChild size="sm" variant="secondary">
                                <Link to={`/app/activities/${item.activity.id}`}>
                                  Open Activity
                                </Link>
                              </Button>
                              <Button asChild size="sm" variant="ghost">
                                <Link
                                  to={`/app/activities?repository=${encodeURIComponent(
                                    item.activity.repository_name,
                                  )}`}
                                >
                                  View Repo Runs
                                </Link>
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Trust reporting
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {trustMetrics.map((metric) => (
                      <div
                        key={metric.label}
                        className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 p-4"
                      >
                        <p className="text-xs font-medium uppercase tracking-wide text-[var(--ph-muted)]">
                          {metric.label}
                        </p>
                        <p
                          className={`mt-2 text-2xl font-semibold ${
                            metric.tone === "ok"
                              ? "text-[var(--ph-success)]"
                              : metric.tone === "warn"
                                ? "text-[var(--ph-warning)]"
                                : metric.tone === "bad"
                                  ? "text-[var(--ph-danger)]"
                                  : metric.tone === "muted"
                                    ? "text-[var(--ph-muted)]"
                                    : "text-[var(--ph-text)]"
                          }`}
                        >
                          {metric.value}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-[var(--ph-muted)]">
                          {metric.detail}
                        </p>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Top noisy failure classes
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {Object.entries(stats?.by_failure_type ?? {})
                      .sort((a, b) => b[1] - a[1])
                      .slice(0, 6)
                      .map(([failureType, count]) => (
                        <div
                          key={failureType}
                          className="flex items-center justify-between rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 px-3 py-3"
                        >
                          <div>
                            <p className="text-sm font-medium text-[var(--ph-text)]">
                              {failureType}
                            </p>
                            <p className="text-xs text-[var(--ph-muted)]">
                              Most frequent failure classes in the current stats window.
                            </p>
                          </div>
                          <Badge variant="outline">{count}</Badge>
                        </div>
                      ))}
                    {stats && Object.keys(stats.by_failure_type ?? {}).length === 0 ? (
                      <p className="text-sm text-[var(--ph-muted)]">
                        No failure-class counts are available yet.
                      </p>
                    ) : null}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Trust-ops guidance
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-[var(--ph-muted)]">
                    <SummaryRows
                      compact
                      rows={[
                        {
                          label: "First check",
                          value: "High-priority queue items",
                          detail:
                            "Start with harmful guidance and failed publication paths before reviewing lower-risk queue items.",
                        },
                        {
                          label: "Then verify",
                          value: "Guided runs without feedback",
                          detail:
                            "Closing the feedback loop is what improves learning readiness and trust reporting quality.",
                        },
                        {
                          label: "Escalate when",
                          value: "A failure class stays noisy",
                          detail:
                            "Use the noisy-failure list to decide where heuristics, runbooks, or better bounded remediation need attention next.",
                        },
                      ]}
                    />
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
    <div className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/20 p-3">
      <div className="mb-2">
        <p className="text-sm font-medium text-[var(--ph-text)]">{title}</p>
        <p className="text-xs text-[var(--ph-muted)]">{description}</p>
      </div>
      <div className="space-y-2">
        {commands.map((item) => (
          <div
            key={`${item.scope}-${item.label}-${item.command}`}
            className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-surface)] px-3 py-2"
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
    <div className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="break-words font-medium text-[var(--ph-text)]">
            {item.title}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {item.failure_type ? (
              <Badge variant="outline">Failure: {item.failure_type}</Badge>
            ) : null}
            {item.reason_code ? (
              <Badge variant="outline">Reason: {item.reason_code}</Badge>
            ) : null}
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
          <p className="break-words text-sm text-[var(--ph-text)]">
            {item.suggested_playbook}
          </p>
          {item.repositories.length > 0 && (
            <p>
              Repositories:{" "}
              <span className="break-words">
                {item.repositories.slice(0, 3).join(", ")}
                {item.repositories.length > 3
                  ? ` +${item.repositories.length - 3} more`
                  : ""}
              </span>
            </p>
          )}
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
              <p>
                Verification: {item.verification_pass_count}/
                {item.verification_sample_count} pass
                {item.verification_sample_count > 0 && (
                  <> · {(item.verification_pass_rate * 100).toFixed(0)}% pass rate</>
                )}
              </p>
            </>
          )}
          {item.guidance_application_count > 0 && (
            <p>
              Guidance applied on {item.guidance_application_count} run
              {item.guidance_application_count === 1 ? "" : "s"}
              {item.guidance_feedback_count > 0 && (
                <>
                  {" · "}
                  {(item.guidance_help_rate * 100).toFixed(0)}% helped
                  {" · "}
                  {item.guidance_hurt_count} hurt
                </>
              )}
            </p>
          )}
          {item.sample_activity_ids.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {item.sample_activity_ids.slice(0, 4).map((activityId) => (
                <Link
                  key={activityId}
                  to={`/app/activities/${activityId}`}
                  className="inline-flex items-center rounded-md border border-[var(--ph-border-subtle)] px-2 py-1 text-[11px] text-[var(--ph-accent)] hover:opacity-80"
                >
                  Sample {activityId.slice(0, 8)}
                </Link>
              ))}
            </div>
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
