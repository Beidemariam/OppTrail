"use client";

import { useRef, useState } from "react";
import { Outlet, useMatch, useNavigate, useSearchParams } from "react-router";

import { confirmDelete } from "../lib/confirm";
import {
  applyOpportunityView,
  boardOrder,
  emptyOpportunityViewState,
  type Opportunity,
  type OpportunityViewState,
} from "../lib/domain";
import { useKeyboardShortcuts } from "../lib/keyboard";
import {
  useDeleteOpportunity,
  useOpportunities,
  useSession,
} from "../lib/queries";
import { paramsWithState, stateFromParams } from "../lib/viewState";
import { AuthPanel } from "./AuthPanel";
import { OpportunityFilterBar } from "./OpportunityFilterBar";
import { OpportunityForm } from "./OpportunityForm";
import { SavedViewsMenu } from "./SavedViewsMenu";
import { StageBoard } from "./StageBoard";
import { TopBar } from "./TopBar";

/**
 * The dashboard: the session gate, the stage board, and the panel beside it.
 *
 * It is the layout route for `/` and `/opportunities/:opportunityId`
 * (`AppRoot.tsx`), so the board stays mounted while the child route swaps the
 * panel. That is what gives an opportunity its own URL without reloading the
 * list behind it.
 */
export function DashboardPage() {
  const session = useSession();
  const opportunities = useOpportunities(Boolean(session.data));
  const [editing, setEditing] = useState<Opportunity | null>(null);
  // The keyboard's cursor over the board (milestone 2.4a). Separate from
  // `selectedId`, which is the opportunity whose timeline is open: `j` and `k`
  // walk the cards without opening anything.
  const [focusedId, setFocusedId] = useState<number | null>(null);
  const newOpportunityRef = useRef<HTMLInputElement>(null);
  const keywordFilterRef = useRef<HTMLInputElement>(null);
  const deleteOpportunity = useDeleteOpportunity();
  const navigate = useNavigate();
  // Read from the URL rather than `useParams`, which in a layout route only
  // sees the segments its own path matched.
  const opened = useMatch("/opportunities/:opportunityId");
  const selectedId = opened ? Number(opened.params.opportunityId) : null;

  // The board's filter/sort state lives in the URL too (milestone 2.2), the
  // same way the timeline's does.
  const [searchParams, setSearchParams] = useSearchParams();
  const viewState = stateFromParams<OpportunityViewState>(
    searchParams,
    emptyOpportunityViewState,
    "opportunities",
  );
  function setViewState(next: OpportunityViewState) {
    setSearchParams(
      paramsWithState(
        searchParams,
        next,
        emptyOpportunityViewState,
        "opportunities",
      ),
    );
  }
  const visibleOpportunities = applyOpportunityView(
    opportunities.data ?? [],
    viewState,
  );
  // Column by column, which is the order the cards are read in.
  const ordered = boardOrder(visibleOpportunities);

  function moveFocus(step: number) {
    if (ordered.length === 0) {
      return;
    }
    const current = ordered.findIndex(
      (opportunity) => opportunity.id === focusedId,
    );
    // From nothing, `j` starts at the first card and `k` at the last.
    const next =
      current === -1
        ? step > 0
          ? 0
          : ordered.length - 1
        : Math.min(Math.max(current + step, 0), ordered.length - 1);
    setFocusedId(ordered[next].id);
  }

  function clearFocus() {
    setFocusedId(null);
    const active = document.activeElement;
    if (active instanceof HTMLElement && active.matches(".opportunity-card")) {
      active.blur();
    }
  }

  // The board's half of the keyboard map. `c` is bound only while no timeline
  // is open, because the open timeline binds it to its own composer
  // (`OpportunityPanel`) — "create the thing this screen is about".
  useKeyboardShortcuts(
    session.data
      ? {
          j: () => moveFocus(1),
          k: () => moveFocus(-1),
          e: () => {
            const focused = ordered.find(
              (opportunity) => opportunity.id === focusedId,
            );
            if (focused?.current_user_role === "owner") {
              setEditing(focused);
            }
          },
          "/": () => keywordFilterRef.current?.focus(),
          Escape: clearFocus,
          ...(selectedId === null
            ? { c: () => newOpportunityRef.current?.focus() }
            : {}),
        }
      : {},
  );

  if (session.isPending) {
    return (
      <main className="app-shell">
        <p className="status">Loading...</p>
      </main>
    );
  }

  if (!session.data) {
    return <AuthPanel />;
  }

  function remove(opportunity: Opportunity) {
    if (!confirmDelete(`"${opportunity.name}" and its entire timeline`)) {
      return;
    }

    deleteOpportunity.mutate(opportunity.id, {
      onSuccess: () => {
        if (editing?.id === opportunity.id) {
          setEditing(null);
        }
        if (selectedId === opportunity.id) {
          navigate("/", { replace: true });
        }
      },
    });
  }

  return (
    <main className="app-shell">
      <TopBar user={session.data} />

      <section className="dashboard-layout">
        {/* Re-keyed so switching which opportunity is being edited reloads the
            fields, and finishing an edit empties them. */}
        <OpportunityForm
          key={editing?.id ?? "new"}
          editing={editing}
          nameRef={newOpportunityRef}
          onDone={() => setEditing(null)}
        />

        <section className="workspace">
          {opportunities.isError && (
            <p className="error">{opportunities.error.message}</p>
          )}
          {deleteOpportunity.isError && (
            <p className="error">{deleteOpportunity.error.message}</p>
          )}

          <SavedViewsMenu
            entity="opportunities"
            state={viewState}
            defaults={emptyOpportunityViewState}
            onApply={setViewState}
          />
          <OpportunityFilterBar
            state={viewState}
            keywordRef={keywordFilterRef}
            onApply={setViewState}
          />

          <StageBoard
            opportunities={visibleOpportunities}
            selectedId={selectedId}
            focusedId={focusedId}
            onFocus={(opportunity) => setFocusedId(opportunity.id)}
            onEdit={setEditing}
            onDelete={remove}
          />

          <Outlet />
        </section>
      </section>
    </main>
  );
}

/** The panel at `/`, before an opportunity has been opened. */
export function NoOpportunitySelected() {
  return (
    <section className="timeline-panel empty-panel">
      <h2>Select an opportunity to open its timeline.</h2>
    </section>
  );
}
