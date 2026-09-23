"use client";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import {
  editableOpportunityFields,
  stages,
  type EditableOpportunityField,
  type Opportunity,
  type OpportunityEditableKey,
} from "../lib/domain";
import { useEditOpportunity } from "../lib/queries";
import { useToasts } from "./Toasts";

/**
 * Editing content where it is read (milestone 2.11, `AGENTS.md` v2 scope
 * item 12).
 *
 * Every editor in this app used to be somewhere other than the thing it
 * edited: an entry's Edit button filled a form at the top of the panel, so a
 * reader fifty entries down was moved to the top of the page and lost their
 * place — worse the longer the timeline, which is the complaint that created
 * this milestone (D-051). The rule here is that an editor opens in the space
 * its content occupied, and closing it puts the reader back exactly where
 * they were.
 *
 * Two shapes, because there are two kinds of editable thing:
 *
 * - `useInlineEditor` is the open/close state and the focus rule, used by
 *   whatever draws its own editor — a timeline entry swaps its card body for
 *   the entry form, a note swaps its rendered Markdown for the composer
 *   (`app/RichTextEditor.tsx` since 3.1, a textarea before it).
 * - `InlineEdit` is one field: it draws the value, and on activation replaces
 *   it with a control over the same space. The opportunity heading and the
 *   table cells use it.
 */

/**
 * Whether an inline editor is open, and the focus that goes with it — which
 * is the whole point of editing in place and the easy half to leave out.
 *
 * Both directions run in one effect, after the render that swapped the views
 * over, because in each case the element to focus does not exist yet when the
 * handler asks for it: `editorRef` takes focus when the editor opens, and
 * `triggerRef` takes it back when the editor closes. `editorRef` is optional
 * for a caller whose editor focuses itself — the rich composer does, because
 * ProseMirror creates its editable element one render later still
 * (`app/RichTextEditor.tsx`). Returning focus is part
 * of **closing** rather than of unmounting, the same rule `app/Modal.tsx`
 * follows for dialogs (D-066) — an editor that goes away because the thing it
 * edited was deleted leaves focus alone.
 *
 * The refs are the caller's and passed in rather than handed back: a ref
 * returned from a hook and then read in JSX is a ref accessed during render
 * as far as the React Compiler can tell, and it is right that it cannot
 * distinguish the two.
 */
export function useInlineEditor(
  /** The control that opens the editor, and takes focus back when it closes. */
  triggerRef: RefObject<HTMLElement | null>,
  /** Where the reader should land while it is open: the first field of the
   * editor. Optional only because not every editor has one to name. */
  editorRef?: RefObject<HTMLElement | null>,
) {
  const [editing, setEditing] = useState(false);
  const restoring = useRef(false);

  useEffect(() => {
    if (editing) {
      editorRef?.current?.focus();
    } else if (restoring.current) {
      restoring.current = false;
      triggerRef.current?.focus();
    }
    // The two refs are in the list because they are the effect's inputs, and
    // they cost nothing there: a `useRef` object is stable for the life of
    // the component, so `editing` is what actually re-runs this.
  }, [editing, editorRef, triggerRef]);

  return {
    editing,
    open: () => setEditing(true),
    close: () => {
      restoring.current = true;
      setEditing(false);
    },
  };
}

/**
 * One opportunity field, edited in the space it is read in.
 *
 * The write is optimistic (`useEditOpportunity`), so this closes as soon as
 * the reader saves rather than holding them in an editor waiting for a round
 * trip — `docs/UX.md`'s "applies immediately, reconciles on response". A
 * refusal rolls the cache back and the caller says so; what is refused here
 * instead is the value the API would reject anyway, because an editor that
 * closes and then silently reverts is worse than one that stays open.
 */
export function InlineEdit({
  field,
  value,
  editable,
  children,
  onSave,
}: {
  field: EditableOpportunityField;
  /** The current value as the control's own string (`field.read`). */
  value: string;
  /** A reader who may not change this sees `children` and no affordance. */
  editable: boolean;
  /** How the value reads when it is not being edited. */
  children: ReactNode;
  onSave: (next: string) => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const controlRef = useRef<HTMLInputElement & HTMLSelectElement>(null);
  const editor = useInlineEditor(triggerRef, controlRef);
  const [draft, setDraft] = useState(value);
  const [refused, setRefused] = useState("");

  // An element rather than a bare fragment, so a reader who may not edit
  // gets the same layout as one who may: the heading's facts are separated by
  // a rule between element siblings, and a text node has none.
  if (!editable) {
    return <span className="inline-edit-static">{children}</span>;
  }

  if (!editor.editing) {
    return (
      <button
        ref={triggerRef}
        type="button"
        className="inline-edit"
        // The name comes from the value, not from an `aria-label` saying
        // "Edit": this control sits inside the opportunity's `h2` and inside
        // table cells, and a label overrides name-from-content, so an
        // `aria-label` here renames the heading it lives in. What the control
        // does is the description instead, which is also how it is addressed
        // in tests — a selector on the value stops matching the moment the
        // value is edited.
        title={`Edit ${field.label}`}
        onClick={() => {
          setDraft(value);
          setRefused("");
          editor.open();
        }}
      >
        {children}
      </button>
    );
  }

  function save() {
    const next = field.input === "date" ? draft : draft.trim();
    const problem = rejection(field, next);
    if (problem) {
      setRefused(problem);
      return;
    }
    setRefused("");
    if (next !== value) {
      onSave(next);
    }
    editor.close();
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      save();
    }
    // The board binds Esc to clearing its cursor and its bulk selection
    // (`DashboardPage`), on a document listener; abandoning an edit is what
    // the key means while an editor is open, so it stops here.
    if (event.key === "Escape") {
      event.stopPropagation();
      editor.close();
    }
  }

  return (
    <span className="inline-editor">
      {field.input === "stage" ? (
        <select
          ref={controlRef}
          aria-label={field.label}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        >
          {stages.map((stage) => (
            <option key={stage}>{stage}</option>
          ))}
        </select>
      ) : (
        <input
          ref={controlRef}
          aria-label={field.label}
          type={field.input === "number" ? "number" : field.input}
          min={field.input === "number" ? "0" : undefined}
          step={field.input === "number" ? "0.01" : undefined}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
      )}
      <button
        type="button"
        className="ghost-button"
        aria-label={`Save ${field.label}`}
        onClick={save}
      >
        Save
      </button>
      <button
        type="button"
        className="ghost-button"
        aria-label={`Cancel editing ${field.label}`}
        onClick={editor.close}
      >
        Cancel
      </button>
      {refused && <span className="error">{refused}</span>}
    </span>
  );
}

/**
 * Why the API would refuse this value, or nothing.
 *
 * The same three rules `backend/app/schemas.py`'s `OpportunityUpdate` carries
 * — a non-empty name, a non-negative number, and a close date that may be
 * cleared — checked here so a rejected edit never reaches the optimistic
 * cache and flickers back.
 */
function rejection(field: EditableOpportunityField, value: string): string {
  if (field.input === "date") {
    return "";
  }
  if (!value) {
    return `${field.label} cannot be empty.`;
  }
  if (field.input === "number" && !(Number(value) >= 0)) {
    return `${field.label} must be a number, and not negative.`;
  }
  return "";
}

/**
 * The write behind every inline opportunity edit, declared once so the table
 * cell and the timeline heading cannot save the same field two different
 * ways.
 *
 * Optimistic in the cache, so the new value is on screen before the request
 * lands; a refusal puts the old one back (`useEditOpportunity`) and says
 * which field on which deal was refused, because by then the editor has
 * closed and there is nowhere else for the message to appear.
 *
 * Called once per view rather than once per cell: a table draws fifty of
 * these, and fifty mutation observers over one endpoint is fifty subscribers
 * to the same cache.
 */
export type OpportunityFieldSave = (
  opportunity: Opportunity,
  field: OpportunityEditableKey,
  next: string,
) => void;

export function useOpportunityFieldSave(): OpportunityFieldSave {
  const edit = useEditOpportunity();
  const showToast = useToasts();
  return (opportunity, field, next) => {
    const { label, patch } = editableOpportunityFields[field];
    edit
      .mutateAsync({ id: opportunity.id, fields: patch(next) })
      .catch((error: Error) =>
        showToast({
          message: `Could not change the ${label.toLowerCase()} of ${
            opportunity.name
          }: ${error.message}`,
          tone: "error",
        }),
      );
  };
}

/** One opportunity field wherever it is read: the table's cells and the
 * opportunity's own heading both draw this, so the affordance, the editor and
 * the write are the same in both. */
export function OpportunityField({
  opportunity,
  field,
  editable,
  save,
  children,
}: {
  opportunity: Opportunity;
  field: OpportunityEditableKey;
  editable: boolean;
  save: OpportunityFieldSave;
  children: ReactNode;
}) {
  const declared = editableOpportunityFields[field];
  return (
    <InlineEdit
      field={declared}
      value={declared.read(opportunity)}
      editable={editable}
      onSave={(next) => save(opportunity, field, next)}
    >
      {children}
    </InlineEdit>
  );
}
