/**
 * The editor half of the content pipeline (milestone 3.1).
 *
 * `app/MarkdownText.tsx` reads user content; this module is what writes it.
 * Both ends are Markdown, which is the whole reason this milestone needed no
 * migration: note, comment and entry bodies have been Markdown text since the
 * MVP, so the editor is a new way to type what was already stored rather than
 * a new storage format (`docs/FEATURES.md` §4, `AGENTS.md`'s TipTap decision).
 *
 * Three things here are load bearing:
 *
 * - **`contentExtensions` is the node set, declared once.** It is what the
 *   editor may produce *and* what `MarkdownText` is able to render, so the two
 *   cannot drift into a document that can be written and not read. Anything
 *   whose Markdown `MarkdownText` would not render — an underline, a table —
 *   is switched off here rather than styled away later.
 * - **`linkProtocols` is shared with the renderer's sanitizer.** The security
 *   boundary is still sanitization on render (`markdownSanitizeSchema`): the
 *   API stores whatever text it is sent, and a client-side editor cannot
 *   police that. What the shared list buys is that the editor cannot *produce*
 *   a link the renderer will strip, so `[go](javascript:alert(1))` is refused
 *   where it is typed instead of silently disappearing when it is read.
 * - **Serialization runs through a standalone `MarkdownManager`**, not through
 *   the editor instance's `getMarkdown()`, so the function the component calls
 *   on every keystroke is the same one the unit suite tests without a DOM.
 */

import type { AnyExtension, JSONContent } from "@tiptap/core";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import { Markdown, MarkdownManager } from "@tiptap/markdown";
import StarterKit from "@tiptap/starter-kit";

/**
 * The protocols a link may carry, in the editor and in the renderer.
 *
 * `app/MarkdownText.tsx`'s sanitizer reads this for its `href` allowlist, so
 * there is one list rather than two that agree today.
 */
export const linkProtocols = ["http", "https", "mailto"];

/** Whether a link's target is one the renderer will keep. */
export function isAllowedLinkHref(href: string): boolean {
  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(href.trim());
  // A relative or anchor href carries no scheme and is left to the sanitizer,
  // which keeps it: only an explicit protocol can be the wrong one.
  return scheme ? linkProtocols.includes(scheme[1].toLowerCase()) : true;
}

/**
 * Every node and mark this app's content may contain.
 *
 * `underline` is off because Markdown has no syntax for it and the renderer's
 * allowlist has no `u` tag — TipTap would serialize it as HTML that
 * `MarkdownText` then strips, which is a formatting control that silently
 * loses what the reader typed.
 */
export const contentExtensions: AnyExtension[] = [
  StarterKit.configure({
    underline: false,
    link: {
      openOnClick: false,
      // Typing `[text](url)` becomes a link, the same input-rule treatment
      // every other Markdown construct gets here.
      markdownLinks: true,
      isAllowedUri: (href, { defaultValidate }) =>
        isAllowedLinkHref(href) && defaultValidate(href),
    },
  }),
  TaskList,
  // A checklist nests, because a Markdown task list does.
  TaskItem.configure({ nested: true }),
  Markdown,
];

/**
 * Markdown to and from the editor's document, one manager for both
 * directions.
 */
const manager = new MarkdownManager({ extensions: contentExtensions });

/**
 * The Markdown for an editor document.
 *
 * Trimmed because the editor keeps a trailing empty paragraph for the reader
 * to click into (TipTap's `TrailingNode`), and that is a cursor affordance
 * rather than content the body should end with.
 */
export function markdownFromDoc(doc: JSONContent): string {
  return manager.serialize(doc).trim();
}

/** The editor document for stored Markdown. */
export function docFromMarkdown(markdown: string): JSONContent {
  return manager.parse(markdown);
}

/**
 * Stored Markdown as this editor would write it.
 *
 * Opening a body in the editor and saving it again normalizes the syntax —
 * `*` bullets become `-`, `__bold__` becomes `**bold**` — because a
 * ProseMirror document records the structure and not the characters that
 * produced it. Callers compare against this rather than against the original
 * text, so re-saving an untouched body is recognised as the no-op it is and
 * does not write a version row that changed nothing.
 */
export function normalizeMarkdown(markdown: string): string {
  return markdownFromDoc(docFromMarkdown(markdown));
}
