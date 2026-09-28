/**
 * The keyboard map (milestone 2.4a), as data and as the listener that serves
 * it.
 *
 * `docs/UX.md` treats keyboard operation as a feature rather than polish, and
 * a map is only worth publishing if every key in it does something. So the
 * reference screen (`app/ShortcutHelp.tsx`) renders `shortcutGroups`, the
 * views bind against `Chord` — a union derived from that same array — and a
 * key that is documented but never bound, or bound but never documented, is a
 * type error rather than a discovery a user makes.
 */

import {
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

/**
 * Every shortcut this app answers, grouped the way the reference screen shows
 * them. `chord` is the internal name a view binds; `keys` is what the user
 * presses.
 */
export const shortcutGroups = [
  {
    group: "Anywhere",
    shortcuts: [
      {
        chord: "mod+k",
        keys: "Ctrl K / Cmd K",
        description: "Open the command palette",
      },
      { chord: "?", keys: "?", description: "Show this keyboard reference" },
      { chord: "g d", keys: "g then d", description: "Go to the dashboard" },
      {
        chord: "g p",
        keys: "g then p",
        description: "Go to the pipeline board",
      },
      { chord: "g s", keys: "g then s", description: "Go to search" },
      // Reserved and deliberately unbound since milestone 2.4a (**D-065**: a
      // key documented before its feature exists is a key that does nothing),
      // bound here because the feature now exists.
      { chord: "g t", keys: "g then t", description: "Go to my tasks" },
      {
        chord: "mod+Enter",
        keys: "Ctrl Enter / Cmd Enter",
        description: "Submit the composer you are typing in",
      },
      {
        chord: "Escape",
        keys: "Esc",
        description:
          "Close what is open, clear a bulk selection, or clear the focused card",
      },
    ],
  },
  {
    group: "The board",
    shortcuts: [
      {
        chord: "c",
        keys: "c",
        description:
          "Create: an opportunity on the board, an entry when a timeline is open",
      },
      {
        chord: "/",
        keys: "/",
        description: "Focus the board's keyword filter",
      },
      { chord: "j", keys: "j", description: "Focus the next opportunity" },
      { chord: "k", keys: "k", description: "Focus the previous opportunity" },
      { chord: "e", keys: "e", description: "Edit the focused opportunity" },
      {
        chord: "x",
        keys: "x",
        description: "Toggle bulk selection of the focused opportunity",
      },
      {
        chord: "Enter",
        keys: "Enter",
        description: "Open the focused opportunity's timeline",
      },
      {
        chord: "[",
        keys: "[",
        description: "Move the focused opportunity back one stage",
      },
      {
        chord: "]",
        keys: "]",
        description: "Move the focused opportunity on one stage",
      },
    ],
  },
] as const;

export type Chord =
  (typeof shortcutGroups)[number]["shortcuts"][number]["chord"];

/** The prefix key that starts a two-stroke `g` sequence. */
const SEQUENCE_PREFIX = "g";

/**
 * Whether the keystroke landed somewhere the user is composing text.
 *
 * Single-key shortcuts are suppressed there — typing "call Casey" into a note
 * must not fire `c`, `/` and `e` — while `Ctrl K` and `Esc` deliberately still
 * work, which is what `docs/UX.md` means by "opens on Cmd K from anywhere
 * including inside inputs".
 */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  // Two readings of the same question, because each catches what the other
  // misses. `isContentEditable` is the browser's own answer and is true inside
  // a nested element of an editable region as well as on the host; jsdom
  // implements no editing at all and leaves it `undefined`, so the attribute is
  // read too — the rich composer (milestone 3.1) is a contenteditable `div`,
  // and without the second reading every letter typed into a note in the unit
  // suite is a command again.
  if (target.isContentEditable || target.closest('[contenteditable="true"]')) {
    return true;
  }
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** Elements that already answer Enter themselves. */
function activatesOnEnter(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return ["BUTTON", "A", "SUMMARY"].includes(target.tagName);
}

/** The subset of a `KeyboardEvent` the matcher reads, so it can be tested
 * without constructing one. */
export interface KeyStroke {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  target: EventTarget | null;
}

/**
 * The chord a keystroke completes, given whatever prefix is pending.
 *
 * Returns `"g"` when the stroke only *starts* a sequence, and `null` when it
 * means nothing here — in which case the browser keeps it.
 */
export function chordFor(stroke: KeyStroke, prefix: string): string | null {
  // Alt-modified keys belong to the operating system and to accented input.
  if (stroke.altKey) {
    return null;
  }

  if (stroke.metaKey || stroke.ctrlKey) {
    if (stroke.key.toLowerCase() === "k") {
      return "mod+k";
    }
    return stroke.key === "Enter" ? "mod+Enter" : null;
  }

  if (stroke.key === "Escape") {
    return "Escape";
  }

  if (isTypingTarget(stroke.target)) {
    return null;
  }

  if (prefix === SEQUENCE_PREFIX) {
    return `${SEQUENCE_PREFIX} ${stroke.key.toLowerCase()}`;
  }

  if (stroke.key === "Enter") {
    return activatesOnEnter(stroke.target) ? null : "Enter";
  }

  if (stroke.key === "?") {
    return "?";
  }

  // Everything left is a single printable key. Shift is excluded so a capital
  // J is text rather than a command.
  if (stroke.shiftKey || stroke.key.length !== 1) {
    return null;
  }
  return stroke.key.toLowerCase();
}

/**
 * Binds part of the keyboard map for as long as the caller is mounted.
 *
 * Several views call this at once — the app shell owns the global chords, the
 * dashboard owns the board's — and each binds only what it can act on, so two
 * views never answer the same chord. Handlers are read through a ref so a
 * closure over fresh props does not re-register the listener on every render.
 */
export function useKeyboardShortcuts(
  bindings: Partial<Record<Chord, () => void>>,
): void {
  const latest = useRef(bindings);
  // Written in an effect rather than during render: the listener below is
  // registered once, and this is what keeps the handlers it calls current.
  useEffect(() => {
    latest.current = bindings;
  });

  useEffect(() => {
    // No timeout: a sequence is cleared by the next keystroke, whatever it is,
    // so "g" followed much later by "d" behaves the same way in a test as it
    // does under a finger.
    let prefix = "";

    function onKeyDown(event: KeyboardEvent) {
      const chord = chordFor(event, prefix);
      prefix = "";

      // "g" on its own arms the sequence, and a second "g" re-arms it rather
      // than being swallowed as an unknown pair.
      if (chord === SEQUENCE_PREFIX || chord === `${SEQUENCE_PREFIX} g`) {
        prefix = SEQUENCE_PREFIX;
        return;
      }

      const handler = chord ? latest.current[chord as Chord] : undefined;
      if (!handler) {
        return;
      }
      event.preventDefault();
      handler();
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}

/**
 * `Ctrl Enter` / `Cmd Enter` inside one composer.
 *
 * A single-line input already submits its form on Enter; a textarea does not,
 * and neither does the "Add note" pair of an input and a button that is not a
 * form at all. This is the one handler all of them share.
 */
export function submitOnModEnter<T extends HTMLElement>(
  submit: () => void,
): (event: ReactKeyboardEvent<T>) => void {
  return (event) => {
    if (isModEnter(event)) {
      event.preventDefault();
      submit();
    }
  };
}

/**
 * The same chord for a composer that *is* a form.
 *
 * It submits the form the keystroke happened in, read off the event rather
 * than held in a ref, so the handler stays a plain function of its event.
 */
export function submitFormOnModEnter<T extends HTMLElement>(): (
  event: ReactKeyboardEvent<T>,
) => void {
  return (event) => {
    if (!isModEnter(event)) {
      return;
    }
    const form = event.currentTarget.closest("form");
    if (form) {
      event.preventDefault();
      form.requestSubmit();
    }
  };
}

function isModEnter(event: {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
}): boolean {
  return event.key === "Enter" && (event.metaKey || event.ctrlKey);
}
