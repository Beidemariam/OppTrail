import { describe, expect, it, vi } from "vitest";

import {
  formatTimestamp,
  localInputToUtc,
  nowDateTimeInput,
  parseTimestamp,
  toDateTimeInput,
  toLocalInput,
} from "./time";

describe("parseTimestamp", () => {
  it("reads the canonical fixed-width UTC format the API returns", () => {
    expect(parseTimestamp("2026-09-06T14:30:00Z").toISOString()).toBe("2026-09-06T14:30:00.000Z");
  });

  it("treats a value with no zone as UTC rather than local", () => {
    // SQLite rows written before the canonical format existed look like this.
    // Reading them as local time would shift the whole timeline by the offset.
    expect(parseTimestamp("2026-09-06 14:30:00").toISOString()).toBe("2026-09-06T14:30:00.000Z");
    expect(parseTimestamp("2026-09-06T14:30:00").toISOString()).toBe("2026-09-06T14:30:00.000Z");
  });

  it("keeps an explicit offset instead of overriding it", () => {
    expect(parseTimestamp("2026-09-06T14:30:00+02:00").toISOString()).toBe(
      "2026-09-06T12:30:00.000Z",
    );
  });
});

describe("toLocalInput", () => {
  it("renders a datetime-local value in the browser's zone", () => {
    // 14:30 UTC is 10:30 in America/New_York during daylight saving time.
    expect(toLocalInput(new Date("2026-09-06T14:30:00Z"))).toBe("2026-09-06T10:30");
  });

  it("follows the zone across a daylight-saving boundary", () => {
    // Five hours behind UTC in January, four in September.
    expect(toLocalInput(new Date("2026-01-06T14:30:00Z"))).toBe("2026-01-06T09:30");
  });
});

describe("round trips", () => {
  it("survives UTC to input and back", () => {
    const stored = "2026-09-06T14:30:00Z";
    expect(localInputToUtc(toDateTimeInput(stored))).toBe(stored);
  });

  it("converts a local input the user typed into UTC", () => {
    expect(localInputToUtc("2026-09-06T10:30")).toBe("2026-09-06T14:30:00Z");
  });
});

describe("nowDateTimeInput", () => {
  it("is the current moment as a local input value", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-06T14:30:00Z"));
    try {
      expect(nowDateTimeInput()).toBe("2026-09-06T10:30");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("formatTimestamp", () => {
  it("shows a stored UTC timestamp in the reader's own zone", () => {
    expect(formatTimestamp("2026-09-06T14:30:00Z")).toBe(
      new Date("2026-09-06T14:30:00Z").toLocaleString(),
    );
    expect(formatTimestamp("2026-09-06T14:30:00Z")).toContain("10:30");
  });
});
