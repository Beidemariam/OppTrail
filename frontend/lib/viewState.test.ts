import { describe, expect, it } from "vitest";

import { paramsWithState, stateFromParams } from "./viewState";

interface Filters extends Record<string, string> {
  q: string;
  order: string;
}

const defaults: Filters = { q: "", order: "asc" };

function timelineParams(state: Filters, from = "") {
  return paramsWithState(
    new URLSearchParams(from),
    state,
    defaults,
    "timeline",
  );
}

describe("stateFromParams", () => {
  it("falls back to defaults for anything the URL does not mention", () => {
    const params = new URLSearchParams("timeline.q=budget");
    expect(stateFromParams(params, defaults, "timeline")).toEqual({
      q: "budget",
      order: "asc",
    });
  });

  it("reads every field the URL does mention", () => {
    const params = new URLSearchParams("timeline.q=budget&timeline.order=desc");
    expect(stateFromParams(params, defaults, "timeline")).toEqual({
      q: "budget",
      order: "desc",
    });
  });

  it("ignores another entity's field of the same name", () => {
    const params = new URLSearchParams("opportunities.q=northwind");
    expect(stateFromParams(params, defaults, "timeline")).toEqual(defaults);
  });
});

describe("paramsWithState", () => {
  it("omits fields that still equal their default", () => {
    expect(timelineParams({ q: "budget", order: "asc" }).toString()).toBe(
      "timeline.q=budget",
    );
  });

  it("produces an empty string for a state that is all defaults", () => {
    expect(timelineParams(defaults).toString()).toBe("");
  });

  it("clears a field that has gone back to its default", () => {
    expect(timelineParams(defaults, "timeline.q=budget").toString()).toBe("");
  });

  it("leaves another entity's parameters untouched", () => {
    expect(
      timelineParams(
        { q: "", order: "desc" },
        "opportunities.stage=Proposal",
      ).toString(),
    ).toBe("opportunities.stage=Proposal&timeline.order=desc");
  });

  it("round-trips through stateFromParams", () => {
    const state: Filters = { q: "renewal", order: "desc" };
    expect(
      stateFromParams(timelineParams(state), defaults, "timeline"),
    ).toEqual(state);
  });
});
