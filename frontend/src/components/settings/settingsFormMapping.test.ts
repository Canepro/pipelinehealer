import { describe, expect, it } from "vitest";

import type { AppSettings } from "../../api/client";
import { toSettingsForm } from "./types";

const settingsWithProvider = (llmProvider: unknown): AppSettings =>
  ({ llm_provider: llmProvider } as AppSettings);

describe("toSettingsForm", () => {
  it("preserves the configured Azure provider when loading settings", () => {
    expect(toSettingsForm(settingsWithProvider("azure_openai")).llm_provider).toBe(
      "azure_openai",
    );
  });

  it("uses Codex App Server only as the fallback for unknown providers", () => {
    expect(toSettingsForm(settingsWithProvider("legacy_provider")).llm_provider).toBe(
      "codex_app_server",
    );
  });
});
