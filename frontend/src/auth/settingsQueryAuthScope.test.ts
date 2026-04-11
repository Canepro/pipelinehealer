import { describe, expect, it } from "vitest";

import {
  getNextAdminKeyScopeId,
  getSettingsQueryAuthScope,
} from "./settingsQueryAuthScope";

describe("settingsQueryAuthScope", () => {
  it("separates session auth from admin-key auth without exposing the raw key", () => {
    const adminSecret = "super-secret-admin-key";

    const adminScope = getSettingsQueryAuthScope({
      useSessionAuth: false,
      adminKey: adminSecret,
      adminKeyScopeId: 3,
    });
    const sessionScope = getSettingsQueryAuthScope({
      useSessionAuth: true,
      adminKey: adminSecret,
      adminKeyScopeId: 3,
    });

    expect(adminScope).toBe("admin-key:3");
    expect(sessionScope).toBe("session-auth");
    expect(adminScope).not.toContain(adminSecret);
    expect(sessionScope).not.toContain(adminSecret);
  });

  it("increments the opaque admin-key scope id for each loaded key", () => {
    expect(getNextAdminKeyScopeId(null)).toBe(1);
    expect(getNextAdminKeyScopeId(1)).toBe(2);
    expect(getNextAdminKeyScopeId(7)).toBe(8);
  });
});
