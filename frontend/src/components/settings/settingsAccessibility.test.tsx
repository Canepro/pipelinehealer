import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SettingToggleField } from "./SettingToggleField";
import { SettingsSectionSwitcher, SwitchField } from "./AdminControlsForm";

describe("Settings accessibility smoke checks", () => {
  it("renders the section switcher as a labelled pressed-button navigation control", () => {
    const markup = renderToStaticMarkup(
      <SettingsSectionSwitcher
        activeSection="security"
        onChange={() => undefined}
      />,
    );

    expect(markup).toContain('aria-label="Settings sections"');
    expect(markup).toContain('id="settings-section-trigger-security"');
    expect(markup).toContain('aria-pressed="true"');
  });

  it("associates admin switch labels and descriptions with the switch control", () => {
    const markup = renderToStaticMarkup(
      <SwitchField
        label="Retry failed workflows"
        field="auto_retry_workflow"
        checked
        onChange={() => undefined}
      />,
    );

    expect(markup).toContain('role="switch"');
    expect(markup).toMatch(
      /role="switch"[\s\S]*id=(?:"|')?([^"'> ]+)(?:"|')?[\s\S]*<label[^>]*for=(?:"|')?\1(?:"|')?[^>]*>Retry failed workflows<\/label>/,
    );
    expect(markup).toMatch(
      /role="switch"[\s\S]*aria-describedby=(?:"|')?([^"'> ]+)(?:"|')?[\s\S]*<p id=(?:"|')?\1(?:"|')?[\s\S]*Allows PipelineHealer to trigger retry of failed workflow jobs/,
    );
  });

  it("associates runtime wiring toggles with the switch control and visible state label", () => {
    const markup = renderToStaticMarkup(
      <SettingToggleField
        label="Verify webhook signatures"
        description="Keep this enabled in production."
        checked
        checkedLabel="Required"
        uncheckedLabel="Disabled"
        badgeLabel="Runtime"
        onChange={() => undefined}
      />,
    );

    expect(markup).toContain('role="switch"');
    expect(markup).toMatch(
      /<label[^>]*for=(?:"|')?([^"'> ]+)(?:"|')?[^>]*>Verify webhook signatures<\/label>[\s\S]*role="switch"[\s\S]*id=(?:"|')?\1(?:"|')?/,
    );
    expect(markup).toMatch(
      /<label[^>]*for=(?:"|')?([^"'> ]+)(?:"|')?[^>]*>Required<\/label>[\s\S]*$/,
    );
  });
});
