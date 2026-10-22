import { afterEach, describe, expect, it, vi } from "vitest";

import {
  NAV_STORAGE_KEY,
  isNavActive,
  navItems,
  readNavCollapsed,
  stuckBottom,
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

describe("how far down the sticky chrome reaches", () => {
  it("is where the band rests plus how tall it is", () => {
    // 56px of application bar above it, and a band that has wrapped to three
    // rows: 292.39px is the number CI measured on Linux, where the literal
    // this replaced said 272px (D-219's third iteration).
    expect(stuckBottom("sticky", "56px", 236.390625)).toBeCloseTo(292.390625);
  });

  it("is null when the band is not sticky at all", () => {
    // Below 900px the band is `position: static` and the application bar is
    // the only chrome; null is what makes the CSS fall back to it, replacing
    // a media query that said the same thing.
    expect(stuckBottom("static", "auto", 236)).toBeNull();
    expect(stuckBottom("relative", "56px", 236)).toBeNull();
  });

  it("treats an unresolvable offset as the top of the screen", () => {
    // `top: auto` on a sticky element parses as NaN, and counting the height
    // alone is the safe direction: over-padding is harmless, under-padding is
    // the 2.4.11 failure.
    expect(stuckBottom("sticky", "auto", 120)).toBe(120);
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
