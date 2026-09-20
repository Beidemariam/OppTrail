"use client";

import { useRef, useState } from "react";
import { Outlet, useMatch, useNavigate, useSearchParams } from "react-router";

import { confirmDelete } from "../lib/confirm";
import {
  applyOpportunityView,
  boardOrder,
  emptyOpportunityViewState,
  stages,
  type BulkActionResultItem,
  type Opportunity,
  type OpportunityViewState,
} from "../lib/domain";
import { useKeyboardShortcuts } from "../lib/keyboard";
import {
  useBulkOpportunityAction,
  useDeleteOpportunity,
  useOpportunities,
  useRestoreOpportunity,
  useSession,
} from "../lib/queries";
import { paramsWithState, stateFromParams } from "../lib/viewState";
import { AuthPanel } from "./AuthPanel";
import { BulkActionBar } from "./BulkActionBar";
import { OpportunityFilterBar } from "./OpportunityFilterBar";
import { OpportunityForm } from "./OpportunityForm";
import { SavedViewsMenu } from "./SavedViewsMenu";
import { StageBoard } from "./StageBoard";
import { useToasts, useUndoableDelete } from "./Toasts";
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
  // The bulk-selection set (milestone 2.4c), separate again from both of the
  // above — a card can be focused, opened and checked independently.
  // `selectionAnchorId` is where a shift-click range starts, tracked on its
  // own rather than reused from `focusedId` so a range never depends on
  // which DOM event (focus, then click) happened to land first.
  const [checkedIds, setCheckedIds] = useState<ReadonlySet<number>>(new Set());
  const [selectionAnchorId, setSelectionAnchorId] = useState<number | null>(
    null,
  );
  const newOpportunityRef = useRef<HTMLInputElement>(null);
  const keywordFilterRef = useRef<HTMLInputElement>(null);
  const deleteOpportunity = useDeleteOpportunity();
  const restoreOpportunity = useRestoreOpportunity();
  const removeOpportunity = useUndoableDelete(
    "Opportunity",
    deleteOpportunity,
    restoreOpportunity,
  );
  const bulkAction = useBulkOpportunityAction();
  const bulkRestoreOpportunity = useRestoreOpportunity();
  const showToast = useToasts();
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
  const checkedOpportunities = ordered.filter((opportunity) =>
    checkedIds.has(opportunity.id),
  );

  function toggleChecked(opportunity: Opportunity) {
    setCheckedIds((current) => {
      const next = new Set(current);
      if (next.has(opportunity.id)) {
        next.delete(opportunity.id);
      } else {
        next.add(opportunity.id);
      }
      return next;
    });
    setSelectionAnchorId(opportunity.id);
  }

  // Shift-click / shift-clicking the checkbox extends the selection from the
  // last-touched card to this one, in board order — the range a reader sees
  // between the two clicks (`docs/UX.md`: "checkbox, x, or shift-click
  // range").
  function rangeSelect(opportunity: Opportunity) {
    const anchorId = selectionAnchorId ?? opportunity.id;
    const anchorIndex = ordered.findIndex((item) => item.id === anchorId);
    const targetIndex = ordered.findIndex((item) => item.id === opportunity.id);
    if (anchorIndex === -1 || targetIndex === -1) {
      toggleChecked(opportunity);
      return;
    }
    const [start, end] =
      anchorIndex <= targetIndex
        ? [anchorIndex, targetIndex]
        : [targetIndex, anchorIndex];
    const rangeIds = ordered.slice(start, end + 1).map((item) => item.id);
    setCheckedIds((current) => new Set([...current, ...rangeIds]));
    setSelectionAnchorId(opportunity.id);
  }

  function clearSelection() {
    setCheckedIds(new Set());
    setSelectionAnchorId(null);
  }

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

  // `docs/UX.md`: "Esc: ... or clear the focused card" — clearing a live
  // bulk selection takes priority, the same order the reference screen lists
  // Esc's effects in.
  function onEscape() {
    if (checkedIds.size > 0) {
      clearSelection();
      return;
    }
    clearFocus();
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
          x: () => {
            const focused = ordered.find(
              (opportunity) => opportunity.id === focusedId,
            );
            if (focused) {
              toggleChecked(focused);
            }
          },
          "/": () => keywordFilterRef.current?.focus(),
          Escape: onEscape,
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

  // The one destructive action that still asks first: it cascades across a
  // whole record, and `docs/UX.md` keeps friction there deliberately. Undo is
  // offered as well, because the restore route puts the cascade back.
  function remove(opportunity: Opportunity) {
    if (!confirmDelete(`"${opportunity.name}" and its entire timeline`)) {
      return;
    }

    removeOpportunity(opportunity.id, () => {
      if (editing?.id === opportunity.id) {
        setEditing(null);
      }
      if (selectedId === opportunity.id) {
        navigate("/", { replace: true });
      }
    });
  }

  /**
   * Reports what a bulk action did, and offers Undo over a delete's
   * successes — the four single-item deletes already put the restore in the
   * toast (`app/Toasts.tsx`); this is the same idea over several ids at once
   * rather than a fifth copy of it. Not optimistic (D-071): outcomes are
   * per-item, so nothing here is safe to guess before the response arrives.
   */
  function reportBulkOutcome(
    verb: "deleted" | "updated",
    results: BulkActionResultItem[],
  ): number[] {
    const okIds = results
      .filter((item) => item.status === "ok")
      .map((item) => item.id);
    const failed = results.filter((item) => item.status === "error");
    const noun = okIds.length === 1 ? "opportunity" : "opportunities";
    let message = `${okIds.length} ${noun} ${verb}.`;
    if (failed.length > 0) {
      message += ` ${failed.length} failed: ${failed
        .map((item) => item.error)
        .join("; ")}`;
    }
    showToast({
      message,
      tone: failed.length > 0 && okIds.length === 0 ? "error" : "info",
      action:
        verb === "deleted" && okIds.length > 0
          ? {
              label: "Undo",
              run: () => {
                Promise.all(
                  okIds.map((id) => bulkRestoreOpportunity.mutateAsync(id)),
                ).catch((error: Error) =>
                  showToast({
                    message: `Could not restore every opportunity: ${error.message}`,
                    tone: "error",
                  }),
                );
              },
            }
          : undefined,
    });
    return okIds;
  }

  function bulkChangeStage(stage: (typeof stages)[number]) {
    const ids = checkedOpportunities.map((opportunity) => opportunity.id);
    bulkAction
      .mutateAsync({ ids, action: "set_stage", stage })
      .then((response) => {
        reportBulkOutcome("updated", response.results);
        clearSelection();
      })
      .catch((error: Error) =>
        showToast({
          message: `Could not change stage: ${error.message}`,
          tone: "error",
        }),
      );
  }

  // Bulk delete keeps the same typed confirmation single-opportunity delete
  // does: it cascades across a whole record, multiplied by however many are
  // selected, which is more reason for the friction rather than less.
  function bulkDelete() {
    const ids = checkedOpportunities.map((opportunity) => opportunity.id);
    const label =
      checkedOpportunities.length === 1
        ? `"${checkedOpportunities[0].name}" and its entire timeline`
        : `${ids.length} opportunities and their entire timelines`;
    if (!confirmDelete(label)) {
      return;
    }
    bulkAction
      .mutateAsync({ ids, action: "delete" })
      .then((response) => {
        const okIds = reportBulkOutcome("deleted", response.results);
        if (editing && okIds.includes(editing.id)) {
          setEditing(null);
        }
        if (selectedId !== null && okIds.includes(selectedId)) {
          navigate("/", { replace: true });
        }
        clearSelection();
      })
      .catch((error: Error) =>
        showToast({
          message: `Could not delete: ${error.message}`,
          tone: "error",
        }),
      );
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
          {/* The action bar replaces the filter bar while a selection is
              live (`docs/UX.md`, milestone 2.4c). */}
          {checkedIds.size > 0 ? (
            <BulkActionBar
              selected={checkedOpportunities}
              onClear={clearSelection}
              onChangeStage={bulkChangeStage}
              onDelete={bulkDelete}
              pending={bulkAction.isPending}
            />
          ) : (
            <OpportunityFilterBar
              state={viewState}
              keywordRef={keywordFilterRef}
              onApply={setViewState}
            />
          )}

          <StageBoard
            opportunities={visibleOpportunities}
            selectedId={selectedId}
            focusedId={focusedId}
            checkedIds={checkedIds}
            onFocus={(opportunity) => setFocusedId(opportunity.id)}
            onEdit={setEditing}
            onDelete={remove}
            onToggleChecked={toggleChecked}
            onRangeSelect={rangeSelect}
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
