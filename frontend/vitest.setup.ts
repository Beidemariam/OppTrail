import "@testing-library/jest-dom/vitest";

// Deterministic time zone (brief §6.5). A non-UTC zone is deliberate: the
// local/UTC conversions in lib/time.ts are exactly where an off-by-an-offset
// bug hides, and a UTC-only run would never see it.
process.env.TZ = "America/New_York";
