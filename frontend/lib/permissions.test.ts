import { describe, expect, it } from "vitest";

import { canChangeItem, canManageOpportunity, canWriteTimeline, type Role } from "./permissions";

const ROLES: (Role | null)[] = ["owner", "editor", "viewer", null];

describe("canManageOpportunity", () => {
  it.each(ROLES)("is owner-only (%s)", (role) => {
    expect(canManageOpportunity(role)).toBe(role === "owner");
  });
});

describe("canWriteTimeline", () => {
  it.each(ROLES)("excludes viewers and strangers (%s)", (role) => {
    expect(canWriteTimeline(role)).toBe(role === "owner" || role === "editor");
  });
});

describe("canChangeItem", () => {
  const me = 7;
  const colleague = 9;

  it("lets the owner change anyone's item", () => {
    expect(canChangeItem({ role: "owner", userId: me, authorId: colleague })).toBe(true);
    expect(canChangeItem({ role: "owner", userId: me, authorId: me })).toBe(true);
  });

  it("lets an editor change only their own", () => {
    expect(canChangeItem({ role: "editor", userId: me, authorId: me })).toBe(true);
    expect(canChangeItem({ role: "editor", userId: me, authorId: colleague })).toBe(false);
  });

  it("refuses a viewer even for their own item", () => {
    expect(canChangeItem({ role: "viewer", userId: me, authorId: me })).toBe(false);
  });

  it("refuses when there is no role at all", () => {
    expect(canChangeItem({ role: null, userId: me, authorId: me })).toBe(false);
    expect(canChangeItem({ role: undefined, userId: me, authorId: me })).toBe(false);
  });

  it("does not treat a missing author as a match for a missing user", () => {
    // A system-generated entry has no author; a signed-out page has no user.
    // Comparing two nulls loosely would hand the buttons to nobody's item.
    expect(canChangeItem({ role: "editor", userId: null, authorId: null })).toBe(false);
    expect(canChangeItem({ role: "editor", userId: undefined, authorId: undefined })).toBe(false);
    expect(canChangeItem({ role: "editor", userId: me, authorId: null })).toBe(false);
  });
});
