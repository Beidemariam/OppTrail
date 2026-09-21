"use client";

import { Link } from "react-router";

import type { User } from "../lib/domain";
import { useLogout } from "../lib/queries";
import { NotificationMenu } from "./NotificationMenu";
import { ThemeToggle } from "./Theme";
import { useOpenCommandPalette } from "./ShortcutsProvider";

/**
 * The application bar: the product, the way into everything, what is waiting,
 * and who you are.
 *
 * It carries no page title from milestone 2.7 — the screen names itself in its
 * own header, which is where the view switcher and the create action sit, so
 * this bar stays the same on every screen rather than being half chrome and
 * half page (D-079). Three regions, in reading order: brand, the palette, and
 * the account controls.
 */
export function TopBar({ user }: { user: User }) {
  const logout = useLogout();
  const openPalette = useOpenCommandPalette();

  return (
    <header className="topbar">
      <Link className="brand" to="/">
        <span className="brand-mark" aria-hidden="true">
          OT
        </span>
        OppTrail
      </Link>

      {/* The palette is the keyboard entry point to everything, so it is
          advertised here rather than left to be discovered (docs/UX.md). */}
      <button type="button" className="palette-button" onClick={openPalette}>
        <span>Search or jump to...</span>
        <kbd>Ctrl K</kbd>
      </button>

      <div className="user-block">
        <Link className="ghost-button" to="/search">
          Search
        </Link>
        <NotificationMenu />
        <ThemeToggle />
        <span className="user-chip" title={user.email}>
          {user.name}
        </span>
        <button
          type="button"
          className="ghost-button"
          onClick={() => logout.mutate()}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
