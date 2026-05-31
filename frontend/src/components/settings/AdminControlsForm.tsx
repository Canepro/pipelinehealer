import { useId, useState, type Dispatch, type SetStateAction } from "react";
import {
  ChevronDown,
  Copy,
  HelpCircle,
  RotateCcw,
  Save,
  Settings2,
  Shield,
  Sparkles,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import type {
  AppSettingMetadata,
  AppSettings,
  LLMProviderHealth,
  MCPProviderHealth,
} from "../../api/client";
import type { SettingsFormState } from "./types";
import {
  normalizeHostnameInput,
  normalizeRepoInput,
  SETTING_DESCRIPTIONS,
  toSettingsForm,
} from "./types";
import {
  describeLlmCapability,
  describeLlmHealthFailure,
  describeMcpHealthFailure,
  formatLlmValidationLabel,
  formatSettingSource,
  getDurabilityLabel,
  getMcpEffectiveState,
  settingSourceTone,
  type IntegrationTone,
  type McpPolicyMode,
} from "./runtimeSemantics";
import { copyToClipboard } from "@/utils/copyToClipboard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface Props {
  data: AppSettings;
  form: SettingsFormState;
  setForm: Dispatch<SetStateAction<SettingsFormState>>;
  llmProviderHealth?: LLMProviderHealth;
  isLlmHealthLoading?: boolean;
  isLlmHealthError?: boolean;
  llmHealthError?: Error | null;
  mcpProviderHealth?: MCPProviderHealth;
  isMcpHealthLoading?: boolean;
  isMcpHealthError?: boolean;
  mcpHealthError?: Error | null;
  llmCapabilitySummary?: {
    summary: string;
    detail: string;
    tone: IntegrationTone;
  };
  hasUnsavedChanges: boolean;
  newRepoInput: string;
  setNewRepoInput: Dispatch<SetStateAction<string>>;
  newMcpRepoInput: string;
  setNewMcpRepoInput: Dispatch<SetStateAction<string>>;
  newHandoffHostInput: string;
  setNewHandoffHostInput: Dispatch<SetStateAction<string>>;
  setGhAwWorkflowsInput: Dispatch<SetStateAction<string>>;
  setLastSavedForm: Dispatch<SetStateAction<SettingsFormState | null>>;
  savePending: boolean;
  saveError: Error | null;
  saveSuccess: boolean;
  onSave: () => void;
}

type SettingsSection = "runtime" | "intelligence" | "security";

const SETTINGS_SECTION_OPTIONS: Array<{
  value: SettingsSection;
  label: string;
  summary: string;
  Icon: typeof Zap;
}> = [
  {
    value: "runtime",
    label: "1. Runtime Controls",
    summary:
      "Runtime Controls: set remediation behavior, repo scope, and operation mode first.",
    Icon: Zap,
  },
  {
    value: "intelligence",
    label: "2. AI & Integrations",
    summary:
      "AI & Integrations: configure model providers, handoff, external diagnostics, and MCP policies.",
    Icon: Sparkles,
  },
  {
    value: "security",
    label: "3. Security & Advanced",
    summary:
      "Security & Advanced: adjust auth posture, retries, limits, and low-level safeguards.",
    Icon: Shield,
  },
];

export function SettingsSectionSwitcher({
  activeSection,
  onChange,
}: {
  activeSection: SettingsSection;
  onChange: (section: SettingsSection) => void;
}) {
  const activeOption =
    SETTINGS_SECTION_OPTIONS.find((option) => option.value === activeSection) ??
    SETTINGS_SECTION_OPTIONS[0];

  return (
    <>
      <nav aria-label="Settings sections">
        <ul className="grid h-auto list-none grid-cols-1 gap-4 p-0 sm:grid-cols-3">
          {SETTINGS_SECTION_OPTIONS.map(({ value, label, Icon }) => {
            const isActive = value === activeSection;
            return (
              <li key={value}>
                <Button
                  type="button"
                  variant={isActive ? "secondary" : "ghost"}
                  className="w-full justify-center gap-2 py-3 text-sm font-semibold"
                  aria-pressed={isActive}
                  id={`settings-section-trigger-${value}`}
                  onClick={() => onChange(value)}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </Button>
              </li>
            );
          })}
        </ul>
      </nav>
      <p className="mt-3 text-sm text-[var(--ph-muted)]">
        {activeOption.summary}
      </p>
    </>
  );
}
type NotificationTargetType =
  | "email"
  | "webhook"
  | "slack_webhook"
  | "teams_webhook"
  | "rocketchat_webhook";
type McpToolDefinition = {
  key:
    | "fetch_failure_context"
    | "fetch_runbook_context"
    | "publish_artifact"
    | "rerun_pipeline";
  label: string;
  description: string;
  write: boolean;
};

const MCP_TOOL_DEFINITIONS: McpToolDefinition[] = [
  {
    key: "fetch_failure_context",
    label: "fetch_failure_context",
    description: "Read failure/job context from provider APIs.",
    write: false,
  },
  {
    key: "fetch_runbook_context",
    label: "fetch_runbook_context",
    description:
      "Read runbook and troubleshooting markdown context from repositories.",
    write: false,
  },
  {
    key: "publish_artifact",
    label: "publish_artifact",
    description: "Publish issue/PR-like artifacts through provider tools.",
    write: true,
  },
  {
    key: "rerun_pipeline",
    label: "rerun_pipeline",
    description: "Trigger pipeline/job reruns through provider tools.",
    write: true,
  },
];

const NOTIFICATION_TARGET_TYPES: Array<{
  value: NotificationTargetType;
  label: string;
  note: string;
}> = [
  {
    value: "email",
    label: "email",
    note: "Send a plain-text summary through SMTP using deployment-managed mail settings.",
  },
  {
    value: "webhook",
    label: "webhook",
    note: "Forward the original PipelineHealer payload unchanged.",
  },
  {
    value: "slack_webhook",
    label: "slack_webhook",
    note: "Send a Slack-compatible summary with text and Block Kit.",
  },
  {
    value: "teams_webhook",
    label: "teams_webhook",
    note: "Send a Teams Incoming Webhook message with an Adaptive Card.",
  },
  {
    value: "rocketchat_webhook",
    label: "rocketchat_webhook",
    note: "Send a compact Rocket.Chat summary payload.",
  },
];

const EXTERNAL_AGENT_TARGETS: Array<{
  value: SettingsFormState["agent_handoff_default_target"];
  label: string;
}> = [
  { value: "codex_app_server", label: "Codex App Server" },
  { value: "openclaw", label: "OpenClaw" },
  { value: "hermes", label: "Hermes" },
  { value: "custom", label: "Custom webhook" },
];

function formatMcpPolicyLabel(policy: McpPolicyMode): string {
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

function parseWebhookUrlInput(
  value: string,
): { url: string; host: string } | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    const rawHost = parsed.hostname.trim().toLowerCase();
    if (!rawHost) return null;
    const normalizedHost = normalizeHostnameInput(rawHost);
    if (!normalizedHost) return null;
    return { url: trimmed, host: normalizedHost };
  } catch {
    return null;
  }
}

function parseJenkinsBridgeUrlInput(
  value: string,
): { url: string; path: string } | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    if (parsed.username || parsed.password || parsed.search || parsed.hash)
      return null;
    const path = parsed.pathname.trim();
    if (path !== "/webhook/jenkins") return null;
    return { url: trimmed, path };
  } catch {
    return null;
  }
}

function shellSingleQuote(value: string): string {
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function parseNotificationEventsInput(value: string): string[] {
  const normalized = value
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  return normalized.length > 0 ? normalized : ["agent_handoff_requested"];
}

function buildNotificationTargetDraft(args: {
  targetType: NotificationTargetType;
  name: string;
  events: string[];
  url: string;
  emailRecipients: string;
  emailSubjectPrefix: string;
}) {
  const payload: Record<string, unknown> = {
    type: args.targetType,
    enabled: true,
  };
  if (args.events.length > 0) {
    payload.events = args.events;
  }
  if (args.name.trim()) {
    payload.name = args.name.trim();
  }
  if (args.targetType === "email") {
    const recipients = args.emailRecipients
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (recipients.length === 0) return null;
    payload.to = recipients;
    if (args.emailSubjectPrefix.trim()) {
      payload.subject_prefix = args.emailSubjectPrefix.trim();
    }
    return payload;
  }

  const parsed = parseWebhookUrlInput(args.url);
  if (!parsed) return null;
  payload.url = parsed.url;
  return payload;
}

function buildHandoffSamplePayload() {
  return JSON.stringify(
    {
      delivery_id: "handoff:test-delivery",
      request_id: "ph-settings-smoke-test",
      activity: {
        id: "activity-demo-123",
        repository: "canepro/pipelinehealer-demo",
        workflow_name: "CI",
        workflow_run_id: 1234567890,
        status: "failed",
        failure_type: null,
      },
      context_format: "markdown",
      context:
        "## PipelineHealer handoff smoke test\n\nThis is a generated sample payload for validating the receiver contract.",
      sent_at: "2026-03-05T22:30:00Z",
    },
    null,
    2,
  );
}

function buildJenkinsBridgeSamplePayload() {
  return JSON.stringify(
    {
      schema_version: "1.0",
      provider: "jenkins",
      delivery_id: "jenkins:security-validation#__TIMESTAMP__",
      sent_at: "__SENT_AT__",
      repository: "canepro/pipelinehealer-demo",
      branch: "main",
      commit_sha: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      job: {
        name: "security-validation",
        url: "https://jenkins.example/job/security-validation/23/",
        build_number: 23,
        result: "FAILURE",
        duration_ms: 1000,
      },
      failure: {
        stage: "Trivy Scan",
        step: "run-trivy",
        command: "trivy image ...",
        summary: "Critical vulnerabilities found",
        log_excerpt: "critical vulnerability threshold exceeded",
      },
      artifacts: [],
      metadata: {
        jenkins_instance: "jenkins.example",
      },
    },
    null,
    2,
  );
}

function buildJenkinsBridgeSmokeScript(
  target: { url: string; path: string },
  payload: string,
) {
  const quotedUrl = shellSingleQuote(target.url);
  return [
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    `TARGET_URL=${quotedUrl}`,
    'if [ -z "${SHARED_SECRET:-}" ]; then',
    '  read -r -s -p "Enter shared secret: " SHARED_SECRET',
    "  echo",
    "fi",
    "TIMESTAMP=$(date +%s)",
    'NONCE="jenkins-smoke-${TIMESTAMP}"',
    'SENT_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")',
    "BODY_FILE=$(mktemp)",
    "trap 'rm -f \"$BODY_FILE\"' EXIT",
    `cat > "$BODY_FILE" <<'JSON'`,
    payload,
    "JSON",
    'sed -i "s/__TIMESTAMP__/${TIMESTAMP}/g; s/__SENT_AT__/${SENT_AT}/g" "$BODY_FILE"',
    `BODY_SHA=$(openssl dgst -sha256 "$BODY_FILE" | awk '{print $NF}')`,
    `CANONICAL=$(printf 'POST\\n${target.path}\\n%s\\n%s\\n%s' "$TIMESTAMP" "$NONCE" "$BODY_SHA")`,
    `SIGNATURE="sha256=$(printf '%s' "$CANONICAL" | openssl dgst -sha256 -hmac "$SHARED_SECRET" | awk '{print $NF}')"`,
    'curl -fsS -X POST "$TARGET_URL" \\',
    '  -H "Content-Type: application/json" \\',
    '  -H "X-PH-Bridge-Provider: jenkins" \\',
    '  -H "X-PH-Bridge-Timestamp: $TIMESTAMP" \\',
    '  -H "X-PH-Bridge-Nonce: $NONCE" \\',
    '  -H "X-PH-Bridge-Signature: $SIGNATURE" \\',
    '  --data-binary @"$BODY_FILE"',
  ].join("\n");
}

export default function AdminControlsForm({
  data,
  form,
  setForm,
  llmProviderHealth,
  isLlmHealthLoading,
  isLlmHealthError,
  llmHealthError,
  mcpProviderHealth,
  isMcpHealthLoading,
  isMcpHealthError,
  mcpHealthError,
  llmCapabilitySummary,
  hasUnsavedChanges,
  newRepoInput,
  setNewRepoInput,
  newMcpRepoInput,
  setNewMcpRepoInput,
  newHandoffHostInput,
  setNewHandoffHostInput,
  setGhAwWorkflowsInput,
  setLastSavedForm,
  savePending,
  saveError,
  saveSuccess,
  onSave,
}: Props) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [workflowInput, setWorkflowInput] = useState("");
  const [handoffWebhookInput, setHandoffWebhookInput] = useState("");
  const [jenkinsBridgeUrlInput, setJenkinsBridgeUrlInput] = useState("");
  const [notificationTargetType, setNotificationTargetType] =
    useState<NotificationTargetType>("webhook");
  const [notificationTargetUrl, setNotificationTargetUrl] = useState("");
  const [notificationTargetName, setNotificationTargetName] = useState("");
  const [notificationTargetEventsInput, setNotificationTargetEventsInput] =
    useState("agent_handoff_requested");
  const [notificationTargetEmailRecipients, setNotificationTargetEmailRecipients] =
    useState("");
  const [notificationTargetEmailSubjectPrefix, setNotificationTargetEmailSubjectPrefix] =
    useState("[PipelineHealer]");
  const [activeSection, setActiveSection] =
    useState<SettingsSection>("runtime");
  const mcpEffectivePolicies = MCP_TOOL_DEFINITIONS.map((tool) => {
    const raw = form.mcp_tool_policies[tool.key];
    const policy: McpPolicyMode =
      raw === "disabled" || raw === "auto" || raw === "write_with_approval"
        ? raw
        : "read_only";
    return {
      tool,
      policy,
      effective: getMcpEffectiveState({
        mcpEnabled: form.mcp_enabled,
        mcpProvider: form.mcp_provider,
        readOnly: form.mcp_read_only,
        write: tool.write,
        policy,
      }),
    };
  });
  const mcpAllowedCount = mcpEffectivePolicies.filter(
    (row) => row.effective.status === "allowed",
  ).length;
  const mcpApprovalCount = mcpEffectivePolicies.filter(
    (row) => row.effective.status === "approval",
  ).length;
  const mcpBlockedCount = mcpEffectivePolicies.filter(
    (row) => row.effective.status === "blocked",
  ).length;
  const providerDefaultModel =
    form.llm_provider === "azure_openai"
      ? form.azure_openai_deployment_name.trim()
      : form.llm_provider === "codex_app_server"
        ? form.codex_app_server_model.trim()
        : form.openai_compatible_model.trim();
  const codexRuntimeSelected = form.llm_provider === "codex_app_server";
  const resolvedLlmCapability =
    llmCapabilitySummary ?? describeLlmCapability(llmProviderHealth);
  const llmValidationLabel = formatLlmValidationLabel(llmProviderHealth);
  const llmHealthFailure = isLlmHealthError
    ? describeLlmHealthFailure(llmHealthError)
    : null;
  const mcpHealthFailure = isMcpHealthError
    ? describeMcpHealthFailure(mcpHealthError)
    : null;
  const taskModelPreview = [
    {
      key: "analysis",
      label: "Analysis",
      override: codexRuntimeSelected ? "" : form.llm_model_analysis.trim(),
    },
    {
      key: "diagnosis",
      label: "Diagnosis",
      override: codexRuntimeSelected ? "" : form.llm_model_diagnosis.trim(),
    },
    {
      key: "remediation",
      label: "Remediation",
      override: codexRuntimeSelected ? "" : form.llm_model_remediation.trim(),
    },
  ];

  const addAllowedRepo = () => {
    const normalized = normalizeRepoInput(newRepoInput);
    if (!normalized) {
      toast.error("Invalid repository format", {
        description: "Use 'owner/repo' or 'https://github.com/owner/repo'.",
      });
      return;
    }
    if (form.ph_allowed_repos.includes(normalized)) {
      toast.error("Repository already in allowlist");
      return;
    }
    setForm((prev) => ({
      ...prev,
      ph_allowed_repos: [...prev.ph_allowed_repos, normalized],
    }));
    setNewRepoInput("");
  };

  const addMcpAllowedRepo = () => {
    const normalized = normalizeRepoInput(newMcpRepoInput);
    if (!normalized) {
      toast.error("Invalid repository format", {
        description: "Use 'owner/repo' or 'https://github.com/owner/repo'.",
      });
      return;
    }
    if (form.mcp_repo_allowlist.includes(normalized)) {
      toast.error("Repository already in MCP allowlist");
      return;
    }
    setForm((prev) => ({
      ...prev,
      mcp_repo_allowlist: [...prev.mcp_repo_allowlist, normalized],
    }));
    setNewMcpRepoInput("");
  };

  const addHandoffAllowlistHost = () => {
    const normalized = normalizeHostnameInput(newHandoffHostInput);
    if (!normalized) {
      toast.error("Invalid hostname format", {
        description: "Use a bare hostname like 'agent.example.com'.",
      });
      return;
    }
    if (form.agent_handoff_webhook_allowlist.includes(normalized)) {
      toast.error("Hostname already in allowlist");
      return;
    }
    setForm((prev) => ({
      ...prev,
      agent_handoff_webhook_allowlist: [
        ...prev.agent_handoff_webhook_allowlist,
        normalized,
      ],
    }));
    setNewHandoffHostInput("");
  };

  const addWorkflow = () => {
    const name = workflowInput.trim().toLowerCase();
    if (!name) return;
    if (form.gh_aw_known_workflows.includes(name)) {
      toast.error("Workflow already in list");
      return;
    }
    const next = [...form.gh_aw_known_workflows, name];
    setForm((prev) => ({ ...prev, gh_aw_known_workflows: next }));
    setGhAwWorkflowsInput(next.join(","));
    setWorkflowInput("");
  };

  const removeWorkflow = (name: string) => {
    const next = form.gh_aw_known_workflows.filter((w) => w !== name);
    setForm((prev) => ({ ...prev, gh_aw_known_workflows: next }));
    setGhAwWorkflowsInput(next.join(","));
  };

  const handoffNeedsStartupUrl =
    form.agent_handoff_enabled && form.agent_handoff_mode === "webhook";
  const handoffMetadata = data.settings_metadata ?? {};
  const handoffWebhookDraft = parseWebhookUrlInput(handoffWebhookInput);
  const handoffSuggestedAllowlist = handoffWebhookDraft
    ? Array.from(
        new Set([
          handoffWebhookDraft.host,
          ...form.agent_handoff_webhook_allowlist,
        ]),
      )
    : form.agent_handoff_webhook_allowlist;
  const handoffSetupEnvBlock = handoffWebhookDraft
    ? [
        `AGENT_HANDOFF_ENABLED=true`,
        `AGENT_HANDOFF_MODE=webhook`,
        `AGENT_HANDOFF_WEBHOOK_URL=${handoffWebhookDraft.url}`,
        `AGENT_HANDOFF_WEBHOOK_ALLOWLIST=${handoffSuggestedAllowlist.join(",")}`,
        `AGENT_HANDOFF_TIMEOUT_SECONDS=${form.agent_handoff_timeout_seconds}`,
        `AGENT_HANDOFF_MAX_RETRIES=${form.agent_handoff_max_retries}`,
      ].join("\n")
    : "";
  const handoffSamplePayload = handoffWebhookDraft
    ? buildHandoffSamplePayload()
    : "";
  const handoffSmokeCurl = handoffWebhookDraft
    ? [
        "curl -X POST \\",
        `  -H "Content-Type: application/json" \\`,
        `  -d @- "${handoffWebhookDraft.url}" <<'EOF'`,
        handoffSamplePayload,
        "EOF",
      ].join("\n")
    : "";
  const jenkinsBridgeTarget = parseJenkinsBridgeUrlInput(jenkinsBridgeUrlInput);
  const jenkinsBridgeSamplePayload = buildJenkinsBridgeSamplePayload();
  const jenkinsBridgeSmokeScript = jenkinsBridgeTarget
    ? buildJenkinsBridgeSmokeScript(
        jenkinsBridgeTarget,
        jenkinsBridgeSamplePayload,
      )
    : "";
  const notificationTargetEvents = parseNotificationEventsInput(
    notificationTargetEventsInput,
  );
  const notificationTargetDraft = buildNotificationTargetDraft({
    targetType: notificationTargetType,
    name: notificationTargetName,
    events: notificationTargetEvents,
    url: notificationTargetUrl,
    emailRecipients: notificationTargetEmailRecipients,
    emailSubjectPrefix: notificationTargetEmailSubjectPrefix,
  });
  const notificationTargetEnvBlock = notificationTargetDraft
    ? [
        `NOTIFY_TARGETS_JSON=${JSON.stringify([notificationTargetDraft])}`,
        `NOTIFY_DELIVERY_TIMEOUT_SECONDS=10`,
        ...(notificationTargetType === "email"
          ? [
              `NOTIFY_EMAIL_SMTP_HOST=smtp.example.com`,
              `NOTIFY_EMAIL_SMTP_PORT=587`,
              `NOTIFY_EMAIL_SMTP_STARTTLS=true`,
              `NOTIFY_EMAIL_SMTP_SSL=false`,
              `NOTIFY_EMAIL_FROM_ADDRESS=pipelinehealer@example.com`,
              `NOTIFY_EMAIL_SMTP_USERNAME=`,
              `NOTIFY_EMAIL_SMTP_PASSWORD=`,
            ]
          : []),
      ].join("\n")
    : "";

  const copyText = async (
    text: string,
    successMessage: string,
    emptyMessage: string,
  ) => {
    if (!text) {
      toast.error(emptyMessage);
      return;
    }
    try {
      await copyToClipboard(text);
      toast.success(successMessage);
    } catch {
      toast.error("Unable to copy generated output");
    }
  };

  const copyHandoffSetupEnvBlock = async () => {
    await copyText(
      handoffSetupEnvBlock,
      "Handoff env block copied",
      "Enter a valid webhook URL first",
    );
  };

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-8">
        <Card>
          <CardContent className="py-5">
            <SettingsSectionSwitcher
              activeSection={activeSection}
              onChange={setActiveSection}
            />
          </CardContent>
        </Card>

        {/* ── Section 1: Healing Behavior ── */}
        {activeSection === "runtime" && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-[var(--ph-accent)]" />
                <CardTitle>Healing Behavior</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                Controls how PipelineHealer responds to pipeline failures.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup
                  label="Heal Mode"
                  field="heal_mode"
                  metadata={data.settings_metadata?.heal_mode}
                >
                  <Select
                    value={form.heal_mode}
                    onValueChange={(v) =>
                      setForm((prev) => ({
                        ...prev,
                        heal_mode: v as SettingsFormState["heal_mode"],
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="safe">
                        Safe — Conservative fixes
                      </SelectItem>
                      <SelectItem value="demo">
                        Demo — Aggressive for demonstrations
                      </SelectItem>
                      <SelectItem value="freestyle">
                        Freestyle — Aggressive open-ended automation
                      </SelectItem>
                      <SelectItem value="debug">
                        Debug — Safe + verbose logging
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>

                <FieldGroup
                  label="Max Remediation Attempts"
                  field="max_remediation_attempts"
                  metadata={data.settings_metadata?.max_remediation_attempts}
                >
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    value={form.max_remediation_attempts}
                    onChange={(e) =>
                      setForm((p) => ({
                        ...p,
                        max_remediation_attempts: Number(e.target.value),
                      }))
                    }
                  />
                </FieldGroup>
              </div>

              <Separator />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <SwitchField
                  label="Auto-Apply Remediation"
                  field="auto_apply_remediation"
                  checked={form.auto_apply_remediation}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, auto_apply_remediation: v }))
                  }
                  metadata={data.settings_metadata?.auto_apply_remediation}
                />
                <SwitchField
                  label="Auto-Create Pull Requests"
                  field="auto_create_pr"
                  checked={form.auto_create_pr}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, auto_create_pr: v }))
                  }
                  metadata={data.settings_metadata?.auto_create_pr}
                />
                <SwitchField
                  label="Jenkins Bridge: Allow PRs"
                  field="jenkins_bridge_allow_pr"
                  checked={form.jenkins_bridge_allow_pr}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, jenkins_bridge_allow_pr: v }))
                  }
                  metadata={data.settings_metadata?.jenkins_bridge_allow_pr}
                />
                <SwitchField
                  label="Auto-Create Issues"
                  field="auto_create_issue"
                  checked={form.auto_create_issue}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, auto_create_issue: v }))
                  }
                  metadata={data.settings_metadata?.auto_create_issue}
                />
                <SwitchField
                  label="Auto-Retry Workflows"
                  field="auto_retry_workflow"
                  checked={form.auto_retry_workflow}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, auto_retry_workflow: v }))
                  }
                  metadata={data.settings_metadata?.auto_retry_workflow}
                />
                <SwitchField
                  label="Auto-Create Tracking Issues"
                  field="auto_create_tracking_issue_for_prs"
                  checked={form.auto_create_tracking_issue_for_prs}
                  onChange={(v) =>
                    setForm((p) => ({
                      ...p,
                      auto_create_tracking_issue_for_prs: v,
                    }))
                  }
                  metadata={
                    data.settings_metadata?.auto_create_tracking_issue_for_prs
                  }
                />
                <SwitchField
                  label="Auto-Merge Remediation PRs"
                  field="auto_merge_remediation_prs"
                  checked={form.auto_merge_remediation_prs}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, auto_merge_remediation_prs: v }))
                  }
                  metadata={data.settings_metadata?.auto_merge_remediation_prs}
                />
                <SwitchField
                  label="Require Clean Checks"
                  field="auto_merge_require_clean_checks"
                  checked={form.auto_merge_require_clean_checks}
                  onChange={(v) =>
                    setForm((p) => ({
                      ...p,
                      auto_merge_require_clean_checks: v,
                    }))
                  }
                  metadata={
                    data.settings_metadata?.auto_merge_require_clean_checks
                  }
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup
                  label="Auto-Merge Strategy"
                  field="auto_merge_strategy"
                  metadata={data.settings_metadata?.auto_merge_strategy}
                >
                  <Select
                    value={form.auto_merge_strategy}
                    onValueChange={(v) =>
                      setForm((p) => ({
                        ...p,
                        auto_merge_strategy:
                          v as SettingsFormState["auto_merge_strategy"],
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="merge_when_clean">
                        Merge when clean
                      </SelectItem>
                      <SelectItem value="github_auto_merge">
                        GitHub native auto-merge
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>

                <FieldGroup
                  label="Auto-Merge Wait Seconds"
                  field="auto_merge_poll_seconds"
                  metadata={data.settings_metadata?.auto_merge_poll_seconds}
                >
                  <Input
                    type="number"
                    min={0}
                    max={900}
                    step={5}
                    value={form.auto_merge_poll_seconds}
                    onChange={(e) =>
                      setForm((p) => ({
                        ...p,
                        auto_merge_poll_seconds: Number(e.target.value),
                      }))
                    }
                  />
                </FieldGroup>
              </div>
              <p className="text-xs text-[var(--ph-muted)]">
                Dependency hints: Jenkins bridge PR output requires both
                `Auto-Create Pull Requests` and `Jenkins Bridge: Allow PRs`.
                Remediation PR auto-merge only applies to PipelineHealer-created
                PRs and still requires GitHub to report the PR mergeable.
              </p>

              <div className="space-y-4 rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 p-4">
                <div>
                  <p className="text-sm font-medium text-[var(--ph-text)]">
                    Jenkins Bridge Setup Assistant
                  </p>
                  <p className="mt-1 text-sm text-[var(--ph-muted)]">
                    Generate a signed smoke test for `POST /webhook/jenkins`
                    without persisting the shared secret to Settings or the
                    backend. This validates the exact HMAC header contract the
                    bridge expects.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-5">
                  <div className="space-y-1">
                    <Label
                      htmlFor="jenkins-bridge-url"
                      className="text-[var(--ph-text)]"
                    >
                      Bridge Target URL
                    </Label>
                    <Input
                      id="jenkins-bridge-url"
                      type="text"
                      value={jenkinsBridgeUrlInput}
                      onChange={(e) => setJenkinsBridgeUrlInput(e.target.value)}
                      placeholder="https://pipelinehealer.example.com/webhook/jenkins"
                    />
                    <p className="text-xs text-[var(--ph-muted)]">
                      Use the full bridge ingress URL ending in
                      <code className="mx-1 font-mono">/webhook/jenkins</code>.
                      Query strings and fragments are
                      rejected so the generated signature path matches runtime
                      verification.
                    </p>
                  </div>
                </div>

                {jenkinsBridgeUrlInput.trim() && !jenkinsBridgeTarget && (
                  <p className="text-sm text-[var(--ph-danger)]">
                    Enter the full{" "}
                    <code className="font-mono">http(s)</code>{" "}
                    bridge URL ending in
                    <code className="mx-1 font-mono">/webhook/jenkins</code>
                    with no query string or fragment so the helper can
                    generate the correct signed path.
                  </p>
                )}

                {jenkinsBridgeTarget && (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Badge variant="success">
                        Signed path: {jenkinsBridgeTarget.path}
                      </Badge>
                      <Badge variant="outline">
                        Runtime state:{" "}
                        {form.jenkins_bridge_allow_pr
                          ? "PR-capable"
                          : "Issue-first"}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Label className="text-[var(--ph-muted)]">
                            Sample bridge payload
                          </Label>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              copyText(
                                jenkinsBridgeSamplePayload,
                                "Jenkins bridge sample payload copied",
                                "Unable to generate bridge payload",
                              )
                            }
                          >
                            <Copy className="h-4 w-4" />
                            Copy Payload
                          </Button>
                        </div>
                        <pre className="max-h-72 overflow-auto rounded-md border border-[var(--ph-border-subtle)] bg-slate-950/70 p-3 text-xs text-slate-100">
                          {jenkinsBridgeSamplePayload}
                        </pre>
                      </div>

                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Label className="text-[var(--ph-muted)]">
                            Signed smoke test
                          </Label>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              copyText(
                                jenkinsBridgeSmokeScript,
                                "Jenkins bridge smoke test copied",
                                "Enter a valid Jenkins bridge URL first",
                              )
                            }
                            disabled={!jenkinsBridgeSmokeScript}
                          >
                            <Copy className="h-4 w-4" />
                            Copy Script
                          </Button>
                        </div>
                        <pre className="max-h-72 overflow-auto rounded-md border border-[var(--ph-border-subtle)] bg-slate-950/70 p-3 text-xs text-slate-100">
                          {jenkinsBridgeSmokeScript ||
                            "# Enter a valid /webhook/jenkins URL to generate a signed smoke test."}
                        </pre>
                        <p className="text-xs text-[var(--ph-muted)]">
                          Recommended flow: run this from Jenkins or any shell
                          with `bash` and `openssl` installed. The script
                          prompts for `SHARED_SECRET` at runtime if it is not
                          already exported. A `200 processing` response confirms
                          the bridge is enabled, signed correctly, and accepting
                          the payload shape.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="space-y-4 rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 p-4">
                <div>
                  <p className="text-sm font-medium text-[var(--ph-text)]">
                    Notification Target Setup Assistant
                  </p>
                  <p className="mt-1 text-sm text-[var(--ph-muted)]">
                    Generate a valid receiver target entry for
                    <code className="mx-1 font-mono">NOTIFY_TARGETS_JSON</code>
                    while keeping downstream sink URLs deployment-managed.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div className="space-y-1">
                    <Label className="text-[var(--ph-text)]">Target Type</Label>
                    <Select
                      value={notificationTargetType}
                      onValueChange={(value) =>
                        setNotificationTargetType(value as NotificationTargetType)
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {NOTIFICATION_TARGET_TYPES.map((target) => (
                          <SelectItem key={target.value} value={target.value}>
                            {target.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {notificationTargetType === "email" ? (
                    <div className="space-y-1">
                      <Label className="text-[var(--ph-text)]">
                        Recipient Email(s)
                      </Label>
                      <Input
                        type="text"
                        value={notificationTargetEmailRecipients}
                        onChange={(e) =>
                          setNotificationTargetEmailRecipients(e.target.value)
                        }
                        placeholder="ops@example.com, engineering@example.com"
                      />
                      <p className="text-xs text-[var(--ph-muted)]">
                        Comma-separated recipients. SMTP relay settings stay
                        deployment-managed and are not stored in runtime
                        settings.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Label className="text-[var(--ph-text)]">
                        Target URL
                      </Label>
                      <Input
                        type="text"
                        value={notificationTargetUrl}
                        onChange={(e) => setNotificationTargetUrl(e.target.value)}
                        placeholder="https://example.com/webhook"
                      />
                      <p className="text-xs text-[var(--ph-muted)]">
                        Use the full destination URL. Store secret-bearing
                        values in deployment env or a secret adapter.
                      </p>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div className="space-y-1">
                    <Label className="text-[var(--ph-text)]">
                      Friendly Name (optional)
                    </Label>
                    <Input
                      type="text"
                      value={notificationTargetName}
                      onChange={(e) => setNotificationTargetName(e.target.value)}
                      placeholder="Ops notifications"
                    />
                  </div>
                  {notificationTargetType === "email" ? (
                    <div className="space-y-1">
                      <Label className="text-[var(--ph-text)]">
                        Subject Prefix (optional)
                      </Label>
                      <Input
                        type="text"
                        value={notificationTargetEmailSubjectPrefix}
                        onChange={(e) =>
                          setNotificationTargetEmailSubjectPrefix(
                            e.target.value,
                          )
                        }
                        placeholder="[PipelineHealer]"
                      />
                      <p className="text-xs text-[var(--ph-muted)]">
                        Prepended to the generated email subject before event,
                        repository, workflow, and status fields.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Label className="text-[var(--ph-text)]">Events</Label>
                      <Input
                        type="text"
                        value={notificationTargetEventsInput}
                        onChange={(e) =>
                          setNotificationTargetEventsInput(e.target.value)
                        }
                        placeholder="agent_handoff_requested"
                      />
                      <p className="text-xs text-[var(--ph-muted)]">
                        Comma-separated. Blank defaults to
                        <code className="mx-1 font-mono">
                          agent_handoff_requested
                        </code>
                        . Use
                        <code className="mx-1 font-mono">*</code>
                        only when you want the target to receive every future
                        receiver event.
                      </p>
                    </div>
                  )}
                </div>

                {notificationTargetType === "email" && (
                  <div className="space-y-1">
                    <Label className="text-[var(--ph-text)]">Events</Label>
                    <Input
                      type="text"
                      value={notificationTargetEventsInput}
                      onChange={(e) =>
                        setNotificationTargetEventsInput(e.target.value)
                      }
                      placeholder="agent_handoff_requested"
                    />
                    <p className="text-xs text-[var(--ph-muted)]">
                      Comma-separated. Blank defaults to
                      <code className="mx-1 font-mono">
                        agent_handoff_requested
                      </code>
                      . Keep email routing narrow unless you intentionally want
                      inbox copies for every future receiver event.
                    </p>
                  </div>
                )}

                <div className="flex flex-wrap gap-2 text-xs">
                  {NOTIFICATION_TARGET_TYPES.map((target) => (
                    <Badge
                      key={target.value}
                      variant={
                        target.value === notificationTargetType
                          ? "success"
                          : "outline"
                      }
                    >
                      {target.label}
                    </Badge>
                  ))}
                </div>
                <p className="text-xs text-[var(--ph-muted)]">
                  {
                    NOTIFICATION_TARGET_TYPES.find(
                      (target) => target.value === notificationTargetType,
                    )?.note
                  }
                </p>

                {((notificationTargetType !== "email" &&
                  notificationTargetUrl.trim()) ||
                  (notificationTargetType === "email" &&
                    notificationTargetEmailRecipients.trim())) &&
                  !notificationTargetDraft && (
                  <p className="text-sm text-[var(--ph-danger)]">
                    {notificationTargetType === "email"
                      ? "Enter at least one valid recipient email so the assistant can generate a valid notification target entry."
                      : 'Enter a full http(s) target URL so the assistant can generate a valid notification target entry.'}
                  </p>
                )}

                {notificationTargetDraft && (
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Label className="text-[var(--ph-muted)]">
                          Target entry preview
                        </Label>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            copyText(
                              JSON.stringify(notificationTargetDraft, null, 2),
                              "Notification target copied",
                              "Enter a valid target URL first",
                            )
                          }
                        >
                          <Copy className="h-4 w-4" />
                          Copy Target
                        </Button>
                      </div>
                      <pre className="max-h-72 overflow-auto rounded-md border border-[var(--ph-border-subtle)] bg-slate-950/70 p-3 text-xs text-slate-100">
                        {JSON.stringify(notificationTargetDraft, null, 2)}
                      </pre>
                    </div>

                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Label className="text-[var(--ph-muted)]">
                          Receiver env block
                        </Label>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            copyText(
                              notificationTargetEnvBlock,
                              "Notification env block copied",
                              "Enter a valid target URL first",
                            )
                          }
                        >
                          <Copy className="h-4 w-4" />
                          Copy Env Block
                        </Button>
                      </div>
                      <pre className="max-h-72 overflow-auto rounded-md border border-[var(--ph-border-subtle)] bg-slate-950/70 p-3 text-xs text-slate-100">
                        {notificationTargetEnvBlock}
                      </pre>
                      <p className="text-xs text-[var(--ph-muted)]">
                        This generates a single-target example. Merge it into
                        your existing
                        <code className="mx-1 font-mono">NOTIFY_TARGETS_JSON</code>
                        array if the receiver already has other destinations.
                        {notificationTargetType === "email" && (
                          <>
                            {" "}
                            SMTP relay host, auth, and from-address values stay
                            deployment-managed in the receiver app settings.
                          </>
                        )}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Section 2: AI Configuration ── */}
        {activeSection === "intelligence" && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-[var(--ph-accent)]" />
                <CardTitle>AI Configuration</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                Configure model provider and deployment for log analysis and
                diagnosis.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup label="LLM Provider" field="llm_provider">
                  <Select
                    value={form.llm_provider}
                    onValueChange={(v) =>
                      setForm((prev) => ({
                        ...prev,
                        llm_provider: v as SettingsFormState["llm_provider"],
                        ...(v === "codex_app_server"
                          ? {
                              llm_model_analysis: "",
                              llm_model_diagnosis: "",
                              llm_model_remediation: "",
                            }
                          : {}),
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select provider" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="azure_openai">
                        azure_openai
                      </SelectItem>
                      <SelectItem value="openai_compatible">
                        openai_compatible
                      </SelectItem>
                      <SelectItem value="codex_app_server">
                        codex_app_server (recommended)
                      </SelectItem>
                      <SelectItem value="custom">custom (scaffold)</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
                <FieldGroup
                  label={
                    form.llm_provider === "azure_openai"
                      ? "Model Deployment Name"
                      : form.llm_provider === "codex_app_server"
                        ? "Codex Model"
                      : "Model Name"
                  }
                  field={
                    form.llm_provider === "azure_openai"
                      ? "azure_openai_deployment_name"
                      : form.llm_provider === "codex_app_server"
                        ? "codex_app_server_model"
                      : "openai_compatible_model"
                  }
                >
                  <Input
                    type="text"
                    value={
                      form.llm_provider === "azure_openai"
                        ? form.azure_openai_deployment_name
                        : form.llm_provider === "codex_app_server"
                          ? form.codex_app_server_model
                        : form.openai_compatible_model
                    }
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        ...(form.llm_provider === "azure_openai"
                          ? { azure_openai_deployment_name: e.target.value }
                          : form.llm_provider === "codex_app_server"
                            ? { codex_app_server_model: e.target.value }
                          : { openai_compatible_model: e.target.value }),
                      }))
                    }
                    placeholder={
                      form.llm_provider === "azure_openai"
                        ? "Azure deployment name"
                        : form.llm_provider === "codex_app_server"
                          ? "gpt-5.4"
                        : "Provider model name"
                    }
                  />
                </FieldGroup>
                {form.llm_provider === "azure_openai" ? (
                  <div className="space-y-1.5">
                    <Label className="text-[var(--ph-muted)]">Endpoint</Label>
                    <p className="text-sm font-medium text-[var(--ph-text)] break-words py-2 font-mono leading-relaxed">
                      {data.azure_openai_endpoint || (
                        <span className="text-[var(--ph-muted)] italic">
                          Not configured
                        </span>
                      )}
                    </p>
                  </div>
                ) : form.llm_provider === "codex_app_server" ? (
                  <FieldGroup
                    label="Transport"
                    field="codex_app_server_transport"
                  >
                    <Select
                      value={form.codex_app_server_transport}
                      onValueChange={(v) =>
                        setForm((prev) => ({
                          ...prev,
                          codex_app_server_transport:
                            v as SettingsFormState["codex_app_server_transport"],
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="stdio">stdio</SelectItem>
                        <SelectItem value="websocket">websocket</SelectItem>
                      </SelectContent>
                    </Select>
                  </FieldGroup>
                ) : (
                  <FieldGroup
                    label="Provider Base URL"
                    field="openai_compatible_base_url"
                  >
                    <Input
                      type="text"
                      value={form.openai_compatible_base_url}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          openai_compatible_base_url: e.target.value,
                        }))
                      }
                      placeholder="https://api.openai.com/v1"
                    />
                  </FieldGroup>
                )}
              </div>

              {form.llm_provider === "codex_app_server" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <FieldGroup
                    label="Command"
                    field="codex_app_server_command"
                  >
                    <Input
                      type="text"
                      value={form.codex_app_server_command}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          codex_app_server_command: e.target.value,
                        }))
                      }
                      placeholder="codex app-server"
                    />
                  </FieldGroup>
                  <FieldGroup
                    label="Turn Timeout (ms)"
                    field="codex_app_server_turn_timeout_ms"
                  >
                    <Input
                      type="number"
                      min={5000}
                      max={600000}
                      step={1000}
                      value={form.codex_app_server_turn_timeout_ms}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          codex_app_server_turn_timeout_ms: Number(e.target.value),
                        }))
                      }
                    />
                  </FieldGroup>
                  {form.codex_app_server_transport === "websocket" && (
                    <>
                      <FieldGroup
                        label="WebSocket URL"
                        field="codex_app_server_ws_url"
                      >
                        <Input
                          type="text"
                          value={form.codex_app_server_ws_url}
                          onChange={(e) =>
                            setForm((prev) => ({
                              ...prev,
                              codex_app_server_ws_url: e.target.value,
                            }))
                          }
                          placeholder="ws://127.0.0.1:8765"
                        />
                      </FieldGroup>
                      <SwitchField
                        label="Allow Remote WebSocket"
                        field="codex_app_server_ws_allow_remote"
                        checked={form.codex_app_server_ws_allow_remote}
                        onChange={(v) =>
                          setForm((prev) => ({
                            ...prev,
                            codex_app_server_ws_allow_remote: v,
                          }))
                        }
                        metadata={
                          data.settings_metadata
                            ?.codex_app_server_ws_allow_remote
                        }
                      />
                    </>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <ReadOnlyField
                  label="API Version"
                  value={data.azure_openai_api_version}
                />
                <ReadOnlyField
                  label="Chat API Version"
                  value={data.azure_openai_chat_api_version}
                />
              </div>
              {form.llm_provider === "openai_compatible" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <ReadOnlyField
                    label="OpenAI-Compatible Key"
                    value={
                      data.openai_compatible_api_key_configured
                        ? "Configured"
                        : "Not configured"
                    }
                    metadata={
                      data.settings_metadata
                        ?.openai_compatible_api_key_configured
                    }
                  />
                  <ReadOnlyField
                    label="Provider Endpoint"
                    value={data.openai_compatible_base_url || "Not configured"}
                  />
                </div>
              )}
              {form.llm_provider === "codex_app_server" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <ReadOnlyField
                    label="Runtime"
                    value={`${data.codex_app_server_transport} via ${data.codex_app_server_command || "codex app-server"}`}
                    metadata={data.settings_metadata?.codex_app_server_transport}
                  />
                  <ReadOnlyField
                    label="Requested Model"
                    value={data.codex_app_server_model || "Not configured"}
                    metadata={data.settings_metadata?.codex_app_server_model}
                  />
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <ReadOnlyField
                  label="Provider Health"
                  value={
                    isLlmHealthLoading
                      ? "Checking..."
                      : isLlmHealthError
                        ? "Request failed"
                      : llmProviderHealth
                        ? `${llmProviderHealth.available ? "Available" : "Unavailable"} (${llmProviderHealth.reason})`
                        : "Unavailable"
                  }
                  description={llmHealthFailure?.detail}
                  guidance={llmHealthFailure?.guidance}
                />
                <ReadOnlyField
                  label="Provider Status"
                  value={
                    isLlmHealthError
                      ? "Unknown"
                      : llmProviderHealth
                      ? llmProviderHealth.implemented
                        ? "Implemented"
                        : "Scaffolded only"
                      : "Unknown"
                  }
                />
                <ReadOnlyField
                  label="Capability State"
                  value={
                    isLlmHealthLoading
                      ? "Checking..."
                      : isLlmHealthError
                        ? "Request failed"
                      : resolvedLlmCapability.summary
                  }
                  description={llmHealthFailure?.detail}
                  guidance={llmHealthFailure?.guidance}
                />
                <ReadOnlyField
                  label="Last validation"
                  value={
                    isLlmHealthLoading
                      ? "Checking..."
                      : isLlmHealthError
                        ? "Unavailable"
                        : llmValidationLabel
                  }
                  description={llmHealthFailure?.detail}
                  guidance={llmHealthFailure?.guidance}
                />
              </div>
              <p className="text-xs text-[var(--ph-muted)]">
                {isLlmHealthLoading
                  ? "Checking recent live LLM capability evidence..."
                  : isLlmHealthError
                    ? `${llmHealthFailure?.detail} ${llmHealthFailure?.guidance}`
                    : resolvedLlmCapability.detail}
              </p>
              <Separator />
              <div className="space-y-3">
                <p className="text-sm font-medium text-[var(--ph-text)]">
                  Task Model Routing (Optional Overrides)
                </p>
                <p className="text-xs text-[var(--ph-muted)]">
                  {codexRuntimeSelected
                    ? "Codex App Server uses the Codex Model above for all tasks."
                    : "Leave blank to use the provider default model/deployment."}
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  <FieldGroup label="Analysis Model" field="llm_model_analysis">
                    <Input
                      type="text"
                      value={codexRuntimeSelected ? "" : form.llm_model_analysis}
                      disabled={codexRuntimeSelected}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          llm_model_analysis: e.target.value,
                        }))
                      }
                      placeholder={
                        providerDefaultModel || "Uses provider default"
                      }
                    />
                  </FieldGroup>
                  <FieldGroup
                    label="Diagnosis Model"
                    field="llm_model_diagnosis"
                  >
                    <Input
                      type="text"
                      value={codexRuntimeSelected ? "" : form.llm_model_diagnosis}
                      disabled={codexRuntimeSelected}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          llm_model_diagnosis: e.target.value,
                        }))
                      }
                      placeholder={
                        providerDefaultModel || "Uses provider default"
                      }
                    />
                  </FieldGroup>
                  <FieldGroup
                    label="Remediation Model"
                    field="llm_model_remediation"
                  >
                    <Input
                      type="text"
                      value={codexRuntimeSelected ? "" : form.llm_model_remediation}
                      disabled={codexRuntimeSelected}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          llm_model_remediation: e.target.value,
                        }))
                      }
                      placeholder={
                        providerDefaultModel || "Uses provider default"
                      }
                    />
                  </FieldGroup>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  {taskModelPreview.map((task) => (
                    <ReadOnlyField
                      key={task.key}
                      label={`Effective ${task.label}`}
                      value={
                        task.override ||
                        providerDefaultModel ||
                        "Not configured"
                      }
                    />
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {activeSection === "intelligence" && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-[var(--ph-accent)]" />
                <CardTitle>Assign-to-Agent</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                Configure the operator handoff path. Non-secret runtime controls
                are editable here; the destination webhook URL lives in the
                separate write-only secrets panel.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <SwitchField
                  label="Enable Assign-to-Agent"
                  field="agent_handoff_enabled"
                  checked={form.agent_handoff_enabled}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, agent_handoff_enabled: v }))
                  }
                  metadata={handoffMetadata.agent_handoff_enabled}
                />
                <FieldGroup
                  label="Handoff Mode"
                  field="agent_handoff_mode"
                  metadata={handoffMetadata.agent_handoff_mode}
                >
                  <Select
                    value={form.agent_handoff_mode}
                    onValueChange={(v) =>
                      setForm((prev) => ({
                        ...prev,
                        agent_handoff_mode:
                          v as SettingsFormState["agent_handoff_mode"],
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="copy_only">copy_only</SelectItem>
                      <SelectItem value="webhook">webhook</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup
                  label="Timeout (seconds)"
                  field="agent_handoff_timeout_seconds"
                  metadata={handoffMetadata.agent_handoff_timeout_seconds}
                >
                  <Input
                    type="number"
                    min={0.5}
                    max={30}
                    step={0.5}
                    value={form.agent_handoff_timeout_seconds}
                    onChange={(e) =>
                      setForm((p) => ({
                        ...p,
                        agent_handoff_timeout_seconds: Number(e.target.value),
                      }))
                    }
                  />
                </FieldGroup>
                <FieldGroup
                  label="Max Retries"
                  field="agent_handoff_max_retries"
                  metadata={handoffMetadata.agent_handoff_max_retries}
                >
                  <Input
                    type="number"
                    min={0}
                    max={5}
                    value={form.agent_handoff_max_retries}
                    onChange={(e) =>
                      setForm((p) => ({
                        ...p,
                        agent_handoff_max_retries: Number(e.target.value),
                      }))
                    }
                  />
                </FieldGroup>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup
                  label="Default External Agent"
                  field="agent_handoff_default_target"
                  metadata={handoffMetadata.agent_handoff_default_target}
                >
                  <Select
                    value={form.agent_handoff_default_target}
                    onValueChange={(v) =>
                      setForm((prev) => ({
                        ...prev,
                        agent_handoff_default_target:
                          v as SettingsFormState["agent_handoff_default_target"],
                        agent_handoff_enabled_targets:
                          prev.agent_handoff_enabled_targets.includes(
                            v as SettingsFormState["agent_handoff_default_target"],
                          )
                            ? prev.agent_handoff_enabled_targets
                            : [
                                ...prev.agent_handoff_enabled_targets,
                                v as SettingsFormState["agent_handoff_default_target"],
                              ],
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EXTERNAL_AGENT_TARGETS.map((target) => (
                        <SelectItem key={target.value} value={target.value}>
                          {target.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FieldGroup>
                <div className="space-y-2">
                  <Label className="text-[var(--ph-muted)]">
                    Enabled Handoff Targets
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    {EXTERNAL_AGENT_TARGETS.map((target) => {
                      const checked =
                        form.agent_handoff_enabled_targets.includes(
                          target.value,
                        );
                      return (
                        <Button
                          key={target.value}
                          type="button"
                          size="sm"
                          variant={checked ? "secondary" : "ghost"}
                          onClick={() =>
                            setForm((prev) => {
                              const next = checked
                                ? prev.agent_handoff_enabled_targets.filter(
                                    (item) => item !== target.value,
                                  )
                                : [
                                    ...prev.agent_handoff_enabled_targets,
                                    target.value,
                                  ];
                              return {
                                ...prev,
                                agent_handoff_enabled_targets: next.includes(
                                  prev.agent_handoff_default_target,
                                )
                                  ? next
                                  : [prev.agent_handoff_default_target, ...next],
                              };
                            })
                          }
                        >
                          {target.label}
                        </Button>
                      );
                    })}
                  </div>
                  <p className="text-xs text-[var(--ph-muted)]">
                    These are policy gates. Each target still needs its own
                    URL or runtime bridge to dispatch externally.
                  </p>
                </div>
              </div>

              <Separator />

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                <StatusChip
                  label="Runtime"
                  value={data.agent_handoff_enabled ? "Enabled" : "Disabled"}
                  ok={data.agent_handoff_enabled}
                />
                <StatusChip
                  label="Webhook URL"
                  value={
                    data.agent_handoff_webhook_configured
                      ? data.agent_handoff_webhook_host || "Configured"
                      : "Not configured"
                  }
                  ok={data.agent_handoff_webhook_configured}
                  metadata={data.settings_metadata?.agent_handoff_webhook_host}
                />
                <StatusChip
                  label="Current Mode"
                  value={
                    data.agent_handoff_mode === "webhook"
                      ? data.agent_handoff_webhook_configured
                        ? "Webhook"
                        : "Webhook needs startup URL"
                      : "Copy only"
                  }
                  ok={
                    data.agent_handoff_mode !== "webhook" ||
                    data.agent_handoff_webhook_configured
                  }
                />
                <StatusChip
                  label="Default Target"
                  value={form.agent_handoff_default_target}
                  ok={form.agent_handoff_enabled_targets.includes(
                    form.agent_handoff_default_target,
                  )}
                  metadata={data.settings_metadata?.agent_handoff_default_target}
                />
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <StatusChip
                  label="Codex App Server"
                  value={
                    data.codex_app_server_handoff_configured
                      ? "Webhook configured"
                      : "Record-only until URL exists"
                  }
                  ok={form.agent_handoff_enabled_targets.includes(
                    "codex_app_server",
                  )}
                />
                <StatusChip
                  label="OpenClaw"
                  value={
                    data.openclaw_handoff_configured
                      ? "Webhook configured"
                      : "Record-only until URL exists"
                  }
                  ok={form.agent_handoff_enabled_targets.includes("openclaw")}
                />
                <StatusChip
                  label="Hermes"
                  value={
                    data.hermes_handoff_configured
                      ? "Webhook configured"
                      : "Record-only until URL exists"
                  }
                  ok={form.agent_handoff_enabled_targets.includes("hermes")}
                />
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-3 text-sm">
                  <span className="text-[var(--ph-muted)]">
                    Webhook host allowlist:
                  </span>
                  {form.agent_handoff_webhook_allowlist.length > 0 ? (
                    <span className="font-medium text-[var(--ph-text)]">
                      {form.agent_handoff_webhook_allowlist.length} host
                      {form.agent_handoff_webhook_allowlist.length !== 1
                        ? "s"
                        : ""}
                    </span>
                  ) : (
                    <Badge variant="outline">No host restrictions</Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 min-h-[2rem]">
                  {form.agent_handoff_webhook_allowlist.length === 0 && (
                    <span className="text-sm text-[var(--ph-muted)] italic py-1">
                      Empty allowlist permits any destination host. Prefer an
                      explicit list for production.
                    </span>
                  )}
                  {form.agent_handoff_webhook_allowlist.map((host) => (
                    <Badge
                      key={host}
                      variant="secondary"
                      className="gap-1 pr-1"
                    >
                      {host}
                      <button
                        type="button"
                        aria-label={`Remove ${host} from handoff allowlist`}
                        title={`Remove ${host} from handoff allowlist`}
                        className="ml-1 rounded-md p-0.5 hover:bg-[var(--ph-bg-elevated)] transition-colors"
                        onClick={() =>
                          setForm((prev) => ({
                            ...prev,
                            agent_handoff_webhook_allowlist:
                              prev.agent_handoff_webhook_allowlist.filter(
                                (item) => item !== host,
                              ),
                          }))
                        }
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Input
                    placeholder="agent.example.com"
                    value={newHandoffHostInput}
                    onChange={(e) => setNewHandoffHostInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addHandoffAllowlistHost();
                      }
                    }}
                    className="max-w-md"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={addHandoffAllowlistHost}
                  >
                    Add
                  </Button>
                </div>
              </div>

              <div className="rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 p-4">
                <p className="text-sm font-medium text-[var(--ph-text)]">
                  Startup-only dependency
                </p>
                <p className="mt-1 text-sm text-[var(--ph-muted)]">
                  The actual webhook receiver URL is not editable from Settings
                  yet. Configure it in deployment env, then use this page for
                  runtime enablement, mode, allowlist, and retry policy.
                </p>
                {handoffNeedsStartupUrl &&
                  !data.agent_handoff_webhook_configured && (
                    <p className="mt-2 text-sm text-[var(--ph-danger)]">
                      Webhook mode is selected, but no startup webhook URL is
                      configured.
                    </p>
                  )}
              </div>

              <div className="space-y-4 rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/22 p-4">
                <div>
                  <p className="text-sm font-medium text-[var(--ph-text)]">
                    Webhook Setup Assistant
                  </p>
                  <p className="mt-1 text-sm text-[var(--ph-muted)]">
                    Enter a candidate webhook URL to generate a portable env
                    block. This keeps startup secret configuration in your
                    deployment system while still making setup easier from the
                    UI.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto] gap-3 items-end">
                  <div className="space-y-1">
                    <Label
                      htmlFor="candidate-webhook-url"
                      className="text-[var(--ph-text)]"
                    >
                      Candidate Webhook URL
                    </Label>
                    <Input
                      id="candidate-webhook-url"
                      type="text"
                      value={handoffWebhookInput}
                      onChange={(e) => setHandoffWebhookInput(e.target.value)}
                      placeholder="https://agent.example.com/hook"
                    />
                    <p className="text-xs text-[var(--ph-muted)]">
                      Full{" "}
                      <code className="font-mono">http(s)</code>{" "}
                      receiver URL used only for setup guidance. The assistant
                      accepts URLs whose derived host can also be used in the
                      runtime allowlist.
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={copyHandoffSetupEnvBlock}
                    disabled={!handoffWebhookDraft}
                  >
                    <Copy className="h-4 w-4" />
                    Copy Env Block
                  </Button>
                </div>

                {handoffWebhookInput.trim() && !handoffWebhookDraft && (
                  <p className="text-sm text-[var(--ph-danger)]">
                    Enter a full{" "}
                    <code className="font-mono">http(s)</code>{" "}
                    webhook URL so the assistant can derive the destination
                    host and startup env block.
                  </p>
                )}

                {handoffWebhookDraft && (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Badge variant="success">
                        Derived host: {handoffWebhookDraft.host}
                      </Badge>
                      {form.agent_handoff_webhook_allowlist.includes(
                        handoffWebhookDraft.host,
                      ) ? (
                        <Badge variant="outline">
                          Host already in runtime allowlist
                        </Badge>
                      ) : (
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            setForm((prev) => ({
                              ...prev,
                              agent_handoff_webhook_allowlist: [
                                ...prev.agent_handoff_webhook_allowlist,
                                handoffWebhookDraft.host,
                              ],
                            }))
                          }
                        >
                          Add Host to Runtime Allowlist
                        </Button>
                      )}
                    </div>

                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Label className="text-[var(--ph-muted)]">
                          Portable startup env block
                        </Label>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline">
                            Local, Docker, Helm, ACA adapter
                          </Badge>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={copyHandoffSetupEnvBlock}
                          >
                            <Copy className="h-4 w-4" />
                            Copy Env Block
                          </Button>
                        </div>
                      </div>
                      <pre className="overflow-x-auto rounded-md border border-[var(--ph-border-subtle)] bg-slate-950/70 p-3 text-xs text-slate-100">
                        {handoffSetupEnvBlock}
                      </pre>
                      <p className="text-xs text-[var(--ph-muted)]">
                        Recommended flow: store this in your deployment env or
                        secret adapter, then redeploy/restart. For ACA
                        specifically, keep the URL secret-backed and use your
                        existing `deploy:env --secure-secrets` path.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Label className="text-[var(--ph-muted)]">
                            Sample receiver payload
                          </Label>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              copyText(
                                handoffSamplePayload,
                                "Handoff sample payload copied",
                                "Enter a valid webhook URL first",
                              )
                            }
                          >
                            <Copy className="h-4 w-4" />
                            Copy Payload
                          </Button>
                        </div>
                        <pre className="max-h-72 overflow-auto rounded-md border border-[var(--ph-border-subtle)] bg-slate-950/70 p-3 text-xs text-slate-100">
                          {handoffSamplePayload}
                        </pre>
                      </div>

                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Label className="text-[var(--ph-muted)]">
                            Receiver smoke test
                          </Label>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              copyText(
                                handoffSmokeCurl,
                                "Handoff smoke test command copied",
                                "Enter a valid webhook URL first",
                              )
                            }
                          >
                            <Copy className="h-4 w-4" />
                            Copy curl
                          </Button>
                        </div>
                        <pre className="max-h-72 overflow-auto rounded-md border border-[var(--ph-border-subtle)] bg-slate-950/70 p-3 text-xs text-slate-100">
                          {handoffSmokeCurl}
                        </pre>
                        <p className="text-xs text-[var(--ph-muted)]">
                          Use this to verify the receiver accepts the expected
                          JSON shape before you wire the real startup env into a
                          deployment.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Section 3: MCP Integration (preview) ── */}
        {activeSection === "intelligence" && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Wrench className="h-5 w-5 text-[var(--ph-accent)]" />
                <CardTitle>MCP Integration (Preview)</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                Foundation controls for provider-agnostic MCP tool integration.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <SwitchField
                  label="Enable MCP"
                  field="mcp_enabled"
                  checked={form.mcp_enabled}
                  onChange={(v) => setForm((p) => ({ ...p, mcp_enabled: v }))}
                  metadata={data.settings_metadata?.mcp_enabled}
                />
                <SwitchField
                  label="Read-Only Mode"
                  field="mcp_read_only"
                  checked={form.mcp_read_only}
                  onChange={(v) => setForm((p) => ({ ...p, mcp_read_only: v }))}
                  metadata={data.settings_metadata?.mcp_read_only}
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup
                  label="MCP Provider"
                  field="mcp_provider"
                  metadata={data.settings_metadata?.mcp_provider}
                >
                  <Select
                    value={form.mcp_provider}
                    onValueChange={(v) =>
                      setForm((prev) => ({
                        ...prev,
                        mcp_provider: v as SettingsFormState["mcp_provider"],
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="disabled">disabled</SelectItem>
                      <SelectItem value="github">
                        github (recommended first)
                      </SelectItem>
                      <SelectItem value="azure_monitor">
                        azure_monitor (scaffold)
                      </SelectItem>
                      <SelectItem value="custom">custom (scaffold)</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
                <FieldGroup
                  label="Timeout (seconds)"
                  field="mcp_timeout_seconds"
                  metadata={data.settings_metadata?.mcp_timeout_seconds}
                >
                  <Input
                    type="number"
                    min={1}
                    max={120}
                    step={0.5}
                    value={form.mcp_timeout_seconds}
                    onChange={(e) =>
                      setForm((p) => ({
                        ...p,
                        mcp_timeout_seconds: Number(e.target.value),
                      }))
                    }
                  />
                </FieldGroup>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <FieldGroup
                  label="Max Retries"
                  field="mcp_max_retries"
                  metadata={data.settings_metadata?.mcp_max_retries}
                >
                  <Input
                    type="number"
                    min={0}
                    max={10}
                    value={form.mcp_max_retries}
                    onChange={(e) =>
                      setForm((p) => ({
                        ...p,
                        mcp_max_retries: Number(e.target.value),
                      }))
                    }
                  />
                </FieldGroup>
                <ReadOnlyField
                  label="MCP Provider Health"
                  value={
                    isMcpHealthLoading
                      ? "Checking..."
                      : isMcpHealthError
                        ? "Probe failed"
                      : mcpProviderHealth
                        ? `${mcpProviderHealth.available ? "Available" : "Unavailable"} (${mcpProviderHealth.reason})`
                        : "Unavailable"
                  }
                  description={mcpHealthFailure?.detail}
                  guidance={mcpHealthFailure?.guidance}
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
                <StatusChip
                  label="Effective Allowed"
                  value={String(mcpAllowedCount)}
                  ok={mcpAllowedCount > 0}
                />
                <StatusChip
                  label="Need Approval"
                  value={String(mcpApprovalCount)}
                />
                <StatusChip
                  label="Effectively Blocked"
                  value={String(mcpBlockedCount)}
                  ok={mcpBlockedCount === 0}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
                <FieldGroup
                  label="Policy: fetch_failure_context"
                  field="mcp_tool_policies"
                >
                  <Select
                    value={form.mcp_tool_policies.fetch_failure_context}
                    onValueChange={(value) =>
                      setForm((prev) => ({
                        ...prev,
                        mcp_tool_policies: {
                          ...prev.mcp_tool_policies,
                          fetch_failure_context: value as
                            | "disabled"
                            | "read_only"
                            | "write_with_approval"
                            | "auto",
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="disabled">disabled</SelectItem>
                      <SelectItem value="read_only">read_only</SelectItem>
                      <SelectItem value="write_with_approval">
                        write_with_approval
                      </SelectItem>
                      <SelectItem value="auto">auto</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
                <FieldGroup
                  label="Policy: fetch_runbook_context"
                  field="mcp_tool_policies"
                >
                  <Select
                    value={form.mcp_tool_policies.fetch_runbook_context}
                    onValueChange={(value) =>
                      setForm((prev) => ({
                        ...prev,
                        mcp_tool_policies: {
                          ...prev.mcp_tool_policies,
                          fetch_runbook_context: value as
                            | "disabled"
                            | "read_only"
                            | "write_with_approval"
                            | "auto",
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="disabled">disabled</SelectItem>
                      <SelectItem value="read_only">read_only</SelectItem>
                      <SelectItem value="write_with_approval">
                        write_with_approval
                      </SelectItem>
                      <SelectItem value="auto">auto</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
                <FieldGroup
                  label="Policy: publish_artifact"
                  field="mcp_tool_policies"
                >
                  <Select
                    value={form.mcp_tool_policies.publish_artifact}
                    onValueChange={(value) =>
                      setForm((prev) => ({
                        ...prev,
                        mcp_tool_policies: {
                          ...prev.mcp_tool_policies,
                          publish_artifact: value as
                            | "disabled"
                            | "read_only"
                            | "write_with_approval"
                            | "auto",
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="disabled">disabled</SelectItem>
                      <SelectItem value="read_only">read_only</SelectItem>
                      <SelectItem value="write_with_approval">
                        write_with_approval
                      </SelectItem>
                      <SelectItem value="auto">auto</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
                <FieldGroup
                  label="Policy: rerun_pipeline"
                  field="mcp_tool_policies"
                >
                  <Select
                    value={form.mcp_tool_policies.rerun_pipeline}
                    onValueChange={(value) =>
                      setForm((prev) => ({
                        ...prev,
                        mcp_tool_policies: {
                          ...prev.mcp_tool_policies,
                          rerun_pipeline: value as
                            | "disabled"
                            | "read_only"
                            | "write_with_approval"
                            | "auto",
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="disabled">disabled</SelectItem>
                      <SelectItem value="read_only">read_only</SelectItem>
                      <SelectItem value="write_with_approval">
                        write_with_approval
                      </SelectItem>
                      <SelectItem value="auto">auto</SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
              </div>
              <div className="space-y-3">
                <Label className="text-[var(--ph-text)]">
                  Effective Tool Actions
                </Label>
                <p className="text-xs text-[var(--ph-muted)]">
                  Configured policy is shown separately from effective runtime
                  behavior. Global read-only or provider disablement can still
                  block a write-capable tool.
                </p>
                <div className="space-y-2">
                  {mcpEffectivePolicies.map(({ tool, policy, effective }) => (
                    <div
                      key={tool.key}
                      className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-surface)] px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="font-mono text-xs text-[var(--ph-text)]">
                            {tool.label}
                          </p>
                          <p className="text-xs text-[var(--ph-muted)]">
                            {tool.description}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">
                            Configured: {formatMcpPolicyLabel(policy)}
                          </Badge>
                          <Badge variant={effective.tone}>
                            {effective.summary}
                          </Badge>
                        </div>
                      </div>
                      <p className="mt-1 text-xs text-[var(--ph-muted)]">
                        {effective.detail}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-sm">
                  <span className="text-[var(--ph-muted)]">
                    MCP repo allowlist:
                  </span>
                  {form.mcp_repo_allowlist.length > 0 ? (
                    <span className="font-medium text-[var(--ph-text)]">
                      {form.mcp_repo_allowlist.length} repo
                      {form.mcp_repo_allowlist.length !== 1 ? "s" : ""}
                    </span>
                  ) : (
                    <Badge variant="outline">Fallback to PH allowlist</Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 min-h-[2rem]">
                  {form.mcp_repo_allowlist.length === 0 && (
                    <span className="text-sm text-[var(--ph-muted)] italic py-1">
                      Empty list means MCP uses PH_ALLOWED_REPOS fallback.
                    </span>
                  )}
                  {form.mcp_repo_allowlist.map((repo) => (
                    <Badge
                      key={repo}
                      variant="secondary"
                      className="gap-1 pr-1"
                    >
                      {repo}
                      <button
                        type="button"
                        className="ml-1 rounded-md p-0.5 hover:bg-[var(--ph-bg-elevated)] transition-colors"
                        onClick={() =>
                          setForm((prev) => ({
                            ...prev,
                            mcp_repo_allowlist: prev.mcp_repo_allowlist.filter(
                              (r) => r !== repo,
                            ),
                          }))
                        }
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Input
                    placeholder="owner/repo or https://github.com/owner/repo"
                    value={newMcpRepoInput}
                    onChange={(e) => setNewMcpRepoInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addMcpAllowedRepo();
                      }
                    }}
                    className="max-w-md"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={addMcpAllowedRepo}
                  >
                    Add
                  </Button>
                </div>
              </div>
              {mcpProviderHealth?.configured_tools?.length ? (
                <div className="space-y-1">
                  <Label className="text-[var(--ph-muted)]">
                    Configured Tools
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    {mcpProviderHealth.configured_tools.map((tool) => (
                      <Badge
                        key={tool}
                        variant="secondary"
                        className="font-mono text-xs"
                      >
                        {tool}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
        )}

        {/* ── Section 4: Repository Scope ── */}
        {activeSection === "runtime" && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-[var(--ph-accent)]" />
                <CardTitle>Repository Scope</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                {SETTING_DESCRIPTIONS.ph_allowed_repos}
              </p>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-3 text-sm">
                <span className="text-[var(--ph-muted)]">Effective now:</span>
                {data.ph_allowed_repos.length > 0 ? (
                  <span className="font-medium text-[var(--ph-text)]">
                    {data.ph_allowed_repos.length} repo
                    {data.ph_allowed_repos.length !== 1 ? "s" : ""}
                  </span>
                ) : (
                  <Badge variant="outline">
                    All repositories (unrestricted)
                  </Badge>
                )}
              </div>

              <div className="flex flex-wrap gap-2 min-h-[2rem]">
                {form.ph_allowed_repos.length === 0 && (
                  <span className="text-sm text-[var(--ph-muted)] italic py-1">
                    No restrictions — all repositories are processed
                  </span>
                )}
                {form.ph_allowed_repos.map((repo) => (
                  <Badge key={repo} variant="secondary" className="gap-1 pr-1">
                    {repo}
                    <button
                      type="button"
                      className="ml-1 rounded-md p-0.5 hover:bg-[var(--ph-bg-elevated)] transition-colors"
                      onClick={() =>
                        setForm((prev) => ({
                          ...prev,
                          ph_allowed_repos: prev.ph_allowed_repos.filter(
                            (r) => r !== repo,
                          ),
                        }))
                      }
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>

              <div className="flex gap-2">
                <Input
                  placeholder="owner/repo or https://github.com/owner/repo"
                  value={newRepoInput}
                  onChange={(e) => setNewRepoInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addAllowedRepo();
                    }
                  }}
                  className="max-w-md"
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={addAllowedRepo}
                >
                  Add
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Section 5: External Diagnostics (gh-aw) ── */}
        {activeSection === "intelligence" && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Wrench className="h-5 w-5 text-[var(--ph-accent)]" />
                <CardTitle>External Diagnostics</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                GitHub Agentic Workflows integration for enhanced CI failure
                analysis.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <SwitchField
                  label="Enable External Diagnostics"
                  field="gh_aw_tools_enabled"
                  checked={form.gh_aw_tools_enabled}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, gh_aw_tools_enabled: v }))
                  }
                />

                <FieldGroup label="Ingestion Mode" field="gh_aw_ingestion_mode">
                  <Select
                    value={form.gh_aw_ingestion_mode}
                    onValueChange={(v) =>
                      setForm((prev) => ({
                        ...prev,
                        gh_aw_ingestion_mode:
                          v as SettingsFormState["gh_aw_ingestion_mode"],
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="disabled">Disabled</SelectItem>
                      <SelectItem value="passive">
                        Passive — Read from GitHub Issues
                      </SelectItem>
                      <SelectItem value="hybrid">
                        Hybrid — GH-AW + GitHub MCP
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </FieldGroup>
              </div>

              <Separator />

              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Label className="text-[var(--ph-text)]">
                    CI-Doctor Skip List
                  </Label>
                  <InfoTip text={SETTING_DESCRIPTIONS.gh_aw_known_workflows} />
                </div>
                <p className="text-xs text-[var(--ph-muted)]">
                  Workflows listed here will not be polled by ci-doctor
                  (prevents circular self-diagnosis). ci-doctor itself should
                  always be in this list.
                </p>

                <div className="flex flex-wrap gap-2 min-h-[2rem]">
                  {form.gh_aw_known_workflows.length === 0 && (
                    <span className="text-sm text-[var(--ph-muted)] italic py-1">
                      No skip list — ci-doctor will poll for all workflows
                    </span>
                  )}
                  {form.gh_aw_known_workflows.map((wf) => (
                    <Badge
                      key={wf}
                      variant="secondary"
                      className="gap-1 pr-1 font-mono text-xs"
                    >
                      {wf}
                      <button
                        type="button"
                        className="ml-1 rounded-md p-0.5 hover:bg-[var(--ph-bg-elevated)] transition-colors"
                        onClick={() => removeWorkflow(wf)}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>

                <div className="flex gap-2">
                  <Input
                    placeholder="workflow-name"
                    value={workflowInput}
                    onChange={(e) => setWorkflowInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addWorkflow();
                      }
                    }}
                    className="max-w-xs font-mono text-sm"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={addWorkflow}
                  >
                    Add
                  </Button>
                </div>
              </div>

              {/* Read-only status summary */}
              <Separator />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <StatusChip
                  label="Auth Mode"
                  value={data.github_auth_mode}
                  metadata={data.settings_metadata?.github_auth_mode}
                />
                <StatusChip
                  label="PAT"
                  value={data.github_pat_configured ? "Configured" : "Not set"}
                  ok={data.github_pat_configured}
                  metadata={data.settings_metadata?.github_pat_configured}
                />
                <StatusChip
                  label="GitHub App"
                  value={data.github_app_configured ? "Configured" : "Not set"}
                  ok={data.github_app_configured}
                  metadata={data.settings_metadata?.github_app_configured}
                />
                <StatusChip
                  label="gh-aw"
                  value={data.gh_aw_tools_enabled ? "Active" : "Off"}
                  ok={data.gh_aw_tools_enabled}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Section 6: Security ── */}
        {activeSection === "security" && (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-[var(--ph-accent)]" />
                <CardTitle>Security</CardTitle>
              </div>
              <p className="text-sm text-[var(--ph-muted)]">
                Authentication and webhook verification status.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <StatusChip
                  label="API Auth"
                  value={data.api_auth_enabled ? "Enabled" : "Disabled"}
                  ok={data.api_auth_enabled}
                />
                <StatusChip
                  label="Admin Auth"
                  value={data.admin_api_auth_enabled ? "Enabled" : "Disabled"}
                  ok={data.admin_api_auth_enabled}
                />
                <StatusChip
                  label="Webhook Sig"
                  value={data.verify_webhook_signature ? "Required" : "Off"}
                  ok={data.verify_webhook_signature}
                />
                <StatusChip label="Environment" value={data.environment} />
              </div>

              <Separator />

              <SwitchField
                label="Verify Webhook Signature in Development"
                field="verify_webhook_signature_in_development"
                checked={form.verify_webhook_signature_in_development}
                onChange={(v) =>
                  setForm((p) => ({
                    ...p,
                    verify_webhook_signature_in_development: v,
                  }))
                }
                metadata={
                  data.settings_metadata
                    ?.verify_webhook_signature_in_development
                }
              />

              {/* CORS read-only */}
              <Separator />
              <div className="space-y-2">
                <Label className="text-[var(--ph-muted)]">
                  CORS Allowed Origins
                </Label>
                <div className="flex flex-wrap gap-2">
                  {data.cors_allowed_origins.map((origin) => (
                    <Badge
                      key={origin}
                      variant="outline"
                      className="font-mono text-xs"
                    >
                      {origin}
                    </Badge>
                  ))}
                </div>
                {data.cors_allow_origin_regex && (
                  <p className="text-xs text-[var(--ph-muted)]">
                    Regex:{" "}
                    <code className="font-mono">
                      {data.cors_allow_origin_regex}
                    </code>
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Section 7: Advanced (collapsed by default) ── */}
        {activeSection === "security" && (
          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <Card>
              <CollapsibleTrigger asChild>
                <CardHeader className="cursor-pointer select-none hover:bg-[var(--ph-bg-elevated)] transition-colors rounded-t-xl pb-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Settings2 className="h-5 w-5 text-[var(--ph-accent)]" />
                      <CardTitle>Advanced</CardTitle>
                    </div>
                    <ChevronDown
                      className={`h-5 w-5 text-[var(--ph-muted)] transition-transform duration-200 ${advancedOpen ? "rotate-180" : ""}`}
                    />
                  </div>
                  <p className="text-sm text-[var(--ph-muted)]">
                    Pipeline timeouts, retry policies, and log prompt tuning.
                    Usually safe to leave at defaults.
                  </p>
                </CardHeader>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <CardContent className="space-y-5 pt-0">
                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">
                    Pipeline Timeouts
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <FieldGroup
                      label="Step Timeout (seconds)"
                      field="pipeline_step_timeout_seconds"
                    >
                      <Input
                        type="number"
                        min={1}
                        max={600}
                        value={form.pipeline_step_timeout_seconds}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            pipeline_step_timeout_seconds: Number(
                              e.target.value,
                            ),
                          }))
                        }
                      />
                    </FieldGroup>
                  </div>

                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">
                    GitHub API Retry Policy
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <FieldGroup
                      label="Max Retries"
                      field="github_api_max_retries"
                    >
                      <Input
                        type="number"
                        min={0}
                        max={10}
                        value={form.github_api_max_retries}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            github_api_max_retries: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup
                      label="Retry Base (seconds)"
                      field="github_api_retry_base_seconds"
                    >
                      <Input
                        type="number"
                        min={0.1}
                        max={30}
                        step={0.1}
                        value={form.github_api_retry_base_seconds}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            github_api_retry_base_seconds: Number(
                              e.target.value,
                            ),
                          }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup
                      label="Retry Max (seconds)"
                      field="github_api_retry_max_seconds"
                    >
                      <Input
                        type="number"
                        min={0.1}
                        max={120}
                        step={0.1}
                        value={form.github_api_retry_max_seconds}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            github_api_retry_max_seconds: Number(
                              e.target.value,
                            ),
                          }))
                        }
                      />
                    </FieldGroup>
                  </div>

                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">
                    Log Prompt Tuning
                  </h4>
                  <p className="text-xs text-[var(--ph-muted)]">
                    Controls how much of the CI log is sent to the AI model.
                    Larger values give more context but cost more tokens.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <FieldGroup
                      label="Max Total Chars"
                      field="log_prompt_max_chars"
                    >
                      <Input
                        type="number"
                        min={1000}
                        max={200000}
                        value={form.log_prompt_max_chars}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            log_prompt_max_chars: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup
                      label="Head Chars (start of log)"
                      field="log_prompt_head_chars"
                    >
                      <Input
                        type="number"
                        min={100}
                        max={200000}
                        value={form.log_prompt_head_chars}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            log_prompt_head_chars: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                    <FieldGroup
                      label="Tail Chars (end of log)"
                      field="log_prompt_tail_chars"
                    >
                      <Input
                        type="number"
                        min={100}
                        max={200000}
                        value={form.log_prompt_tail_chars}
                        onChange={(e) =>
                          setForm((p) => ({
                            ...p,
                            log_prompt_tail_chars: Number(e.target.value),
                          }))
                        }
                      />
                    </FieldGroup>
                  </div>

                  {form.log_prompt_head_chars + form.log_prompt_tail_chars >
                    form.log_prompt_max_chars && (
                    <p className="text-sm text-[var(--ph-danger)]">
                      Head + tail chars (
                      {form.log_prompt_head_chars + form.log_prompt_tail_chars})
                      exceeds max ({form.log_prompt_max_chars}). The log will be
                      over-truncated.
                    </p>
                  )}

                  <Separator />

                  <h4 className="text-sm font-medium text-[var(--ph-text)]">
                    Runtime Info
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                    <StatusChip label="Environment" value={data.environment} />
                    <StatusChip label="Storage" value={data.storage_backend} />
                    <StatusChip
                      label="Storage Mode"
                      value={data.storage_mode}
                    />
                    <StatusChip label="Heal Mode" value={data.heal_mode} />
                    <StatusChip
                      label="Max Attempts"
                      value={String(data.max_remediation_attempts)}
                    />
                  </div>
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>
        )}

        {/* ── Save / Discard Bar ── */}
        <Card className="sticky bottom-4 z-20 shadow-[var(--ph-shadow-lg)]">
          <CardContent className="py-4 px-6">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <Badge variant={hasUnsavedChanges ? "destructive" : "success"}>
                  {hasUnsavedChanges ? "Unsaved changes" : "In sync"}
                </Badge>
                {saveError && (
                  <span className="text-sm text-[var(--ph-danger)]">
                    {saveError.message || "Failed to save"}
                  </span>
                )}
                {saveSuccess && !hasUnsavedChanges && (
                  <span className="text-sm text-[var(--ph-success)]">
                    Settings saved
                  </span>
                )}
              </div>

              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={savePending || !hasUnsavedChanges || !data}
                  onClick={() => {
                    const reset = toSettingsForm(data);
                    setForm(reset);
                    setLastSavedForm(reset);
                    setNewRepoInput("");
                    setNewHandoffHostInput("");
                    setHandoffWebhookInput("");
                    setNotificationTargetType("webhook");
                    setNotificationTargetUrl("");
                    setNotificationTargetName("");
                    setNotificationTargetEventsInput(
                      "agent_handoff_requested",
                    );
                    setGhAwWorkflowsInput(
                      reset.gh_aw_known_workflows.join(","),
                    );
                  }}
                >
                  <RotateCcw className="h-4 w-4" />
                  Discard
                </Button>
                <Button
                  disabled={
                    savePending ||
                    !hasUnsavedChanges ||
                    form.log_prompt_head_chars + form.log_prompt_tail_chars >
                      form.log_prompt_max_chars
                  }
                  onClick={onSave}
                >
                  <Save className="h-4 w-4" />
                  {savePending ? "Saving..." : "Save"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}

/* ── Presentational helpers ── */

function InfoTip({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <HelpCircle className="h-3.5 w-3.5 text-[var(--ph-muted)] cursor-help" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

function FieldGroup({
  label,
  field,
  metadata,
  children,
}: {
  label: string;
  field: string;
  metadata?: AppSettingMetadata;
  children: React.ReactNode;
}) {
  const desc = SETTING_DESCRIPTIONS[field];
  const durability = getDurabilityLabel(metadata);
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Label className="text-[var(--ph-text)]">{label}</Label>
        {desc && <InfoTip text={desc} />}
        {metadata && (
          <>
            <Badge variant={settingSourceTone(metadata.source)}>
              {formatSettingSource(metadata.source)}
            </Badge>
            {durability ? <Badge variant="outline">{durability}</Badge> : null}
          </>
        )}
      </div>
      {children}
    </div>
  );
}

export function SwitchField({
  label,
  field,
  checked,
  onChange,
  metadata,
}: {
  label: string;
  field: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  metadata?: AppSettingMetadata;
}) {
  const desc = SETTING_DESCRIPTIONS[field];
  const durability = getDurabilityLabel(metadata);
  const switchId = useId();
  const descriptionId = desc ? `${switchId}-description` : undefined;

  return (
    <div className="flex items-start gap-3 py-1">
      <Switch
        id={switchId}
        checked={checked}
        onCheckedChange={onChange}
        className="mt-0.5"
        aria-describedby={descriptionId}
      />
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Label htmlFor={switchId} className="text-[var(--ph-text)] cursor-pointer">
            {label}
          </Label>
          {metadata && (
            <>
              <Badge variant={settingSourceTone(metadata.source)}>
                {formatSettingSource(metadata.source)}
              </Badge>
              {durability ? (
                <Badge variant="outline">{durability}</Badge>
              ) : null}
            </>
          )}
        </div>
        {desc && (
          <p id={descriptionId} className="text-xs text-[var(--ph-muted)] mt-0.5">
            {desc}
          </p>
        )}
      </div>
    </div>
  );
}

function ReadOnlyField({
  label,
  value,
  description,
  guidance,
  metadata,
}: {
  label: string;
  value: string | number;
  description?: string;
  guidance?: string;
  metadata?: AppSettingMetadata;
}) {
  const durability = getDurabilityLabel(metadata);
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Label className="text-[var(--ph-muted)]">{label}</Label>
        {metadata && (
          <>
            <Badge variant={settingSourceTone(metadata.source)}>
              {formatSettingSource(metadata.source)}
            </Badge>
            {metadata.sensitive ? (
              <Badge variant="secondary">Sensitive</Badge>
            ) : null}
            {durability ? <Badge variant="outline">{durability}</Badge> : null}
          </>
        )}
      </div>
      <p className="text-sm font-medium text-[var(--ph-text)] py-2">
        {value || (
          <span className="text-[var(--ph-muted)] italic">Not set</span>
        )}
      </p>
      {description ? (
        <p className="text-xs text-[var(--ph-muted)]">{description}</p>
      ) : null}
      {guidance ? (
        <p className="text-xs text-[var(--ph-muted)]">{guidance}</p>
      ) : null}
      {metadata?.note ? (
        <p className="text-xs text-[var(--ph-muted)]">{metadata.note}</p>
      ) : null}
    </div>
  );
}

function StatusChip({
  label,
  value,
  ok,
  metadata,
}: {
  label: string;
  value: string;
  ok?: boolean;
  metadata?: AppSettingMetadata;
}) {
  const durability = getDurabilityLabel(metadata);
  return (
    <div className="space-y-1">
      <p className="text-xs text-[var(--ph-muted)]">{label}</p>
      <Badge
        variant={ok === undefined ? "outline" : ok ? "success" : "destructive"}
      >
        {value}
      </Badge>
      {metadata && (
        <div className="flex flex-wrap gap-1">
          <Badge variant={settingSourceTone(metadata.source)}>
            {formatSettingSource(metadata.source)}
          </Badge>
          {metadata.sensitive ? (
            <Badge variant="secondary">Sensitive</Badge>
          ) : null}
          {durability ? <Badge variant="outline">{durability}</Badge> : null}
        </div>
      )}
      {metadata?.note ? (
        <p className="text-xs text-[var(--ph-muted)]">{metadata.note}</p>
      ) : null}
    </div>
  );
}
