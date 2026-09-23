"use client";

import { useEffect, useRef, type ChangeEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";

import type { Opportunity } from "../lib/domain";

/**
 * What a board card and a list row share (milestone 2.7): the keyboard
 * cursor, Enter to open, and the bulk-selection checkbox.
 *
 * The two views draw an opportunity differently but behave identically, and
 * when that behaviour was written twice it is exactly the kind of pair that
 * drifts — `j` landing on a row that does not take focus, or shift-click
 * selecting a range on the board and one item in the list. One hook, two
 * renderers.
 */
export function useOpportunityItem({
  className,
  opportunity,
  selected,
  focused,
  checked,
  onFocus,
  onToggleChecked,
  onRangeSelect,
}: {
  /** The view's own class for one item: `opportunity-card`,
   * `opportunity-row`, `opportunity-table-row`, `opportunity-chip`. The
   * shared `opportunity-item` class and the state classes below are appended
   * to it. */
  className: string;
  opportunity: Opportunity;
  selected: boolean;
  focused: boolean;
  checked: boolean;
  onFocus: (opportunity: Opportunity) => void;
  onToggleChecked: (opportunity: Opportunity) => void;
  onRangeSelect: (opportunity: Opportunity) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const item = ref.current;
    // Guarded on `contains`, not on equality: once the reader has tabbed to a
    // control inside the focused item, taking focus back to the item itself
    // would trap them.
    if (focused && item && !item.contains(document.activeElement)) {
      item.focus();
    }
  }, [focused]);

  // Enter opens the opportunity the cursor is on. Bound here rather than in
  // the document-level map because the item is what has focus, and a global
  // Enter binding would swallow every button press on the page.
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Enter" && event.target === ref.current) {
      event.preventDefault();
      navigate(`/opportunities/${opportunity.id}`);
    }
  }

  // Shift-click extends the selection from the last-touched item rather than
  // toggling this one (`docs/UX.md`: "checkbox, x, or shift-click range").
  // Read off `onChange` rather than `onClick` and a `preventDefault`: the
  // checkbox is fully controlled by `checked`, so whichever ids the parent
  // decides belong in the selection are what render checked on the next pass
  // regardless of what the browser's own click toggled first.
  function onCheckboxChange(event: ChangeEvent<HTMLInputElement>) {
    if ((event.nativeEvent as MouseEvent).shiftKey) {
      onRangeSelect(opportunity);
    } else {
      onToggleChecked(opportunity);
    }
  }

  return {
    itemProps: {
      ref,
      tabIndex: -1,
      onKeyDown,
      onFocus: () => onFocus(opportunity),
      className: [
        // Every view's item carries this as well as its own class: it is how
        // anything outside the item recognises one without knowing which view
        // drew it (`DashboardPage`'s Esc, which blurs whatever the cursor is
        // on).
        "opportunity-item",
        className,
        selected ? "selected" : "",
        focused ? "focused" : "",
        checked ? "checked" : "",
      ]
        .filter(Boolean)
        .join(" "),
    },
    checkboxProps: {
      type: "checkbox" as const,
      "aria-label": `Select ${opportunity.name} for bulk actions`,
      checked,
      onChange: onCheckboxChange,
    },
  };
}
