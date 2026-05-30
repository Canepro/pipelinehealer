import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow, format } from "date-fns";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  GitBranch,
  RefreshCw,
  FileCode,
  AlertTriangle,
  Bot,
  KeyRound,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type Activity,
  type HandoffSessionCreateRequest,
  type HandoffSessionView,
} from "../api/client";
import { getActivitySourceInfo } from "../utils/activitySource";
import { copyToClipboard } from "../utils/copyToClipboard";
import { formatSourceLabel } from "../utils/formatSourceLabel";
import StatusBadge from "../components/StatusBadge";
import FailureTypeBadge from "../components/FailureTypeBadge";
import VerificationWorkspace from "../components/activity/VerificationWorkspace";
import {
  formatVerificationOutcomeLabel,
  getLatestVerification,
  getVerificationHistory,
} from "../components/activity/verification";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const RAW_EVIDENCE_KEYS = new Set([
  "key_log_lines",
  "relevant_log_lines",
  "log_messages",
  "evidence",
  "raw_log_lines",
  "error_lines",
]);

const STRUCTURED_EVIDENCE_OMIT_KEYS = new Set([
  ...RAW_EVIDENCE_KEYS,
  "violations",
  "additional",
  "message",
  "raw_logs",
  "llm_payload_rejected",
  "llm_payload_rejection_reason",
  "llm_payload_candidate_count",
]);

function formatSourceSelectionPath(path: string): string {
  const known: Record<string, string> = {
    gh_aw_passive: "GitHub Agentic Workflows (passive)",
    github_mcp_direct: "GitHub MCP (direct)",
    github_mcp_blocked: "GitHub MCP blocked by policy/provider",
    jenkins_bridge: "Jenkins Bridge",
  };
  const normalized = path.trim().toLowerCase();
  if (known[normalized]) return known[normalized];
  if (!normalized) return "Unknown";
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getExternalDiagnosticStatusMeta(
  status: string,
  metadata?: Record<string, unknown>,
): {
  label: string;
  className: string;
} {
  const displayState =
    typeof metadata?.display_state === "string" ? metadata.display_state : "";
  if (displayState === "context_only") {
    return {
      label: "Context only",
      className:
        "inline-flex items-center rounded-md bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--ph-text)]",
    };
  }
  switch (status) {
    case "available":
      return {
        label: "Available",
        className:
          "inline-flex items-center rounded-md bg-[var(--ph-success-bg)] px-2 py-1 text-xs font-medium text-[var(--ph-success)]",
      };
    case "error":
      return {
        label: "Error",
        className:
          "inline-flex items-center rounded-md bg-[var(--ph-danger-bg)] px-2 py-1 text-xs font-medium text-[var(--ph-danger)]",
      };
    case "unavailable":
      return {
        label: "Unavailable",
        className:
          "inline-flex items-center rounded-md bg-[var(--ph-warning-bg)] px-2 py-1 text-xs font-medium text-[var(--ph-warning)]",
      };
    case "disabled":
      return {
        label: "Disabled",
        className:
          "inline-flex items-center rounded-md bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--ph-text)]",
      };
    default:
      return {
        label: status || "Unknown",
        className:
          "inline-flex items-center rounded-md bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--ph-text)]",
      };
  }
}

function formatConfidenceDelta(delta: number): string {
  if (delta === 0) {
    return "No confidence change";
  }
  const sign = delta > 0 ? "+" : "-";
  const pct = Math.round(Math.abs(delta) * 100);
  return `${sign}${pct}% confidence`;
}

function formatDiagnosticConfidenceLabel(
  delta: number,
  metadata?: Record<string, unknown>,
): string {
  const displayState =
    typeof metadata?.display_state === "string" ? metadata.display_state : "";
  if (displayState === "context_only") {
    return "Unscored context";
  }
  return formatConfidenceDelta(delta);
}

function formatFailureTypeHeadline(failureType?: string | null): string {
  const normalized = (failureType || "").trim().toLowerCase();
  if (!normalized) return "Pipeline incident";
  if (normalized === "unknown") return "Unclassified incident";
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase()) + " incident";
}

function formatSourceRunResultLabel(result: string): string {
  const normalized = result.trim().toLowerCase();
  if (!normalized) return "Unknown";
  switch (normalized) {
    case "failure":
      return "Failed";
    case "success":
      return "Succeeded";
    case "unstable":
      return "Unstable";
    case "aborted":
      return "Aborted";
    default:
      return normalized.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }
}

function formatActionTaken(actionTaken: string): string {
  return actionTaken
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bPr\b/, "PR");
}

function getIssueProposalMeta(details: Record<string, unknown> | undefined): {
  includesProposedFix: boolean;
  reasonCode: string | null;
  reasonDetail: string | null;
  reusedExistingPr: boolean;
  appliedLearningTitle: string | null;
  appliedLearningId: string | null;
  guidanceEffectiveness: string | null;
} {
  const includes = details?.includes_proposed_fix === true;
  const reason = (
    typeof details?.not_auto_reason_code === "string"
      ? details.not_auto_reason_code
      : typeof details?.reason_code === "string"
        ? details.reason_code
        : null
  ) as string | null;
  const reasonDetail =
    typeof details?.not_auto_reason_detail === "string"
      ? details.not_auto_reason_detail
      : typeof details?.reason_detail === "string"
        ? details.reason_detail
        : null;
  const reusedExistingPr = details?.reused_existing_pr === true;
  const appliedLearning =
    details?.applied_learning_context &&
    typeof details.applied_learning_context === "object"
      ? (details.applied_learning_context as Record<string, unknown>)
      : null;
  const verification =
    details?.verification && typeof details.verification === "object"
      ? (details.verification as Record<string, unknown>)
      : null;
  return {
    includesProposedFix: includes,
    reasonCode: reason,
    reasonDetail,
    reusedExistingPr,
    appliedLearningTitle:
      typeof appliedLearning?.title === "string" ? appliedLearning.title : null,
    appliedLearningId:
      typeof appliedLearning?.id === "string" ? appliedLearning.id : null,
    guidanceEffectiveness:
      typeof verification?.guidance_effectiveness === "string"
        ? verification.guidance_effectiveness
        : null,
  };
}

function toEvidenceLabel(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function normalizeEvidenceLines(value: unknown): string[] {
  if (typeof value === "string") {
    const line = value.trim();
    return line ? [line] : [];
  }
  if (!Array.isArray(value)) return [];
  return value
    .filter((line): line is string => typeof line === "string")
    .map((line) => line.trim())
    .filter(Boolean);
}

function collectRawEvidenceLines(
  details: Record<string, unknown> | undefined,
): string[] {
  if (!details) return [];
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const key of RAW_EVIDENCE_KEYS) {
    const entries = normalizeEvidenceLines(details[key]);
    for (const entry of entries) {
      if (seen.has(entry)) continue;
      seen.add(entry);
      lines.push(entry);
      if (lines.length >= 40) return lines;
    }
  }
  const fallbackMessage =
    typeof details.message === "string" ? details.message.trim() : "";
  if (fallbackMessage && !seen.has(fallbackMessage)) {
    lines.push(fallbackMessage);
  }
  return lines;
}

function formatStructuredEvidenceValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  if (Array.isArray(value)) {
    const compact = value
      .map((item) => (typeof item === "string" ? item : JSON.stringify(item)))
      .filter((item) => typeof item === "string" && item.length > 0)
      .slice(0, 5);
    if (compact.length === 0) return "";
    return compact.join(", ");
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "";
    }
  }
  return "";
}

function collectStructuredEvidence(
  details: Record<string, unknown> | undefined,
): Array<{ key: string; label: string; value: string }> {
  if (!details) return [];
  const rows: Array<{ key: string; label: string; value: string }> = [];
  for (const [key, rawValue] of Object.entries(details)) {
    if (STRUCTURED_EVIDENCE_OMIT_KEYS.has(key)) continue;
    const formatted = formatStructuredEvidenceValue(rawValue).trim();
    if (!formatted) continue;
    rows.push({
      key,
      label: toEvidenceLabel(key),
      value: formatted,
    });
    if (rows.length >= 12) break;
  }
  return rows;
}

function aggregateConfidenceBySource(
  diagnostics: Array<{
    source: string;
    confidence_delta: number;
    status: string;
  }>,
): Array<{
  source: string;
  delta: number;
  samples: number;
  available: number;
}> {
  const bySource = new Map<
    string,
    { delta: number; samples: number; available: number }
  >();
  for (const diagnostic of diagnostics) {
    const source = diagnostic.source || "unknown";
    const current = bySource.get(source) ?? {
      delta: 0,
      samples: 0,
      available: 0,
    };
    current.delta += diagnostic.confidence_delta;
    current.samples += 1;
    if (diagnostic.status === "available") {
      current.available += 1;
    }
    bySource.set(source, current);
  }
  return Array.from(bySource.entries())
    .map(([source, value]) => ({ source, ...value }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
}

type ExternalSignalSource = {
  source: string;
  delta: number;
  reason: string;
};

function parseExternalSignalSources(value: unknown): ExternalSignalSource[] {
  if (!Array.isArray(value)) return [];
  const parsed: ExternalSignalSource[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const source =
      typeof (item as Record<string, unknown>).source === "string"
        ? ((item as Record<string, unknown>).source as string)
        : "unknown";
    const deltaRaw = (item as Record<string, unknown>).delta;
    const delta = typeof deltaRaw === "number" ? deltaRaw : 0;
    const reason =
      typeof (item as Record<string, unknown>).reason === "string"
        ? ((item as Record<string, unknown>).reason as string)
        : "";
    parsed.push({ source, delta, reason });
  }
  return parsed;
}

function formatMcpStatus(enabled: boolean, available: boolean): string {
  if (!enabled) return "Disabled";
  return available ? "Available" : "Unavailable";
}

function formatMcpReason(reason: string): string {
  const normalized = reason.trim().toLowerCase();
  const labels: Record<string, string> = {
    ok: "Healthy and available",
    disabled: "Disabled by runtime settings",
    provider_not_github: "Unsupported provider for this action path",
    provider_health_error: "Provider health check failed",
    missing_github_token: "Missing GitHub credential/token",
    repo_not_allowlisted: "Repository is outside MCP allowlist",
    tool_policy_disabled: "Tool is disabled by policy",
    tool_policy_read_only: "Tool policy allows read-only actions only",
    blocked_by_read_only_mode: "Blocked by global read-only mode",
    approval_required: "Blocked pending manual approval",
    mcp_disabled: "MCP is disabled",
  };
  if (labels[normalized]) return labels[normalized];
  if (normalized.startsWith("branch_protection_respected")) {
    return "Blocked to respect protected branch constraints";
  }
  return reason || "Unknown";
}

type McpActionOutcome = {
  kind: "success" | "blocked" | "error" | "timeout" | "other";
  label: string;
  detail: string;
  code: string | null;
};

function mcpOutcomeBadgeClass(kind: McpActionOutcome["kind"]): string {
  switch (kind) {
    case "success":
      return "bg-[var(--ph-success-bg)] text-[var(--ph-success)]";
    case "blocked":
      return "bg-[var(--ph-warning-bg)] text-[var(--ph-warning)]";
    case "error":
      return "bg-[var(--ph-danger-bg)] text-[var(--ph-danger)]";
    case "timeout":
      return "bg-[var(--ph-warning-bg)] text-[var(--ph-warning)]";
    default:
      return "bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]";
  }
}

function parseMcpActionResult(rawResult: string): McpActionOutcome {
  const value = (rawResult || "").trim();
  if (!value) {
    return {
      kind: "other",
      label: "Unknown",
      detail: "No result string captured.",
      code: null,
    };
  }

  if (value.startsWith("success:")) {
    const attempt = value.split(":").slice(1).join(":");
    return {
      kind: "success",
      label: "Allowed",
      detail: attempt
        ? `Completed (${attempt.replace(/_/g, " ")})`
        : "Completed successfully",
      code: value,
    };
  }
  if (value.startsWith("blocked:")) {
    const code = value.slice("blocked:".length);
    return {
      kind: "blocked",
      label: "Blocked",
      detail: formatMcpReason(code),
      code,
    };
  }
  if (value.startsWith("timeout:")) {
    const code = value.slice("timeout:".length);
    return {
      kind: "timeout",
      label: "Timeout",
      detail: code ? `Timed out (${code.replace(/_/g, " ")})` : "Timed out",
      code,
    };
  }
  if (value.startsWith("error:")) {
    const rest = value.slice("error:".length);
    const [errorType] = rest.split(":");
    return {
      kind: "error",
      label: "Error",
      detail: errorType ? `Execution error (${errorType})` : "Execution error",
      code: rest || value,
    };
  }
  return {
    kind: "other",
    label: "Result",
    detail: value,
    code: value,
  };
}

const COPY_CONTEXT_MAX_CHARS = 16 * 1024;
const COPY_CONTEXT_SECTION_ITEM_LIMIT = 6;
const COPY_CONTEXT_TRUNCATION_MARKER =
  "\n\n...truncated due to context size limit (16KB)...";

function sanitizeSecretLikeText(input: string): string {
  let output = input;
  output = output.replace(
    /\bgh[pousr]_[A-Za-z0-9]{20,}\b/g,
    "[REDACTED_GITHUB_TOKEN]",
  );
  output = output.replace(
    /\b(AIza[0-9A-Za-z\-_]{20,})\b/g,
    "[REDACTED_API_KEY]",
  );
  output = output.replace(
    /(authorization\s*:\s*bearer\s+)[^\s"']+/gi,
    "$1[REDACTED_TOKEN]",
  );
  output = output.replace(
    /\b(api[_-]?key|token|secret|password|client[_-]?secret)\b(\s*[:=]\s*)["']?[^\s"']{8,}/gi,
    "$1$2[REDACTED]",
  );
  return output;
}

function clampText(value: unknown, maxChars = 280): string {
  const normalized = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return "N/A";
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, maxChars)} ...truncated...`;
}

function clampList<T>(
  items: T[],
  limit = COPY_CONTEXT_SECTION_ITEM_LIMIT,
): T[] {
  if (items.length <= limit) return items;
  return items.slice(0, limit);
}

function finalizeContextPayload(rawPayload: string): string {
  const redacted = sanitizeSecretLikeText(rawPayload);
  if (redacted.length <= COPY_CONTEXT_MAX_CHARS) return redacted;
  const cutoff = Math.max(
    0,
    COPY_CONTEXT_MAX_CHARS - COPY_CONTEXT_TRUNCATION_MARKER.length,
  );
  return `${redacted.slice(0, cutoff)}${COPY_CONTEXT_TRUNCATION_MARKER}`;
}

function buildActivityContext(activity: Activity): string {
  const lines: string[] = [];
  const remediationMeta = getIssueProposalMeta(
    activity.remediation_result?.details,
  );
  const diagnostics = activity.external_diagnostics ?? [];

  lines.push("# PipelineHealer Activity Context");
  lines.push("");
  lines.push("## 1) Activity Identity");
  lines.push(`- activity_id: ${activity.id}`);
  lines.push(`- repository: ${activity.repository_name}`);
  lines.push(`- workflow: ${activity.workflow_name}`);
  lines.push(`- workflow_run_id: ${activity.workflow_run_id}`);
  lines.push(`- status: ${activity.status}`);
  lines.push(`- created_at: ${activity.created_at}`);
  lines.push(`- updated_at: ${activity.updated_at}`);
  lines.push(
    `- duration_seconds: ${typeof activity.duration_seconds === "number" ? Math.round(activity.duration_seconds) : "N/A"}`,
  );

  lines.push("");
  lines.push("## 2) Diagnosis Summary");
  lines.push(`- failure_type: ${activity.failure_type || "not determined"}`);
  if (activity.diagnosis) {
    lines.push(
      `- diagnosis_source: ${activity.diagnosis.diagnosis_source || "unknown"}`,
    );
    lines.push(
      `- confidence: ${Math.round(activity.diagnosis.confidence * 100)}%`,
    );
    lines.push(`- root_cause: ${clampText(activity.diagnosis.root_cause)}`);
    lines.push(
      `- suggested_fix: ${clampText(activity.diagnosis.suggested_fix || "N/A")}`,
    );
    lines.push(
      `- auto_fixable: ${activity.diagnosis.is_auto_fixable ? "yes" : "no"}`,
    );
    const files = clampList(activity.diagnosis.affected_files);
    lines.push(
      `- affected_files_count: ${activity.diagnosis.affected_files.length}`,
    );
    lines.push("- affected_files_sample:");
    if (files.length > 0) {
      for (const file of files) {
        lines.push(`  - ${clampText(file, 180)}`);
      }
    } else {
      lines.push("  - none");
    }
    if (activity.diagnosis.llm_rejection?.rejected) {
      lines.push(`- llm_diagnosis_discarded: yes`);
      lines.push(
        `- llm_discard_reason: ${clampText(activity.diagnosis.llm_rejection.reason || "unknown")}`,
      );
      lines.push(
        `- llm_candidate_count: ${activity.diagnosis.llm_rejection.candidate_count}`,
      );
    }
  } else {
    lines.push("- diagnosis: N/A");
  }

  if (activity.learning_context_trace) {
    lines.push(`- learning_context_diagnosis_matches: ${activity.learning_context_trace.diagnosis_matches.length}`);
    lines.push(`- learning_context_remediation_matches: ${activity.learning_context_trace.remediation_matches.length}`);
  }

  lines.push("");
  lines.push("## 3) Remediation Outcome");
  if (activity.remediation_result) {
    lines.push(
      `- success: ${activity.remediation_result.success ? "yes" : "no"}`,
    );
    lines.push(`- action_taken: ${activity.remediation_result.action_taken}`);
    lines.push(
      `- issue_url: ${activity.remediation_result.issue_url || "N/A"}`,
    );
    lines.push(`- pr_url: ${activity.remediation_result.pr_url || "N/A"}`);
    lines.push(`- reason_code: ${remediationMeta.reasonCode || "N/A"}`);
    lines.push(
      `- reason_detail: ${clampText(remediationMeta.reasonDetail || "N/A")}`,
    );
    if (activity.remediation_result.error_message) {
      lines.push(
        `- error_message: ${clampText(activity.remediation_result.error_message)}`,
      );
    }
  } else {
    lines.push("- remediation_result: N/A");
  }

  lines.push("");
  lines.push("## 4) Failure Context");
  lines.push(
    `- failing_job: ${activity.failure_context?.failing_job || "N/A"}`,
  );
  lines.push(
    `- failing_step: ${activity.failure_context?.failing_step || "N/A"}`,
  );
  lines.push(
    `- failing_command: ${clampText(activity.failure_context?.failing_command || "N/A")}`,
  );
  lines.push(
    `- signal: ${clampText(activity.failure_context?.signal || "N/A")}`,
  );

  lines.push("");
  lines.push("## 5) External Diagnostics Summary");
  lines.push(`- diagnostics_count: ${diagnostics.length}`);
  if (diagnostics.length > 0) {
    for (const [index, diagnostic] of clampList(diagnostics).entries()) {
      lines.push(`- signal_${index + 1}:`);
      lines.push(`  - source: ${diagnostic.source}`);
      lines.push(`  - status: ${diagnostic.status}`);
      lines.push(`  - confidence_delta: ${diagnostic.confidence_delta}`);
      lines.push(`  - run_id: ${diagnostic.matched_run_id ?? "N/A"}`);
      lines.push(`  - findings_url: ${diagnostic.url || "N/A"}`);
      lines.push(`  - summary: ${clampText(diagnostic.summary || "N/A")}`);
    }
    if (diagnostics.length > COPY_CONTEXT_SECTION_ITEM_LIMIT) {
      lines.push(
        `- ...truncated... (${diagnostics.length - COPY_CONTEXT_SECTION_ITEM_LIMIT} additional signals omitted)`,
      );
    }
  } else {
    lines.push("- no external diagnostics captured");
  }

  lines.push("");
  lines.push("## 6) MCP/LLM Observability Summary");
  if (activity.mcp_model_path) {
    lines.push(`- mcp_provider: ${activity.mcp_model_path.provider}`);
    lines.push(`- mcp_enabled: ${activity.mcp_model_path.enabled}`);
    lines.push(`- mcp_available: ${activity.mcp_model_path.available}`);
    lines.push(`- mcp_reason: ${activity.mcp_model_path.reason || "N/A"}`);
    lines.push(
      `- mcp_tool_calls_total: ${Object.values(activity.mcp_model_path.tool_invocations ?? {}).reduce((total, count) => total + count, 0)}`,
    );
    lines.push(
      `- mcp_total_latency_ms: ${activity.mcp_model_path.total_latency_ms}`,
    );
  } else {
    lines.push("- mcp: N/A");
  }
  if (activity.llm_model_path) {
    lines.push(`- llm_provider: ${activity.llm_model_path.provider}`);
    lines.push(`- llm_model: ${activity.llm_model_path.model}`);
    lines.push(`- llm_fallback_used: ${activity.llm_model_path.fallback_used}`);
    lines.push(`- llm_call_count: ${activity.llm_model_path.call_count}`);
    lines.push(
      `- llm_total_latency_ms: ${activity.llm_model_path.total_latency_ms}`,
    );
  } else {
    lines.push("- llm: N/A");
  }

  lines.push("");
  lines.push("## 7) Operator Ask Template");
  lines.push(
    "- Propose a minimal safe fix for the root cause, with exact file-level changes.",
  );
  lines.push("- List verification steps for CI and local checks.");
  lines.push("- Provide a rollback plan if the fix regresses behavior.");

  return finalizeContextPayload(lines.join("\n"));
}

function buildHandoffGoal(activity: Activity): string {
  const failureType = activity.failure_type || "unclassified";
  const runUrl = getActivitySourceInfo(activity).runUrl || "not available";
  return [
    `Fix the ${failureType} failure in ${activity.repository_name}.`,
    `Use PipelineHealer activity ${activity.id} and workflow run ${activity.workflow_run_id}.`,
    `Open a PR or comment with findings, apply PipelineHealer labels, rerun checks when appropriate, then report the result back to the handoff callback.`,
    `Run URL: ${runUrl}`,
  ].join(" ");
}

function formatHandoffTarget(target: string): string {
  const labels: Record<string, string> = {
    codex_app_server: "Codex App Server",
    openclaw: "OpenClaw",
    hermes: "Hermes",
    custom: "Custom",
  };
  return labels[target] || target.replace(/_/g, " ");
}

function formatHandoffStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function handoffStatusClass(status: string): string {
  switch (status) {
    case "completed":
      return "bg-[var(--ph-success-bg)] text-[var(--ph-success)]";
    case "failed":
      return "bg-[var(--ph-danger-bg)] text-[var(--ph-danger)]";
    case "waiting_on_pipelinehealer":
    case "pr_opened":
      return "bg-[var(--ph-warning-bg)] text-[var(--ph-warning)]";
    case "queued":
    case "acknowledged":
    case "in_progress":
      return "bg-[var(--ph-info-bg)] text-[var(--ph-info)]";
    default:
      return "bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]";
  }
}

function HandoffSessionsPanel({
  sessions,
}: {
  sessions: HandoffSessionView[];
}) {
  const sorted = [...sessions].sort(
    (a, b) =>
      new Date(b.session.updated_at).getTime() -
      new Date(a.session.updated_at).getTime(),
  );
  return (
    <div className="card p-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-[var(--ph-text)]">
          External Agent Handoffs
        </h2>
        <p className="text-sm text-[var(--ph-muted)]">
          Durable sessions for Codex App Server, OpenClaw, Hermes, and callback events.
        </p>
      </div>
      {sorted.length === 0 ? (
        <p className="mt-5 text-sm text-[var(--ph-muted)]">
          No external agent handoff has been recorded for this activity.
        </p>
      ) : (
        <div className="mt-5 space-y-4">
          {sorted.map(({ session, messages }) => {
            const latestMessages = [...messages].slice(-4).reverse();
            const githubLinks = [
              { label: "PR", url: session.github.pr_url },
              { label: "Issue", url: session.github.issue_url },
              { label: "Comment", url: session.github.comment_url },
              { label: "Rerun", url: session.github.workflow_rerun_url },
            ].filter((link): link is { label: string; url: string } =>
              Boolean(link.url),
            );
            return (
              <div
                key={session.id}
                className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/30 p-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">
                        {formatHandoffTarget(session.target)}
                      </Badge>
                      <span
                        className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ${handoffStatusClass(session.status)}`}
                      >
                        {formatHandoffStatus(session.status)}
                      </span>
                      <Badge variant="outline">
                        {session.policy_decision || "operator_requested"}
                      </Badge>
                    </div>
                    <p className="mt-3 text-sm font-medium text-[var(--ph-text)]">
                      {session.goal}
                    </p>
                    <p className="mt-2 text-xs text-[var(--ph-muted)] break-all">
                      Session {session.id} • context sha256 {session.context_sha256.slice(0, 12)}
                      {session.external_thread_id
                        ? ` • thread ${session.external_thread_id}`
                        : ""}
                    </p>
                  </div>
                  <div className="text-xs text-[var(--ph-muted)] lg:text-right">
                    <p>{format(new Date(session.updated_at), "PPpp")}</p>
                    <p>
                      {formatDistanceToNow(new Date(session.updated_at), {
                        addSuffix: true,
                      })}
                    </p>
                  </div>
                </div>

                {session.labels.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {session.labels.map((label) => (
                      <Badge key={label} variant="secondary">
                        {label}
                      </Badge>
                    ))}
                  </div>
                ) : null}

                {githubLinks.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-3">
                    {githubLinks.map((link) => (
                      <a
                        key={link.label}
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center text-sm text-[var(--ph-accent)] hover:opacity-80"
                      >
                        {link.label}
                        <ExternalLink className="ml-1 h-3.5 w-3.5" />
                      </a>
                    ))}
                  </div>
                ) : null}

                {latestMessages.length > 0 ? (
                  <div className="mt-4 space-y-2">
                    {latestMessages.map((message) => (
                      <div
                        key={message.id}
                        className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)] px-3 py-2"
                      >
                        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--ph-muted)]">
                          <span>{formatHandoffStatus(message.event_type)}</span>
                          <span>{message.direction}</span>
                          <span>{message.actor || "unknown actor"}</span>
                          <span>
                            {formatDistanceToNow(new Date(message.created_at), {
                              addSuffix: true,
                            })}
                          </span>
                          {message.signature_verified ? (
                            <Badge variant="outline">signed callback</Badge>
                          ) : null}
                        </div>
                        {message.body ? (
                          <p className="mt-1 text-sm text-[var(--ph-text)]">
                            {message.body}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const DETAIL_SECTIONS: Array<{ key: string; label: string }> = [
  { key: "summary", label: "Summary" },
  { key: "root_cause", label: "Root Cause" },
  { key: "failed_jobs", label: "Failed Jobs" },
  { key: "investigation_findings", label: "Investigation Findings" },
  { key: "recommended_actions", label: "Recommended Actions" },
  { key: "prevention_strategies", label: "Prevention Strategies" },
  { key: "historical_context", label: "Historical Context" },
  { key: "ai_self_improvement", label: "AI Self-Improvement" },
];

/** Maximum visible lines before truncation with "Show more". */
const SECTION_LINE_LIMIT = 6;

/**
 * Lightweight inline markdown renderer.
 *
 * Handles:
 * - `**bold**`
 * - `` `code` ``
 * - `[text](url)` links
 *
 * Returns an array of React nodes suitable for inline rendering.
 */
function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // Regex alternation: bold | code | link
  const re = /\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    if (match[1] != null) {
      parts.push(
        <strong key={key++} className="font-semibold">
          {match[1]}
        </strong>,
      );
    } else if (match[2] != null) {
      parts.push(
        <code
          key={key++}
          className="bg-[var(--ph-bg-elevated)] px-1 py-0.5 rounded text-xs font-mono"
        >
          {match[2]}
        </code>,
      );
    } else if (match[3] != null && match[4] != null) {
      parts.push(
        <a
          key={key++}
          href={match[4]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--ph-accent)] hover:opacity-80 underline"
        >
          {match[3]}
        </a>,
      );
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

/**
 * Render a section body string as structured content.
 *
 * Detects bullet lists (- item, * item) vs plain paragraphs and renders
 * them with appropriate styling instead of raw whitespace-pre-wrap.
 */
function MarkdownBody({ text }: { text: string }) {
  const lines = text.split("\n");
  const groups: Array<{ type: "paragraph" | "bullet"; lines: string[] }> = [];

  for (const raw of lines) {
    const trimmed = raw.trim();
    if (!trimmed) {
      // Blank line — start a fresh group on next non-empty line.
      continue;
    }
    const isBullet = /^[-*]\s|^- \[[ x]\]\s/i.test(trimmed);
    const last = groups[groups.length - 1];
    if (last && last.type === (isBullet ? "bullet" : "paragraph")) {
      last.lines.push(trimmed);
    } else {
      groups.push({
        type: isBullet ? "bullet" : "paragraph",
        lines: [trimmed],
      });
    }
  }

  return (
    <>
      {groups.map((group, gi) =>
        group.type === "bullet" ? (
          <ul key={gi} className="list-disc list-inside space-y-1 ml-1">
            {group.lines.map((line, li) => {
              // Strip leading - / * / - [x]
              const content = line.replace(/^[-*]\s+(\[[ x]\]\s+)?/i, "");
              const checked = /^- \[x\]/i.test(line);
              return (
                <li
                  key={li}
                  className="text-sm text-[var(--ph-text)] leading-relaxed"
                >
                  {checked && (
                    <span className="text-[var(--ph-success)] mr-1">
                      &#10003;
                    </span>
                  )}
                  {renderInlineMarkdown(content)}
                </li>
              );
            })}
          </ul>
        ) : (
          <p key={gi} className="text-sm text-[var(--ph-text)] leading-relaxed">
            {group.lines.map((line, li) => (
              <span key={li}>
                {li > 0 && " "}
                {renderInlineMarkdown(line)}
              </span>
            ))}
          </p>
        ),
      )}
    </>
  );
}

/**
 * Renders a section with optional "Show more / Show less" truncation.
 */
function CollapsibleSection({ label, text }: { label: string; text: string }) {
  const lines = text.split("\n").filter((l) => l.trim());
  const needsTruncation = lines.length > SECTION_LINE_LIMIT;
  const [showAll, setShowAll] = useState(false);

  const displayText =
    needsTruncation && !showAll
      ? lines.slice(0, SECTION_LINE_LIMIT).join("\n")
      : text;

  return (
    <div>
      <p className="text-xs font-semibold text-[var(--ph-muted)] uppercase tracking-wide mb-1.5">
        {label}
      </p>
      <div className="space-y-2">
        <MarkdownBody text={displayText} />
      </div>
      {needsTruncation && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-1 text-xs font-medium text-[var(--ph-accent)] hover:opacity-80"
        >
          {showAll
            ? "Show less"
            : `Show more (${lines.length - SECTION_LINE_LIMIT} more lines)`}
        </button>
      )}
    </div>
  );
}

function ExternalFindingsPanel({
  details,
  defaultOpen = false,
}: {
  details: Record<string, unknown>;
  defaultOpen?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultOpen);

  const hasSections = DETAIL_SECTIONS.some(
    (s) =>
      typeof details[s.key] === "string" && (details[s.key] as string).trim(),
  );
  if (!hasSections) return null;

  const doctorRunUrl =
    typeof details.doctor_run_url === "string" ? details.doctor_run_url : null;
  const doctorEngine =
    typeof details.doctor_engine === "string" ? details.doctor_engine : null;
  const doctorModel =
    typeof details.doctor_model === "string" ? details.doctor_model : null;
  const trigger = typeof details.trigger === "string" ? details.trigger : null;

  return (
    <div className="mt-3 w-full">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-sm font-medium text-[var(--ph-text)] hover:opacity-80 transition-opacity"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        External Findings Details
      </button>
      {expanded && (
        <div className="mt-3 space-y-4 rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
          {(doctorEngine || doctorModel || trigger) && (
            <div className="flex flex-wrap items-center gap-2 pb-3 border-b border-[var(--ph-border)]">
              {doctorEngine && (
                <span className="inline-flex items-center rounded-md bg-[var(--ph-info-bg)] px-2 py-1 text-xs font-medium text-[var(--ph-info)]">
                  Engine: {doctorEngine}
                </span>
              )}
              {doctorModel && (
                <span className="inline-flex items-center rounded-md bg-[var(--ph-info-bg)] px-2 py-1 text-xs font-medium text-[var(--ph-info)]">
                  Model: {doctorModel}
                </span>
              )}
              {trigger && (
                <span className="inline-flex items-center rounded-md bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--ph-text)]">
                  Trigger: {trigger}
                </span>
              )}
              {doctorRunUrl && (
                <a
                  href={doctorRunUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center text-xs text-[var(--ph-accent)] hover:opacity-80"
                >
                  Doctor workflow run
                  <ExternalLink className="h-3 w-3 ml-1" />
                </a>
              )}
            </div>
          )}
          {DETAIL_SECTIONS.map(({ key, label }) => {
            const value = details[key];
            if (typeof value !== "string" || !value.trim()) return null;
            return <CollapsibleSection key={key} label={label} text={value} />;
          })}
        </div>
      )}
    </div>
  );
}

function IncidentRecordPanel({
  icon,
  sectionLabel,
  title,
  summary,
  children,
}: {
  icon: React.ReactNode;
  sectionLabel: string;
  title: string;
  summary: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-lg bg-[color:var(--ph-surface)] p-2 text-[var(--ph-accent)]">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-[var(--ph-muted)]">
            {sectionLabel}
          </p>
          <h3 className="mt-1 text-base font-semibold text-[var(--ph-text)]">
            {title}
          </h3>
          <p className="mt-1 text-sm text-[var(--ph-muted)]">{summary}</p>
        </div>
      </div>
      <div className="mt-4 space-y-4">{children}</div>
    </div>
  );
}

export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [showRawEvidence, setShowRawEvidence] = useState(false);
  const [showMcpDetails, setShowMcpDetails] = useState(false);
  const [showRawMcpCodes, setShowRawMcpCodes] = useState(false);

  const {
    data: activity,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["activity", id],
    queryFn: () => api.getActivity(id!),
    enabled: !!id,
  });
  const { data: handoffConfig } = useQuery({
    queryKey: ["agent-handoff-config"],
    queryFn: () => api.getAgentHandoffConfig(),
  });
  const { data: handoffSessions = [] } = useQuery({
    queryKey: ["activity-handoff-sessions", id],
    queryFn: () => api.getActivityHandoffSessions(id!),
    enabled: !!id,
  });

  const retryMutation = useMutation({
    mutationFn: () => api.retryActivity(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["activity", id] });
    },
  });

  const backfillMutation = useMutation({
    mutationFn: () => api.backfillDiagnostics(24),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["activity", id] });
    },
  });
  const handoffMutation = useMutation({
    mutationFn: (payload: HandoffSessionCreateRequest) =>
      api.createHandoffSession(id!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["activity", id] });
      queryClient.invalidateQueries({
        queryKey: ["activity-handoff-sessions", id],
      });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-[var(--ph-accent)] border-t-transparent rounded-full"></div>
        <span className="sr-only">Loading activity</span>
      </div>
    );
  }

  if (error || !activity) {
    return (
      <div className="card p-8 text-center">
        <AlertTriangle className="mx-auto h-12 w-12 text-[var(--ph-danger)]" />
        <h2 className="mt-4 text-lg font-semibold text-[var(--ph-text)]">
          Activity Not Found
        </h2>
        <p className="mt-2 text-[var(--ph-muted)]">
          The requested activity could not be found.
        </p>
        <Button asChild className="mt-4">
          <Link to="/app/activities">Back to Activities</Link>
        </Button>
      </div>
    );
  }
  const remediationMeta = getIssueProposalMeta(
    activity.remediation_result?.details,
  );
  const remediationDetails = activity.remediation_result?.details as
    | Record<string, unknown>
    | undefined;
  const currentVerification = getLatestVerification(remediationDetails);
  const verificationHistory = getVerificationHistory(remediationDetails);
  const externalDiagnostics = activity.external_diagnostics ?? [];
  const diagnosisDetails = activity.diagnosis?.error_details as
    | Record<string, unknown>
    | undefined;
  const sourceConfidenceImpact =
    aggregateConfidenceBySource(externalDiagnostics);
  const structuredEvidence = collectStructuredEvidence(diagnosisDetails);
  const rawEvidenceLines = collectRawEvidenceLines(diagnosisDetails);
  const sourceMetadata =
    activity.source_metadata && typeof activity.source_metadata === "object"
      ? (activity.source_metadata as Record<string, unknown>)
      : {};
  const classificationSignal =
    typeof diagnosisDetails?.classification_signal === "string"
      ? diagnosisDetails.classification_signal.trim()
      : "";
  const classificationPattern =
    typeof diagnosisDetails?.classification_pattern === "string"
      ? diagnosisDetails.classification_pattern.trim()
      : "";
  const externalSignalBefore =
    typeof diagnosisDetails?.external_signal_confidence_before === "number"
      ? diagnosisDetails.external_signal_confidence_before
      : null;
  const externalSignalAfter =
    typeof diagnosisDetails?.external_signal_confidence_after === "number"
      ? diagnosisDetails.external_signal_confidence_after
      : null;
  const externalSignalDelta =
    typeof diagnosisDetails?.external_signal_confidence_delta === "number"
      ? diagnosisDetails.external_signal_confidence_delta
      : null;
  const externalSignalSources = parseExternalSignalSources(
    diagnosisDetails?.external_signal_sources,
  );
  const learningContextTrace = activity.learning_context_trace;
  const diagnosisLearningMatches = learningContextTrace?.diagnosis_matches ?? [];
  const remediationLearningMatches =
    learningContextTrace?.remediation_matches ?? [];
  const llmRejection = activity.diagnosis?.llm_rejection;
  const llmFallbackLabel =
    activity.diagnosis?.diagnosis_source === "pattern"
      ? "Deterministic fallback was used."
      : "Fallback diagnosis was used.";
  const llmTelemetrySummary =
    activity.diagnosis?.diagnosis_source === "pattern"
      ? "PipelineHealer rejected the LLM payload and kept the deterministic diagnosis path for this activity."
      : "PipelineHealer rejected at least one LLM payload while constructing the diagnosis for this activity.";
  const mcpPath = activity.mcp_model_path;
  const mcpSourceAttribution = Object.entries(
    mcpPath?.source_attribution ?? {},
  ).sort((a, b) => b[1] - a[1]);
  const mcpToolUsage = Object.entries(mcpPath?.tool_invocations ?? {}).sort(
    (a, b) => b[1] - a[1],
  );
  const mcpToolCallCount = mcpToolUsage.reduce(
    (total, [, count]) => total + count,
    0,
  );
  const mcpActionAudit = [...(mcpPath?.action_audit ?? [])].slice(-8).reverse();
  const mcpReasonCode = (mcpPath?.reason || "").trim();
  const mcpReasonLabel = formatMcpReason(mcpReasonCode);
  const failureContext = activity.failure_context;
  const isJenkinsBridge =
    activity.source_selection_path === "jenkins_bridge" ||
    typeof sourceMetadata.provider === "string" &&
      sourceMetadata.provider.trim().toLowerCase() === "jenkins";
  const activitySourceInfo = getActivitySourceInfo(activity);
  const bridgeEvidenceQuality =
    typeof diagnosisDetails?.bridge_evidence_quality === "string"
      ? diagnosisDetails.bridge_evidence_quality
      : typeof sourceMetadata.evidence_quality === "string"
        ? sourceMetadata.evidence_quality
        : "";
  const bridgeClassificationReason =
    typeof diagnosisDetails?.classification_reason === "string"
      ? diagnosisDetails.classification_reason.trim()
      : "";
  const bridgeClassificationState =
    typeof diagnosisDetails?.bridge_classification_state === "string"
      ? diagnosisDetails.bridge_classification_state.trim()
      : "";
  const lowEvidenceBridge =
    isJenkinsBridge &&
    (bridgeEvidenceQuality === "summary_only" ||
      bridgeClassificationState === "summary_only_context");
  const sourceRunResultRaw =
    typeof sourceMetadata.job_result === "string"
      ? sourceMetadata.job_result
      : typeof diagnosisDetails?.bridge_run_result === "string"
        ? diagnosisDetails.bridge_run_result
        : "";
  const sourceRunResult = sourceRunResultRaw.trim();
  const sourceRunTrigger =
    typeof sourceMetadata.triggered_by === "string"
      ? sourceMetadata.triggered_by.trim()
      : "";
  const hasFailureContext = Boolean(
    failureContext?.failing_job ||
    failureContext?.failing_step ||
    failureContext?.failing_command ||
    failureContext?.signal,
  );
  const summaryLine = [
    formatFailureTypeHeadline(activity.failure_type),
    activity.repository_name,
    activity.workflow_name,
  ]
    .filter(Boolean)
    .join(" • ");
  const whatHappenedSummary = hasFailureContext
    ? [
        failureContext?.failing_job ? `Job ${failureContext.failing_job}` : null,
        failureContext?.failing_step ? `Step ${failureContext.failing_step}` : null,
        failureContext?.signal ? `Signal: ${failureContext.signal}` : null,
      ]
        .filter(Boolean)
        .join(" • ")
    : "Failure context was not captured for this pipeline run.";
  const remediationOutcomeSummary = activity.remediation_result
    ? `${formatActionTaken(activity.remediation_result.action_taken)} ${activity.remediation_result.success ? "completed successfully" : "did not complete successfully"}.`
    : "No remediation artifact was published for this activity.";
  const handleCopyContext = async () => {
    try {
      await copyToClipboard(buildActivityContext(activity));
      toast.success("Activity context copied");
    } catch {
      toast.error("Unable to copy activity context");
    }
  };
  const assignEnabled =
    Boolean(handoffConfig?.enabled) &&
    Boolean(handoffConfig?.enabled_targets?.length);
  const assignDisabledReason = !handoffConfig
    ? "Assign-to-Agent configuration is unavailable."
    : !handoffConfig.enabled
      ? "Assign-to-Agent is disabled by runtime configuration."
      : !handoffConfig.enabled_targets?.length
        ? "No external agent targets are enabled."
        : "Assign-to-Agent is unavailable.";
  const handleAssignToAgent = async () => {
    if (!handoffConfig) {
      toast.error("Assign-to-Agent configuration is unavailable");
      return;
    }
    const context = buildActivityContext(activity);
    if (handoffConfig.mode === "copy_only") {
      try {
        await copyToClipboard(context);
      } catch {
        toast.error("Unable to copy handoff context");
        return;
      }
    }
    handoffMutation.mutate(
      {
        target: handoffConfig.default_target,
        goal: buildHandoffGoal(activity),
        context,
        context_format: "markdown",
        send: handoffConfig.mode === "webhook",
      },
      {
        onSuccess: (result) => {
          if (
            result.delivery_status === "queued" ||
            result.delivery_status === "copied"
          ) {
            toast.success(
              result.message || "External agent handoff recorded",
            );
          } else if (result.delivery_status === "disabled") {
            toast.info(result.message || "Assign-to-Agent is disabled");
          } else {
            toast.error(result.message || "Assign-to-Agent handoff failed");
          }
        },
        onError: (err) => {
          toast.error(
            err instanceof Error
              ? err.message
              : "Assign-to-Agent handoff failed",
          );
        },
      },
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/app/activities"
            className="p-2 hover:bg-[var(--ph-bg-elevated)] rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-[var(--ph-muted)]" />
          </Link>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-[var(--ph-text)]">
              Activity Details
            </h1>
            <p className="text-sm text-[var(--ph-muted)]">{activity.id}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--ph-border)] bg-[color:var(--ph-bg-elevated)]/60 p-2">
          <button
            onClick={handleCopyContext}
            className="inline-flex h-9 items-center rounded-md border border-[var(--ph-border)] bg-[color:var(--ph-bg-elevated)] px-3 text-sm font-semibold text-[var(--ph-text)] transition-colors hover:bg-[color:var(--ph-surface)]"
          >
            <Copy className="mr-2 h-4 w-4" />
            Copy Context
          </button>
          <button
            type="button"
            aria-disabled={!assignEnabled || handoffMutation.isPending}
            disabled={!assignEnabled || handoffMutation.isPending}
            onClick={handleAssignToAgent}
            title={
              assignEnabled
                ? `Assign-to-Agent (${formatHandoffTarget(handoffConfig?.default_target ?? "codex_app_server")})`
                : assignDisabledReason
            }
            className={`inline-flex h-9 items-center rounded-md border border-[var(--ph-border)] bg-[color:var(--ph-bg-elevated)] px-3 text-sm font-semibold text-[var(--ph-text)] ${
              !assignEnabled || handoffMutation.isPending
                ? "cursor-not-allowed opacity-75"
                : "transition-colors hover:bg-[color:var(--ph-surface)]"
            }`}
          >
            <Bot className="mr-2 h-4 w-4" />
            Assign to Agent
            {!assignEnabled && (
              <span className="ml-2 inline-flex items-center rounded-md border border-[var(--ph-border)] bg-[color:var(--ph-surface)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--ph-text)]">
                {handoffConfig?.enabled ? "Needs setup" : "Disabled"}
              </span>
            )}
          </button>
          {(activity.status === "failed" || activity.status === "skipped") && (
            <button
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
              className="inline-flex h-9 items-center rounded-md bg-[var(--ph-accent)] px-3 text-sm font-semibold text-white transition-colors hover:brightness-95 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-4 w-4 mr-2 ${
                  retryMutation.isPending ? "animate-spin" : ""
                }`}
              />
              Retry
            </button>
          )}
        </div>
      </div>

      <div className="card overflow-hidden p-0">
        <div className="border-b border-[var(--ph-border)] bg-[var(--ph-surface)] px-6 py-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--ph-muted)]">
                Incident snapshot
              </p>
              <h2 className="mt-1 text-2xl font-semibold text-[var(--ph-text)]">
                {summaryLine}
              </h2>
              <p className="mt-2 max-w-3xl text-sm text-[var(--ph-muted)]">
                One record for the run, diagnosis, remediation decision, and any operator verification that followed.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={activity.status} />
              {isJenkinsBridge && sourceRunResult ? (
                <Badge variant="outline">
                  Jenkins {formatSourceRunResultLabel(sourceRunResult)}
                </Badge>
              ) : null}
              {activity.failure_type ? (
                <FailureTypeBadge type={activity.failure_type} />
              ) : (
                <Badge variant="outline">Failure Type Pending</Badge>
              )}
              {currentVerification ? (
                <Badge variant="outline">
                  Verified {formatVerificationOutcomeLabel(currentVerification.overall)}
                </Badge>
              ) : (
                <Badge variant="outline">Needs Verification</Badge>
              )}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-px bg-[var(--ph-border)] md:grid-cols-2 xl:grid-cols-4">
          <div className="bg-[var(--ph-surface)] px-6 py-5">
            <p className="text-[11px] uppercase tracking-wide text-[var(--ph-muted)]">
              Repository
            </p>
            <div className="mt-2 flex items-center">
              <GitBranch className="mr-2 h-4 w-4 text-[var(--ph-muted)]" />
              {activitySourceInfo.repositoryUrl ? (
                <a
                  href={activitySourceInfo.repositoryUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-[var(--ph-accent)] hover:opacity-80"
                >
                  {activity.repository_name}
                  <ExternalLink className="ml-1 inline h-3 w-3" />
                </a>
              ) : (
                <span className="font-medium text-[var(--ph-text)]">
                  {activity.repository_name}
                </span>
              )}
            </div>
            <p className="mt-3 text-[11px] text-[var(--ph-muted)]">
              Activity ID: {activity.id}
            </p>
          </div>
          <div className="bg-[var(--ph-surface)] px-6 py-5">
            <p className="text-[11px] uppercase tracking-wide text-[var(--ph-muted)]">
              {activitySourceInfo.runLabel}
            </p>
            <p className="mt-2 font-medium text-[var(--ph-text)]">
              {activity.workflow_name}
            </p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              {activitySourceInfo.runNumberLabel}
            </p>
            {activitySourceInfo.runUrl && (
              <a
                href={activitySourceInfo.runUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex items-center text-xs font-medium text-[var(--ph-accent)] hover:opacity-80"
              >
                Open {activitySourceInfo.runLinkLabel}
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            )}
          </div>
          <div className="bg-[var(--ph-surface)] px-6 py-5">
            <p className="text-[11px] uppercase tracking-wide text-[var(--ph-muted)]">
              Created
            </p>
            <p className="mt-2 font-medium text-[var(--ph-text)]">
              {format(new Date(activity.created_at), "PPpp")}
            </p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              {formatDistanceToNow(new Date(activity.created_at), {
                addSuffix: true,
              })}
            </p>
          </div>
          <div className="bg-[var(--ph-surface)] px-6 py-5">
            <p className="text-[11px] uppercase tracking-wide text-[var(--ph-muted)]">
              Updated
            </p>
            <p className="mt-2 font-medium text-[var(--ph-text)]">
              {format(new Date(activity.updated_at), "PPpp")}
            </p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              Duration:{" "}
              {typeof activity.duration_seconds === "number"
                ? `${Math.round(activity.duration_seconds)}s`
                : "N/A"}
            </p>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <div className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold text-[var(--ph-text)]">
            Incident Record
          </h2>
          <p className="text-sm text-[var(--ph-muted)]">
            Structured operator view of what happened, what PipelineHealer concluded, what action it took, and what still needs review.
          </p>
        </div>
        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <IncidentRecordPanel
            icon={<AlertTriangle className="h-4 w-4" />}
            sectionLabel="What happened"
            title="Failure context and run evidence"
            summary={whatHappenedSummary}
          >
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                  Failing Job
                </p>
                <p className="mt-1 text-sm text-[var(--ph-text)] break-words">
                  {failureContext?.failing_job || "Not captured"}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                  Failing Step
                </p>
                <p className="mt-1 text-sm text-[var(--ph-text)] break-words">
                  {failureContext?.failing_step || "Not captured"}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                  Command
                </p>
                <p className="mt-1 text-sm text-[var(--ph-text)] break-words">
                  {failureContext?.failing_command || "Not captured"}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                  Diagnostics
                </p>
                <p className="mt-1 text-sm text-[var(--ph-text)]">
                  {externalDiagnostics.length} external signal
                  {externalDiagnostics.length === 1 ? "" : "s"}
                </p>
              </div>
              {isJenkinsBridge && sourceRunResult ? (
                <div>
                  <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                    Source Run
                  </p>
                  <p className="mt-1 text-sm text-[var(--ph-text)]">
                    Jenkins {formatSourceRunResultLabel(sourceRunResult)}
                  </p>
                  {sourceRunTrigger ? (
                    <p className="mt-1 text-xs text-[var(--ph-muted)]">
                      Trigger: {sourceRunTrigger}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </IncidentRecordPanel>

          <IncidentRecordPanel
            icon={<ShieldCheck className="h-4 w-4" />}
            sectionLabel="What PipelineHealer concluded"
            title="Diagnosis and confidence"
            summary={
              activity.diagnosis
                ? activity.diagnosis.root_cause
                : "Diagnosis has not been captured for this activity."
            }
          >
            {activity.diagnosis ? (
              <>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">
                    Confidence {Math.round(activity.diagnosis.confidence * 100)}%
                  </Badge>
                  <Badge variant="outline">
                    Auto-fixable {activity.diagnosis.is_auto_fixable ? "Yes" : "No"}
                  </Badge>
                  <Badge variant="outline">
                    Source {(activity.diagnosis.diagnosis_source || "unknown").replace(/_/g, " ")}
                  </Badge>
                  {lowEvidenceBridge ? (
                    <Badge variant="outline">Low-evidence Jenkins payload</Badge>
                  ) : null}
                </div>
                {bridgeClassificationReason ? (
                  <div className="rounded-md border border-[var(--ph-warning)]/25 bg-[var(--ph-warning-bg)] px-3 py-3">
                    <p className="text-sm font-medium text-[var(--ph-text)]">
                      Evidence limitation
                    </p>
                    <p className="mt-1 text-sm text-[var(--ph-text)] break-words">
                      {bridgeClassificationReason}
                    </p>
                  </div>
                ) : null}
                {activity.diagnosis.suggested_fix ? (
                  <div>
                    <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                      {lowEvidenceBridge ? "Suggested Next Step" : "Suggested Fix"}
                    </p>
                    <p className="mt-1 text-sm text-[var(--ph-text)]">
                      {activity.diagnosis.suggested_fix}
                    </p>
                  </div>
                ) : null}
                {llmRejection?.rejected ? (
                  <div className="rounded-md border border-[var(--ph-warning)]/25 bg-[var(--ph-warning-bg)] px-3 py-3">
                    <p className="text-sm font-medium text-[var(--ph-text)]">
                      LLM diagnosis discarded
                    </p>
                    <p className="mt-1 text-sm text-[var(--ph-text)] break-words">
                      {llmRejection.reason ||
                        "The model response did not satisfy the diagnosis contract."}
                    </p>
                    <p className="mt-1 text-xs text-[var(--ph-muted)]">
                      {llmFallbackLabel} JSON candidates checked:{" "}
                      {llmRejection.candidate_count}
                    </p>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-[var(--ph-muted)]">
                This activity has no diagnosis payload yet.
              </p>
            )}
          </IncidentRecordPanel>

          <IncidentRecordPanel
            icon={<Workflow className="h-4 w-4" />}
            sectionLabel="What it did"
            title="Remediation artifact and publishing outcome"
            summary={remediationOutcomeSummary}
          >
            {activity.remediation_result ? (
              <>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                      Action Taken
                    </p>
                    <p className="mt-1 text-sm text-[var(--ph-text)]">
                      {formatActionTaken(activity.remediation_result.action_taken)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                      Success
                    </p>
                    <p
                      className={
                        activity.remediation_result.success
                          ? "mt-1 text-sm font-medium text-[var(--ph-success)]"
                          : "mt-1 text-sm font-medium text-[var(--ph-danger)]"
                      }
                    >
                      {activity.remediation_result.success ? "Yes" : "No"}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {activity.remediation_result.pr_url ? (
                    <a
                      href={activity.remediation_result.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center text-sm text-[var(--ph-accent)] hover:opacity-80"
                    >
                      Open Pull Request
                      <ExternalLink className="ml-1 h-4 w-4" />
                    </a>
                  ) : null}
                  {activity.remediation_result.issue_url ? (
                    <a
                      href={activity.remediation_result.issue_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center text-sm text-[var(--ph-accent)] hover:opacity-80"
                    >
                      Open Issue
                      <ExternalLink className="ml-1 h-4 w-4" />
                    </a>
                  ) : null}
                </div>
                {(remediationMeta.includesProposedFix ||
                  remediationMeta.reusedExistingPr ||
                  remediationMeta.appliedLearningId ||
                  remediationMeta.reasonCode ||
                  remediationMeta.reasonDetail) && (
                  <div>
                    <p className="text-xs uppercase tracking-wide text-[var(--ph-muted)]">
                      Publication metadata
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {remediationMeta.includesProposedFix ? (
                        <Badge variant="outline">Includes Proposed Fix</Badge>
                      ) : null}
                      {remediationMeta.reusedExistingPr ? (
                        <Badge variant="outline">Reused Existing PR</Badge>
                      ) : null}
                      {remediationMeta.appliedLearningId ? (
                        <Badge variant="outline">Applied Learning Guidance</Badge>
                      ) : null}
                      {remediationMeta.reasonCode ? (
                        <Badge variant="outline">{remediationMeta.reasonCode}</Badge>
                      ) : null}
                    </div>
                    {remediationMeta.reasonDetail ? (
                      <p className="mt-2 text-sm text-[var(--ph-text)]">
                        {remediationMeta.reasonDetail}
                      </p>
                    ) : null}
                    {activity.remediation_result.error_message ? (
                      <p className="mt-2 text-sm text-[var(--ph-danger)]">
                        {activity.remediation_result.error_message}
                      </p>
                    ) : null}
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-[var(--ph-muted)]">
                No remediation result has been recorded for this activity.
              </p>
            )}
          </IncidentRecordPanel>

          <IncidentRecordPanel
            icon={<KeyRound className="h-4 w-4" />}
            sectionLabel="What still needs review"
            title="Operator verification and feedback"
            summary={
              currentVerification
                ? `Latest overall verification is ${formatVerificationOutcomeLabel(currentVerification.overall)}.`
                : "This incident has not been operator-verified yet."
            }
          >
            <VerificationWorkspace
              activity={activity}
              currentVerification={currentVerification}
              verificationHistory={verificationHistory}
              appliedLearningId={remediationMeta.appliedLearningId}
              appliedLearningTitle={remediationMeta.appliedLearningTitle}
            />
          </IncidentRecordPanel>
        </div>
      </div>

      <HandoffSessionsPanel sessions={handoffSessions} />

      {/* External Diagnostics Card */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-[var(--ph-text)]">
            External Diagnostics
          </h2>
          {(activity.status === "completed" ||
            activity.status === "failed") && (
            <button
              onClick={() => backfillMutation.mutate()}
              disabled={backfillMutation.isPending}
              className="inline-flex items-center text-sm font-medium text-[var(--ph-accent)] hover:opacity-80 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 mr-1.5 ${backfillMutation.isPending ? "animate-spin" : ""}`}
              />
              {backfillMutation.isPending
                ? "Backfilling..."
                : "Backfill Diagnostics"}
            </button>
          )}
        </div>
        {externalDiagnostics.length === 0 ? (
          <p className="text-sm text-[var(--ph-muted)]">
            No external diagnostics available. PipelineHealer used built-in
            analysis only.
          </p>
        ) : (
          <div className="space-y-4">
            {externalDiagnostics.map((diagnostic, index) => {
              const metadata =
                diagnostic.metadata && typeof diagnostic.metadata === "object"
                  ? (diagnostic.metadata as Record<string, unknown>)
                  : {};
              const statusMeta = getExternalDiagnosticStatusMeta(
                diagnostic.status,
                metadata,
              );
              const sourceSelectionPath =
                typeof metadata?.source_selection_path === "string"
                  ? (metadata.source_selection_path as string)
                  : "";
              const sourceSelectionReason =
                typeof metadata?.source_selection_reason === "string"
                  ? (metadata.source_selection_reason as string)
                  : "";
              const openLinkLabel =
                sourceSelectionPath === "jenkins_bridge" ||
                diagnostic.source.trim().toLowerCase() === "jenkins-bridge"
                  ? "Open Jenkins job"
                  : "Open findings";
              return (
                <div
                  key={`${diagnostic.source}-${diagnostic.collected_at}-${index}`}
                  className="rounded-lg border border-[var(--ph-border)] p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center rounded-md bg-[var(--ph-info-bg)] px-2 py-1 text-xs font-medium text-[var(--ph-info)]">
                      {formatSourceLabel(diagnostic.source)}
                    </span>
                    <span className={statusMeta.className}>
                      {statusMeta.label}
                    </span>
                    {typeof diagnostic.matched_run_id === "number" && (
                      <span className="inline-flex items-center rounded-md bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--ph-text)]">
                        {sourceSelectionPath === "jenkins_bridge" ||
                        diagnostic.source.trim().toLowerCase() ===
                          "jenkins-bridge"
                          ? `Build #${diagnostic.matched_run_id}`
                          : `Run #${diagnostic.matched_run_id}`}
                      </span>
                    )}
                    <span className="inline-flex items-center rounded-md bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--ph-text)]">
                      {formatDiagnosticConfidenceLabel(
                        diagnostic.confidence_delta,
                        metadata,
                      )}
                    </span>
                  </div>

                  {diagnostic.summary && (
                    <p className="mt-3 text-sm text-[var(--ph-text)]">
                      {diagnostic.summary}
                    </p>
                  )}
                  {typeof metadata?.confidence_reason === "string" && (
                    <p className="mt-2 text-xs text-[var(--ph-muted)]">
                      Signal rationale:{" "}
                      {metadata.confidence_reason as string}
                    </p>
                  )}
                  {sourceSelectionPath && (
                    <p className="mt-2 text-xs text-[var(--ph-muted)]">
                      Source path:{" "}
                      {formatSourceSelectionPath(sourceSelectionPath)}
                      {sourceSelectionReason
                        ? ` (${sourceSelectionReason})`
                        : ""}
                    </p>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    {diagnostic.url && (
                      <a
                        href={diagnostic.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center text-sm text-[var(--ph-accent)] hover:opacity-80"
                      >
                        {openLinkLabel}
                        <ExternalLink className="h-4 w-4 ml-1" />
                      </a>
                    )}
                    {typeof metadata?.details === "object" &&
                      metadata.details !== null && (
                        <ExternalFindingsPanel
                          details={metadata.details as Record<string, unknown>}
                          defaultOpen={diagnostic.status === "available"}
                        />
                      )}
                  </div>
                  {!diagnostic.url &&
                    typeof metadata?.details !== "object" && (
                      <p className="mt-3 text-xs text-[var(--ph-muted)]">
                        No findings link published by the external workflow.
                      </p>
                    )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Diagnosis Card */}
      {activity.diagnosis && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-[var(--ph-text)] mb-4">
            Technical Analysis & Enrichment
          </h2>
          <div className="space-y-4">
            {hasFailureContext && (
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
                <p className="text-sm font-medium text-[var(--ph-text)]">
                  Failure Context
                </p>
                <div className="mt-2 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
                  <div>
                    <p className="text-[var(--ph-muted)]">Failing Job</p>
                    <p className="text-[var(--ph-text)] break-words">
                      {failureContext?.failing_job || "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Failing Step</p>
                    <p className="text-[var(--ph-text)] break-words">
                      {failureContext?.failing_step || "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Command</p>
                    <p className="text-[var(--ph-text)] break-words">
                      {failureContext?.failing_command || "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Signal</p>
                    <p className="text-[var(--ph-text)] break-words">
                      {failureContext?.signal || "N/A"}
                    </p>
                  </div>
                </div>
              </div>
            )}
            {classificationSignal && (
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
                <p className="text-sm font-medium text-[var(--ph-text)]">
                  Classification Signal
                </p>
                <p className="mt-1 text-sm text-[var(--ph-text)] break-words">
                  {classificationSignal}
                </p>
                {classificationPattern && (
                  <p
                    className="mt-1 break-all font-mono text-[11px] text-[var(--ph-muted)]"
                    title={classificationPattern}
                  >
                    rule: {classificationPattern}
                  </p>
                )}
              </div>
            )}
            {llmRejection?.rejected && (
              <div className="rounded-lg border border-[var(--ph-warning)]/25 bg-[var(--ph-warning-bg)] p-4">
                <p className="text-sm font-medium text-[var(--ph-text)]">
                  LLM Rejection Telemetry
                </p>
                <div className="mt-2 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
                  <div>
                    <p className="text-[var(--ph-muted)]">Discard Reason</p>
                    <p className="text-[var(--ph-text)] break-words">
                      {llmRejection.reason || "Unknown"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">JSON Candidates Checked</p>
                    <p className="text-[var(--ph-text)]">
                      {llmRejection.candidate_count}
                    </p>
                  </div>
                </div>
                <p className="mt-3 text-xs text-[var(--ph-muted)]">
                  {llmTelemetrySummary}
                </p>
              </div>
            )}
            {learningContextTrace &&
              (diagnosisLearningMatches.length > 0 ||
                remediationLearningMatches.length > 0) && (
                <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
                  <p className="text-sm font-medium text-[var(--ph-text)]">
                    Learning Context
                  </p>
                  <p className="mt-1 text-xs text-[var(--ph-muted)]">
                    Active playbooks retrieved for this activity and carried into diagnosis/remediation.
                  </p>
                  {diagnosisLearningMatches.length > 0 && (
                    <div className="mt-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
                        Diagnosis Retrieval
                      </p>
                      <div className="mt-2 space-y-2">
                        {diagnosisLearningMatches.map((match) => (
                          <div
                            key={`diag-${match.id}`}
                            className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)] px-3 py-2"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-medium text-[var(--ph-text)]">
                                {match.title}
                              </p>
                              <span className="text-xs text-[var(--ph-muted)]">
                                rank {match.match_rank} • score {match.match_score.toFixed(2)}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-[var(--ph-muted)]">
                              {match.id}
                              {match.reason_code ? ` • ${match.reason_code}` : ""}
                            </p>
                            {match.suggested_playbook && (
                              <p className="mt-1 text-sm text-[var(--ph-text)]">
                                {match.suggested_playbook}
                              </p>
                            )}
                            {match.match_basis.length > 0 && (
                              <p className="mt-1 text-xs text-[var(--ph-muted)]">
                                Match basis: {match.match_basis.join(", ")}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {remediationLearningMatches.length > 0 && (
                    <div className="mt-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
                        Remediation Retrieval
                      </p>
                      <div className="mt-2 space-y-2">
                        {remediationLearningMatches.map((match) => (
                          <div
                            key={`rem-${match.id}`}
                            className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)] px-3 py-2"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-medium text-[var(--ph-text)]">
                                {match.title}
                              </p>
                              <span className="text-xs text-[var(--ph-muted)]">
                                rank {match.match_rank} • score {match.match_score.toFixed(2)}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-[var(--ph-muted)]">
                              {match.id}
                              {match.reason_code ? ` • ${match.reason_code}` : ""}
                            </p>
                            {match.suggested_playbook && (
                              <p className="mt-1 text-sm text-[var(--ph-text)]">
                                {match.suggested_playbook}
                              </p>
                            )}
                            {match.match_basis.length > 0 && (
                              <p className="mt-1 text-xs text-[var(--ph-muted)]">
                                Match basis: {match.match_basis.join(", ")}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-[var(--ph-muted)]">Confidence</p>
                <div className="mt-1 flex items-center">
                  <div className="flex-1 bg-[var(--ph-bg-elevated)] rounded-full h-2 mr-2">
                    <div
                      className="bg-[var(--ph-accent)] h-2 rounded-full"
                      style={{
                        width: `${activity.diagnosis.confidence * 100}%`,
                      }}
                    />
                  </div>
                  <span className="text-sm font-medium text-[var(--ph-text)]">
                    {Math.round(activity.diagnosis.confidence * 100)}%
                  </span>
                </div>
              </div>
              <div>
                <p className="text-sm text-[var(--ph-muted)]">Auto-Fixable</p>
                <p className="mt-1 text-[var(--ph-text)]">
                  {activity.diagnosis.is_auto_fixable ? "Yes" : "No"}
                </p>
              </div>
              <div>
                <p className="text-sm text-[var(--ph-muted)]">
                  Diagnosis Source
                </p>
                <p className="mt-1 text-[var(--ph-text)] capitalize">
                  {activity.diagnosis.diagnosis_source || "unknown"}
                </p>
              </div>
            </div>
            {externalSignalDelta !== null && (
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
                <p className="text-sm font-medium text-[var(--ph-text)]">
                  External Signal Attribution
                </p>
                <div className="mt-2 grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
                  <div>
                    <p className="text-[var(--ph-muted)]">Confidence Before</p>
                    <p className="text-[var(--ph-text)]">
                      {externalSignalBefore !== null
                        ? `${Math.round(externalSignalBefore * 100)}%`
                        : "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">External Delta</p>
                    <p
                      className={
                        externalSignalDelta >= 0
                          ? "text-[var(--ph-success)]"
                          : "text-[var(--ph-danger)]"
                      }
                    >
                      {formatConfidenceDelta(externalSignalDelta)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Confidence After</p>
                    <p className="text-[var(--ph-text)]">
                      {externalSignalAfter !== null
                        ? `${Math.round(externalSignalAfter * 100)}%`
                        : "N/A"}
                    </p>
                  </div>
                </div>
                {externalSignalSources.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {externalSignalSources.map((signal, idx) => (
                      <div
                        key={`${signal.source}-${idx}`}
                        className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)] px-3 py-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-medium text-[var(--ph-text)]">
                            {formatSourceLabel(signal.source)}
                          </p>
                          <span
                            className={`text-xs font-semibold ${signal.delta >= 0 ? "text-[var(--ph-success)]" : "text-[var(--ph-danger)]"}`}
                          >
                            {formatConfidenceDelta(signal.delta)}
                          </span>
                        </div>
                        {signal.reason && (
                          <p className="mt-1 text-xs text-[var(--ph-muted)]">
                            {signal.reason}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {activity.llm_model_path && (
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
                <p className="text-sm font-medium text-[var(--ph-text)]">
                  Model Path
                </p>
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
                  <div>
                    <p className="text-[var(--ph-muted)]">Provider</p>
                    <p className="text-[var(--ph-text)]">
                      {activity.llm_model_path.provider}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Model/Deployment</p>
                    <p className="text-[var(--ph-text)] break-all">
                      {activity.llm_model_path.model}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Fallback Used</p>
                    <p className="text-[var(--ph-text)]">
                      {activity.llm_model_path.fallback_used ? "Yes" : "No"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">LLM Calls</p>
                    <p className="text-[var(--ph-text)]">
                      {activity.llm_model_path.call_count}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Total Latency</p>
                    <p className="text-[var(--ph-text)]">
                      {Math.round(activity.llm_model_path.total_latency_ms)} ms
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">LLM Errors</p>
                    <p className="text-[var(--ph-text)]">
                      {activity.llm_model_path.error_count}
                    </p>
                  </div>
                </div>
              </div>
            )}
            {mcpPath && (
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-[var(--ph-text)]">
                    MCP Observability
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowMcpDetails((prev) => !prev)}
                    className="text-xs font-medium text-[var(--ph-accent)] hover:opacity-80"
                  >
                    {showMcpDetails ? "Hide details" : "Show details"}
                  </button>
                </div>
                <div className="mt-2 grid grid-cols-1 gap-3 text-sm md:grid-cols-2 lg:grid-cols-6">
                  <div>
                    <p className="text-[var(--ph-muted)]">Provider</p>
                    <p className="text-[var(--ph-text)]">{mcpPath.provider}</p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Status</p>
                    <p className="text-[var(--ph-text)]">
                      {formatMcpStatus(mcpPath.enabled, mcpPath.available)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Read Only</p>
                    <p className="text-[var(--ph-text)]">
                      {mcpPath.read_only ? "Yes" : "No"}
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[var(--ph-muted)]">Reason</p>
                      {mcpReasonCode && (
                        <button
                          type="button"
                          onClick={() => setShowRawMcpCodes((prev) => !prev)}
                          className="text-[11px] font-medium text-[var(--ph-accent)] hover:opacity-80"
                        >
                          {showRawMcpCodes ? "Hide raw code" : "Show raw code"}
                        </button>
                      )}
                    </div>
                    <p className="text-[var(--ph-text)] break-words">
                      {mcpReasonLabel}
                    </p>
                    {mcpReasonCode && showRawMcpCodes && (
                      <p
                        className="mt-1 break-all font-mono text-[11px] text-[var(--ph-muted)]"
                        title={mcpReasonCode}
                      >
                        raw: {mcpReasonCode}
                      </p>
                    )}
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">MCP Tool Calls</p>
                    <p className="text-[var(--ph-text)]">{mcpToolCallCount}</p>
                  </div>
                  <div>
                    <p className="text-[var(--ph-muted)]">Total Latency</p>
                    <p className="text-[var(--ph-text)]">
                      {Math.round(mcpPath.total_latency_ms || 0)} ms
                    </p>
                  </div>
                </div>

                {showMcpDetails && (
                  <div className="mt-4 border-t border-[var(--ph-border)] pt-3">
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                      <div>
                        <p className="text-xs text-[var(--ph-muted)]">
                          Configured Tools
                        </p>
                        {mcpPath.configured_tools.length > 0 ? (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {mcpPath.configured_tools.map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center rounded-md bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-mono text-[var(--ph-text)]"
                              >
                                {tool}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-2 text-sm text-[var(--ph-muted)]">
                            No configured MCP tools for this provider.
                          </p>
                        )}
                      </div>
                      <div>
                        <p className="text-xs text-[var(--ph-muted)]">
                          Source Attribution
                        </p>
                        <p className="mt-1 text-xs text-[var(--ph-muted)]">
                          Includes passive GH-AW diagnostics and MCP-derived
                          signals. This can be non-zero even when MCP tool calls
                          are zero.
                        </p>
                        {mcpSourceAttribution.length > 0 ? (
                          <ul className="mt-2 space-y-1">
                            {mcpSourceAttribution.map(([source, count]) => (
                              <li
                                key={source}
                                className="flex items-center justify-between rounded border border-[var(--ph-border)] px-2 py-1 text-sm"
                              >
                                <span className="min-w-0">
                                  <span className="block text-[var(--ph-text)]">
                                    {formatSourceLabel(source)}
                                  </span>
                                  <span className="block break-all font-mono text-[11px] text-[var(--ph-muted)]">
                                    {source}
                                  </span>
                                </span>
                                <span className="font-mono text-xs text-[var(--ph-muted)]">
                                  {count}
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-2 text-sm text-[var(--ph-muted)]">
                            No external source attributions were recorded for
                            this activity.
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="mt-4">
                      <p className="text-xs text-[var(--ph-muted)]">
                        Tool Usage
                      </p>
                      {mcpToolUsage.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {mcpToolUsage.map(([tool, count]) => (
                            <li
                              key={tool}
                              className="flex items-center justify-between rounded border border-[var(--ph-border)] px-2 py-1 text-sm"
                            >
                              <span className="font-mono text-xs text-[var(--ph-text)]">
                                {tool}
                              </span>
                              <span className="font-mono text-xs text-[var(--ph-muted)]">
                                {count}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2 text-sm text-[var(--ph-muted)]">
                          No direct MCP tool invocations captured for this
                          activity yet. Passive diagnostics may still appear
                          under Source Attribution.
                        </p>
                      )}
                    </div>
                    <div className="mt-4">
                      <p className="text-xs text-[var(--ph-muted)]">
                        Action Audit
                      </p>
                      {mcpActionAudit.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {mcpActionAudit.map((entry, index) => {
                            const outcome = parseMcpActionResult(entry.result);
                            return (
                              <li
                                key={`${entry.request_id}-${entry.tool}-${entry.payload_hash}-${index}`}
                                className="rounded border border-[var(--ph-border)] px-2 py-1 text-xs"
                              >
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <p className="break-all font-mono text-[var(--ph-text)]">
                                    {entry.tool}
                                  </p>
                                  <span
                                    className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${mcpOutcomeBadgeClass(outcome.kind)}`}
                                  >
                                    {outcome.label}
                                  </span>
                                </div>
                                <p className="mt-1 break-words text-[11px] text-[var(--ph-text)]">
                                  {outcome.detail}
                                </p>
                                {outcome.code && showRawMcpCodes && (
                                  <p
                                    className="mt-0.5 break-all font-mono text-[11px] text-[var(--ph-muted)]"
                                    title={outcome.code}
                                  >
                                    raw: {outcome.code}
                                  </p>
                                )}
                                <p className="mt-1 text-[11px] text-[var(--ph-muted)]">
                                  actor: {entry.actor} • provider:{" "}
                                  {entry.provider} • request: {entry.request_id}
                                </p>
                                <p className="text-[11px] text-[var(--ph-muted)]">
                                  payload: {entry.payload_hash} • latency:{" "}
                                  {Math.round(entry.latency_ms || 0)} ms
                                  {entry.error_class
                                    ? ` • error: ${entry.error_class}`
                                    : ""}
                                </p>
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <p className="mt-2 text-sm text-[var(--ph-muted)]">
                          No MCP action audit entries captured for this
                          activity.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            {(sourceConfidenceImpact.length > 0 ||
              structuredEvidence.length > 0 ||
              rawEvidenceLines.length > 0) && (
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-[var(--ph-text)]">
                    Evidence Layers
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowRawEvidence((prev) => !prev)}
                    disabled={rawEvidenceLines.length === 0}
                    className="text-xs font-medium text-[var(--ph-accent)] hover:opacity-80 disabled:text-[var(--ph-muted)] disabled:cursor-not-allowed"
                  >
                    {showRawEvidence
                      ? "Hide raw extracts"
                      : "Show raw extracts"}
                  </button>
                </div>
                <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <p className="text-xs text-[var(--ph-muted)]">
                      Confidence Impact By Source
                    </p>
                    {sourceConfidenceImpact.length > 0 ? (
                      <div className="space-y-2">
                        {sourceConfidenceImpact.map((item) => (
                          <div
                            key={item.source}
                            className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)] px-3 py-2"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-medium text-[var(--ph-text)]">
                                {formatSourceLabel(item.source)}
                              </p>
                              <span
                                className={`text-xs font-semibold ${item.delta >= 0 ? "text-[var(--ph-success)]" : "text-[var(--ph-danger)]"}`}
                              >
                                {formatConfidenceDelta(item.delta)}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-[var(--ph-muted)]">
                              Samples: {item.samples} • Available findings:{" "}
                              {item.available}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-[var(--ph-muted)]">
                        No external confidence signals recorded.
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <p className="text-xs text-[var(--ph-muted)]">
                      Structured Context
                    </p>
                    {structuredEvidence.length > 0 ? (
                      <div className="space-y-2">
                        {structuredEvidence.map((item) => (
                          <div
                            key={item.key}
                            className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-surface)] px-3 py-2"
                          >
                            <p className="text-xs text-[var(--ph-muted)]">
                              {item.label}
                            </p>
                            <p className="mt-1 text-sm text-[var(--ph-text)] break-words">
                              {item.value}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-[var(--ph-muted)]">
                        No additional structured context in this activity.
                      </p>
                    )}
                  </div>
                </div>
                {showRawEvidence && (
                  <div className="mt-4 border-t border-[var(--ph-border)] pt-3">
                    <p className="text-xs text-[var(--ph-muted)]">
                      Raw Log Extracts
                    </p>
                    {rawEvidenceLines.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {rawEvidenceLines.map((line, index) => (
                          <li
                            key={`${line}-${index}`}
                            className="rounded bg-[var(--ph-bg-elevated)] px-2 py-1 text-xs font-mono text-[var(--ph-text)]"
                          >
                            {line}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-sm text-[var(--ph-muted)]">
                        Raw extracts are not present in this diagnosis payload.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
            {activity.diagnosis.affected_files.length > 0 && (
              <div>
                <p className="text-sm text-[var(--ph-muted)]">Affected Files</p>
                <div className="mt-2 space-y-1">
                  {activity.diagnosis.affected_files.map((file) => (
                    <div
                      key={file}
                      className="flex items-center text-sm text-[var(--ph-text)]"
                    >
                      <FileCode className="h-4 w-4 text-[var(--ph-muted)] mr-2" />
                      <code className="bg-[var(--ph-bg-elevated)] px-2 py-0.5 rounded">
                        {file}
                      </code>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Error Card */}
      {activity.error && (
        <div className="card border-[var(--ph-danger-border)] bg-[var(--ph-danger-bg)] p-6">
          <h2 className="mb-2 text-lg font-semibold text-[var(--ph-danger)]">Error</h2>
          <p className="text-[var(--ph-text)]">{activity.error}</p>
        </div>
      )}
    </div>
  );
}
