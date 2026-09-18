"use client";

import { FormEvent } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";

import type { components } from "../lib/api-types";
import { apiRequest } from "../lib/api";
import { snippetSegments } from "../lib/snippet";
import { formatTimestamp } from "../lib/time";

type AuthResponse = components["schemas"]["AuthResponse"];
type SearchResult = components["schemas"]["SearchResultPublic"];
type SearchResultPage = components["schemas"]["Page_SearchResultPublic_"];

const PAGE_SIZE = 20;

const kindLabels: Record<SearchResult["kind"], string> = {
  entry: "Entry",
  note: "Note",
  comment: "Comment",
};

function searchPath(query: string, cursor: string | null): string {
  const params = new URLSearchParams({ q: query, limit: String(PAGE_SIZE) });
  if (cursor) {
    params.set("cursor", cursor);
  }
  return `/api/v2/search?${params.toString()}`;
}

/**
 * Ranked keyword search across every opportunity the signed-in user can read
 * (`GET /api/v2/search`, ADR 0007).
 *
 * The query lives in the URL, which is the point of introducing the router:
 * a search is linkable, and the back button walks the searches you ran.
 */
export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = (searchParams.get("q") ?? "").trim();

  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => apiRequest<AuthResponse>("/api/auth/me"),
  });

  const results = useInfiniteQuery({
    queryKey: ["search", query],
    enabled: query !== "" && session.data !== undefined,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      apiRequest<SearchResultPage>(searchPath(query, pageParam)),
    getNextPageParam: (lastPage: SearchResultPage) =>
      lastPage.next_cursor ?? null,
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const typed = String(new FormData(event.currentTarget).get("q") ?? "");
    setSearchParams(typed.trim() ? { q: typed.trim() } : {});
  }

  if (session.isPending) {
    return (
      <main className="app-shell">
        <p className="status">Loading...</p>
      </main>
    );
  }

  if (session.isError) {
    return (
      <main className="app-shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">OppTrail</p>
            <h1>Search</h1>
          </div>
        </header>
        <p className="empty-state">
          <Link to="/">Sign in</Link> to search your opportunities.
        </p>
      </main>
    );
  }

  const matches = results.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OppTrail</p>
          <h1>Search</h1>
        </div>
        <div className="user-block">
          <span>{session.data.user.name}</span>
          <Link className="secondary-button" to="/">
            Opportunities
          </Link>
        </div>
      </header>

      <form className="form search-form" onSubmit={submit}>
        <label>
          Search
          {/* Uncontrolled, re-keyed on the URL: the address bar owns the
              query, so the box follows the back button without a second
              copy of the same string in component state. */}
          <input
            key={query}
            name="q"
            defaultValue={query}
            placeholder="A word from an entry, note or comment"
          />
        </label>
        <button className="primary-button" type="submit">
          Search
        </button>
      </form>

      <section className="search-results" aria-label="Search results">
        {query === "" && (
          <p className="empty-state">
            Search entries, notes and comments across every opportunity you can
            read.
          </p>
        )}

        {query !== "" && results.isPending && (
          <p className="status" role="status">
            Searching...
          </p>
        )}

        {results.isError && (
          <p className="error" role="status">
            {results.error.message}
          </p>
        )}

        {results.isSuccess && matches.length === 0 && (
          <p className="empty-state">No matches for &ldquo;{query}&rdquo;.</p>
        )}

        {matches.map((match) => (
          <article className="search-result" key={`${match.kind}-${match.id}`}>
            <div className="search-result-header">
              <h2>{match.opportunity_name}</h2>
              <span className="search-kind">{kindLabels[match.kind]}</span>
            </div>
            {match.title && (
              <p className="search-result-title">{match.title}</p>
            )}
            <p className="search-snippet">
              {snippetSegments(match.snippet).map((segment, index) =>
                segment.match ? (
                  <mark key={index}>{segment.text}</mark>
                ) : (
                  <span key={index}>{segment.text}</span>
                ),
              )}
            </p>
            <p className="search-result-meta">
              {match.author_name ?? "OppTrail"} &middot;{" "}
              {formatTimestamp(match.timestamp)}
            </p>
          </article>
        ))}

        {results.hasNextPage && (
          <button
            className="secondary-button"
            type="button"
            disabled={results.isFetchingNextPage}
            onClick={() => void results.fetchNextPage()}
          >
            {results.isFetchingNextPage ? "Loading..." : "Load more results"}
          </button>
        )}
      </section>
    </main>
  );
}
