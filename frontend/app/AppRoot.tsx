"use client";

import { useState, useSyncExternalStore } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import Home from "./Home";
import { SearchPage } from "./SearchPage";
import { createQueryClient } from "../lib/query";

/** Nothing to subscribe to; hoisted so React is not handed a new one to
 * resubscribe to on every render. */
const noSubscription = () => () => {};

/**
 * Client router and query cache for the whole app (ADR 0005).
 *
 * The router is mounted only in the browser. This tree is also rendered once
 * at build time by the static export, where `BrowserRouter` has no
 * `window.history` to read; rendering nothing on that pass keeps the export a
 * plain shell and keeps the first client render identical to the emitted HTML,
 * so hydration has nothing to reconcile.
 */
export function AppRoot() {
  const [queryClient] = useState(createQueryClient);
  // The two snapshots differ, which is what makes this read "am I past the
  // export and hydration pass yet".
  const inBrowser = useSyncExternalStore(
    noSubscription,
    () => true,
    () => false,
  );

  if (!inBrowser) {
    return null;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/search" element={<SearchPage />} />
          {/* Any other path reached the shell through FastAPI's catch-all
              rather than through a link, so there is nothing to render. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
