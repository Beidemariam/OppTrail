# 0007. SQLite FTS5 over an external-content table

Status: Accepted (v2)

## Context

Keyword search today is four `LIKE '%term%'` predicates plus two correlated `EXISTS`
subqueries across entries, notes and comments (`routes_timeline.py:148-173`). It
cannot use an index, matches substrings inside words, has no ranking, and offers no
snippets.

Benchmarked at the confirmed scale (800,400 rows, Zipf-distributed vocabulary), in
the same sandbox environment and SQLite version as ADR 0001 (3.50.4; see that
ADR's note and D-045 in `docs/autopilot/DECISIONS.md` — the shipped image ships
3.46.1, and the query planner these numbers depend on changed between 3.40 and
3.46, which is why the image no longer runs the older engine):

| Query term | Matches | `LIKE` | FTS5 + bm25 |
|---|---|---|---|
| Very common | 140,644 | 0.1 ms | 121 ms |
| Mid-frequency | 2,302 | 9 ms | 4 ms |
| Rare | 250 | 100 ms | 1 ms |
| No match (full scan) | 0 | **294 ms** | 0.1 ms |

`LIKE` is fast only when matches are dense, because it short-circuits on `LIMIT`.
It is slowest **exactly when a user searches for something specific** — which is
what search is for — and 294 ms against a 300 ms budget leaves no margin. FTS5
inverts the curve.

## Options

1. Keep `LIKE`. Passes budget today by 6 ms, unranked and unhighlightable.
2. **SQLite FTS5** with an external-content virtual table kept in sync by triggers.
3. An external engine (Meilisearch, Typesense, Elasticsearch).

## Decision

**Option 2.** FTS5 is compiled into SQLite, needs no new service, fixes the
worst-case latency shown above, and provides stemming, prefix matching, `bm25()`
ranking and `snippet()` highlighting — the features that make search feel like a
product rather than a filter. Option 3 adds a service to run and sync for a 136 MB
corpus.

Note the honest framing: FTS5 is **not** uniformly faster. It is slower for very
common terms (121 ms vs 0.1 ms) because ranking 140,000 matches costs something.
It is chosen for worst-case latency and for ranking and snippets, not raw speed.

- One `search_index` FTS5 table, **contentless** (`content=''`), storing
  `rowid` → a `(kind, id)` mapping. Contentless matters for size: a
  content-duplicating index measured **+212 MB** over the three source tables,
  against **+13 MB** contentless for the same 80,000 entries. Snippets are then
  produced by re-reading the matched rows, which is cheap for a page of 50.
- Kept current by `AFTER INSERT/UPDATE/DELETE` triggers on `timeline_entries`,
  `notes` and `comments`, including soft-delete transitions.
- Search returns ranked, snippeted results grouped by opportunity, and the timeline
  keyword filter is reimplemented against it.
- A rebuild command exists for corruption or schema change.

## Consequences

- Ties search to SQLite (consistent with ADR 0001).
- Triggers must handle `deleted_at` transitions, or deleted content stays findable.
  This is the main correctness risk and needs an explicit test.
- Ranking makes cross-opportunity global search feasible, which is a Phase 2
  feature the current implementation could not support.
