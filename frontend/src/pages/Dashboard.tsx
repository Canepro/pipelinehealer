import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Activity,
  ArrowRight,
  CheckCircle,
  Clock,
  FileText,
  ShieldAlert,
  SearchCheck,
  Copy,
  ExternalLink,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "../api/client";
import type { Activity as ActivityItem } from "../api/client";
import { EMPTY_STATES } from "../constants/emptyStates";
import { buildActivitiesDrilldownPath } from "../utils/activityFilters";
import { copyToClipboard } from "../utils/copyToClipboard";
import {
  getRepresentativeExternalDiagnostic,
  hasStrongExternalDiagnostic,
  isContextOnlyExternalDiagnostic,
} from "../utils/externalDiagnostics";
import StatsCard from "../components/StatsCard";
import ActivityTable from "../components/ActivityTable";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function getCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function useChartTheme() {
  const [theme, setTheme] = useState({
    tooltipBg: "#1e293b",
    tooltipBorder: "#475569",
    tooltipText: "#e2e8f0",
    gridStroke: "#475569",
    tickFill: "#96a5b6",
  });
  useEffect(() => {
    const update = () =>
      setTheme({
        tooltipBg: getCssVar("--ph-tooltip-bg") || "#1e293b",
        tooltipBorder: getCssVar("--ph-tooltip-border") || "#475569",
        tooltipText: getCssVar("--ph-tooltip-text") || "#e2e8f0",
        gridStroke: getCssVar("--ph-border") || "#475569",
        tickFill: getCssVar("--ph-muted") || "#96a5b6",
      });
    update();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    // Older Safari/WebView runtimes still use addListener/removeListener here.
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", update);
      return () => mq.removeEventListener("change", update);
    }
    mq.addListener(update);
    return () => mq.removeListener(update);
  }, []);
  return theme;
}

const COLORS = [
  "#2563eb",
  "#0ea5e9",
  "#14b8a6",
  "#16a34a",
  "#f59e0b",
  "#64748b",
];
const REASON_LABELS: Record<string, string> = {
  OUTSIDE_ALLOWED_FILES: "Touches non-allowlisted files.",
  LOW_CONFIDENCE: "Model confidence below threshold.",
  MISSING_CONTEXT: "Insufficient logs or stack trace.",
  REQUIRES_ENV_CONTEXT: "Needs repo/environment context not available.",
  SAFETY_BOUND: "Blocked by configured safety policy.",
};

function formatReasonLabel(code: string | null): string {
  if (!code) return "N/A";
  if (REASON_LABELS[code]) return REASON_LABELS[code];
  return code
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getEvidenceLines(activity: ActivityItem | null): string[] {
  const lines: string[] = [];
  const details = (activity?.diagnosis?.error_details ?? {}) as Record<
    string,
    unknown
  >;
  const listKeys = [
    "key_log_lines",
    "relevant_log_lines",
    "log_messages",
    "evidence",
  ];
  for (const key of listKeys) {
    const value = details[key];
    if (!Array.isArray(value)) continue;
    for (const line of value) {
      if (typeof line !== "string" || line.trim().length === 0) continue;
      lines.push(line.trim());
      if (lines.length >= 2) {
        return lines;
      }
    }
  }
  const message = details.message;
  if (typeof message === "string" && message.trim().length > 0) {
    lines.push(message.trim());
  }
  const context = activity?.failure_context;
  if (context) {
    if (
      typeof context.failing_step === "string" &&
      context.failing_step.trim().length > 0
    ) {
      lines.push(`Step: ${context.failing_step.trim()}`);
    }
    if (
      typeof context.failing_command === "string" &&
      context.failing_command.trim().length > 0
    ) {
      lines.push(`Command: ${context.failing_command.trim()}`);
    }
    if (
      typeof context.signal === "string" &&
      context.signal.trim().length > 0
    ) {
      lines.push(`Signal: ${context.signal.trim()}`);
    }
  }
  const rootCause = activity?.diagnosis?.root_cause;
  if (typeof rootCause === "string" && rootCause.trim().length > 0) {
    lines.push(rootCause.trim());
  }
  if (lines.length > 0) return lines.slice(0, 2);

  const representative = activity
    ? getRepresentativeExternalDiagnostic(activity)
    : null;
  if (!representative) return [];
  if (isContextOnlyExternalDiagnostic(representative)) return [];
  const meta = representative.metadata as Record<string, unknown>;
  const detailsBlock = meta.details as Record<string, unknown> | undefined;
  if (detailsBlock) {
    const candidateKeys = ["summary", "root_cause", "investigation_findings"];
    for (const key of candidateKeys) {
      const value = detailsBlock[key];
      if (typeof value !== "string" || value.trim().length === 0) continue;
      lines.push(value.trim());
      if (lines.length >= 2) return lines;
    }
  }
  if (representative.summary && representative.summary.trim().length > 0) {
    lines.push(representative.summary.trim());
  }
  return lines.slice(0, 2);
}

function shortActivityId(id: string): string {
  if (id.length <= 18) return id;
  return `${id.slice(0, 8)}...${id.slice(-6)}`;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const chartTheme = useChartTheme();
  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    error: statsErrorValue,
  } = useQuery({
    queryKey: ["stats"],
    queryFn: api.getStats,
    retry: 1,
  });

  const { data: activities, isLoading: activitiesLoading } = useQuery({
    queryKey: ["activities", { limit: 50 }],
    queryFn: () => api.getActivities({ limit: 50 }),
  });

  const { data: failureBreakdown } = useQuery({
    queryKey: ["failureBreakdown"],
    queryFn: () => api.getFailureBreakdown(30),
  });

  // Transform failure breakdown for pie chart
  const pieData = failureBreakdown
    ? Object.entries(failureBreakdown).map(([name, value]) => ({
        failureType: name,
        name: formatReasonLabel(name),
        value,
      }))
    : [];
  const totalFailures = pieData.reduce((sum, item) => sum + item.value, 0);

  // Transform repository data for bar chart
  const repoData = stats?.by_repository
    ? Object.entries(stats.by_repository)
        .slice(0, 5)
        .map(([name, value]) => ({
          fullName: name,
          name: name.split("/")[1] || name,
          count: value,
        }))
    : [];
  const topRepository = repoData[0];

  const safetyGatedRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round(
          (stats.safety_blocked_remediations / stats.actioned_remediations) *
            100,
        )
      : 0
    : 0;
  const issueRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round(
          (stats.issue_remediations / stats.actioned_remediations) * 100,
        )
      : 0
    : 0;
  const successRate = stats
    ? stats.actioned_remediations > 0
      ? Math.round(
          (stats.successful_remediations / stats.actioned_remediations) * 100,
        )
      : 0
    : 0;
  const llmFallbackRate30d = stats
    ? Math.round(stats.llm_fallback_rate_30d)
    : 0;
  const recentActivities = (activities || []).slice(0, 5);
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(
    null,
  );
  const [showRawReasonCode, setShowRawReasonCode] = useState(false);

  useEffect(() => {
    if (!selectedActivityId && recentActivities.length > 0) {
      setSelectedActivityId(recentActivities[0].id);
    }
  }, [recentActivities, selectedActivityId]);

  const selectedActivity = useMemo(() => {
    if (recentActivities.length === 0) return null;
    return (
      recentActivities.find((activity) => activity.id === selectedActivityId) ||
      recentActivities[0]
    );
  }, [recentActivities, selectedActivityId]);

  const selectedReasonCode =
    typeof selectedActivity?.remediation_result?.details
      ?.not_auto_reason_code === "string"
      ? selectedActivity.remediation_result.details.not_auto_reason_code
      : null;
  const selectedReasonLabel = formatReasonLabel(selectedReasonCode);
  const selectedActionTaken =
    typeof selectedActivity?.remediation_result?.action_taken === "string"
      ? selectedActivity.remediation_result.action_taken
          .replace("_", " ")
          .toUpperCase()
      : "N/A";
  const selectedConfidence =
    typeof selectedActivity?.diagnosis?.confidence === "number"
      ? `${Math.round(selectedActivity.diagnosis.confidence * 100)}%`
      : "N/A";
  const selectedDiagnosisSource =
    selectedActivity?.diagnosis?.diagnosis_source === "llm"
      ? "LLM"
      : selectedActivity?.diagnosis?.diagnosis_source === "pattern"
        ? "Pattern"
        : "Unknown";
  const selectedModelPath = selectedActivity?.llm_model_path
    ? `${selectedActivity.llm_model_path.provider}:${selectedActivity.llm_model_path.model}`
    : "N/A";
  const selectedFallbackUsed = selectedActivity?.llm_model_path?.fallback_used
    ? "Yes"
    : "No";
  const selectedLlmCalls = selectedActivity?.llm_model_path?.call_count ?? 0;
  const selectedFailureType = selectedActivity?.failure_type || "unknown";
  const selectedClassificationSignal =
    typeof selectedActivity?.diagnosis?.error_details?.classification_signal ===
    "string"
      ? selectedActivity.diagnosis.error_details.classification_signal
      : "";
  const selectedArtifactUrl =
    selectedActivity?.remediation_result?.pr_url ||
    selectedActivity?.remediation_result?.issue_url ||
    null;
  const selectedRunUrl =
    selectedActivity?.repository_name && selectedActivity?.workflow_run_id
      ? `https://github.com/${selectedActivity.repository_name}/actions/runs/${selectedActivity.workflow_run_id}`
      : null;
  const evidenceLines = useMemo(
    () => getEvidenceLines(selectedActivity),
    [selectedActivity],
  );

  const safetyGateReasonCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const activity of activities || []) {
      const reason =
        activity?.remediation_result?.details?.not_auto_reason_code;
      if (typeof reason === "string" && reason.length > 0) {
        counts.set(reason, (counts.get(reason) || 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .map(([code, count]) => ({ code, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 4);
  }, [activities]);
  const externalSignalCount = useMemo(
    () =>
      (activities || []).filter((activity) => hasStrongExternalDiagnostic(activity))
        .length,
    [activities],
  );
  const lastUpdatedLabel = stats?.last_updated
    ? new Date(stats.last_updated).toLocaleString()
    : "Unavailable";

  const showStatsLoading = statsLoading && !statsError;
  const statsErrorMessage =
    statsError && statsErrorValue instanceof Error
      ? statsErrorValue.message
      : "Stats temporarily unavailable";
  const handleActivitiesDrilldown = (filters: {
    repository?: string;
    failureType?: string;
  }) => {
    navigate(buildActivitiesDrilldownPath(filters));
  };
  const handleRepositoryBarClick = (repositoryName?: string) => {
    if (!repositoryName) return;
    handleActivitiesDrilldown({ repository: repositoryName });
  };
  const handleFailureTypeSliceClick = (failureType?: string) => {
    if (!failureType) return;
    handleActivitiesDrilldown({ failureType });
  };

  return (
    <div className="space-y-8">
      {/* Executive header */}
      <Card>
        <CardContent className="p-5 md:p-6">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-center xl:justify-between">
            <div className="max-w-2xl">
              <h1 className="text-2xl font-semibold tracking-tight text-[var(--ph-text)] sm:text-3xl">
                Pipeline Reliability Dashboard
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-[var(--ph-muted)] sm:text-base">
                Track remediation throughput, safety posture, and external
                diagnostic signals from one place.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button asChild size="sm">
                  <Link to="/app/activities">
                    Review Activities
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="sm" variant="secondary">
                  <Link to="/app/control-center">Control Center</Link>
                </Button>
                <Button asChild size="sm" variant="ghost">
                  <Link to="/app/settings">Runtime Settings</Link>
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:min-w-[360px] lg:grid-cols-3">
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs text-[var(--ph-muted)]">Success rate</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {successRate}%
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs text-[var(--ph-muted)]">
                  External signals
                </p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {externalSignalCount}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs text-[var(--ph-muted)]">MCP runs (30d)</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {stats?.mcp_enabled_runs_30d ?? 0}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs text-[var(--ph-muted)]">
                  LLM fallback (30d)
                </p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {llmFallbackRate30d}%
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs text-[var(--ph-muted)]">Avg resolution</p>
                <p className="mt-1 text-lg font-semibold text-[var(--ph-text)]">
                  {stats?.average_resolution_time_seconds
                    ? `${Math.round(stats.average_resolution_time_seconds)}s`
                    : "N/A"}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)]/75 p-3">
                <p className="text-xs text-[var(--ph-muted)]">Last updated</p>
                <p className="mt-1 truncate text-sm font-medium text-[var(--ph-text)]">
                  {lastUpdatedLabel}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-[var(--ph-text)]">
            Healing Throughput
          </h2>
          <Badge variant="outline">Last 30 days</Badge>
        </div>
        {showStatsLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Card key={`stats-skeleton-${index}`}>
                <CardContent className="p-4 md:p-5 space-y-3">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-8 w-20" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatsCard
              title="Processed"
              value={stats?.total_runs_processed || 0}
              icon={Activity}
              color="blue"
            />
            <StatsCard
              title="Actioned"
              value={stats?.actioned_remediations || 0}
              icon={CheckCircle}
              color="green"
            />
            <StatsCard
              title="Safety Gated"
              value={`${stats?.safety_blocked_remediations || 0} (${safetyGatedRate}%)`}
              icon={ShieldAlert}
              color="red"
            />
            <StatsCard
              title="Issue-Only"
              value={`${stats?.issue_remediations || 0} (${issueRate}%)`}
              icon={FileText}
              color="yellow"
            />
          </div>
        )}
      </section>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Why Safety Gated</CardTitle>
          <p className="text-sm text-[var(--ph-muted)]">
            We create review-ready proposals when changes touch non-allowlisted
            paths or require extra context.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 pt-0">
          {safetyGateReasonCounts.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {safetyGateReasonCounts.map((item) => (
                <div
                  key={item.code}
                  className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] px-3 py-2 text-xs text-[var(--ph-text)]"
                >
                  <div className="font-semibold">
                    {formatReasonLabel(item.code)} ({item.count})
                  </div>
                  <div className="mt-1 text-[var(--ph-muted)]">
                    <span className="font-mono">{item.code}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div>
              <p className="text-sm font-medium text-[var(--ph-text)]">
                {EMPTY_STATES.safetyGated.title}
              </p>
              <p className="mt-1 text-sm text-[var(--ph-muted)]">
                {EMPTY_STATES.safetyGated.body}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {statsError && (
        <div className="rounded-lg border border-[var(--ph-warning-border)] bg-[var(--ph-warning-bg)] px-4 py-3 text-sm text-[var(--ph-warning)]">
          Dashboard stats endpoint is unavailable: {statsErrorMessage}
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Failure Types Pie Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              Failure Types (Last 30 Days)
            </CardTitle>
            <p className="text-sm text-[var(--ph-muted)]">
              Total failures observed:{" "}
              <span className="font-semibold text-[var(--ph-text)]">
                {totalFailures}
              </span>
            </p>
            <p className="text-sm text-[var(--ph-muted)]">
              Click a slice to open Activities filtered to that failure type.
            </p>
          </CardHeader>
          <CardContent>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    fill="#8884d8"
                    paddingAngle={2}
                    dataKey="value"
                    cursor="pointer"
                    label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                    fontSize={12}
                    onClick={(
                      data: { payload?: { failureType?: string } } | undefined,
                    ) =>
                      handleFailureTypeSliceClick(
                        typeof data?.payload?.failureType === "string"
                          ? data.payload.failureType
                          : undefined,
                      )
                    }
                  >
                    {pieData.map((_, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={COLORS[index % COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, _name, item) => [
                      `${value} case${value === 1 ? "" : "s"}`,
                      item.payload.name,
                    ]}
                    contentStyle={{
                      backgroundColor: chartTheme.tooltipBg,
                      border: `1px solid ${chartTheme.tooltipBorder}`,
                      borderRadius: "8px",
                      color: chartTheme.tooltipText,
                      fontSize: "12px",
                      padding: "8px 10px",
                    }}
                    labelStyle={{ color: chartTheme.tooltipText, fontWeight: 500 }}
                    itemStyle={{ color: chartTheme.tooltipText }}
                    wrapperStyle={{ maxWidth: "min(90vw, 320px)" }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] flex-col items-center justify-center gap-3 text-sm text-[var(--ph-muted)]">
                <p>{EMPTY_STATES.activities.body}</p>
                <Button asChild size="sm" variant="secondary">
                  <a
                    href="https://github.com/Canepro/pipelinehealer-demo"
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Open demo repo
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top Repositories Bar Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Top Repositories</CardTitle>
            <p className="text-sm text-[var(--ph-muted)]">
              Most active repo:{" "}
              <span className="font-semibold text-[var(--ph-text)]">
                {topRepository?.name || "N/A"}
              </span>{" "}
              <span className="text-[var(--ph-muted)]">
                ({topRepository?.count || 0} runs)
              </span>
            </p>
            <p className="text-sm text-[var(--ph-muted)]">
              Click a bar to open Activities filtered to that repository.
            </p>
          </CardHeader>
          <CardContent>
            {repoData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={repoData}>
                  <CartesianGrid
                    strokeDasharray="2 4"
                    stroke={chartTheme.gridStroke}
                    strokeOpacity={0.25}
                    vertical={false}
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: chartTheme.tickFill, fontSize: 12 }}
                    interval={0}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: chartTheme.tickFill, fontSize: 12 }}
                    tickCount={5}
                    axisLine={false}
                    tickLine={false}
                    width={40}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: chartTheme.tooltipBg,
                      border: `1px solid ${chartTheme.tooltipBorder}`,
                      borderRadius: "8px",
                      color: chartTheme.tooltipText,
                      fontSize: "12px",
                      padding: "8px 10px",
                    }}
                    labelStyle={{ color: chartTheme.tooltipText, fontWeight: 500 }}
                    itemStyle={{ color: chartTheme.tooltipText }}
                    formatter={(value: number) => [
                      `${value} run${value === 1 ? "" : "s"}`,
                      "Runs",
                    ]}
                    wrapperStyle={{ maxWidth: "min(90vw, 320px)" }}
                  />
                  <Bar
                    dataKey="count"
                    fill="#3b82f6"
                    radius={[4, 4, 0, 0]}
                    cursor="pointer"
                    onClick={(data: { payload?: { fullName?: string } } | undefined) =>
                      handleRepositoryBarClick(
                        typeof data?.payload?.fullName === "string"
                          ? data.payload.fullName
                          : undefined,
                      )
                    }
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] flex-col items-center justify-center gap-3 text-sm text-[var(--ph-muted)]">
                <p>{EMPTY_STATES.activities.body}</p>
                <Button asChild size="sm" variant="secondary">
                  <a
                    href="https://github.com/Canepro/pipelinehealer-demo"
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Open demo repo
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Explainability Snapshot */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <SearchCheck className="h-4 w-4 text-[var(--ph-accent)]" />
            Explainability Snapshot
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {recentActivities.length > 0 ? (
            <>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-xs text-[var(--ph-muted)]">
                    Selected activity
                  </span>
                  <select
                    value={selectedActivity?.id || ""}
                    onChange={(e) => setSelectedActivityId(e.target.value)}
                    className="h-10 w-full rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] px-3 py-2 text-sm text-[var(--ph-text)] focus:outline-none focus:ring-2 focus:ring-azure-500"
                  >
                    {recentActivities.map((activity) => (
                      <option key={activity.id} value={activity.id}>
                        Run #{activity.workflow_run_id} ·{" "}
                        {activity.failure_type || "unknown"}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="flex flex-wrap items-end gap-2">
                  <Button asChild variant="secondary" size="sm">
                    <Link
                      to={`/app/activities?focus=${selectedActivity?.id || ""}`}
                    >
                      View activity
                    </Link>
                  </Button>
                  {selectedArtifactUrl && (
                    <Button asChild variant="ghost" size="sm">
                      <a
                        href={selectedArtifactUrl}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        Open Issue/PR
                      </a>
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => {
                      const traceId = selectedActivity?.id || "";
                      try {
                        await copyToClipboard(traceId);
                        toast.success("Activity ID copied");
                      } catch {
                        toast.error("Copy failed");
                      }
                    }}
                  >
                    <Copy className="mr-1 h-4 w-4" />
                    Copy ID
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-6">
                <div className="min-w-0 rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs text-[var(--ph-muted)]">Failure type</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">
                    {selectedFailureType}
                  </p>
                  {selectedClassificationSignal && (
                    <p
                      className="mt-1 line-clamp-2 text-xs text-[var(--ph-muted)]"
                      title={`Pattern signal: ${selectedClassificationSignal}`}
                    >
                      Signal: {selectedClassificationSignal}
                    </p>
                  )}
                </div>
                <div className="min-w-0 rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs text-[var(--ph-muted)]">Confidence</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">
                    {selectedConfidence}
                  </p>
                </div>
                <div className="min-w-0 rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs text-[var(--ph-muted)]">
                    Diagnosis source
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[var(--ph-text)]">
                    {selectedDiagnosisSource}
                  </p>
                </div>
                <div className="min-w-0 rounded-lg border border-[var(--ph-border)] p-3 md:col-span-2 xl:col-span-2">
                  <p className="text-xs text-[var(--ph-muted)]">Model path</p>
                  <p
                    className="mt-1 truncate text-sm font-semibold text-[var(--ph-text)]"
                    title={selectedModelPath}
                  >
                    {selectedModelPath}
                  </p>
                  {selectedActivity?.llm_model_path && (
                    <p className="mt-1 text-xs text-[var(--ph-muted)]">
                      Calls: {selectedLlmCalls} • Fallback used:{" "}
                      {selectedFallbackUsed}
                    </p>
                  )}
                </div>
                <div className="min-w-0 rounded-lg border border-[var(--ph-border)] p-3">
                  <p className="text-xs text-[var(--ph-muted)]">
                    Proposed action
                  </p>
                  <p className="mt-1 break-words text-sm font-semibold text-[var(--ph-text)]">
                    {selectedActionTaken}
                  </p>
                </div>
                <div className="min-w-0 rounded-lg border border-[var(--ph-border)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-[var(--ph-muted)]">
                      Safety gate
                    </p>
                    {selectedReasonCode && (
                      <button
                        type="button"
                        onClick={() => setShowRawReasonCode((prev) => !prev)}
                        className="text-[11px] font-medium text-[var(--ph-accent)] hover:opacity-80"
                      >
                        {showRawReasonCode ? "Hide raw code" : "Show raw code"}
                      </button>
                    )}
                  </div>
                  <p className="mt-1 break-words text-sm font-semibold text-[var(--ph-text)]">
                    {selectedReasonLabel}
                  </p>
                  {selectedReasonCode && showRawReasonCode && (
                    <p
                      className="mt-1 break-all font-mono text-[11px] text-[var(--ph-muted)]"
                      title={selectedReasonCode}
                    >
                      raw: {selectedReasonCode}
                    </p>
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-[var(--ph-border)] p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs text-[var(--ph-muted)]">Evidence</p>
                  <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
                    {selectedRunUrl && (
                      <Button asChild size="sm" variant="ghost">
                        <a
                          href={selectedRunUrl}
                          rel="noopener noreferrer"
                          target="_blank"
                        >
                          Workflow run
                          <ExternalLink className="ml-1 h-3.5 w-3.5" />
                        </a>
                      </Button>
                    )}
                    {selectedActivity?.id && (
                      <Badge
                        variant="secondary"
                        className="max-w-full truncate font-mono text-[11px]"
                        title={selectedActivity.id}
                      >
                        {shortActivityId(selectedActivity.id)}
                      </Badge>
                    )}
                  </div>
                </div>
                {evidenceLines.length > 0 ? (
                  <ul className="space-y-1 text-sm text-[var(--ph-text)]">
                    {evidenceLines.map((line, index) => (
                      <li
                        key={index}
                        className="line-clamp-2 break-words"
                        title={line}
                      >
                        {line}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-[var(--ph-muted)]">
                    No structured evidence lines available.
                  </p>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-[var(--ph-muted)]">
              {EMPTY_STATES.activities.body}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Recent Activities */}
      <section className="space-y-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-[var(--ph-text)]">
            Recent Activities
          </h2>
          <Button asChild size="sm" variant="ghost">
            <Link to="/app/activities">View all</Link>
          </Button>
        </div>
        <ActivityTable
          activities={recentActivities}
          isLoading={activitiesLoading}
        />
      </section>

      {/* Average Resolution Time */}
      {stats && stats.average_resolution_time_seconds > 0 && (
        <Card>
          <CardContent className="p-4 md:p-6">
            <div className="flex items-center gap-4">
              <Clock className="h-8 w-8 text-[var(--ph-accent)]" />
              <div>
                <p className="text-sm text-[var(--ph-muted)]">
                  Average resolution time
                </p>
                <p className="text-2xl font-semibold text-[var(--ph-text)]">
                  {Math.round(stats.average_resolution_time_seconds)}s
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
