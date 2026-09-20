"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

/**
 * The dialog shell the command palette and the shortcut reference share
 * (milestone 2.4a; Radix underneath it from 2.5).
 *
 * Radix's `Dialog` owns what every dialog needs and this app used to hand-roll
 * — the portal, the focus trap, `role="dialog"` with `aria-modal`, and hiding
 * the rest of the page from assistive technology (`docs/DESIGN-SYSTEM.md`).
 * Two behaviours are still ours, because they are this app's rules rather than
 * the primitive's:
 *
 * - **Esc stops here.** The board is mounted behind the palette and binds Esc
 *   itself (`lib/keyboard.ts`), so the keystroke is answered on the dialog and
 *   not allowed to reach the document.
 * - **Focus returns when you dismiss, not when the dialog unmounts** (D-066).
 *   Esc, the backdrop and the Close button hand focus back to the control the
 *   dialog was opened from. A dialog that closes because something it did
 *   moved the page — the palette jumping to an opportunity — lets focus fall
 *   to the document, so the next Tab starts at the top of the screen the
 *   reader is now on rather than on the one they left.
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
  const openedFrom = useRef<Element | null>(null);
  const dismissed = useRef(false);

  useEffect(() => {
    openedFrom.current = document.activeElement;
    return () => {
      const previous = openedFrom.current;
      if (dismissed.current && previous instanceof HTMLElement) {
        previous.focus();
      }
    };
  }, []);

  // Focus return stays this component's job rather than Radix's, because the
  // rule is D-066's: Esc, the backdrop and Close hand focus back, and a close
  // that happened because the dialog moved the page does not. The restore runs
  // in the unmount cleanup rather than here so that it is the last word —
  // Radix's focus guards are still on the page while `onClose` is running, and
  // whatever focuses first loses.
  function dismiss() {
    dismissed.current = true;
    onClose();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      dismiss();
    }
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && dismiss()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop" />
        <Dialog.Content
          className="modal"
          onKeyDown={onKeyDown}
          // Radix would otherwise focus something of its own choosing as the
          // dialog goes away, on top of `dismiss` above.
          onCloseAutoFocus={(event) => event.preventDefault()}
          // The palette describes itself through its own labelled controls;
          // without this Radix warns about a missing description.
          aria-describedby={undefined}
        >
          {title ? (
            <div className="section-heading">
              <Dialog.Title asChild>
                <h2>{title}</h2>
              </Dialog.Title>
              <Dialog.Close asChild>
                <button type="button" className="secondary-button">
                  Close
                </button>
              </Dialog.Close>
            </div>
          ) : (
            <Dialog.Title className="visually-hidden">{label}</Dialog.Title>
          )}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
