"use client";

import { useRef, useState, type FormEvent } from "react";

import {
  emptyOpportunityViewState,
  stages,
  type AiFilterProposal,
  type OpportunityViewState,
} from "../lib/domain";
import { useProposeFilter } from "../lib/queries";
import { useInlineEditor } from "./InlineEdit";

/**
 * A sentence, as a filter you look at before applying it (milestone 6.4).
 *
 * `docs/FEATURES.md` §14 calls this "the safest high-value AI feature here,
 * because its output is a query the user can inspect" — and the whole design
 * is that sentence taken literally:
 *
 * - **Nothing is applied until Apply.** The proposal is drawn as the filters
 *   it would set, in the same words the filter bar uses for them, and Apply
 *   writes the ordinary URL parameters. The AI is the actor in nothing
 *   (ADR 0012).
 * - **What was not understood is shown**, not swallowed. Two sources, and
 *   the second was found by asking the running system rather than a stub:
 *   the server names every key it dropped, *and* the model is asked to
 *   report in the person's own words anything the board cannot express
 *   (**D-186**). Without the second, "Gavin deals closing before December in
 *   EMEA" came back as a search for "Gavin" with no mention of the two
 *   thirds that had vanished.
 * - **Applying replaces the filters rather than merging them.** A proposal
 *   read as a whole sentence should produce the filter that sentence
 *   describes; merging it into whatever was already set would give a result
 *   that matches neither the sentence nor what was on screen.
 *
 * Collapsed behind a trigger, like every control that is not always wanted
 * (D-110): the filter bar is the ordinary way to filter and this is the
 * shortcut for a question that would take four controls.
 */
export function AiFilterBuilder({
  state,
  onApply,
}: {
  state: OpportunityViewState;
  onApply: (next: OpportunityViewState) => void;
}) {
  const [request, setRequest] = useState("");
  const propose = useProposeFilter();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const editor = useInlineEditor(triggerRef, panelRef);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const asked = request.trim();
    if (asked) {
      propose.mutate(asked);
    }
  }

  function apply(proposal: AiFilterProposal) {
    onApply({
      ...emptyOpportunityViewState,
      // The view, the columns and the month are how the reader is *looking*
      // at the board rather than what they are looking at, so a filter
      // proposal leaves them alone.
      view: state.view,
      columns: state.columns,
      month: state.month,
      q: proposal.q ?? "",
      stage: proposal.stage ?? "",
      minValue: proposal.min_value ?? "",
      maxValue: proposal.max_value ?? "",
      stalled: proposal.stalled ? "true" : "",
      sortField: (proposal.sort ??
        emptyOpportunityViewState.sortField) as OpportunityViewState["sortField"],
      sortDirection:
        proposal.direction ?? emptyOpportunityViewState.sortDirection,
    });
    editor.close();
    propose.reset();
    setRequest("");
  }

  return (
    <div className="ai-filter">
      <button
        type="button"
        className="secondary-button"
        ref={triggerRef}
        aria-expanded={editor.editing}
        onClick={editor.editing ? editor.close : editor.open}
      >
        Describe a filter
      </button>

      {editor.editing && (
        <div className="ai-filter-panel" ref={panelRef}>
          <form className="ai-filter-form" onSubmit={submit}>
            <label>
              Describe what you are looking for
              <input
                value={request}
                onChange={(event) => setRequest(event.target.value)}
                placeholder="deals stuck in negotiation over 50k"
                maxLength={300}
              />
            </label>
            <button
              type="submit"
              className="primary-button"
              disabled={propose.isPending}
            >
              {propose.isPending ? "Reading..." : "Suggest"}
            </button>
          </form>

          {propose.isError && <p className="error">{propose.error.message}</p>}

          {propose.data && (
            <div className="ai-filter-proposal">
              {propose.data.empty ? (
                <p className="empty-state">
                  Nothing in that could be turned into a filter this board has.
                  Try naming a stage, an amount, or a word to search for.
                </p>
              ) : (
                <>
                  <p>This would set:</p>
                  <ul>
                    {describe(propose.data.proposal).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
              {propose.data.ignored.length > 0 && (
                <p className="form-hint">
                  Could not express: {propose.data.ignored.join("; ")}.
                </p>
              )}
              {!propose.data.empty && (
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => apply(propose.data.proposal)}
                >
                  Apply
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The proposal in the filter bar's own words.
 *
 * Deliberately not the raw JSON: "stage: Negotiation" is a key and a value,
 * and "Stage is Negotiation" is the thing the reader is about to agree to.
 * The vocabulary matches the controls so the two can be compared — that is
 * what makes the inspection worth doing.
 */
export function describe(proposal: AiFilterProposal): string[] {
  const lines: string[] = [];
  if (proposal.q) {
    lines.push(`Search for "${proposal.q}"`);
  }
  if (
    proposal.stage &&
    stages.includes(proposal.stage as (typeof stages)[number])
  ) {
    lines.push(`Stage is ${proposal.stage}`);
  }
  if (proposal.min_value) {
    lines.push(`Value is at least ${proposal.min_value}`);
  }
  if (proposal.max_value) {
    lines.push(`Value is at most ${proposal.max_value}`);
  }
  if (proposal.stalled) {
    lines.push("Stalled only");
  }
  if (proposal.sort) {
    const direction = proposal.direction === "asc" ? "ascending" : "descending";
    lines.push(`Sorted by ${proposal.sort}, ${direction}`);
  }
  return lines;
}
