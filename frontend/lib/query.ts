/**
 * The single TanStack Query client for the app (ADR 0005).
 *
 * Server state is cached and invalidated here rather than copied into
 * component state. Every read and write the app makes is declared against this
 * client in `lib/queries.ts`.
 */

import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { isUnauthenticated } from "./api";
import { keys } from "./queries";

/**
 * The single TanStack Query configuration.
 *
 * **A 401 is handled here, once, for every read and every write** (milestone
 * 4.2a, **D-145**). A session can end while the app is open — it expires, or
 * somebody signs in as somebody else in another tab, which rotates the shared
 * cookie by design (`backend/app/auth.py`). Before this, nothing noticed: the
 * session query kept its cached answer, so the screen went on showing a
 * signed-in page while every request failed, and a reader pressing Delete was
 * told "Authentication required" as though the *task* had refused them. The
 * Phase 4 reviewer met exactly that and reported it as a broken delete.
 *
 * Invalidating `keys.session` is the whole fix: `useSession` refetches, gets
 * `null`, and every view already branches on that to show the sign-in panel.
 * One place rather than a check in each hook, because the answer cannot
 * sensibly differ between them — and at the cache level rather than in
 * `apiRequest`, so `lib/api.ts` keeps knowing nothing about the query cache.
 */
function onQueryError(client: QueryClient, error: unknown): void {
  if (!isUnauthenticated(error)) {
    return;
  }
  // Not `refetchQueries`: the session read is what decides whether the app is
  // signed in at all, so it has to be marked stale even if nothing is currently
  // observing it.
  void client.invalidateQueries({ queryKey: keys.session });
}

export function createQueryClient(): QueryClient {
  // The caches have to exist before the client that owns them, and their
  // handlers need the client -- so they close over a binding declared below.
  // Safe because `onError` is only ever called by a request, long after
  // construction.
  const queryCache = new QueryCache({
    onError: (error) => onQueryError(client, error),
  });
  const mutationCache = new MutationCache({
    onError: (error) => onQueryError(client, error),
  });

  const client: QueryClient = new QueryClient({
    queryCache,
    mutationCache,
    defaultOptions: {
      queries: {
        // `apiRequest` throws on every non-2xx, including the 401 an expired
        // session gives and the 422 a bad query gives. Retrying those only
        // delays the message the user needs.
        retry: false,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
    },
  });
  return client;
}
