/**
 * The five destinations, and whether the rail that holds them is collapsed
 * (milestone R.1, decision 4A).
 *
 * Declared here rather than in `app/AppShell.tsx` for the reason
 * `lib/keyboard.ts` declares the shortcut map and `lib/nav`'s neighbours
 * declare their preferences: it is data, it is read by more than one thing
 * (the rail draws it, the palette could), and it is testable without a DOM.
 *
 * Before this the app had no navigation at all beyond three links in the top
 * bar, and four of the five screens hand-rolled their own header without
 * them -- so from Reports there was no way to reach Automations.
 */
export type NavItem = {
  /** What the rail calls it. Also its accessible name. */
  readonly label: string;
  readonly path: string;
};

export const navItems: readonly NavItem[] = [
  { label: "Opportunities", path: "/" },
  { label: "Tasks", path: "/tasks" },
  { label: "Reports", path: "/reports" },
  { label: "Automations", path: "/automations" },
  { label: "Search", path: "/search" },
];

/**
 * Which destination a path belongs to.
 *
 * A deal is its own page from R.1 (decision 1A), so `/opportunities/7` has to
 * light Opportunities rather than nothing: an exact match on "/" would leave
 * the rail saying the reader is nowhere, on the one screen they spend the
 * most time in. Every other item is a prefix match, which is also what keeps
 * a future `/reports/pipeline` under Reports.
 */
export function isNavActive(itemPath: string, pathname: string): boolean {
  if (itemPath === "/") {
    return pathname === "/" || pathname.startsWith("/opportunities");
  }
  return pathname === itemPath || pathname.startsWith(`${itemPath}/`);
}

export const NAV_STORAGE_KEY = "opptrail-nav";

/**
 * Collapsed is a preference, not state: it survives a reload, like the theme
 * and the density. Unlike those two it writes no root attribute, because
 * nothing outside the rail changes when it collapses -- the main column is
 * simply given the width.
 */
export function readNavCollapsed(): boolean {
  try {
    return window.localStorage.getItem(NAV_STORAGE_KEY) === "collapsed";
  } catch {
    // Safari in private mode throws on access, not on write.
    return false;
  }
}

export function writeNavCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(
      NAV_STORAGE_KEY,
      collapsed ? "collapsed" : "expanded",
    );
  } catch {
    // A preference that cannot be stored still applies for this page load.
  }
}
