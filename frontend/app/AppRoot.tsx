"use client";

import { useState, useSyncExternalStore } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { AppShell } from "./AppShell";
import { AutomationsPage } from "./AutomationsPage";
import { ConfirmProvider } from "./ConfirmDialog";
import { DashboardPage } from "./DashboardPage";
import { DensityProvider } from "./Density";
import { OpportunityPanel } from "./OpportunityPanel";
import { SearchPage } from "./SearchPage";
import { ReportsPage } from "./ReportsPage";
import { TasksPage } from "./TasksPage";
import { ShortcutsProvider } from "./ShortcutsProvider";
import { ThemeProvider } from "./Theme";
import { ToastProvider } from "./Toasts";
import { createQueryClient } from "../lib/query";

/** Nothing to subscribe to; hoisted so React is not handed a new one to
 * resubscribe to on every render. */
const noSubscription = () => () => {};

/**
 * Every route in the app (ADR 0005). Exported on its own so the tests can
 * mount the real route table inside a `MemoryRouter` rather than a copy of it.
 *
 * `AppShell` is the layout route every screen sits inside (R.1, decision 4A):
 * it resolves the session once and draws the navigation rail and the
 * application bar around whatever the route renders.
 *
 * A deal is a route of its own rather than a child of the dashboard (R.1,
 * decision 1A). It used to be a panel appended *below* the board, which left
 * the first pixel of the thing the reader had just clicked 888px down a 900px
 * screen, under two filter bars acting on a list they were no longer looking
 * at. The board unmounts now; the view state is in the URL, so going back
 * restores it.
 *
 * `ShortcutsProvider` wraps the table rather than sitting inside a route: the
 * command palette and the keyboard map work on every screen (milestone 2.4a),
 * and the tests mount this component, so they exercise the real one. The same
 * is true of `ToastProvider` (milestone 2.4b): an undo toast outlives the
 * screen that raised it, so deleting the open opportunity and navigating away
 * still leaves a way back.
 *
 * `ThemeProvider` and `ConfirmProvider` wrap the same way for the same reason
 * (milestone 2.5): the theme applies to the sign-in screen as much as to the
 * board, and the confirmation dialog is asked for from three screens.
 * `DensityProvider` joins them (milestone 2.8): its control is offered on the
 * table alone, but what it writes is a root attribute, so the preference has
 * to be resolved and applied above every screen rather than inside the one
 * that offers the choice.
 */
export function AppRoutes() {
  return (
    <ThemeProvider>
      <DensityProvider>
        <ToastProvider>
          <ConfirmProvider>
            <ShortcutsProvider>
              <Routes>
                <Route element={<AppShell />}>
                  <Route path="/" element={<DashboardPage />} />
                  <Route
                    path="/opportunities/:opportunityId"
                    element={<OpportunityPanel />}
                  />
                  <Route path="/search" element={<SearchPage />} />
                  {/* My Tasks is its own screen rather than a panel on the
                      dashboard (milestone 4.1): the question it answers is not
                      about one deal. */}
                  <Route path="/tasks" element={<TasksPage />} />
                  <Route path="/reports" element={<ReportsPage />} />
                  {/* Automations (milestone 6.3). Its own screen for the reason
                      /reports and /tasks are: a rule is about every deal at
                      once, so there is no one deal to hang it off. */}
                  <Route path="/automations" element={<AutomationsPage />} />
                </Route>
                {/* Any other path reached the shell through FastAPI's catch-all
          rather than through a link, so there is nothing to render. */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ShortcutsProvider>
          </ConfirmProvider>
        </ToastProvider>
      </DensityProvider>
    </ThemeProvider>
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
