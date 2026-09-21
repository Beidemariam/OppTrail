"use client";

import { useRef, useState } from "react";
import { Outlet, useMatch, useNavigate, useSearchParams } from "react-router";

import {
  adjacentStage,
  applyOpportunityView,
  emptyOpportunityViewState,
  stages,
  viewOrder,
  type BulkActionResultItem,
  type Opportunity,
  type OpportunityView,
  type Stage,
  type OpportunityViewState,
} from "../lib/domain";
import { useKeyboardShortcuts } from "../lib/keyboard";
import {
  useBulkOpportunityAction,
  useChangeOpportunityStage,
  useDeleteOpportunity,
  useOpportunities,
  useRestoreOpportunity,
  useSession,
} from "../lib/queries";
import { paramsWithState, stateFromParams } from "../lib/viewState";
import { AuthPanel } from "./AuthPanel";
import { BulkActionBar } from "./BulkActionBar";
import { useConfirm } from "./ConfirmDialog";
import { Modal } from "./Modal";
import { OpportunityFilterBar } from "./OpportunityFilterBar";
import { OpportunityForm } from "./OpportunityForm";
import { OpportunityList } from "./OpportunityList";
import { SavedViewsMenu } from "./SavedViewsMenu";
import { StageBoard } from "./StageBoard";
import { useToasts, useUndoableDelete } from "./Toasts";
import { TopBar } from "./TopBar";
import { ViewSwitcher } from "./ViewSwitcher";

/**
 * The dashboard: the session gate, one filtered set of opportunities drawn as
 * a board or a list, and the timeline panel below it.
 *
 * It is the layout route for `/` and `/opportunities/:opportunityId`
 * (`AppRoot.tsx`), so the views stay mounted while the child route swaps the
 * panel. That is what gives an opportunity its own URL without reloading the
 * list behind it.
 *
 * Both views are renderers over the same already-filtered array and share
 * every piece of state around them — the cursor, the selection, the filters —
 * so switching between them is a URL change and nothing else (milestone 2.7).
 * The one write they share is `moveToStage`: a drag, the move-to-stage select
 * and the `[`/`]` chords all land on it.
 */
export function DashboardPage() {
  const session = useSession();
  const opportunities = useOpportunities(Boolean(session.data));
  // The create/edit form is a dialog (D-079): `editing` is which opportunity
  // it is editing, `composing` is that same dialog opened empty.
  const [editing, setEditing] = useState<Opportunity | null>(null);
  const [composing, setComposing] = useState(false);
  // What a stage change just did, for a reader who cannot see the card move.
  const [announcement, setAnnouncement] = useState("");
  // The keyboard's cursor over the board (milestone 2.4a). Separate from
  // `selectedId`, which is the opportunity whose timeline is open: `j` and `k`
  // walk the cards without opening anything.
  const [focusedId, setFocusedId] = useState<number | null>(null);
  // Whether the column should scroll the focused card into view. True only
  // while the cursor is being moved by the keyboard: `j` can land on a card
  // that windowing has not mounted, so the list has to go and get it
  // (`app/VirtualList.tsx`). A card focused by a click is already under the
  // reader's pointer, and scrolling it then moves the control out from under
  // the click that focused it (D-072).
  const [followCursor, setFollowCursor] = useState(false);
  // The bulk-selection set (milestone 2.4c), separate again from both of the
  // above — a card can be focused, opened and checked independently.
  // `selectionAnchorId` is where a shift-click range starts, tracked on its
  // own rather than reused from `focusedId` so a range never depends on
  // which DOM event (focus, then click) happened to land first.
  const [checkedIds, setCheckedIds] = useState<ReadonlySet<number>>(new Set());
  const [selectionAnchorId, setSelectionAnchorId] = useState<number | null>(
    null,
  );
  const confirm = useConfirm();
  const keywordFilterRef = useRef<HTMLInputElement>(null);
  const deleteOpportunity = useDeleteOpportunity();
  const restoreOpportunity = useRestoreOpportunity();
  const removeOpportunity = useUndoableDelete(
    "Opportunity",
    deleteOpportunity,
    restoreOpportunity,
  );
  const changeStage = useChangeOpportunityStage();
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
  // The order this view is read in — column by column on the board, top to
  // bottom in the list — which is what the cursor and a range walk.
  const ordered = viewOrder(visibleOpportunities, viewState.view);
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

  /**
   * The one stage-change path: a card dropped in another column, the
   * move-to-stage select, and the `[`/`]` chords all call this.
   *
   * Optimistic in the cache (`useChangeOpportunityStage`), so the card is in
   * its new column before the request lands and goes back if it fails. The
   * move is also announced, because the reader who used the keyboard to make
   * it may not be watching the card that moved.
   */
  function moveToStage(opportunity: Opportunity, stage: Stage) {
    if (opportunity.stage === stage) {
      return;
    }
    setAnnouncement(`${opportunity.name} moved to ${stage}.`);
    changeStage
      .mutateAsync({ id: opportunity.id, stage })
      .catch((error: Error) => {
        setAnnouncement("");
        showToast({
          message: `Could not move ${opportunity.name} to ${stage}: ${error.message}`,
          tone: "error",
        });
      });
  }

  /** `[` and `]`: the focused opportunity, one stage either way. Owner-only,
   * like every other change to an opportunity's own fields. */
  function nudgeStage(step: 1 | -1) {
    const focused = ordered.find((opportunity) => opportunity.id === focusedId);
    if (!focused || focused.current_user_role !== "owner") {
      return;
    }
    const stage = adjacentStage(focused.stage, step);
    if (stage) {
      moveToStage(focused, stage);
    }
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
    setFollowCursor(true);
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
          "[": () => nudgeStage(-1),
          "]": () => nudgeStage(1),
          Escape: onEscape,
          ...(selectedId === null ? { c: () => setComposing(true) } : {}),
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

  // The one destructive action that still asks first, and the only one that
  // asks the reader to type the name back: it cascades across a whole record,
  // and `docs/UX.md` keeps friction there deliberately. Undo is offered as
  // well, because the restore route puts the cascade back.
  async function remove(opportunity: Opportunity) {
    const confirmed = await confirm({
      title: `Delete ${opportunity.name}?`,
      description:
        "This deletes the opportunity and its entire timeline - every entry, note and comment on it. Undo is offered for ten seconds afterwards.",
      confirmLabel: "Delete opportunity",
      typeToConfirm: opportunity.name,
    });
    if (!confirmed) {
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
  async function bulkDelete() {
    const ids = checkedOpportunities.map((opportunity) => opportunity.id);
    const single = checkedOpportunities.length === 1;
    const confirmed = await confirm({
      title: single
        ? `Delete ${checkedOpportunities[0].name}?`
        : `Delete ${ids.length} opportunities?`,
      description: single
        ? "This deletes the opportunity and its entire timeline. Undo is offered for ten seconds afterwards."
        : `This deletes all ${ids.length} selected opportunities and their entire timelines. Undo is offered for ten seconds afterwards.`,
      confirmLabel: single ? "Delete opportunity" : "Delete opportunities",
      typeToConfirm: single ? checkedOpportunities[0].name : "delete",
    });
    if (!confirmed) {
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

  const total = opportunities.data?.length ?? 0;
  const filteredOut = total - visibleOpportunities.length;
  const viewProps = {
    opportunities: visibleOpportunities,
    selectedId,
    focusedId,
    followCursor,
    checkedIds,
    onFocus: (opportunity: Opportunity) => {
      setFocusedId(opportunity.id);
      setFollowCursor(false);
    },
    onEdit: setEditing,
    onDelete: remove,
    onMoveToStage: moveToStage,
    onToggleChecked: toggleChecked,
    onRangeSelect: rangeSelect,
  };

  function closeForm() {
    setComposing(false);
    setEditing(null);
  }

  return (
    <main className="app-shell">
      <TopBar user={session.data} />

      <section className="workspace">
        <div className="page-header">
          <div>
            <h1>Opportunities</h1>
            <p className="page-subtitle">
              {filteredOut > 0
                ? `${visibleOpportunities.length} of ${total} shown, ${filteredOut} filtered out`
                : `${total} ${total === 1 ? "opportunity" : "opportunities"}`}
            </p>
          </div>
          <div className="page-actions">
            <ViewSwitcher
              view={viewState.view}
              onChange={(view: OpportunityView) =>
                setViewState({ ...viewState, view })
              }
            />
            <button
              type="button"
              className="primary-button"
              onClick={() => setComposing(true)}
            >
              New opportunity
            </button>
          </div>
        </div>

        {opportunities.isError && (
          <p className="error">{opportunities.error.message}</p>
        )}
        {deleteOpportunity.isError && (
          <p className="error">{deleteOpportunity.error.message}</p>
        )}

        <div className="view-controls">
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
        </div>

        {/* The four states this view has, in the order they are reached
            (`docs/DESIGN-SYSTEM.md`): loading, nothing yet, nothing left
            after filtering, and the data itself. The last two are
            deliberately different answers — "there is none" and "you filtered
            it out" need different next actions. */}
        {opportunities.isPending ? (
          <LoadingOpportunities />
        ) : total === 0 ? (
          <section className="onboarding-panel">
            <h2>Track your first opportunity</h2>
            <p>
              An opportunity is one deal: who it is with, what it is worth, and
              every call, email and note that moved it. Create one and its
              timeline starts itself.
            </p>
            <button
              type="button"
              className="primary-button"
              onClick={() => setComposing(true)}
            >
              New opportunity
            </button>
          </section>
        ) : visibleOpportunities.length === 0 ? (
          <section className="onboarding-panel">
            <h2>No opportunities match these filters</h2>
            <p>
              All {total} of them are filtered out by the current view. Clear
              the filters to see them again.
            </p>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setViewState(emptyOpportunityViewState)}
            >
              Clear filters
            </button>
          </section>
        ) : viewState.view === "list" ? (
          <OpportunityList {...viewProps} />
        ) : (
          <StageBoard {...viewProps} />
        )}

        {/* A stage change moves a card the reader may not be looking at, and
            the keyboard paths move one they cannot see at all. */}
        <p className="visually-hidden" role="status">
          {announcement}
        </p>

        <Outlet />
      </section>

      {(composing || editing) && (
        <Modal
          label="Opportunity"
          title={editing ? "Edit opportunity" : "New opportunity"}
          onClose={closeForm}
        >
          {/* Re-keyed so switching which opportunity is being edited reloads
              the fields, and finishing an edit empties them. */}
          <OpportunityForm
            key={editing?.id ?? "new"}
            editing={editing}
            onDone={closeForm}
          />
        </Modal>
      )}
    </main>
  );
}

/** First paint, before the list has arrived: the shape of what is coming,
 * rather than a spinner that makes a dense view feel slower than it is
 * (`docs/DESIGN-SYSTEM.md`). */
function LoadingOpportunities() {
  return (
    <div className="skeleton-view">
      <p className="visually-hidden" role="status">
        Loading opportunities
      </p>
      {[0, 1, 2, 3, 4, 5].map((index) => (
        <div className="skeleton-card" key={index} aria-hidden="true" />
      ))}
    </div>
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
