"use client";

import * as AlertDialog from "@radix-ui/react-alert-dialog";
import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

/**
 * The one place this app asks "are you sure" (milestone 2.5, replacing the
 * `window.confirm` placeholder `lib/confirm.ts` held).
 *
 * `docs/UX.md` took confirmation off the timeline's destructive actions in
 * 2.4b — they apply and offer Undo — and names the exceptions this dialog
 * still serves:
 *
 * - Deleting an opportunity, and bulk-deleting several, which cascade across
 *   whole records. Those get the **typed** confirmation `docs/UX.md` asks for:
 *   the reader types the name back before the button is live.
 * - Removing someone's access (**D-069**), which has no restore route, so the
 *   question is still worth asking — but not worth typing for, since the
 *   grant can be made again.
 *
 * Radix's `AlertDialog` supplies the focus trap, the `alertdialog` role and
 * the `aria-describedby` wiring (`docs/DESIGN-SYSTEM.md`: "headless primitives
 * from Radix UI ... Writing an accessible combobox, dialog and menu by hand is
 * weeks of work to arrive somewhere worse"). What is ours is the promise: a
 * caller awaits an answer, so the three call sites read the way the
 * `window.confirm` they replace did.
 */

export interface ConfirmRequest {
  /** The question, as a heading. */
  title: string;
  /** What confirming will do, including what cannot be undone. */
  description: string;
  /** The affirmative button's label. Names the action, never "OK". */
  confirmLabel: string;
  /** When set, the reader must type this back before confirming is possible. */
  typeToConfirm?: string;
}

type Confirm = (request: ConfirmRequest) => Promise<boolean>;

const ConfirmContext = createContext<Confirm>(() => Promise.resolve(false));

/**
 * Asks the question and resolves to the answer. Returns the same function for
 * the life of the provider, so it is safe in a dependency list.
 */
export function useConfirm(): Confirm {
  return useContext(ConfirmContext);
}

interface Pending {
  request: ConfirmRequest;
  settle: (confirmed: boolean) => void;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const confirm = useCallback<Confirm>(
    (request) =>
      new Promise<boolean>((resolve) => {
        setPending({ request, settle: resolve });
      }),
    [],
  );

  // Every path out of the dialog comes through here, so the promise is settled
  // exactly once whether the reader confirmed, cancelled, pressed Esc or
  // clicked away.
  const answer = useCallback(
    (confirmed: boolean) => {
      setPending((current) => {
        current?.settle(confirmed);
        return null;
      });
    },
    [setPending],
  );

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <ConfirmBody
          // A fresh request is a fresh dialog: the typed text does not carry
          // over from the last question.
          key={pending.request.title}
          request={pending.request}
          onAnswer={answer}
        />
      )}
    </ConfirmContext.Provider>
  );
}

function ConfirmBody({
  request,
  onAnswer,
}: {
  request: ConfirmRequest;
  onAnswer: (confirmed: boolean) => void;
}) {
  const [typed, setTyped] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const ready =
    request.typeToConfirm === undefined ||
    typed.trim() === request.typeToConfirm.trim();

  // The document-level keyboard map must not also act on this Esc: the board
  // is still mounted behind the dialog, and its Esc clears the selection the
  // reader is asking about (`lib/keyboard.ts`, `app/Modal.tsx`).
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onAnswer(false);
    }
  }

  return (
    <AlertDialog.Root open onOpenChange={(open) => !open && onAnswer(false)}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="modal-backdrop" />
        <AlertDialog.Content
          className="modal confirm-dialog"
          onKeyDown={onKeyDown}
          // Radix focuses the cancel button; when there is something to type,
          // the field is where the reader has to go next.
          onOpenAutoFocus={(event) => {
            if (request.typeToConfirm !== undefined) {
              event.preventDefault();
              inputRef.current?.focus();
            }
          }}
        >
          <AlertDialog.Title>{request.title}</AlertDialog.Title>
          <AlertDialog.Description className="status">
            {request.description}
          </AlertDialog.Description>

          {request.typeToConfirm !== undefined && (
            <label className="confirm-field">
              Type <strong>{request.typeToConfirm}</strong> to confirm
              <input
                ref={inputRef}
                type="text"
                value={typed}
                autoComplete="off"
                onChange={(event) => setTyped(event.target.value)}
              />
            </label>
          )}

          <div className="inline-actions confirm-actions">
            <AlertDialog.Cancel asChild>
              <button type="button" className="secondary-button">
                Cancel
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button
                type="button"
                className="danger-button"
                disabled={!ready}
                onClick={() => onAnswer(true)}
              >
                {request.confirmLabel}
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
