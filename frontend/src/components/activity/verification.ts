import type {
  LearningGuidanceEffectiveness,
  LearningVerificationOutcome,
} from "@/api/client";

export type VerificationEntry = {
  identification: LearningVerificationOutcome;
  diagnosis: LearningVerificationOutcome;
  remediation: LearningVerificationOutcome;
  overall: LearningVerificationOutcome;
  guidanceEffectiveness: LearningGuidanceEffectiveness | null;
  notes: string;
  issueNumber: number | null;
  issueUrl: string | null;
  targetVersion: string | null;
  recordedAt: string | null;
  actor: string | null;
  requestId: string | null;
};

function parseVerificationOutcome(
  value: unknown,
): LearningVerificationOutcome | null {
  return value === "pass" || value === "partial" || value === "fail"
    ? value
    : null;
}

function parseGuidanceEffectiveness(
  value: unknown,
): LearningGuidanceEffectiveness | null {
  return value === "helped" || value === "neutral" || value === "hurt"
    ? value
    : null;
}

function parseVerificationEntry(value: unknown): VerificationEntry | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const identification = parseVerificationOutcome(row.identification);
  const diagnosis = parseVerificationOutcome(row.diagnosis);
  const remediation = parseVerificationOutcome(row.remediation);
  const overall = parseVerificationOutcome(row.overall);
  if (!identification || !diagnosis || !remediation || !overall) return null;
  return {
    identification,
    diagnosis,
    remediation,
    overall,
    guidanceEffectiveness: parseGuidanceEffectiveness(
      row.guidance_effectiveness,
    ),
    notes: typeof row.notes === "string" ? row.notes : "",
    issueNumber:
      typeof row.issue_number === "number" ? row.issue_number : null,
    issueUrl: typeof row.issue_url === "string" ? row.issue_url : null,
    targetVersion:
      typeof row.target_version === "string" ? row.target_version : null,
    recordedAt: typeof row.recorded_at === "string" ? row.recorded_at : null,
    actor: typeof row.actor === "string" ? row.actor : null,
    requestId: typeof row.request_id === "string" ? row.request_id : null,
  };
}

export function getLatestVerification(
  details: Record<string, unknown> | undefined,
): VerificationEntry | null {
  return parseVerificationEntry(details?.verification);
}

export function getVerificationHistory(
  details: Record<string, unknown> | undefined,
): VerificationEntry[] {
  const value = details?.verification_history;
  if (!Array.isArray(value)) return [];
  return value
    .map((entry) => parseVerificationEntry(entry))
    .filter((entry): entry is VerificationEntry => entry !== null)
    .sort((a, b) => {
      const leftParsed = a.recordedAt ? Date.parse(a.recordedAt) : 0;
      const rightParsed = b.recordedAt ? Date.parse(b.recordedAt) : 0;
      const left = Number.isFinite(leftParsed) ? leftParsed : 0;
      const right = Number.isFinite(rightParsed) ? rightParsed : 0;
      return right - left;
    });
}

export function formatVerificationOutcomeLabel(
  value: LearningVerificationOutcome,
): string {
  switch (value) {
    case "pass":
      return "Pass";
    case "partial":
      return "Partial";
    case "fail":
      return "Fail";
    default:
      return value;
  }
}

export function formatGuidanceEffectivenessLabel(
  value: LearningGuidanceEffectiveness,
): string {
  switch (value) {
    case "helped":
      return "Helped";
    case "neutral":
      return "Neutral";
    case "hurt":
      return "Hurt";
    default:
      return value;
  }
}

export function verificationToneClass(
  value: LearningVerificationOutcome,
): string {
  switch (value) {
    case "pass":
      return "bg-[var(--ph-success-bg)] text-[var(--ph-success)]";
    case "partial":
      return "bg-[var(--ph-warning-bg)] text-[var(--ph-warning)]";
    case "fail":
      return "bg-[var(--ph-danger-bg)] text-[var(--ph-danger)]";
    default:
      return "bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]";
  }
}

export function guidanceToneClass(
  value: LearningGuidanceEffectiveness,
): string {
  switch (value) {
    case "helped":
      return "bg-[var(--ph-success-bg)] text-[var(--ph-success)]";
    case "neutral":
      return "bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]";
    case "hurt":
      return "bg-[var(--ph-danger-bg)] text-[var(--ph-danger)]";
    default:
      return "bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]";
  }
}
