import { describe, expect, it } from "vitest";

import {
  THEME_STORAGE_KEY,
  applyTheme,
  readThemePreference,
  resolveTheme,
  storeThemePreference,
  themeLabel,
} from "./theme";

/** A `Storage` that works, for the ordinary path. */
function memoryStorage(initial: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(initial));
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => void values.delete(key),
    setItem: (key, value) => void values.set(key, value),
  };
}

/** A `Storage` that throws, which is what a locked-down browser gives you. */
function refusingStorage(): Storage {
  return {
    ...memoryStorage(),
    getItem: () => {
      throw new Error("denied");
    },
    setItem: () => {
      throw new Error("denied");
    },
  };
}

describe("resolving a theme preference", () => {
  it("follows the system when the reader has not chosen", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("ignores the system once the reader has", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});

describe("remembering the preference", () => {
  it("round-trips a choice", () => {
    const storage = memoryStorage();
    storeThemePreference(storage, "dark");
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(readThemePreference(storage)).toBe("dark");
  });

  it("falls back to the system for anything it did not write", () => {
    expect(readThemePreference(memoryStorage())).toBe("system");
    expect(
      readThemePreference(memoryStorage({ [THEME_STORAGE_KEY]: "sepia" })),
    ).toBe("system");
    expect(readThemePreference(undefined)).toBe("system");
  });

  it("survives storage that refuses, rather than failing the page", () => {
    expect(readThemePreference(refusingStorage())).toBe("system");
    expect(() => storeThemePreference(refusingStorage(), "dark")).not.toThrow();
  });
});

describe("applying a theme", () => {
  it("writes the attribute the stylesheet keys off, and the colour scheme", () => {
    const root = document.createElement("html");
    applyTheme(root, "dark");
    expect(root.dataset.theme).toBe("dark");
    expect(root.style.colorScheme).toBe("dark");

    applyTheme(root, "light");
    expect(root.dataset.theme).toBe("light");
    expect(root.style.colorScheme).toBe("light");
  });
});

describe("the control's labels", () => {
  it("names each preference", () => {
    expect(themeLabel("system")).toBe("System");
    expect(themeLabel("light")).toBe("Light");
    expect(themeLabel("dark")).toBe("Dark");
  });
});
