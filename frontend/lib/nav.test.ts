import { afterEach, describe, expect, it, vi } from "vitest";

import {
  NAV_STORAGE_KEY,
  isNavActive,
  navItems,
  readNavCollapsed,
  writeNavCollapsed,
} from "./nav";

describe("the five destinations", () => {
  it("names every screen the app has, once", () => {
    expect(navItems.map((item) => item.path)).toEqual([
      "/",
      "/tasks",
      "/reports",
      "/automations",
      "/search",
    ]);
  });
});

describe("which destination a path belongs to", () => {
  it("lights Opportunities on the board", () => {
    expect(isNavActive("/", "/")).toBe(true);
  });

  it("lights Opportunities on a deal, which is its own page since R.1", () => {
    // An exact match on "/" would leave the rail saying the reader is nowhere,
    // on the screen they spend the most time in.
    expect(isNavActive("/", "/opportunities/7")).toBe(true);
  });

  it("does not light Opportunities on another screen", () => {
    expect(isNavActive("/", "/reports")).toBe(false);
    expect(isNavActive("/", "/tasks")).toBe(false);
  });

  it("matches a section and anything under it", () => {
    expect(isNavActive("/reports", "/reports")).toBe(true);
    expect(isNavActive("/reports", "/reports/pipeline")).toBe(true);
  });

  it("does not match a path that merely starts with the same letters", () => {
    expect(isNavActive("/tasks", "/tasksheet")).toBe(false);
  });
});

describe("the collapsed preference", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("is expanded until somebody collapses it", () => {
    expect(readNavCollapsed()).toBe(false);
  });

  it("survives a reload, which is what makes it a preference", () => {
    writeNavCollapsed(true);
    expect(window.localStorage.getItem(NAV_STORAGE_KEY)).toBe("collapsed");
    expect(readNavCollapsed()).toBe(true);

    writeNavCollapsed(false);
    expect(readNavCollapsed()).toBe(false);
  });

  it("still applies for this page load when storage refuses", () => {
    // Safari in private mode throws on access, not only on write.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });

    expect(readNavCollapsed()).toBe(false);
    expect(() => writeNavCollapsed(true)).not.toThrow();
  });
});
