"use client";

import { useState, useSyncExternalStore } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { DashboardPage, NoOpportunitySelected } from "./DashboardPage";
import { OpportunityPanel } from "./OpportunityPanel";
import { SearchPage } from "./SearchPage";
import { ShortcutsProvider } from "./ShortcutsProvider";
import { ToastProvider } from "./Toasts";
import { createQueryClient } from "../lib/query";

/** Nothing to subscribe to; hoisted so React is not handed a new one to
 * resubscribe to on every render. */
const noSubscription = () => () => {};

/**
 * Every route in the app (ADR 0005). Exported on its own so the tests can
 * mount the real route table inside a `MemoryRouter` rather than a copy of it.
 *
 * The dashboard is a layout route: the board stays mounted and the child route
 * decides which panel sits beside it, which is what gives an opportunity its
 * own URL.
 *
 * `ShortcutsProvider` wraps the table rather than sitting inside a route: the
 * command palette and the keyboard map work on every screen (milestone 2.4a),
 * and the tests mount this component, so they exercise the real one. The same
 * is true of `ToastProvider` (milestone 2.4b): an undo toast outlives the
 * screen that raised it, so deleting the open opportunity and navigating away
 * still leaves a way back.
 */
export function AppRoutes() {
  return (
    <ToastProvider>
      <ShortcutsProvider>
        <Routes>
          <Route path="/search" element={<SearchPage />} />
          <Route path="/" element={<DashboardPage />}>
            <Route index element={<NoOpportunitySelected />} />
            <Route
              path="opportunities/:opportunityId"
              element={<OpportunityPanel />}
            />
          </Route>
          {/* Any other path reached the shell through FastAPI's catch-all
          rather than through a link, so there is nothing to render. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ShortcutsProvider>
    </ToastProvider>
  );
}

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
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
