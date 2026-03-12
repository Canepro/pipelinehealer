import { describe, expect, it } from "vitest";

import { buildActivitiesDrilldownPath } from "./activityFilters";

describe("buildActivitiesDrilldownPath", () => {
  it("builds a repository drill-down path with preserved owner/repo casing", () => {
    expect(
      buildActivitiesDrilldownPath({ repository: "Canepro/GrafanaLocal" }),
    ).toBe("/app/activities?repository=Canepro%2FGrafanaLocal");
  });

  it("builds a failure-type drill-down path for pie slice navigation", () => {
    expect(
      buildActivitiesDrilldownPath({ failureType: "build_config" }),
    ).toBe("/app/activities?failure_type=build_config");
  });

  it("omits empty filters and combines multiple values in query order", () => {
    expect(
      buildActivitiesDrilldownPath({
        repository: " owner/repo ",
        failureType: "lint",
        status: "",
        focus: "activity-123",
      }),
    ).toBe(
      "/app/activities?repository=owner%2Frepo&failure_type=lint&focus=activity-123",
    );
  });
});
