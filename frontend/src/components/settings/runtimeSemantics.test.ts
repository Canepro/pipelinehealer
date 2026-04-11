import { describe, expect, it } from "vitest";

import {
  describeLlmHealthFailure,
  describeMcpHealthFailure,
  describeSecretSettingsFailure,
  formatIntegrationQueryState,
} from "./runtimeSemantics";

describe("runtimeSemantics subquery failures", () => {
  it("surfaces explicit secret settings failures with retry guidance", () => {
    expect(describeSecretSettingsFailure(new Error("401 Unauthorized"))).toEqual({
      title: "Secret settings request failed",
      detail: "401 Unauthorized",
      guidance:
        "Check the active auth method and secret backend configuration, then retry.",
    });
  });

  it("falls back to a stable LLM failure message when the error is absent", () => {
    expect(describeLlmHealthFailure()).toEqual({
      title: "LLM health request failed",
      detail: "LLM health request failed.",
      guidance:
        "Check the active auth method and LLM provider health configuration, then retry.",
    });
  });

  it("preserves MCP probe failure detail instead of collapsing to unavailable", () => {
    expect(describeMcpHealthFailure(new Error("gateway timeout"))).toEqual({
      title: "MCP health request failed",
      detail: "gateway timeout",
      guidance:
        "Check the active auth method and MCP provider health configuration, then retry.",
    });
  });

  it("keeps integration probe failures distinct from normal unavailable states", () => {
    expect(
      formatIntegrationQueryState({
        isError: true,
        error: new Error("invalid bearer token"),
      }),
    ).toEqual({
      summary: "Probe failed",
      detail: "invalid bearer token",
      tone: "bad",
    });
  });
});
