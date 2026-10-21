"use client";

import type { ChainedCommands, Editor } from "@tiptap/core";
import { Placeholder } from "@tiptap/extensions";
import { EditorContent, useEditor, useEditorState } from "@tiptap/react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { submitOnModEnter } from "../lib/keyboard";
import { contentExtensions, markdownFromDoc } from "../lib/markdown";
import { useInlineEditor } from "./InlineEdit";
import { useSuggestionMenu } from "./Suggestions";

/**
 * The composer, for every place this app takes user-written content
 * (milestone 3.1).
 *
 * `docs/code_review.md` finding 10 is what this closes: notes and comments
 * were composed in single-line `<input>` elements, so the bullet list
 * requirement 17 asks for could not be typed at all. The editor is TipTap
 * (`AGENTS.md`'s technical decisions) and what it reads and writes is
 * Markdown, the same text the API has always stored — see `lib/markdown.ts`
 * for the node set and why it is the renderer's and not a wider one.
 *
 * Five things about this component are load bearing:
 *
 * - **It is uncontrolled, like the `<textarea>` it replaces.** `value` seeds
 *   the document once, at creation, and every keystroke reports Markdown back
 *   through `onChange`. Feeding the serialized text back in would re-parse the
 *   document under the cursor on every character; where a caller needs to
 *   start over — a composer that cleared after posting — it unmounts this
 *   instead, which is what collapsing the composer already does.
 * - **The editable element is named, not wrapped in a `<label>`.** A
 *   contenteditable `div` cannot be a form control's target, so the name rides
 *   on `aria-label` with `role="textbox"` and `aria-multiline`, and `label` is
 *   also how tests and the keyboard journeys address it.
 * - **It focuses itself when it is asked to.** `useInlineEditor` moves focus
 *   into an editor in the effect after the render that opened it
 *   (`app/InlineEdit.tsx`), and that is one render too early here: ProseMirror
 *   creates the editable element in its own layout effect, so at that point
 *   there is nothing to focus. `autoFocus` is therefore the editor's own job,
 *   done in `onCreate`, while returning focus to the trigger on close stays
 *   the hook's.
 * - **The three typed triggers are one hook.** `@`, `/` and `#` open the same
 *   menu (`app/Suggestions.tsx`, milestone 3.2), and it is rendered inside this
 *   wrapper rather than in a portal so it is positioned against the composer the
 *   reader is typing in. What each offers comes from `lib/suggestions.ts`; what
 *   this component owns is that the editable points at the highlighted option,
 *   which cannot ride on `editorProps.attributes` because it changes on every
 *   arrow key and those are read once when the editor is created.
 * - **`onKeyDown` is the caller's, on the wrapper.** `Ctrl Enter` submits the
 *   composer a reader is typing in (`lib/keyboard.ts`), and that stays the
 *   caller's rule: the keystroke bubbles out of the editable exactly as it did
 *   out of the textarea, so `submitOnModEnter` and `submitFormOnModEnter` are
 *   unchanged.
 */
export function RichTextEditor({
  label,
  placeholder,
  value,
  onChange,
  onKeyDown,
  autoFocus,
}: {
  /** The editable region's accessible name. */
  label: string;
  /** What the empty editor says, the way a placeholder attribute would. */
  placeholder: string;
  /** The Markdown the editor opens with. Read once. */
  value: string;
  onChange: (markdown: string) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLDivElement>) => void;
  /** Whether the cursor starts here: true for an editor that opened in place
   * of what it edits, false for one field of a form. */
  autoFocus?: boolean;
}) {
  const suggestions = useSuggestionMenu();

  // Placeholder text is per composer, so the extension list is per instance.
  // `contentExtensions` is still the one declaration of the node set.
  const extensions = useMemo(
    () => [
      ...contentExtensions,
      Placeholder.configure({ placeholder }),
      ...suggestions.extensions,
    ],
    [placeholder, suggestions.extensions],
  );

  // `immediatelyRender` is explicit because TipTap turns it *off* when it
  // detects Next.js, to protect a hydration pass this app does not have: the
  // export renders `app/AppRoot.tsx`, which renders nothing at all outside a
  // browser (ADR 0005). Off, the editable element does not exist until an
  // effect after the first render, which is one render too late for
  // `useInlineEditor` to move focus into it — the note editor opened with the
  // cursor still on the Edit button.
  const editor = useEditor({
    extensions,
    immediatelyRender: true,
    content: value,
    contentType: "markdown",
    editorProps: {
      attributes: {
        "aria-label": label,
        "aria-multiline": "true",
        class: "rich-editor-input",
        role: "textbox",
      },
    },
    onCreate: ({ editor: created }) => {
      if (autoFocus) {
        // The element is focused directly, and the cursor put after the text
        // the editor opened with. TipTap's own `focus` command does both, but
        // it waits a frame before touching the DOM — and "the editor has focus
        // the moment it is open" is the rule 2.11 established, not "a frame
        // later".
        created.view.dom.focus();
        created.commands.focus("end", { scrollIntoView: false });
      }
    },
    onUpdate: ({ editor: changed }) =>
      onChange(markdownFromDoc(changed.getJSON())),
  });

  // Which option is highlighted is an attribute on the editable element, which
  // belongs to ProseMirror: the hook says what it should be and this puts it
  // there, so a reader on a screen reader hears the choice their arrow key
  // landed on while the caret stays in the sentence.
  useEffect(() => {
    const editable = editor.view.dom;
    if (suggestions.activeOptionId) {
      editable.setAttribute(
        "aria-activedescendant",
        suggestions.activeOptionId,
      );
    } else {
      editable.removeAttribute("aria-activedescendant");
    }
  }, [editor, suggestions.activeOptionId]);

  return (
    <div className="rich-editor" onKeyDown={onKeyDown}>
      <Toolbar editor={editor} />
      <EditorContent editor={editor} />
      {suggestions.menu}
    </div>
  );
}

/**
 * The formatting controls, as data.
 *
 * Only the marks and blocks that need no further input are here: a link and a
 * heading are typed — `[text](url)` and `### ` are input rules like every
 * other Markdown construct — because a button for either has to ask a question
 * first, and a dialog opening out of a composer is the thing
 * `docs/UX.md` spends its Design bar on avoiding. Bold and italic also answer
 * `Ctrl B` / `Ctrl I`, which the `title` says.
 */
const controls = [
  {
    name: "bold",
    label: "Bold",
    keys: "Ctrl B",
    run: (c: ChainedCommands) => c.toggleBold(),
  },
  {
    name: "italic",
    label: "Italic",
    keys: "Ctrl I",
    run: (c: ChainedCommands) => c.toggleItalic(),
  },
  {
    name: "strike",
    label: "Strike",
    keys: "Ctrl Shift X",
    run: (c: ChainedCommands) => c.toggleStrike(),
  },
  {
    name: "code",
    label: "Code",
    keys: "Ctrl E",
    run: (c: ChainedCommands) => c.toggleCode(),
  },
  {
    name: "bulletList",
    label: "Bullets",
    keys: "- then space",
    run: (c: ChainedCommands) => c.toggleBulletList(),
  },
  {
    name: "orderedList",
    label: "Numbers",
    keys: "1. then space",
    run: (c: ChainedCommands) => c.toggleOrderedList(),
  },
  {
    name: "taskList",
    label: "Checklist",
    keys: "[ ] then space",
    run: (c: ChainedCommands) => c.toggleTaskList(),
  },
  {
    name: "blockquote",
    label: "Quote",
    keys: "> then space",
    run: (c: ChainedCommands) => c.toggleBlockquote(),
  },
];

function Toolbar({ editor }: { editor: Editor }) {
  // `useEditor` does not re-render on a transaction, so what the buttons say
  // about themselves is subscribed to explicitly and nothing else re-renders
  // while the reader types.
  const active = useEditorState({
    editor,
    selector: ({ editor: current }) =>
      controls.map((control) => current.isActive(control.name)),
  });

  return (
    /* Named for what it does rather than for the field it belongs to: a group
       called "Formatting: Body" is also a match for a query for "Body", which
       made every `getByLabel("Body")` in the E2E suite ambiguous between the
       editor and its toolbar. */
    <div className="rich-toolbar" role="group" aria-label="Formatting">
      {controls.map((control, index) => (
        <button
          key={control.name}
          type="button"
          className="ghost-button"
          aria-pressed={active[index]}
          title={`${control.label} (${control.keys})`}
          // The chain starts with `focus` so a click on a control puts the
          // cursor back where the reader was typing rather than leaving it on
          // the button.
          onClick={() => control.run(editor.chain().focus()).run()}
        >
          {control.label}
        </button>
      ))}
    </div>
  );
}

/**
 * A composer that is closed until someone writes in it: the second shape in
 * this module, the way `app/InlineEdit.tsx` holds two.
 *
 * Collapsed it is one control saying what it would add — `docs/UX.md`'s
 * progressive disclosure, "collapsed it is one line". Expanded it is the
 * editor, its formatting controls and the button that posts. Three reasons it
 * is built this way rather than as an always-open editor:
 *
 * - **A timeline is made of composers.** Every entry offers to add a note and
 *   every note offers to add a comment, so an always-open editor would mount
 *   dozens of ProseMirror views on one screen to serve the one a reader is
 *   actually typing in.
 * - **Collapsing keeps the draft.** The text lives here rather than in the
 *   editor, so `Esc` or Cancel puts the composer away with what was written
 *   still in it, and reopening continues it.
 * - **Posting unmounts it**, which is how the editor is cleared: a document is
 *   reset by creating a new one, not by writing an empty string back into the
 *   one under the cursor (see `value` above).
 */
export function Composer({
  label,
  trigger,
  placeholder,
  submitLabel,
  onSubmit,
}: {
  /** The editable region's accessible name, while it is open. */
  label: string;
  /** What the collapsed control says. */
  trigger: string;
  placeholder: string;
  submitLabel: string;
  /**
   * Posts what was written. The composer closes when this resolves and stays
   * open, with the draft, when it rejects — the caller's mutation is what says
   * why.
   */
  onSubmit: (markdown: string) => Promise<unknown>;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const composer = useInlineEditor(triggerRef);
  const [draft, setDraft] = useState("");

  if (!composer.editing) {
    return (
      <button
        ref={triggerRef}
        type="button"
        className="composer-trigger"
        onClick={composer.open}
      >
        {trigger}
      </button>
    );
  }

  async function submit() {
    const markdown = draft.trim();
    if (!markdown) {
      return;
    }
    const posted = await onSubmit(markdown).then(
      () => true,
      () => false,
    );
    if (posted) {
      setDraft("");
      composer.close();
    }
  }

  const onModEnter = submitOnModEnter<HTMLDivElement>(() => void submit());

  return (
    <div className="stacked-form">
      <RichTextEditor
        label={label}
        placeholder={placeholder}
        value={draft}
        onChange={setDraft}
        autoFocus
        onKeyDown={(event) => {
          // The board binds Esc on the document; putting away the composer you
          // are typing in is what it means here, so it stops (`InlineEdit`).
          if (event.key === "Escape") {
            event.stopPropagation();
            composer.close();
            return;
          }
          onModEnter(event);
        }}
      />
      <div className="inline-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={() => void submit()}
        >
          {submitLabel}
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={composer.close}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
