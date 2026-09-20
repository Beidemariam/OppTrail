"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { useKeyboardShortcuts } from "../lib/keyboard";
import { useSession } from "../lib/queries";
import { CommandPalette } from "./CommandPalette";
import { ShortcutHelp } from "./ShortcutHelp";

type Overlay = "palette" | "shortcuts" | null;

const OpenPaletteContext = createContext<() => void>(() => {});

/**
 * Opens the command palette from somewhere other than Ctrl K.
 *
 * The palette is deliberately not keyboard-only: `TopBar` offers it as a
 * button, because a shortcut nobody can see is a shortcut nobody learns.
 */
export function useOpenCommandPalette(): () => void {
  return useContext(OpenPaletteContext);
}

/**
 * The app-wide half of the keyboard map (milestone 2.4a): the chords that mean
 * the same thing on every screen, and the two dialogs they open.
 *
 * Screen-specific chords are bound by the screen that can act on them —
 * `DashboardPage` owns the board's `j`/`k`/`e`, `OpportunityPanel` owns `c`
 * while a timeline is open — so no two views answer the same chord and a
 * binding never outlives the thing it acts on.
 */
export function ShortcutsProvider({ children }: { children: ReactNode }) {
  const [overlay, setOverlay] = useState<Overlay>(null);
  const navigate = useNavigate();
  const session = useSession();
  const signedIn = Boolean(session.data);

  useKeyboardShortcuts(
    signedIn
      ? {
          "mod+k": () => setOverlay("palette"),
          "?": () => setOverlay("shortcuts"),
          "g d": () => navigate("/"),
          // The board is the dashboard today. It becomes a destination of its
          // own when milestone 2.7 splits board and list views apart.
          "g p": () => navigate("/"),
          "g s": () => navigate("/search"),
        }
      : {},
  );

  return (
    <OpenPaletteContext.Provider value={() => setOverlay("palette")}>
      {children}
      {signedIn && overlay === "palette" && (
        <CommandPalette
          onClose={() => setOverlay(null)}
          onShowShortcuts={() => setOverlay("shortcuts")}
        />
      )}
      {signedIn && overlay === "shortcuts" && (
        <ShortcutHelp onClose={() => setOverlay(null)} />
      )}
    </OpenPaletteContext.Provider>
  );
}
