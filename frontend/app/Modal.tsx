"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The dialog shell the command palette and the shortcut reference share
 * (milestone 2.4a).
 *
 * It owns the three things a keyboard user needs from a dialog and nothing
 * else: focus moves in on open, Tab stays inside, and Esc closes. `Esc` also
 * stops here rather than bubbling on to the document, so the board's own Esc
 * binding does not act on a keystroke the reader aimed at this dialog.
 *
 * Returning focus is part of *dismissing* — Esc, the backdrop, the Close
 * button — not of unmounting. A dialog that closes because something it did
 * moved the page (the palette jumping to an opportunity) calls `onClose`
 * directly, and focus falls to the document so the next Tab starts at the top
 * of the screen the reader is now on rather than on the one they left.
 *
 * Milestone 2.5 replaces the internals with the Radix primitive; keeping both
 * dialogs behind one component is what makes that a one-file change.
 */
export function Modal({
  label,
  title,
  onClose,
  children,
}: {
  label: string;
  /** Rendered as the dialog's heading, with a Close button beside it. */
  title?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const openedFrom = useRef<Element | null>(null);

  useEffect(() => {
    openedFrom.current = document.activeElement;
    const first = dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? dialogRef.current)?.focus();
  }, []);

  function dismiss() {
    const previous = openedFrom.current;
    onClose();
    if (previous instanceof HTMLElement) {
      previous.focus();
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      // The document-level map must not see this one.
      event.stopPropagation();
      dismiss();
      return;
    }

    if (event.key !== "Tab") {
      return;
    }

    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
    );
    if (focusable.length === 0) {
      return;
    }
    const edge = event.shiftKey
      ? focusable[0]
      : focusable[focusable.length - 1];
    if (document.activeElement === edge) {
      event.preventDefault();
      (event.shiftKey ? focusable[focusable.length - 1] : focusable[0]).focus();
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={dismiss}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        ref={dialogRef}
        onKeyDown={onKeyDown}
        // Keeps a click inside the dialog from reaching the backdrop.
        onMouseDown={(event) => event.stopPropagation()}
      >
        {title && (
          <div className="section-heading">
            <h2>{title}</h2>
            <button
              type="button"
              className="secondary-button"
              onClick={dismiss}
            >
              Close
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
