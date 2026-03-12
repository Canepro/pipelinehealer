import type { Activity } from "../api/client";

type ExternalDiagnostic = NonNullable<Activity["external_diagnostics"]>[number];

function diagnosticMetadata(
  diagnostic: ExternalDiagnostic,
): Record<string, unknown> {
  return diagnostic.metadata && typeof diagnostic.metadata === "object"
    ? (diagnostic.metadata as Record<string, unknown>)
    : {};
}

export function isContextOnlyExternalDiagnostic(
  diagnostic: ExternalDiagnostic,
): boolean {
  const metadata = diagnosticMetadata(diagnostic);
  return metadata.display_state === "context_only";
}

export function isStrongExternalDiagnostic(
  diagnostic: ExternalDiagnostic,
): boolean {
  const metadata = diagnosticMetadata(diagnostic);
  if (metadata.noop === true) return false;
  return (
    diagnostic.status === "available" && !isContextOnlyExternalDiagnostic(diagnostic)
  );
}

export function getRepresentativeExternalDiagnostic(
  activity: Pick<Activity, "external_diagnostics">,
): ExternalDiagnostic | null {
  const diagnostics = activity.external_diagnostics ?? [];
  const nonNoopDiagnostics = diagnostics.filter((item) => {
    const metadata = diagnosticMetadata(item);
    return metadata.noop !== true;
  });
  return (
    nonNoopDiagnostics.find((item) => isStrongExternalDiagnostic(item)) ??
    nonNoopDiagnostics.find((item) => item.status === "error") ??
    nonNoopDiagnostics.find((item) => !isContextOnlyExternalDiagnostic(item)) ??
    nonNoopDiagnostics[0] ??
    null
  );
}

export function hasStrongExternalDiagnostic(
  activity: Pick<Activity, "external_diagnostics">,
): boolean {
  return (activity.external_diagnostics ?? []).some((item) =>
    isStrongExternalDiagnostic(item),
  );
}
