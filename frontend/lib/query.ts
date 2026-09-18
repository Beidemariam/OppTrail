/**
 * The single TanStack Query client for the app (ADR 0005).
 *
 * Server state is cached and invalidated here rather than copied into
 * component state; `app/Home.tsx` still predates this and is migrated in
 * milestone 2.1, when it is decomposed into routed views.
 */

import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
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
}
