import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SettingToggleField } from "./SettingToggleField";
import { SettingsSectionSwitcher, SwitchField } from "./AdminControlsForm";

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function getSwitchId(markup: string) {
  const match = markup.match(
    /role="switch"[\s\S]*?id=(?:"|')?([^"'> ]+)(?:"|')?/,
  );
  expect(match).not.toBeNull();
  return match?.[1] ?? "";
}

function getSwitchDescribedByIds(markup: string) {
  const match = markup.match(
    /role="switch"[\s\S]*?aria-describedby=(?:"|')?([^"'>]+)(?:"|')?/,
  );
  expect(match).not.toBeNull();
  return (match?.[1] ?? "").split(/\s+/).filter(Boolean);
}

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

    const switchId = getSwitchId(markup);
    const describedByIds = getSwitchDescribedByIds(markup);

    expect(markup).toContain('role="switch"');
    expect(markup).toMatch(
      new RegExp(
        `<label[^>]*for=(?:"|')?${escapeRegex(switchId)}(?:"|')?[^>]*>Retry failed workflows<\\/label>`,
      ),
    );
    expect(describedByIds).toHaveLength(1);
    expect(markup).toMatch(
      new RegExp(
        `<p id=(?:"|')?${escapeRegex(describedByIds[0])}(?:"|')?[^>]*>`,
      ),
    );
  });

  it("associates runtime wiring toggles with one label, descriptive help text, and state text", () => {
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

    const switchId = getSwitchId(markup);
    const describedByIds = getSwitchDescribedByIds(markup);
    const labelsForSwitch = markup.match(
      new RegExp(
        `<label[^>]*for=(?:"|')?${escapeRegex(switchId)}(?:"|')?`,
        "g",
      ),
    );

    expect(markup).toContain('role="switch"');
    expect(labelsForSwitch).toHaveLength(1);
    expect(markup).toMatch(
      new RegExp(
        `<label[^>]*for=(?:"|')?${escapeRegex(switchId)}(?:"|')?[^>]*>Verify webhook signatures<\\/label>`,
      ),
    );
    expect(describedByIds).toHaveLength(2);
    expect(markup).toMatch(
      new RegExp(
        `<p id=(?:"|')?${escapeRegex(describedByIds[0])}(?:"|')?[^>]*>`,
      ),
    );
    expect(markup).toMatch(
      new RegExp(
        `<span id=(?:"|')?${escapeRegex(describedByIds[1])}(?:"|')?[^>]*aria-live="polite"`,
      ),
    );
  });
});
