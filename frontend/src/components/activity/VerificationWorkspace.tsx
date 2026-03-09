import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";
import { ExternalLink } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type Activity,
  type LearningGuidanceEffectiveness,
  type LearningVerificationOutcome,
} from "@/api/client";
import { detectCachedAdminSession } from "@/auth/adminSession";
import { useApiAuthReady } from "@/auth/apiAuthReady";
import { AUTH_ENABLED } from "@/auth/config";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  formatGuidanceEffectivenessLabel,
  formatVerificationOutcomeLabel,
  guidanceToneClass,
  type VerificationEntry,
  verificationToneClass,
} from "./verification";

const VERIFICATION_OUTCOME_OPTIONS: Array<{
  value: LearningVerificationOutcome;
  label: string;
  description: string;
}> = [
  { value: "pass", label: "Pass", description: "Confirmed as correct" },
  {
    value: "partial",
    label: "Partial",
    description: "Useful, but incomplete or mixed",
  },
  { value: "fail", label: "Fail", description: "Incorrect or misleading" },
];

const GUIDANCE_EFFECTIVENESS_OPTIONS: Array<{
  value: LearningGuidanceEffectiveness;
  label: string;
  description: string;
}> = [
  { value: "helped", label: "Helped", description: "Guidance improved the fix" },
  {
    value: "neutral",
    label: "Neutral",
    description: "Guidance matched, but did not change the outcome",
  },
  { value: "hurt", label: "Hurt", description: "Guidance created confusion or noise" },
];

export default function VerificationWorkspace({
  activity,
  currentVerification,
  verificationHistory,
  appliedLearningId,
  appliedLearningTitle,
}: {
  activity: Activity;
  currentVerification: VerificationEntry | null;
  verificationHistory: VerificationEntry[];
  appliedLearningId: string | null;
  appliedLearningTitle: string | null;
}) {
  const queryClient = useQueryClient();
  const isApiAuthReady = useApiAuthReady();
  const [adminKeyInput, setAdminKeyInput] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [useSessionAuth, setUseSessionAuth] = useState(false);
  const [identification, setIdentification] =
    useState<LearningVerificationOutcome>("pass");
  const [diagnosis, setDiagnosis] =
    useState<LearningVerificationOutcome>("pass");
  const [remediation, setRemediation] =
    useState<LearningVerificationOutcome>("pass");
  const [guidanceEffectiveness, setGuidanceEffectiveness] =
    useState<LearningGuidanceEffectiveness | "">("");
  const [notes, setNotes] = useState("");
  const [issueNumber, setIssueNumber] = useState("");
  const [issueUrl, setIssueUrl] = useState("");
  const [targetVersion, setTargetVersion] = useState("");

  useEffect(() => {
    if (!AUTH_ENABLED || !isApiAuthReady || adminKey.length > 0) {
      return;
    }
    if (detectCachedAdminSession()) {
      setUseSessionAuth(true);
    }
  }, [adminKey.length, isApiAuthReady]);

  useEffect(() => {
    if (currentVerification) {
      setIdentification(currentVerification.identification);
      setDiagnosis(currentVerification.diagnosis);
      setRemediation(currentVerification.remediation);
      setGuidanceEffectiveness(currentVerification.guidanceEffectiveness ?? "");
      setNotes(currentVerification.notes);
      setIssueNumber(
        currentVerification.issueNumber !== null
          ? String(currentVerification.issueNumber)
          : "",
      );
      setIssueUrl(currentVerification.issueUrl ?? "");
      setTargetVersion(currentVerification.targetVersion ?? "");
      return;
    }
    setIdentification("pass");
    setDiagnosis("pass");
    setRemediation("pass");
    setGuidanceEffectiveness("");
    setNotes("");
    setIssueNumber("");
    setIssueUrl("");
    setTargetVersion("");
  }, [currentVerification]);

  const sessionAuthActive = AUTH_ENABLED && useSessionAuth;
  const sessionBootstrapPending =
    AUTH_ENABLED && !isApiAuthReady && adminKey.length === 0;
  const effectiveAdminKey = useSessionAuth ? undefined : adminKey;
  const hasAuthAttempt =
    adminKey.length > 0 || (isApiAuthReady && sessionAuthActive);
  const requiresGuidanceRating = Boolean(appliedLearningId);
  const canSubmit =
    hasAuthAttempt &&
    Boolean(activity.remediation_result) &&
    (!requiresGuidanceRating || guidanceEffectiveness !== "");

  const feedbackMutation = useMutation({
    mutationFn: () => {
      const normalizedIssueNumber = issueNumber.trim();
      const parsedIssueNumber =
        normalizedIssueNumber.length > 0
          ? Number.parseInt(normalizedIssueNumber, 10)
          : null;
      return api.submitLearningFeedback(effectiveAdminKey, {
        activity_id: activity.id,
        identification,
        diagnosis,
        remediation,
        guidance_effectiveness:
          requiresGuidanceRating && guidanceEffectiveness
            ? guidanceEffectiveness
            : undefined,
        notes: notes.trim() || undefined,
        issue_number:
          parsedIssueNumber !== null &&
          Number.isFinite(parsedIssueNumber) &&
          parsedIssueNumber >= 1
            ? parsedIssueNumber
            : undefined,
        issue_url: issueUrl.trim() || undefined,
        target_version: targetVersion.trim() || undefined,
      });
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["activity", activity.id] });
      toast.success(
        `Verification recorded (${formatVerificationOutcomeLabel(result.verification_overall)})`,
      );
    },
    onError: (err) => {
      toast.error(
        err instanceof Error ? err.message : "Unable to record verification",
      );
    },
  });

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-[var(--ph-border)] bg-[color:var(--ph-surface)] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-[var(--ph-text)]">
              Latest operator verification
            </p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              Verify whether identification, diagnosis, and remediation were correct.
            </p>
          </div>
          {currentVerification ? (
            <Badge variant="outline" className="text-[11px]">
              Recorded{" "}
              {currentVerification.recordedAt
                ? formatDistanceToNow(new Date(currentVerification.recordedAt), {
                    addSuffix: true,
                  })
                : "recently"}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[11px]">
              No verification yet
            </Badge>
          )}
        </div>
        {currentVerification ? (
          <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-4">
            {[
              ["Identification", currentVerification.identification],
              ["Diagnosis", currentVerification.diagnosis],
              ["Remediation", currentVerification.remediation],
              ["Overall", currentVerification.overall],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] px-3 py-2"
              >
                <p className="text-[11px] uppercase tracking-wide text-[var(--ph-muted)]">
                  {label}
                </p>
                <span
                  className={`mt-2 inline-flex rounded-md px-2 py-1 text-xs font-semibold ${verificationToneClass(value as LearningVerificationOutcome)}`}
                >
                  {formatVerificationOutcomeLabel(
                    value as LearningVerificationOutcome,
                  )}
                </span>
              </div>
            ))}
          </div>
        ) : null}
        {currentVerification?.guidanceEffectiveness ? (
          <p className="mt-3 text-sm text-[var(--ph-text)]">
            Guidance impact:{" "}
            <span
              className={`inline-flex rounded-md px-2 py-1 text-xs font-semibold ${guidanceToneClass(currentVerification.guidanceEffectiveness)}`}
            >
              {formatGuidanceEffectivenessLabel(
                currentVerification.guidanceEffectiveness,
              )}
            </span>
          </p>
        ) : null}
        {currentVerification?.notes ? (
          <p className="mt-3 text-sm text-[var(--ph-text)]">
            {currentVerification.notes}
          </p>
        ) : null}
      </div>

      <div className="rounded-lg border border-[var(--ph-border)] bg-[color:var(--ph-surface)] p-4">
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
            variant="secondary"
            onClick={() => {
              setUseSessionAuth(false);
              setAdminKey(adminKeyInput.trim());
            }}
            disabled={!adminKeyInput.trim() || feedbackMutation.isPending}
          >
            Load with Admin Key
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setUseSessionAuth(true);
              setAdminKey("");
            }}
            disabled={
              feedbackMutation.isPending ||
              !AUTH_ENABLED ||
              !isApiAuthReady ||
              sessionAuthActive
            }
          >
            {sessionAuthActive ? "Using Login Session" : "Use Login Session"}
          </Button>
        </div>
        <p className="mt-2 text-xs text-[var(--ph-muted)]">
          {AUTH_ENABLED
            ? sessionAuthActive
              ? "Signed-in session detected. Verification writes will use it unless you override with X-Admin-Key."
              : "Use a signed-in Entra session or provide X-Admin-Key to submit verification feedback."
            : "Session login is disabled in this deployment. Use X-Admin-Key for verification feedback."}
        </p>
        {sessionBootstrapPending ? (
          <p className="mt-2 text-xs text-[var(--ph-muted)]">
            Preparing your signed-in admin session...
          </p>
        ) : null}
      </div>

      <div className="rounded-lg border border-[var(--ph-border)] bg-[color:var(--ph-surface)] p-4">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
              Identification
            </p>
            <Select
              value={identification}
              onValueChange={(value) =>
                setIdentification(value as LearningVerificationOutcome)
              }
            >
              <SelectTrigger className="mt-2 bg-[var(--ph-bg-elevated)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VERIFICATION_OUTCOME_OPTIONS.map((option) => (
                  <SelectItem key={`identification-${option.value}`} value={option.value}>
                    {option.label} - {option.description}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
              Diagnosis
            </p>
            <Select
              value={diagnosis}
              onValueChange={(value) =>
                setDiagnosis(value as LearningVerificationOutcome)
              }
            >
              <SelectTrigger className="mt-2 bg-[var(--ph-bg-elevated)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VERIFICATION_OUTCOME_OPTIONS.map((option) => (
                  <SelectItem key={`diagnosis-${option.value}`} value={option.value}>
                    {option.label} - {option.description}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
              Remediation
            </p>
            <Select
              value={remediation}
              onValueChange={(value) =>
                setRemediation(value as LearningVerificationOutcome)
              }
            >
              <SelectTrigger className="mt-2 bg-[var(--ph-bg-elevated)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VERIFICATION_OUTCOME_OPTIONS.map((option) => (
                  <SelectItem key={`remediation-${option.value}`} value={option.value}>
                    {option.label} - {option.description}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {requiresGuidanceRating ? (
          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
              Guidance effectiveness
            </p>
            <p className="mt-1 text-sm text-[var(--ph-muted)]">
              This activity used playbook guidance from{" "}
              <span className="font-medium text-[var(--ph-text)]">
                {appliedLearningTitle || appliedLearningId}
              </span>
              .
            </p>
            <Select
              value={guidanceEffectiveness}
              onValueChange={(value) =>
                setGuidanceEffectiveness(
                  value as LearningGuidanceEffectiveness | "",
                )
              }
            >
              <SelectTrigger className="mt-2 bg-[var(--ph-bg-elevated)]">
                <SelectValue placeholder="Select guidance impact" />
              </SelectTrigger>
              <SelectContent>
                {GUIDANCE_EFFECTIVENESS_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label} - {option.description}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <div className="mt-4 rounded-md border border-dashed border-[var(--ph-border)] px-3 py-3 text-sm text-[var(--ph-muted)]">
            No promoted learning guidance was applied to this activity, so guidance-effectiveness rating is not required.
          </div>
        )}

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
              Related issue number
            </p>
            <Input
              type="number"
              min="1"
              value={issueNumber}
              onChange={(e) => setIssueNumber(e.target.value)}
              placeholder="Optional"
              className="mt-2"
            />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
              Target version
            </p>
            <Input
              value={targetVersion}
              onChange={(e) => setTargetVersion(e.target.value)}
              placeholder="Optional, e.g. v0.6.0"
              className="mt-2"
            />
          </div>
        </div>
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
            Related issue URL
          </p>
          <Input
            value={issueUrl}
            onChange={(e) => setIssueUrl(e.target.value)}
            placeholder="Optional issue or PR URL"
            className="mt-2"
          />
        </div>
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--ph-muted)]">
            Notes
          </p>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            placeholder="What was correct, missing, or misleading in this activity?"
            className="mt-2 w-full rounded-lg border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] px-3 py-2 text-sm text-[var(--ph-text)] outline-none ring-offset-2 placeholder:text-[var(--ph-muted)] focus:ring-2 focus:ring-[var(--ph-accent)]"
          />
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-[var(--ph-muted)]">
            Verification updates the activity record and recalculates affected learning candidates.
          </p>
          <Button
            onClick={() => feedbackMutation.mutate()}
            disabled={!canSubmit || feedbackMutation.isPending}
          >
            {feedbackMutation.isPending
              ? "Saving verification..."
              : "Record verification"}
          </Button>
        </div>
        {!hasAuthAttempt ? (
          <p className="mt-3 text-xs text-[var(--ph-muted)]">
            Provide admin credentials above before saving.
          </p>
        ) : null}
        {requiresGuidanceRating && guidanceEffectiveness === "" ? (
          <p className="mt-3 text-xs text-[var(--ph-warning)]">
            Guidance effectiveness is required because this run used promoted playbook guidance.
          </p>
        ) : null}
      </div>

      {verificationHistory.length > 0 ? (
        <div className="rounded-lg border border-[var(--ph-border)] bg-[color:var(--ph-surface)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-[var(--ph-text)]">
                Verification history
              </p>
              <p className="mt-1 text-sm text-[var(--ph-muted)]">
                Last {verificationHistory.length} verification update
                {verificationHistory.length === 1 ? "" : "s"} recorded for this activity.
              </p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {verificationHistory.slice(0, 6).map((entry, index) => (
              <div
                key={`${entry.recordedAt ?? "unknown"}-${index}`}
                className="rounded-md border border-[var(--ph-border)] bg-[var(--ph-bg-elevated)] px-3 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-2">
                    <span
                      className={`inline-flex rounded-md px-2 py-1 text-xs font-semibold ${verificationToneClass(entry.overall)}`}
                    >
                      Overall {formatVerificationOutcomeLabel(entry.overall)}
                    </span>
                    {entry.guidanceEffectiveness ? (
                      <span
                        className={`inline-flex rounded-md px-2 py-1 text-xs font-semibold ${guidanceToneClass(entry.guidanceEffectiveness)}`}
                      >
                        Guidance{" "}
                        {formatGuidanceEffectivenessLabel(
                          entry.guidanceEffectiveness,
                        )}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-xs text-[var(--ph-muted)]">
                    {entry.recordedAt
                      ? format(new Date(entry.recordedAt), "PPpp")
                      : "Recorded time unavailable"}
                  </p>
                </div>
                <p className="mt-2 text-xs text-[var(--ph-muted)]">
                  Identification {formatVerificationOutcomeLabel(entry.identification)}
                  {" • "}
                  Diagnosis {formatVerificationOutcomeLabel(entry.diagnosis)}
                  {" • "}
                  Remediation {formatVerificationOutcomeLabel(entry.remediation)}
                </p>
                {entry.actor ? (
                  <p className="mt-1 text-xs text-[var(--ph-muted)]">
                    Actor: {entry.actor}
                    {entry.requestId ? ` • Request ${entry.requestId}` : ""}
                  </p>
                ) : null}
                {entry.issueUrl ? (
                  <a
                    href={entry.issueUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center text-xs text-[var(--ph-accent)] hover:opacity-80"
                  >
                    Open linked issue
                    <ExternalLink className="ml-1 h-3 w-3" />
                  </a>
                ) : null}
                {entry.notes ? (
                  <p className="mt-2 text-sm text-[var(--ph-text)]">
                    {entry.notes}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
