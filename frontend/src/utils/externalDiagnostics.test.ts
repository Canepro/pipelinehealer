import { describe, expect, it } from "vitest";

import type { Activity } from "../api/client";
import {
  getRepresentativeExternalDiagnostic,
  hasStrongExternalDiagnostic,
  isContextOnlyExternalDiagnostic,
  isStrongExternalDiagnostic,
} from "./externalDiagnostics";

type ExternalDiagnostic = NonNullable<Activity["external_diagnostics"]>[number];

function diagnostic(
  overrides: Partial<ExternalDiagnostic> = {},
): ExternalDiagnostic {
  return {
    source: "jenkins-bridge",
    status: "available",
    summary: "summary",
    confidence_delta: 0,
    metadata: {},
    collected_at: "2026-03-12T00:00:00Z",
    ...overrides,
  };
}

function activity(
  diagnostics: ExternalDiagnostic[],
): Pick<Activity, "external_diagnostics"> {
  return { external_diagnostics: diagnostics };
}

describe("externalDiagnostics helpers", () => {
  it("treats summary-only bridge diagnostics as context instead of strong signals", () => {
    const summaryOnly = diagnostic({
      metadata: { display_state: "context_only" },
    });

    expect(isContextOnlyExternalDiagnostic(summaryOnly)).toBe(true);
    expect(isStrongExternalDiagnostic(summaryOnly)).toBe(false);
    expect(hasStrongExternalDiagnostic(activity([summaryOnly]))).toBe(false);
  });

  it("prefers a strong available diagnostic over bridge-only context", () => {
    const summaryOnly = diagnostic({
      metadata: { display_state: "context_only" },
      url: "https://jenkins.example/context",
    });
    const strongSignal = diagnostic({
      source: "github-actions",
      summary: "real signal",
      url: "https://github.example/run",
    });

    expect(
      getRepresentativeExternalDiagnostic(activity([summaryOnly, strongSignal])),
    ).toBe(strongSignal);
  });

  it("falls back to errors before summary-only context when no strong signal exists", () => {
    const summaryOnly = diagnostic({
      metadata: { display_state: "context_only" },
    });
    const errorDiagnostic = diagnostic({
      source: "sentry",
      status: "error",
      summary: "sentry fetch failed",
    });
    const noopAvailable = diagnostic({
      source: "noop-source",
      metadata: { noop: true },
    });

    expect(
      getRepresentativeExternalDiagnostic(
        activity([noopAvailable, summaryOnly, errorDiagnostic]),
      ),
    ).toBe(errorDiagnostic);
  });
});
