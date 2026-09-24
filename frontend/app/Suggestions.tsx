"use client";

import { Extension, type AnyExtension, type Editor } from "@tiptap/core";
import { PluginKey } from "@tiptap/pm/state";
import Suggestion, {
  type SuggestionKeyDownProps,
  type SuggestionProps,
} from "@tiptap/suggestion";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  emptySuggestionSources,
  suggestionTriggers,
  type SuggestionItem,
  type SuggestionSources,
  type SuggestionTrigger,
} from "../lib/suggestions";

/**
 * The popup behind all three of the composer's triggers (milestone 3.2).
 *
 * `@` offers the people a mention would reach, `/` the blocks a document can
 * contain, `#` the entries on this timeline — one `@tiptap/suggestion` plugin
 * per character, one menu, one keyboard rule (**D-111**: building this three
 * times is the duplication `AGENTS.md`'s standards rule out). What each trigger
 * offers is data in `lib/suggestions.ts`; this file is how it reaches an editor
 * and a screen.
 *
 * Four things here are load bearing:
 *
 * - **The sources arrive through context, not props.** Every composer in this
 *   app is inside one opportunity's panel — an entry's body, a note, an edit to
 *   a note, a comment — and threading "who is on this deal" through five
 *   components to reach the editor at the bottom is the prop drilling
 *   `lib/queries.ts` exists to avoid. `SuggestionSourceProvider` reads it once
 *   per opportunity; a `RichTextEditor` outside one still works, with the two
 *   triggers that need no opportunity.
 * - **The plugins read a ref, so the extension list never changes.**
 *   `useEditor` rebuilds the editor when its extensions change, which would
 *   throw away the document under the cursor every time a member list
 *   refetched. The plugins are built once and look the current sources up when
 *   a key is pressed.
 * - **The editable keeps focus the whole time.** The menu is not a focus trap
 *   and not focusable: it is a `listbox` the editable points at with
 *   `aria-activedescendant`, driven by the arrow keys the suggestion plugin
 *   hands over — which is the only way a menu can appear mid-sentence without
 *   interrupting typing. A mouse choice is taken on `mousedown` with the
 *   default prevented, so even a click never moves focus out.
 * - **`Escape` stops at the menu.** A composer closes on `Escape`
 *   (`RichTextEditor`'s `Composer`), and the first `Escape` after a popup opens
 *   has to mean "put the popup away" — so the handler stops the native event
 *   before React's root listener sees it, rather than letting one keystroke do
 *   both.
 */
const SuggestionSourceContext = createContext<SuggestionSources>(
  emptySuggestionSources,
);

export function SuggestionSourceProvider({
  sources,
  children,
}: {
  sources: SuggestionSources;
  children: ReactNode;
}) {
  return (
    <SuggestionSourceContext.Provider value={sources}>
      {children}
    </SuggestionSourceContext.Provider>
  );
}

export function useSuggestionSources(): SuggestionSources {
  return useContext(SuggestionSourceContext);
}

/** What is on screen while a trigger is open. */
interface MenuState {
  trigger: SuggestionTrigger;
  items: SuggestionItem[];
  active: number;
  /** Where the caret is, relative to the composer. */
  top: number;
  left: number;
  /** Applies one item to the document the trigger was typed in. */
  choose: (item: SuggestionItem) => void;
}

/**
 * Puts one chosen item into the document.
 *
 * The three insert shapes `lib/suggestions.ts` declares are the three things a
 * trigger can mean, and this is the only place they touch an editor: text in
 * place of what was typed, the same as a link, or a command over the block once
 * the typed trigger is deleted.
 */
function applyItem(
  editor: Editor,
  range: { from: number; to: number },
  item: SuggestionItem,
): void {
  switch (item.insert) {
    case "text":
      editor.chain().insertContentAt(range, item.text).run();
      return;
    case "link":
      editor
        .chain()
        .insertContentAt(range, [
          {
            type: "text",
            marks: [{ type: "link", attrs: { href: item.href } }],
            text: item.text,
          },
          // A trailing space, outside the link: without it the next word the
          // reader types joins the link text.
          { type: "text", text: " " },
        ])
        .run();
      return;
    case "command":
      item.run(editor.chain().deleteRange(range)).run();
  }
}

/**
 * The suggestion plugins and the menu they drive.
 *
 * Returns the extensions to hand `useEditor`, the menu to render inside the
 * composer, and the option id the editable should point at — which is the
 * caller's to apply, because the editable element is the editor's and not this
 * hook's.
 */
export function useSuggestionMenu(): {
  extensions: AnyExtension[];
  menu: ReactNode;
  activeOptionId: string | null;
} {
  const sources = useSuggestionSources();
  const [menu, setMenu] = useState<MenuState | null>(null);

  // Two refs, because the plugins are built once and read from a keystroke,
  // which happens outside any render: the current sources (a member list that
  // arrives after the composer opened must still be offered) and the menu the
  // key handler is acting on. They are captured by the plugins below rather
  // than passed to them — a ref handed to a function is a ref the React
  // Compiler has to assume is read while rendering, which is the same rule
  // `app/InlineEdit.tsx` works around from the other direction. Nothing here
  // is read during a render; the screen is drawn from `menu` above.
  const sourcesRef = useRef(sources);
  useEffect(() => {
    sourcesRef.current = sources;
  }, [sources]);
  const menuRef = useRef<MenuState | null>(null);
  const update = useCallback((next: MenuState | null) => {
    menuRef.current = next;
    setMenu(next);
  }, []);

  // Unique per composer: two open composers must not both claim `option-0`.
  const listId = useId();
  const optionId = (index: number) => `${listId}-option-${index}`;

  const extensions = useMemo(
    () =>
      // The lint rule reads "a ref captured by a function built while
      // rendering" as "a ref read while rendering", and cannot see that these
      // closures are the suggestion plugin's callbacks: nothing below runs
      // until a key is pressed. Suppressed here rather than worked around,
      // because every way around it is worse — extensions rebuilt when the
      // member list arrives would recreate the editor and throw away the
      // document under the cursor, and a mutable store that is not a ref is
      // refused by the compiler's immutability rule instead.
      // eslint-disable-next-line react-hooks/refs
      suggestionTriggers.map((trigger) => {
        /** What one of this trigger's renders puts on screen. */
        function menuFrom(props: SuggestionProps<SuggestionItem>): MenuState {
          const caret = props.clientRect?.();
          // The composer is the menu's containing block and the editable is
          // inside it, so the wrapper is read off the editor rather than
          // through a second ref the caller would have to hold.
          const container = props.editor.view.dom
            .closest(".rich-editor")
            ?.getBoundingClientRect();
          const previous = menuRef.current;
          return {
            trigger,
            items: props.items,
            // The highlight stays where it was while the query narrows, unless
            // the choice it was on has gone.
            active:
              previous &&
              previous.trigger === trigger &&
              previous.active < props.items.length
                ? previous.active
                : 0,
            top: caret && container ? caret.bottom - container.top : 0,
            left: caret && container ? caret.left - container.left : 0,
            choose: (item) => {
              applyItem(props.editor, props.range, item);
              update(null);
            },
          };
        }

        return Extension.create({
          name: `suggestion-${trigger.label.toLowerCase()}`,
          addProseMirrorPlugins() {
            return [
              Suggestion<SuggestionItem>({
                editor: this.editor,
                char: trigger.char,
                // A key per trigger, so three plugins can be active over one
                // document without sharing one state.
                pluginKey: new PluginKey(`suggestion-${trigger.char}`),
                items: ({ query }) => trigger.items(query, sourcesRef.current),
                render: () => ({
                  onStart: (props) => update(menuFrom(props)),
                  onUpdate: (props) => update(menuFrom(props)),
                  onExit: () => update(null),
                  onKeyDown: ({ event }: SuggestionKeyDownProps) =>
                    handleKey(event, menuRef.current, update),
                }),
              }),
            ];
          },
        });
      }),
    [update],
  );

  return {
    extensions,
    activeOptionId:
      menu && menu.items.length > 0 ? optionId(menu.active) : null,
    menu: menu && (
      <div
        className="suggestion-menu"
        style={{ top: `${menu.top}px`, left: `${menu.left}px` }}
      >
        {menu.items.length === 0 ? (
          <p className="suggestion-empty">{menu.trigger.empty}</p>
        ) : (
          <ul role="listbox" aria-label={menu.trigger.label}>
            {menu.items.map((item, index) => (
              <li
                key={item.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === menu.active}
                className={index === menu.active ? "is-active" : undefined}
                // Mousedown with the default prevented, so choosing with the
                // mouse never takes focus off the text being written.
                onMouseDown={(event) => {
                  event.preventDefault();
                  menu.choose(item);
                }}
              >
                <span className="suggestion-label">{item.label}</span>
                <span className="suggestion-detail">{item.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    ),
  };
}

/**
 * The menu's keyboard rule, over the keystrokes the suggestion plugin offers
 * before the editor sees them.
 *
 * `Tab` chooses as well as `Enter` — a suggestion is a completion, and that is
 * the key a completion answers to. With nothing matched, every key is handed
 * back: a popup saying "no matching entry" must not swallow the Enter that
 * starts a new line.
 */
function handleKey(
  event: KeyboardEvent,
  menu: MenuState | null,
  update: (next: MenuState | null) => void,
): boolean {
  if (!menu) {
    return false;
  }
  if (event.key === "Escape") {
    // The plugin closes the popup itself; what this stops is the same keystroke
    // reaching the composer and closing that too.
    event.stopPropagation();
    return true;
  }
  if (menu.items.length === 0) {
    return false;
  }
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    const step = event.key === "ArrowDown" ? 1 : -1;
    update({
      ...menu,
      active: (menu.active + step + menu.items.length) % menu.items.length,
    });
    return true;
  }
  if (event.key === "Enter" || event.key === "Tab") {
    menu.choose(menu.items[menu.active]);
    return true;
  }
  return false;
}
