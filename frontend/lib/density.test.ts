import { describe, expect, it } from "vitest";

import {
  DENSITY_STORAGE_KEY,
  applyDensity,
  densityLabel,
  readDensity,
  storeDensity,
} from "./density";

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

describe("reading a stored density (milestone 2.8)", () => {
  it("defaults to comfortable, which is what a reader who never chose gets", () => {
    expect(readDensity(memoryStorage())).toBe("comfortable");
    expect(readDensity(undefined)).toBe("comfortable");
  });

  it("returns what was stored", () => {
    expect(
      readDensity(memoryStorage({ [DENSITY_STORAGE_KEY]: "compact" })),
    ).toBe("compact");
  });

  it("ignores a stored value that is not a density", () => {
    // A hand-edited or stale key must not leave the app with no density at
    // all, which would resolve to no size tokens.
    expect(readDensity(memoryStorage({ [DENSITY_STORAGE_KEY]: "tiny" }))).toBe(
      "comfortable",
    );
  });

  it("survives storage that refuses to answer", () => {
    expect(readDensity(refusingStorage())).toBe("comfortable");
    // And a write that throws costs the reader the memory of the choice, not
    // the choice itself.
    expect(() => storeDensity(refusingStorage(), "compact")).not.toThrow();
  });
});

describe("applying it", () => {
  it("writes the one attribute the stylesheet keys the size tokens off", () => {
    const root = document.createElement("html");
    applyDensity(root, "compact");
    expect(root.dataset.density).toBe("compact");
    applyDensity(root, "comfortable");
    expect(root.dataset.density).toBe("comfortable");
  });

  it("remembers the choice", () => {
    const storage = memoryStorage();
    storeDensity(storage, "compact");
    expect(storage.getItem(DENSITY_STORAGE_KEY)).toBe("compact");
  });

  it("names both modes the way the control does", () => {
    expect(densityLabel("comfortable")).toBe("Comfortable");
    expect(densityLabel("compact")).toBe("Compact");
  });
});
