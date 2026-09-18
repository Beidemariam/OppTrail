import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SearchPage } from "./SearchPage";
import { ALEX, FakeApi, aSearchResult } from "./test-api";
import { createQueryClient } from "../lib/query";

let api: FakeApi;

function start(
  options: ConstructorParameters<typeof FakeApi>[0] = {},
  path = "/search",
) {
  api = new FakeApi({ user: ALEX, ...options });
  api.install();
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <SearchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function search(term: string) {
  await userEvent.type(screen.getByLabelText("Search"), term);
  await userEvent.click(screen.getByRole("button", { name: "Search" }));
}

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("search page", () => {
  it("invites a search before anything is typed", async () => {
    start();

    expect(
      await screen.findByText(/Search entries, notes and comments/),
    ).toBeInTheDocument();
    expect(api.callsTo("GET", "/api/v2/search")).toHaveLength(0);
  });

  it("searches what was typed and highlights the matched words", async () => {
    start({
      searchResults: [
        aSearchResult({
          opportunity_name: "Globex renewal",
          snippet: {
            text: "They want viewer-only for finance.",
            matches: [{ start: 26, length: 7 }],
          },
        }),
      ],
    });
    await screen.findByText(/Search entries, notes and comments/);

    await search("finance");

    const result = await screen.findByRole("article");
    expect(
      within(result).getByRole("heading", { name: "Globex renewal" }),
    ).toBeInTheDocument();
    expect(within(result).getByText("Note")).toBeInTheDocument();
    expect(result.querySelector("mark")).toHaveTextContent("finance");
    expect(api.callsTo("GET", "/api/v2/search")[0].path).toContain("q=finance");
  });

  it("runs the search a link arrived with", async () => {
    start(
      { searchResults: [aSearchResult({ title: "Proposal sent" })] },
      "/search?q=finance",
    );

    expect(await screen.findByText("Proposal sent")).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toHaveValue("finance");
    expect(screen.getByRole("link", { name: "Opportunities" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("clears the query, and the results with it", async () => {
    start({ searchResults: [aSearchResult()] }, "/search?q=finance");
    await screen.findByRole("article");

    await userEvent.clear(screen.getByLabelText("Search"));
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(
      await screen.findByText(/Search entries, notes and comments/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("names the app as the author of a system-generated match", async () => {
    start(
      {
        searchResults: [
          aSearchResult({ author_id: null, author_name: null, kind: "entry" }),
        ],
      },
      "/search?q=finance",
    );

    expect(await screen.findByText(/OppTrail ·/)).toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    start({ searchResults: [aSearchResult()] }, "/search?q=procurement");

    expect(
      await screen.findByText("No matches for “procurement”."),
    ).toBeInTheDocument();
  });

  it("follows the cursor for the next page of matches", async () => {
    const many = Array.from({ length: 21 }, (_, index) =>
      aSearchResult({
        id: index,
        title: `Match ${index}`,
        snippet: { text: "finance", matches: [] },
      }),
    );
    start({ searchResults: many }, "/search?q=finance");

    await screen.findByText("Match 0");
    expect(screen.queryByText("Match 20")).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Load more results" }),
    );

    expect(await screen.findByText("Match 20")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Load more results" }),
    ).not.toBeInTheDocument();
    expect(api.callsTo("GET", "/api/v2/search")[1].path).toContain("cursor=20");
  });

  it("shows the message a failed search came back with", async () => {
    start(
      {
        failures: { "GET /api/v2/search": [422, "Enter a word to search for"] },
      },
      "/search?q=%22",
    );

    expect(
      await screen.findByText("Enter a word to search for"),
    ).toBeInTheDocument();
  });

  it("asks an unauthenticated visitor to sign in instead of searching", async () => {
    start({ user: null }, "/search?q=finance");

    expect(
      await screen.findByRole("link", { name: "Sign in" }),
    ).toHaveAttribute("href", "/");
    await waitFor(() =>
      expect(api.callsTo("GET", "/api/v2/search")).toHaveLength(0),
    );
  });
});
