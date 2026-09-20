import { describe, expect, it } from "vitest";

import { filterCommands, fuzzyMatches, type Command } from "./palette";

const commands: Command[] = [
  {
    id: "a",
    label: "Go to the dashboard",
    hint: "The pipeline board",
    run: () => {},
  },
  {
    id: "b",
    label: "Northwind platform rollout",
    hint: "Northwind Energy",
    run: () => {},
  },
  { id: "c", label: "Sign out", run: () => {} },
];

describe("fuzzyMatches", () => {
  it("matches characters in order rather than as a substring", () => {
    expect(fuzzyMatches("Northwind platform rollout", "nwp")).toBe(true);
    expect(fuzzyMatches("Northwind platform rollout", "pwn")).toBe(false);
  });

  it("ignores case and treats spaces in the query as separators", () => {
    expect(fuzzyMatches("Northwind platform rollout", "NORTH ROLL")).toBe(true);
  });

  it("matches everything when the query is blank", () => {
    expect(fuzzyMatches("anything", "   ")).toBe(true);
  });
});

describe("filterCommands", () => {
  it("searches the hint as well as the label", () => {
    expect(filterCommands(commands, "energy").map((c) => c.id)).toEqual(["b"]);
  });

  it("keeps the declared order", () => {
    expect(filterCommands(commands, "o").map((c) => c.id)).toEqual([
      "a",
      "b",
      "c",
    ]);
  });

  it("can match nothing", () => {
    expect(filterCommands(commands, "zzz")).toEqual([]);
  });
});
