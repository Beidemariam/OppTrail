import { render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoot } from "./AppRoot";
import Page, { generateStaticParams } from "./[[...slug]]/page";
import { ALEX, FakeApi, aSearchResult } from "./test-api";

function start(path: string) {
  const api = new FakeApi({
    user: ALEX,
    searchResults: [aSearchResult({ title: "Proposal sent" })],
  });
  api.install();
  window.history.pushState({}, "", path);
  return render(<AppRoot />);
}

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  window.history.pushState({}, "", "/");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("app routing", () => {
  it("serves the dashboard at the root", async () => {
    start("/");

    expect(
      await screen.findByRole("heading", { name: "Opportunities" }),
    ).toBeInTheDocument();
  });

  it("serves the search page at /search, with the query from the URL", async () => {
    start("/search?q=finance");

    expect(
      await screen.findByRole("heading", { name: "Search" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Proposal sent")).toBeInTheDocument();
  });

  it("sends a path nothing renders back to the dashboard", async () => {
    start("/opportunities/10/board");

    expect(
      await screen.findByRole("heading", { name: "Opportunities" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("exports exactly one HTML file for the whole app", () => {
    // Every route above is served by that one file (ADR 0005): Next emits
    // `out/index.html` and FastAPI answers any unmatched path with it. A
    // second entry here would emit a second page and split the SPA.
    expect(generateStaticParams()).toEqual([{ slug: [] }]);
    expect(Page().type).toBe(AppRoot);
  });

  it("renders nothing where there is no browser to route in", () => {
    // The static export renders this tree once in Node (`output: "export"`),
    // where `BrowserRouter` has no history to read. The shell it emits is what
    // FastAPI serves for every deep link, so this has to stay empty and quiet.
    expect(renderToStaticMarkup(<AppRoot />)).toBe("");
  });

  it("links the dashboard to the search route", async () => {
    start("/");
    await screen.findByRole("heading", { name: "Opportunities" });

    expect(screen.getByRole("link", { name: "Search" })).toHaveAttribute(
      "href",
      "/search",
    );
  });
});
