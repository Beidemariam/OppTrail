"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { UseMutationResult } from "@tanstack/react-query";

/**
 * The toast surface, and the undo interaction built on it (milestone 2.4b).
 *
 * `docs/UX.md`: "Destructive actions do not confirm — they apply and offer
 * Undo for 10 seconds." That reversal is only safe because a delete here is a
 * `deleted_at` stamp and the restore routes clear it
 * (`backend/app/soft_delete.py`), so Undo puts the same row back rather than
 * writing a copy of it.
 */

/** `docs/UX.md` names the window; it is the only timing in this file. */
export const TOAST_DURATION_MS = 10_000;

interface ToastAction {
  label: string;
  run: () => void;
}

export interface ToastRequest {
  message: string;
  action?: ToastAction;
  tone?: "info" | "error";
}

interface Toast extends ToastRequest {
  id: number;
}

const ToastContext = createContext<(request: ToastRequest) => void>(() => {});

/** Raises a toast. Returns the same function for the life of the provider. */
export function useToasts(): (request: ToastRequest) => void {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback((request: ToastRequest) => {
    setToasts((current) => [
      ...current,
      // Date.now collides when two toasts are raised in the same millisecond;
      // the counter cannot, and the id is only ever a React key and a handle
      // for dismissal.
      { ...request, id: nextToastId() },
    ]);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      {/* A live region rather than a dialog: a toast never takes focus, so a
          reader in the middle of typing is told what happened and keeps their
          place. The Undo button is still reachable by Tab. */}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <ToastRow key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

let lastToastId = 0;

function nextToastId(): number {
  lastToastId += 1;
  return lastToastId;
}

function ToastRow({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: number) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_MS);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div className={`toast ${toast.tone ?? "info"}`}>
      <p>{toast.message}</p>
      <div className="inline-actions">
        {toast.action && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              toast.action?.run();
              onDismiss(toast.id);
            }}
          >
            {toast.action.label}
          </button>
        )}
        <button
          type="button"
          className="secondary-button"
          onClick={() => onDismiss(toast.id)}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

type Deleter = UseMutationResult<unknown, Error, number>;

/**
 * "Delete it, and say so with a way back."
 *
 * One definition of the interaction rather than four copies of it: each
 * destructive control passes the noun it deletes and the pair of mutations
 * that remove and restore the row. A failure on either leg raises the
 * explanatory toast `docs/UX.md` asks for; the optimistic update in
 * `lib/queries.ts` has already been rolled back by the time it appears.
 *
 * Both legs go through `mutateAsync` rather than `mutate`'s per-call
 * callbacks, because the component that owns the control is usually gone by
 * the time either resolves — deleting a note unmounts the note. TanStack Query
 * drops `mutate(vars, { onSuccess })` when the observer has no listeners left;
 * the promise resolves either way.
 */
export function useUndoableDelete(
  what: string,
  remove: Deleter,
  restore: Deleter,
): (id: number, onRemoved?: () => void) => void {
  const show = useToasts();
  const noun = what.toLowerCase();

  return (id, onRemoved) => {
    remove
      .mutateAsync(id)
      .then(() => {
        onRemoved?.();
        show({
          message: `${what} deleted.`,
          action: {
            label: "Undo",
            run: () => {
              restore.mutateAsync(id).catch((error: Error) =>
                show({
                  message: `Could not restore the ${noun}: ${error.message}`,
                  tone: "error",
                }),
              );
            },
          },
        });
      })
      .catch((error: Error) =>
        show({
          message: `Could not delete the ${noun}: ${error.message}`,
          tone: "error",
        }),
      );
  };
}
