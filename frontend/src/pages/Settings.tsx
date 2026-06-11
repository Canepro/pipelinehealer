import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { KeyRound, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../api/client";
import type { SecretSetting, SetupCheck } from "../api/client";
import { detectCachedAdminSession } from "../auth/adminSession";
import { useApiAuthReady } from "../auth/apiAuthReady";
import { AUTH_ENABLED } from "../auth/config";
import {
  getNextAdminKeyScopeId,
  getSettingsQueryAuthScope,
} from "../auth/settingsQueryAuthScope";
import {
  AdminControlsForm,
  RuntimePolicyBanner,
  toSettingsForm,
} from "../components/settings";
import type { SettingsFormState } from "../components/settings";
import {
  describeLlmCapability,
  describeSecretSettingsFailure,
  formatIntegrationQueryState,
  type SubqueryFailureState,
} from "../components/settings/runtimeSemantics";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfirm } from "@/components/ui/use-confirm";
import { SettingToggleField } from "../components/settings/SettingToggleField";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const isApiAuthReady = useApiAuthReady();
  const [adminKeyInput, setAdminKeyInput] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [showAuthPanel, setShowAuthPanel] = useState(false);
  const [adminKeyScopeId, setAdminKeyScopeId] = useState<number | null>(null);
  const [useSessionAuth, setUseSessionAuth] = useState(false);
  const [newMcpRepoInput, setNewMcpRepoInput] = useState("");
  const [newHandoffHostInput, setNewHandoffHostInput] = useState("");
  const [secretDrafts, setSecretDrafts] = useState<Record<string, string>>({});
  const [form, setForm] = useState<SettingsFormState>({
    llm_provider: "codex_app_server",
    openai_compatible_base_url: "",
    openai_compatible_model: "",
    codex_app_server_transport: "stdio",
    codex_app_server_command: "codex app-server",
    codex_app_server_model: "gpt-5.4",
    codex_app_server_turn_timeout_ms: 120000,
    codex_app_server_ws_url: "",
    codex_app_server_ws_allow_remote: false,
    llm_model_analysis: "",
    llm_model_diagnosis: "",
    llm_model_remediation: "",
    mcp_enabled: false,
    mcp_provider: "disabled",
    mcp_read_only: true,
    mcp_timeout_seconds: 15,
    mcp_max_retries: 1,
    mcp_tool_policies: {
      fetch_failure_context: "read_only",
      fetch_runbook_context: "read_only",
      publish_artifact: "write_with_approval",
      rerun_pipeline: "write_with_approval",
    },
    mcp_repo_allowlist: [],
    heal_mode: "safe",
    auto_apply_remediation: true,
    auto_create_pr: true,
    jenkins_bridge_allow_pr: false,
    auto_create_issue: true,
    auto_retry_workflow: true,
    auto_create_tracking_issue_for_prs: true,
    auto_close_on_workflow_success: true,
    auto_merge_remediation_prs: false,
    auto_merge_strategy: "merge_when_clean",
    auto_merge_poll_seconds: 90,
    auto_merge_require_clean_checks: true,
    max_remediation_attempts: 3,
    verify_webhook_signature: true,
    verify_webhook_signature_in_development: false,
    pipeline_step_timeout_seconds: 120,
    github_api_max_retries: 3,
    github_api_retry_base_seconds: 0.5,
    github_api_retry_max_seconds: 8,
    log_prompt_max_chars: 18000,
    log_prompt_head_chars: 9000,
    log_prompt_tail_chars: 9000,
    gh_aw_tools_enabled: false,
    gh_aw_ingestion_mode: "disabled",
    gh_aw_known_workflows: ["ci-doctor"],
    agent_handoff_enabled: false,
    agent_handoff_mode: "copy_only",
    agent_handoff_webhook_allowlist: [],
    agent_handoff_timeout_seconds: 8,
    agent_handoff_max_retries: 1,
    agent_handoff_default_target: "codex_app_server",
    agent_handoff_enabled_targets: ["codex_app_server"],
    agent_handoff_local_codex_enabled: false,
    agent_handoff_local_codex_open_pr: true,
    agent_handoff_local_codex_timeout_ms: 600000,
    agent_handoff_local_codex_workspace_root: "",
    agent_handoff_local_max_concurrent: 1,
    agent_handoff_auto_local: false,
    ph_allowed_repos: [],
    azure_openai_endpoint: "",
    azure_openai_deployment_name: "",
    azure_openai_api_version: "2025-04-01-preview",
    azure_openai_chat_api_version: "2024-12-01-preview",
    github_app_id: "",
    jenkins_bridge_enabled: false,
    jenkins_bridge_max_skew_seconds: 300,
    jenkins_bridge_replay_ttl_seconds: 86400,
    jenkins_bridge_max_body_bytes: 524288,
  });
  const [lastSavedForm, setLastSavedForm] = useState<SettingsFormState | null>(
    null,
  );
  const [newRepoInput, setNewRepoInput] = useState("");
  const [, setGhAwWorkflowsInput] = useState("");
  const hasAuthAttempt =
    adminKey.length > 0 || (isApiAuthReady && useSessionAuth);
  const effectiveAdminKey = useSessionAuth ? undefined : adminKey;
  const authQueryScope = getSettingsQueryAuthScope({
    useSessionAuth,
    adminKey,
    adminKeyScopeId,
  });
  const settingsQueryKey = ["app-settings", authQueryScope] as const;
  const secretSettingsQueryKey = ["secret-settings", authQueryScope] as const;
  const llmProviderHealthQueryKey = [
    "llm-provider-health",
    authQueryScope,
  ] as const;
  const mcpProviderHealthQueryKey = [
    "mcp-provider-health",
    authQueryScope,
  ] as const;
  const handoffIntegrationStatusQueryKey = [
    "agent-handoff-integration-status",
    authQueryScope,
  ] as const;

  const { data, isLoading, isError, error } = useQuery({
    queryKey: settingsQueryKey,
    queryFn: () => api.getSettings(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const {
    data: secretSettings,
    isError: isSecretSettingsError,
    error: secretSettingsError,
  } = useQuery({
    queryKey: secretSettingsQueryKey,
    queryFn: () => api.getSecretSettings(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const {
    data: llmProviderHealth,
    isLoading: isLlmHealthLoading,
    isError: isLlmHealthError,
    error: llmHealthError,
  } = useQuery({
    queryKey: llmProviderHealthQueryKey,
    queryFn: () => api.getLLMProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const {
    data: mcpProviderHealth,
    isLoading: isMcpHealthLoading,
    isError: isMcpHealthError,
    error: mcpHealthError,
  } = useQuery({
    queryKey: mcpProviderHealthQueryKey,
    queryFn: () => api.getMCPProviderHealth(effectiveAdminKey),
    enabled: hasAuthAttempt,
    retry: false,
  });

  const {
    data: handoffIntegrationStatus,
    isError: isHandoffIntegrationError,
    error: handoffIntegrationError,
  } = useQuery({
    queryKey: handoffIntegrationStatusQueryKey,
    queryFn: () => api.getAgentHandoffIntegrationStatus(),
    enabled: hasAuthAttempt,
    retry: false,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!data) return;
    const next = toSettingsForm(data);
    setForm(next);
    setLastSavedForm(next);
    setGhAwWorkflowsInput(next.gh_aw_known_workflows.join(","));
  }, [data]);

  useEffect(() => {
    if (!AUTH_ENABLED || !isApiAuthReady || adminKey.length > 0) {
      return;
    }
    if (detectCachedAdminSession()) {
      setUseSessionAuth(true);
    }
  }, [adminKey.length, isApiAuthReady]);

  const hasUnsavedChanges =
    lastSavedForm !== null &&
    JSON.stringify(form) !== JSON.stringify(lastSavedForm);
  const settingsErrorMessage =
    error instanceof Error ? error.message : "Unknown error";
  const secretSettingsFailure = isSecretSettingsError
    ? describeSecretSettingsFailure(
        secretSettingsError instanceof Error ? secretSettingsError : null,
      )
    : null;
  const sessionAuthActive = AUTH_ENABLED && useSessionAuth;
  const sessionBootstrapPending =
    AUTH_ENABLED && !isApiAuthReady && adminKey.length === 0;
  const sessionAuthDisabledByConfig = useSessionAuth && !AUTH_ENABLED;
  const showSessionRefreshHint =
    useSessionAuth &&
    AUTH_ENABLED &&
    isError &&
    (() => {
      const normalized = settingsErrorMessage.toLowerCase();
      return (
        normalized.includes("invalid or missing admin api key") ||
        normalized.includes("invalid bearer token") ||
        normalized.includes("missing credentials")
      );
    })();
  const handoffIntegrationSummary = formatIntegrationQueryState({
    status: handoffIntegrationStatus,
    isError: isHandoffIntegrationError,
    error:
      handoffIntegrationError instanceof Error ? handoffIntegrationError : null,
  });
  const llmCapabilitySummary = describeLlmCapability(llmProviderHealth);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const codexRuntimeSelected = form.llm_provider === "codex_app_server";
      const payload: Record<string, unknown> = {
        llm_provider: form.llm_provider,
        openai_compatible_base_url: form.openai_compatible_base_url.trim(),
        openai_compatible_model: form.openai_compatible_model.trim(),
        codex_app_server_transport: form.codex_app_server_transport,
        codex_app_server_command: form.codex_app_server_command.trim(),
        codex_app_server_model: form.codex_app_server_model.trim(),
        codex_app_server_turn_timeout_ms:
          form.codex_app_server_turn_timeout_ms,
        codex_app_server_ws_url: form.codex_app_server_ws_url.trim(),
        codex_app_server_ws_allow_remote:
          form.codex_app_server_ws_allow_remote,
        llm_model_analysis: codexRuntimeSelected
          ? ""
          : form.llm_model_analysis.trim(),
        llm_model_diagnosis: codexRuntimeSelected
          ? ""
          : form.llm_model_diagnosis.trim(),
        llm_model_remediation: codexRuntimeSelected
          ? ""
          : form.llm_model_remediation.trim(),
        mcp_enabled: form.mcp_enabled,
        mcp_provider: form.mcp_provider,
        mcp_read_only: form.mcp_read_only,
        mcp_timeout_seconds: form.mcp_timeout_seconds,
        mcp_max_retries: form.mcp_max_retries,
        mcp_tool_policies: form.mcp_tool_policies,
        mcp_repo_allowlist: form.mcp_repo_allowlist,
        heal_mode: form.heal_mode,
        auto_apply_remediation: form.auto_apply_remediation,
        auto_create_pr: form.auto_create_pr,
        jenkins_bridge_allow_pr: form.jenkins_bridge_allow_pr,
        auto_create_issue: form.auto_create_issue,
        auto_retry_workflow: form.auto_retry_workflow,
        auto_create_tracking_issue_for_prs:
          form.auto_create_tracking_issue_for_prs,
        auto_close_on_workflow_success: form.auto_close_on_workflow_success,
        auto_merge_remediation_prs: form.auto_merge_remediation_prs,
        auto_merge_strategy: form.auto_merge_strategy,
        auto_merge_poll_seconds: form.auto_merge_poll_seconds,
        auto_merge_require_clean_checks: form.auto_merge_require_clean_checks,
        max_remediation_attempts: form.max_remediation_attempts,
        verify_webhook_signature: form.verify_webhook_signature,
        verify_webhook_signature_in_development:
          form.verify_webhook_signature_in_development,
        pipeline_step_timeout_seconds: form.pipeline_step_timeout_seconds,
        github_api_max_retries: form.github_api_max_retries,
        github_api_retry_base_seconds: form.github_api_retry_base_seconds,
        github_api_retry_max_seconds: form.github_api_retry_max_seconds,
        log_prompt_max_chars: form.log_prompt_max_chars,
        log_prompt_head_chars: form.log_prompt_head_chars,
        log_prompt_tail_chars: form.log_prompt_tail_chars,
        gh_aw_tools_enabled: form.gh_aw_tools_enabled,
        gh_aw_ingestion_mode: form.gh_aw_ingestion_mode,
        gh_aw_known_workflows: form.gh_aw_known_workflows,
        agent_handoff_enabled: form.agent_handoff_enabled,
        agent_handoff_mode: form.agent_handoff_mode,
        agent_handoff_webhook_allowlist: form.agent_handoff_webhook_allowlist,
        agent_handoff_timeout_seconds: form.agent_handoff_timeout_seconds,
        agent_handoff_max_retries: form.agent_handoff_max_retries,
        agent_handoff_default_target: form.agent_handoff_default_target,
        agent_handoff_enabled_targets: form.agent_handoff_enabled_targets,
        agent_handoff_local_codex_enabled: form.agent_handoff_local_codex_enabled,
        agent_handoff_local_codex_open_pr: form.agent_handoff_local_codex_open_pr,
        agent_handoff_local_codex_timeout_ms: form.agent_handoff_local_codex_timeout_ms,
        agent_handoff_local_codex_workspace_root:
          form.agent_handoff_local_codex_workspace_root.trim(),
        agent_handoff_local_max_concurrent: form.agent_handoff_local_max_concurrent,
        agent_handoff_auto_local: form.agent_handoff_auto_local,
        ph_allowed_repos: form.ph_allowed_repos,
        azure_openai_endpoint: form.azure_openai_endpoint.trim(),
        azure_openai_api_version: form.azure_openai_api_version.trim(),
        azure_openai_chat_api_version: form.azure_openai_chat_api_version.trim(),
        github_app_id: form.github_app_id.trim(),
        jenkins_bridge_enabled: form.jenkins_bridge_enabled,
        jenkins_bridge_max_skew_seconds: form.jenkins_bridge_max_skew_seconds,
        jenkins_bridge_replay_ttl_seconds: form.jenkins_bridge_replay_ttl_seconds,
        jenkins_bridge_max_body_bytes: form.jenkins_bridge_max_body_bytes,
      };
      const deploymentName = form.azure_openai_deployment_name.trim();
      payload.azure_openai_deployment_name = deploymentName;
      return await api.updateSettings(effectiveAdminKey, payload);
    },
    onSuccess: async (updated) => {
      const next = toSettingsForm(updated);
      setForm(next);
      setLastSavedForm(next);
      setGhAwWorkflowsInput(next.gh_aw_known_workflows.join(","));
      queryClient.setQueryData(settingsQueryKey, updated);
      await queryClient.invalidateQueries({
        queryKey: settingsQueryKey,
      });
      toast.success("Settings saved", {
        description: "Changes are active now and persisted for future restarts unless overridden by env.",
      });
    },
    onError: (err) => {
      toast.error("Failed to save settings", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    },
  });

  const saveSecretMutation = useMutation({
    mutationFn: async ({ key, clear }: { key: string; clear?: boolean }) => {
      const draft = secretDrafts[key] ?? "";
      return api.updateSecretSettings(effectiveAdminKey, {
        secrets: {
          [key]: clear ? { clear: true } : { value: draft },
        },
      });
    },
    onSuccess: async (_data, variables) => {
      setSecretDrafts((current) => {
        const next = { ...current };
        delete next[variables.key];
        return next;
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: secretSettingsQueryKey }),
        queryClient.invalidateQueries({ queryKey: settingsQueryKey }),
        queryClient.invalidateQueries({ queryKey: llmProviderHealthQueryKey }),
        queryClient.invalidateQueries({ queryKey: mcpProviderHealthQueryKey }),
        queryClient.invalidateQueries({
          queryKey: handoffIntegrationStatusQueryKey,
        }),
      ]);
      toast.success("Secret updated", {
        description: "The value was stored without being returned to the UI.",
      });
    },
    onError: (err) => {
      toast.error("Failed to update secret", {
        description: describeSecretUpdateError(err),
      });
    },
  });

  const handleSaveSettings = async () => {
    if (
      data?.environment === "production" &&
      data.heal_mode === "safe" &&
      ["demo", "freestyle"].includes(form.heal_mode) &&
      !(await confirm({
        title: "Enable aggressive healing in production?",
        description:
          "This increases autonomous write actions in a production environment.",
        confirmLabel: "Enable",
        destructive: true,
      }))
    ) {
      return;
    }
    if (
      data?.verify_webhook_signature &&
      !form.verify_webhook_signature &&
      !(await confirm({
        title: "Disable webhook signature verification?",
        description: "Incoming webhook authenticity checks will be removed.",
        confirmLabel: "Disable",
        destructive: true,
      }))
    ) {
      return;
    }
    saveMutation.mutate();
  };

  const handleSecretAction = async (secret: SecretSetting, clear = false) => {
    if (
      clear &&
      !(await confirm({
        title: `Clear ${formatSecretLabel(secret.key)}?`,
        description: "Dependent integrations may stop working immediately.",
        confirmLabel: "Clear secret",
        destructive: true,
      }))
    ) {
      return;
    }
    if (
      secret.key === "agent_handoff_webhook_url" &&
      !clear &&
      secret.configured &&
      (secretDrafts[secret.key] ?? "").trim() &&
      !(await confirm({
        title: "Rotate the Assign-to-Agent destination URL?",
        description: "Future deliveries will go to the new host.",
        confirmLabel: "Rotate",
      }))
    ) {
      return;
    }
    saveSecretMutation.mutate({ key: secret.key, clear });
  };

  const loadWithAdminKey = () => {
    const trimmed = adminKeyInput.trim();
    if (!trimmed) {
      return;
    }
    setUseSessionAuth(false);
    setAdminKey(trimmed);
    setAdminKeyScopeId((current) => getNextAdminKeyScopeId(current));
    setAdminKeyInput("");
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {confirmDialog}
      {/* Page header */}
      <div className="flex items-start gap-3.5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]">
          <Settings2 className="h-5 w-5 text-[var(--ph-accent)]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--ph-text)]">Settings</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--ph-muted)]">
            Operator control surface for runtime policy, startup-managed
            dependencies, and durable settings.
          </p>
        </div>
      </div>

      {/* Admin access */}
      {data && !showAuthPanel ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div className="flex items-center gap-2 text-sm">
              <KeyRound className="h-4 w-4 text-[var(--ph-accent)]" />
              <span className="font-medium text-[var(--ph-text)]">
                Admin access active
              </span>
              <span className="text-[var(--ph-muted)]">
                via {sessionAuthActive ? "Entra session" : "admin key"}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAuthPanel(true)}
            >
              Change credentials
            </Button>
          </CardContent>
        </Card>
      ) : (
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-[var(--ph-accent)]" />
            <CardTitle>Admin access</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
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
            <Button onClick={loadWithAdminKey} disabled={!adminKeyInput.trim() || isLoading}>
              {isLoading ? "Loading..." : "Load with Admin Key"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setUseSessionAuth(true);
                setAdminKey("");
              }}
              disabled={
                isLoading ||
                !AUTH_ENABLED ||
                !isApiAuthReady ||
                sessionAuthActive
              }
            >
              {isLoading
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
                    Signed-in Entra session detected. This page is already
                    using your current session. Enter
                    <code className="mx-1 font-mono">X-Admin-Key</code>
                    only if you need to override it for troubleshooting.
                  </>
                ) : (
                  <>
                    Use either{" "}
                    <code className="font-mono">X-Admin-Key</code> or a
                    signed-in Entra role with admin permissions.
                  </>
                )}
              </>
            ) : (
              <>
                Session sign-in is disabled in this deployment. Authenticate
                with the admin key, or enable Entra sign-in in the frontend
                runtime configuration (
                <code className="font-mono">VITE_AUTH_MODE=entra</code>).
              </>
            )}
          </p>
        </CardContent>
      </Card>
      )}

      {sessionBootstrapPending && (
        <Card>
          <CardContent className="py-6 text-sm text-[var(--ph-muted)]">
            Preparing your signed-in admin session...
          </CardContent>
        </Card>
      )}

      {/* Loading skeleton */}
      {hasAuthAttempt && isLoading && (
        <Card>
          <CardContent className="py-6">
            <div className="space-y-4">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-2/3" />
              <Skeleton className="h-10 w-full" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error state */}
      {hasAuthAttempt && isError && (
        <Card className="border-[var(--ph-danger-border)]">
          <CardContent className="py-6">
            <p className="text-sm font-medium text-[var(--ph-danger)]">
              Failed to load settings
            </p>
            <p className="text-sm text-[var(--ph-muted)] mt-1">
              {settingsErrorMessage}
            </p>
            {showSessionRefreshHint && (
              <p className="text-xs text-[var(--ph-muted)] mt-3">
                Session may be stale. Try signing out, signing in again, or
                clearing site data and retrying.
              </p>
            )}
            {sessionAuthDisabledByConfig && (
              <p className="text-xs text-[var(--ph-muted)] mt-3">
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

      {/* Main settings content */}
      {data && (
        <>
          <RuntimePolicyBanner data={data} />

          <AdminControlsForm
            data={data}
            form={form}
            setForm={setForm}
            llmProviderHealth={llmProviderHealth}
            isLlmHealthLoading={isLlmHealthLoading}
            isLlmHealthError={isLlmHealthError}
            llmHealthError={llmHealthError}
            mcpProviderHealth={mcpProviderHealth}
            isMcpHealthLoading={isMcpHealthLoading}
            isMcpHealthError={isMcpHealthError}
            mcpHealthError={mcpHealthError}
            llmCapabilitySummary={llmCapabilitySummary}
            hasUnsavedChanges={hasUnsavedChanges}
            newRepoInput={newRepoInput}
            setNewRepoInput={setNewRepoInput}
            newMcpRepoInput={newMcpRepoInput}
            setNewMcpRepoInput={setNewMcpRepoInput}
            newHandoffHostInput={newHandoffHostInput}
            setNewHandoffHostInput={setNewHandoffHostInput}
            setGhAwWorkflowsInput={setGhAwWorkflowsInput}
            setLastSavedForm={setLastSavedForm}
            savePending={saveMutation.isPending}
            saveError={
              saveMutation.isError ? (saveMutation.error as Error) : null
            }
            saveSuccess={saveMutation.isSuccess}
            onSave={handleSaveSettings}
          />

          <div className="grid gap-4 xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)] xl:items-start">
            <SetupChecklistCard status={data.setup_status} />
            <SecretSettingsCard
              secrets={secretSettings ?? []}
              errorState={secretSettingsFailure}
              values={secretDrafts}
              onChange={(key, value) =>
                setSecretDrafts((current) => ({ ...current, [key]: value }))
              }
              onSave={handleSecretAction}
              pendingKey={saveSecretMutation.isPending ? saveSecretMutation.variables?.key : null}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_360px] xl:items-stretch">
            <div className="space-y-4">
              <RuntimeWiringCard form={form} setForm={setForm} data={data} />

              <Card className="overflow-hidden">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Runtime posture</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-6 lg:grid-cols-2">
                  <SettingsSummarySection
                    title="Automation"
                    items={[
                      { label: "Heal mode", value: data.heal_mode },
                      {
                        label: "Auto-apply remediation",
                        value: data.auto_apply_remediation ? "Yes" : "No",
                      },
                      {
                        label: "Auto-create PR",
                        value: data.auto_create_pr ? "Yes" : "No",
                      },
                      {
                        label: "Auto-create issue",
                        value: data.auto_create_issue ? "Yes" : "No",
                      },
                      {
                        label: "Auto-retry workflow",
                        value: data.auto_retry_workflow ? "Yes" : "No",
                      },
                      {
                        label: "Auto-merge PRs",
                        value: data.auto_merge_remediation_prs
                          ? data.auto_merge_strategy
                          : "No",
                      },
                      {
                        label: "Max attempts",
                        value: data.max_remediation_attempts,
                      },
                    ]}
                  />
                  <SettingsSummarySection
                    title="Scope and provider"
                    items={[
                      {
                        label: "Repo scope",
                        value:
                          data.ph_allowed_repos.length > 0
                            ? `${data.ph_allowed_repos.length} allowlisted repos`
                            : "All repositories",
                      },
                      {
                        label: "MCP allowlist",
                        value:
                          data.mcp_repo_allowlist.length > 0
                            ? `${data.mcp_repo_allowlist.length} repos`
                            : "Fallback to PH scope",
                      },
                      { label: "LLM provider", value: data.llm_provider },
                      {
                        label: "Default model",
                        value:
                          data.llm_provider === "azure_openai"
                            ? data.azure_openai_deployment_name ||
                              "Not configured"
                            : data.llm_provider === "codex_app_server"
                              ? data.codex_app_server_model || "Not configured"
                            : data.openai_compatible_model || "Not configured",
                      },
                      { label: "Auth mode", value: data.auth_mode },
                      {
                        label: "Webhook signature",
                        value: data.verify_webhook_signature
                          ? "Required"
                          : "Off",
                      },
                    ]}
                  />
                </CardContent>
              </Card>

              <Card className="overflow-hidden">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">
                    Integration management boundary
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid gap-6 lg:grid-cols-2">
                  <SettingsSummarySection
                    title="Managed here"
                    items={[
                      {
                        label: "Assign-to-Agent runtime",
                        value: data.agent_handoff_enabled
                          ? "Enabled"
                          : "Disabled",
                      },
                      {
                        label: "Handoff mode",
                        value:
                          data.agent_handoff_mode === "webhook"
                            ? "Webhook"
                            : "Copy only",
                      },
                      {
                        label: "Allowlist hosts",
                        value:
                          data.agent_handoff_webhook_allowlist.length || "None",
                      },
                      {
                        label: "Timeout",
                        value: `${data.agent_handoff_timeout_seconds}s`,
                      },
                      {
                        label: "Retries",
                        value: data.agent_handoff_max_retries,
                      },
                      {
                        label: "Jenkins bridge PRs",
                        value: data.jenkins_bridge_allow_pr
                          ? "Allowed"
                          : "Issue-first",
                      },
                    ]}
                  />
                  <div className="space-y-3 px-1">
                    <div className="text-sm font-semibold text-[var(--ph-text)]/90">
                      Bootstrap and override boundary
                    </div>
                    <ul className="space-y-2 text-sm leading-6 text-[var(--ph-muted)]">
                      <li>
                        Auth bootstrap, storage bootstrap, CORS, and observability still come from environment configuration.
                      </li>
                      <li>
                        Runtime values saved here are durable immediately unless the same key is overridden in env.
                      </li>
                      <li>
                        Secret values are managed separately and never returned to the browser after write.
                      </li>
                    </ul>
                    <p className="border-t border-[var(--ph-border-subtle)] pt-3 text-xs leading-5 text-[var(--ph-muted)]">
                      Use env only for bootstrap wiring or forced overrides. Normal operator changes belong in this UI.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="flex h-full flex-col gap-4">
              <Card className="flex h-full flex-col overflow-hidden">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">
                    Live integration status
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col gap-4">
                  <SettingsSummarySection
                    title="Assign-to-Agent"
                    compact
                    items={[
                      {
                        label: "Destination",
                        value:
                          data.agent_handoff_webhook_host ||
                          "Startup URL not configured",
                        mono: Boolean(data.agent_handoff_webhook_host),
                      },
                      {
                        label: "Receiver",
                        value: handoffIntegrationSummary.summary,
                        detail: handoffIntegrationSummary.detail,
                      },
                      {
                        label: "Notification targets",
                        value: isHandoffIntegrationError
                          ? "Probe failed"
                          : handoffIntegrationStatus?.notifications
                            ? `${handoffIntegrationStatus.notifications.enabled_targets} enabled / ${handoffIntegrationStatus.notifications.invalid_targets} invalid`
                            : "No receiver probe data",
                        detail:
                          isHandoffIntegrationError
                            ? undefined
                            : handoffIntegrationStatus?.notifications
                                  ?.supported_target_types.length
                              ? `Supported sinks: ${handoffIntegrationStatus.notifications.supported_target_types.join(
                                  ", ",
                                )}`
                              : undefined,
                      },
                    ]}
                  />
                  <div className="mt-auto border-t border-[var(--ph-border-subtle)] pt-4 text-sm text-[var(--ph-muted)]">
                    <div className="font-semibold text-[var(--ph-text)]/90">
                      Operator workflow
                    </div>
                    <ol className="mt-3 space-y-2 leading-6">
                      <li>
                        1. Authenticate and confirm the current runtime posture.
                      </li>
                      <li>
                        2. Change controls in the section tabs at the top of
                        this page.
                      </li>
                      <li>
                        3. Save once to apply and persist runtime changes.
                      </li>
                      <li>
                        4. Confirm the effect in Control Center and activity
                        evidence.
                      </li>
                    </ol>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>

          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
              <p className="text-sm text-[var(--ph-muted)]">
                Runtime settings save immediately to durable storage.
                Environment values act as explicit startup overrides.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm" variant="secondary">
                  <Link to="/app/control-center">Open Control Center</Link>
                </Button>
                <Button asChild size="sm" variant="ghost">
                  <Link to="/app/activities">Review activities</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function SettingsSummarySection({
  title,
  items,
  compact = false,
}: {
  title: string;
  items: Array<{
    label: string;
    value: string | number;
    detail?: string;
    mono?: boolean;
  }>;
  compact?: boolean;
}) {
  return (
    <div>
      <div className="mb-3 text-sm font-semibold text-[var(--ph-text)]/90">
        {title}
      </div>
      <div className={compact ? "space-y-2" : "space-y-2.5"}>
        {items.map((item) => (
          <div
            key={`${title}-${item.label}`}
            className={
              compact
                ? "rounded-md bg-[var(--ph-bg-elevated)]/28 px-3 py-2.5 shadow-[inset_0_0_0_1px_var(--ph-border-subtle)]"
                : "flex items-start justify-between gap-4 rounded-md bg-[var(--ph-bg-elevated)]/28 px-3 py-2.5 shadow-[inset_0_0_0_1px_var(--ph-border-subtle)]"
            }
          >
            <span
              className={
                compact
                  ? "text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--ph-muted)]/90"
                  : "text-sm text-[var(--ph-muted)]"
              }
            >
              {item.label}
            </span>
            <div
              className={
                compact
                  ? "mt-1.5 min-w-0 space-y-1"
                  : "min-w-[112px] max-w-[52%] flex-none space-y-1 text-right"
              }
            >
              <span
                className={`block font-medium text-[var(--ph-text)]/90 ${
                  item.mono
                    ? "break-all font-mono text-xs"
                    : "break-words"
                }`}
              >
                {item.value}
              </span>
              {item.detail ? (
                <div className="break-words text-xs text-[var(--ph-muted)]">
                  {item.detail}
                </div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RuntimeWiringCard({
  data,
  form,
  setForm,
}: {
  data: { settings_metadata: Record<string, { source: string }> };
  form: SettingsFormState;
  setForm: Dispatch<SetStateAction<SettingsFormState>>;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Runtime wiring</CardTitle>
          <Badge variant="outline">UI-managed</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <FieldHeader
            label="Azure OpenAI endpoint"
            source={data.settings_metadata?.azure_openai_endpoint?.source}
          />
          <Input
            value={form.azure_openai_endpoint}
            onChange={(event) =>
              setForm((current) => ({ ...current, azure_openai_endpoint: event.target.value }))
            }
            placeholder="https://resource.cognitiveservices.azure.com/"
          />

          <FieldHeader
            label="Deployment name"
            source={data.settings_metadata?.azure_openai_deployment_name?.source}
          />
          <Input
            value={form.azure_openai_deployment_name}
            onChange={(event) =>
              setForm((current) => ({ ...current, azure_openai_deployment_name: event.target.value }))
            }
            placeholder="Azure deployment name"
          />

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <FieldHeader
                label="Primary API version"
                source={data.settings_metadata?.azure_openai_api_version?.source}
              />
              <Input
                value={form.azure_openai_api_version}
                onChange={(event) =>
                  setForm((current) => ({ ...current, azure_openai_api_version: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <FieldHeader
                label="Fallback API version"
                source={data.settings_metadata?.azure_openai_chat_api_version?.source}
              />
              <Input
                value={form.azure_openai_chat_api_version}
                onChange={(event) =>
                  setForm((current) => ({ ...current, azure_openai_chat_api_version: event.target.value }))
                }
              />
            </div>
          </div>

          <FieldHeader
            label="GitHub App ID"
            source={data.settings_metadata?.github_app_id?.source}
          />
          <Input
            value={form.github_app_id}
            onChange={(event) =>
              setForm((current) => ({ ...current, github_app_id: event.target.value }))
            }
            placeholder="123456"
          />
          <p className="text-xs leading-5 text-[var(--ph-muted)]">
            GitHub App inputs are stored here for configuration readiness, but the current live GitHub API runtime still requires a personal access token.
          </p>
        </div>

        <div className="space-y-4">
          <div className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/20 px-3 py-3">
            <SettingToggleField
              label="Verify webhook signatures"
              description="Keep this enabled in production unless you have a trusted intermediary in front of the webhook endpoint."
              checked={form.verify_webhook_signature}
              checkedLabel="Required"
              uncheckedLabel="Disabled"
              badgeLabel={
                data.settings_metadata?.verify_webhook_signature?.source === "env"
                  ? "Env override"
                  : "Runtime"
              }
              onChange={(value) =>
                setForm((current) => ({
                  ...current,
                  verify_webhook_signature: value,
                }))
              }
            />
          </div>

          <div className="rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/20 px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-[var(--ph-text)]">Jenkins bridge</div>
                <p className="mt-1 text-xs leading-5 text-[var(--ph-muted)]">
                  Runtime bridge policy now lives here; the shared secret stays in the separate secrets section.
                </p>
              </div>
              <Badge variant="outline">
                {data.settings_metadata?.jenkins_bridge_enabled?.source === "env" ? "Env override" : "Runtime"}
              </Badge>
            </div>
            <div className="mt-3 space-y-3 border-t border-[var(--ph-border-subtle)] pt-3">
              <SettingToggleField
                label="Enabled"
                description="Turn the Jenkins bridge runtime policy on or off."
                checked={form.jenkins_bridge_enabled}
                checkedLabel="On"
                uncheckedLabel="Off"
                badgeLabel={
                  data.settings_metadata?.jenkins_bridge_enabled?.source === "env"
                    ? "Env override"
                    : "Runtime"
                }
                onChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    jenkins_bridge_enabled: value,
                  }))
                }
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Max skew (s)</Label>
                  <Input
                    type="number"
                    value={form.jenkins_bridge_max_skew_seconds}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, jenkins_bridge_max_skew_seconds: Number(event.target.value) || 0 }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Replay TTL (s)</Label>
                  <Input
                    type="number"
                    value={form.jenkins_bridge_replay_ttl_seconds}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, jenkins_bridge_replay_ttl_seconds: Number(event.target.value) || 0 }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Max body (bytes)</Label>
                  <Input
                    type="number"
                    value={form.jenkins_bridge_max_body_bytes}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, jenkins_bridge_max_body_bytes: Number(event.target.value) || 0 }))
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function FieldHeader({ label, source }: { label: string; source?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <Label>{label}</Label>
      <Badge variant="outline">{source === "env" ? "Env override" : "Runtime"}</Badge>
    </div>
  );
}

function SetupChecklistCard({ status }: { status: { ready: boolean; storage_bootstrap: SetupCheck; auth_bootstrap: SetupCheck; secret_backend: SetupCheck; llm_runtime: SetupCheck; github_runtime: SetupCheck; jenkins_bridge: SetupCheck; webhook_secrets: SetupCheck } }) {
  const items = [
    ["Storage bootstrap", status.storage_bootstrap],
    ["Auth bootstrap", status.auth_bootstrap],
    ["Secret backend", status.secret_backend],
    ["LLM runtime", status.llm_runtime],
    ["GitHub runtime", status.github_runtime],
    ["Jenkins bridge", status.jenkins_bridge],
    ["Webhook secrets", status.webhook_secrets],
  ] as const;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Setup checklist</CardTitle>
          <Badge variant={status.ready ? "success" : "outline"}>
            {status.ready ? "Ready" : "Action needed"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map(([label, check]) => (
          <div
            key={label}
            className="grid gap-1 rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/20 px-3 py-2"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-[var(--ph-text)]">{label}</div>
              <Badge variant={check.ready ? "success" : "outline"}>
                {check.ready ? "Ready" : "Missing"}
              </Badge>
            </div>
            <p className="text-sm leading-5 text-[var(--ph-muted)]">{check.detail}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function SecretSettingsCard({
  secrets,
  errorState,
  values,
  onChange,
  onSave,
  pendingKey,
}: {
  secrets: SecretSetting[];
  errorState?: SubqueryFailureState | null;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onSave: (secret: SecretSetting, clear?: boolean) => void;
  pendingKey: string | null;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Secrets</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm leading-6 text-[var(--ph-muted)]">
          Secrets are write-only. This page only shows configuration status, source, and safe hints.
        </p>
        {errorState ? (
          <div className="rounded-md border border-[var(--ph-danger-border)] bg-[var(--ph-danger-bg)] px-3 py-3">
            <p className="text-sm font-medium text-[var(--ph-danger)]">
              {errorState.title}
            </p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              {errorState.detail}
            </p>
            <p className="mt-2 text-xs text-[var(--ph-muted)]">
              {errorState.guidance}
            </p>
          </div>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          {secrets.map((secret) => (
            <div
              key={secret.key}
              className="flex flex-col rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]/20 px-3 py-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-[var(--ph-text)]">
                    {formatSecretLabel(secret.key)}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-[var(--ph-muted)]">
                    {secret.note}
                    {secret.safe_hint ? ` Hint: ${secret.safe_hint}.` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <SecretStatusBadge secret={secret} />
                  <Badge variant="outline">{secret.backend}</Badge>
                </div>
              </div>
              <div className="mt-3 space-y-2">
                <Label htmlFor={`secret-${secret.key}`}>Set or rotate value</Label>
                {secret.key === "github_app_private_key" ? (
                  <textarea
                    id={`secret-${secret.key}`}
                    value={values[secret.key] ?? ""}
                    onChange={(event) => onChange(secret.key, event.target.value)}
                    className="min-h-28 w-full rounded-lg border border-[var(--ph-border-strong)] bg-[var(--ph-bg-elevated)] px-3 py-2 text-sm text-[var(--ph-text)] outline-none placeholder:text-[var(--ph-muted)] focus-visible:ring-2 focus-visible:ring-[var(--ph-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--ph-surface)]"
                    placeholder="Paste the new secret value"
                  />
                ) : (
                  <Input
                    id={`secret-${secret.key}`}
                    type={secret.key === "agent_handoff_webhook_url" ? "url" : "password"}
                    value={values[secret.key] ?? ""}
                    onChange={(event) => onChange(secret.key, event.target.value)}
                    placeholder={secret.key === "agent_handoff_webhook_url" ? "https://receiver.example/api/agent-handoff" : "Enter a new secret value"}
                  />
                )}
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => onSave(secret)}
                    disabled={pendingKey === secret.key || !(values[secret.key] ?? "").trim()}
                  >
                    {pendingKey === secret.key ? "Saving..." : secret.configured ? "Rotate" : "Set"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onSave(secret, true)}
                    disabled={pendingKey === secret.key || !secret.configured}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function SecretStatusBadge({ secret }: { secret: SecretSetting }) {
  if (secret.overridden_by_env) {
    return <Badge variant="outline">Overridden by env</Badge>;
  }
  if (secret.configured) {
    return <Badge variant="success">Configured in UI</Badge>;
  }
  return <Badge variant="outline">Not configured</Badge>;
}

function formatSecretLabel(key: string): string {
  switch (key) {
    case "azure_openai_api_key":
      return "Azure OpenAI API key";
    case "openai_compatible_api_key":
      return "OpenAI-compatible API key";
    case "github_personal_access_token":
      return "GitHub personal access token";
    case "github_webhook_secret":
      return "GitHub webhook secret";
    case "jenkins_bridge_shared_secret":
      return "Jenkins bridge shared secret";
    case "agent_handoff_webhook_url":
      return "Assign-to-Agent webhook URL";
    case "github_app_private_key":
      return "GitHub App private key";
    default:
      return key;
  }
}

function describeSecretUpdateError(err: unknown): string {
  const message = err instanceof Error ? err.message : "Unknown error";
  const normalized = message.toLowerCase();

  if (
    normalized.includes("settings_db_encryption_key") ||
    normalized.includes("key_vault_url") ||
    normalized.includes("runtime secret backend")
  ) {
    return "Configure the runtime secret backend in env first, then retry the secret write.";
  }

  return message;
}
