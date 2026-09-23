import { fireEvent } from "@testing-library/react";

/**
 * Puts Markdown into a rich composer, replacing whatever it held.
 *
 * `userEvent.type` cannot drive a ProseMirror editor under jsdom: the
 * keystrokes arrive but the document never changes, because ProseMirror reads
 * back the DOM mutation the browser would have made from the keypress and
 * jsdom makes none. Pasting is the one content-entry path that is pure state —
 * ProseMirror parses the clipboard text itself and dispatches a transaction —
 * so it works here, and it is still a real reader's action rather than a
 * handle into the component. Select-all first, so this reads as "the composer
 * now says this".
 *
 * What jsdom therefore cannot cover is typing, and with it the Markdown input
 * rules: `frontend/e2e/18-rich-text.spec.ts` types a bullet list in a real
 * browser for exactly that reason.
 */
export function writeInEditor(editable: HTMLElement, markdown: string): void {
  selectAllInEditor(editable);
  fireEvent.paste(editable, {
    clipboardData: {
      files: [],
      getData: (type: string) => (type === "text/plain" ? markdown : ""),
      items: [],
      types: ["text/plain"],
    },
  });
}

/** Selects the whole document, the way `Ctrl A` does. */
export function selectAllInEditor(editable: HTMLElement): void {
  fireEvent.keyDown(editable, { ctrlKey: true, key: "a" });
}

/**
 * Empties a composer.
 *
 * Unlike typing, deleting a selection is a ProseMirror command rather than a
 * DOM mutation the editor reads back, so it works here.
 */
export function clearEditor(editable: HTMLElement): void {
  selectAllInEditor(editable);
  fireEvent.keyDown(editable, { key: "Backspace" });
}
