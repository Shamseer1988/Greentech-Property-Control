import { beforeEach, describe, expect, it } from "vitest";
import { useAuth } from "./auth-store";

function makeUser(overrides: Partial<{ is_super_user: boolean; permissions: string[] }> = {}) {
  return {
    id: 1,
    username: "alice",
    email: "alice@example.com",
    full_name: "Alice",
    is_active: true,
    is_super_user: false,
    roles: [],
    permissions: [],
    ...overrides,
  };
}

describe("auth store", () => {
  beforeEach(() => {
    useAuth.getState().clear();
  });

  it("returns false when no user is signed in", () => {
    expect(useAuth.getState().has("property.view")).toBe(false);
  });

  it("super users pass every permission check", () => {
    useAuth.setState({ user: makeUser({ is_super_user: true, permissions: ["*"] }) });
    expect(useAuth.getState().has("anything.at.all")).toBe(true);
  });

  it("wildcard permission entry grants everything", () => {
    useAuth.setState({ user: makeUser({ permissions: ["*"] }) });
    expect(useAuth.getState().has("user.manage")).toBe(true);
  });

  it("matches an explicit code", () => {
    useAuth.setState({ user: makeUser({ permissions: ["property.view", "landlord.view"] }) });
    expect(useAuth.getState().has("property.view")).toBe(true);
    expect(useAuth.getState().has("landlord.view")).toBe(true);
    expect(useAuth.getState().has("settings.manage")).toBe(false);
  });

  it("setUser stores the profile and unlocks permission checks", () => {
    // Phase 1: tokens live in httpOnly cookies, not the store. The store
    // only holds the user profile we got back from /auth/login.
    useAuth.getState().setUser(makeUser({ permissions: ["property.view"] }));
    const s = useAuth.getState();
    expect(s.user?.username).toBe("alice");
    expect(s.has("property.view")).toBe(true);
    expect(s.has("settings.manage")).toBe(false);
  });
});
