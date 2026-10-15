"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Link,
  Outlet,
  useLocation,
  useOutletContext,
  useSearchParams,
} from "react-router";

import type { User } from "../lib/domain";
import {
  STICKY_ATTRIBUTE,
  isNavActive,
  navItems,
  readNavCollapsed,
  stickyStack,
  writeNavCollapsed,
} from "../lib/nav";
import { useMyTasks, useSession } from "../lib/queries";
import { AuthPanel } from "./AuthPanel";
import { TopBar } from "./TopBar";

/**
 * One shell for every screen (milestone R.1, decision 4A).
 *
 * It is a layout route, so it resolves the session once for all five screens
 * rather than each of them deciding separately what to draw while it loads and
 * what to draw when nobody is signed in -- which is how four of them came to
 * hand-roll a header with no navigation in it at all.
 *
 * Two regions: a rail of destinations down the left, and the application bar
 * above whatever the route renders. The rail is the thing that scales -- a
 * sixth screen is a row in `lib/nav.ts`, not another link crowded into a bar
 * that is already 449px tall at 420px wide.
 */
export function AppShell() {
  const session = useSession();
  const [collapsed, setCollapsed] = useState(readNavCollapsed);
  const contentRef = useRef<HTMLDivElement>(null);
  useScrollToTopOnNavigate();
  useFocusOnNavigate(contentRef);
  useStickyStack();

  function toggleNav() {
    setCollapsed((previous) => {
      writeNavCollapsed(!previous);
      return !previous;
    });
  }

  if (session.isPending) {
    return (
      <main className="app-shell">
        <p className="status">Loading...</p>
      </main>
    );
  }

  // One answer for every screen. Before R.1 the dashboard showed the sign-in
  // panel and the other four showed a sentence with a link back to it.
  if (!session.data) {
    return <AuthPanel />;
  }

  return (
    <div className={collapsed ? "app-frame is-collapsed" : "app-frame"}>
      {/* First in the DOM, so it is the first thing a Tab reaches (R.2). */}
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <NavRail collapsed={collapsed} onToggle={toggleNav} />
      <div className="app-main">
        <TopBar user={session.data} />
        {/* `tabIndex={-1}` is what makes the skip link above actually move
            focus: an anchor to an element that cannot hold focus scrolls the
            page and leaves the keyboard where it was, which is the common way
            a skip link is shipped broken. */}
        <div
          className="app-content"
          id="main-content"
          ref={contentRef}
          tabIndex={-1}
        >
          <Outlet context={{ user: session.data } satisfies ShellContext} />
        </div>
      </div>
    </div>
  );
}

/**
 * Every navigation starts at the top of the new screen.
 *
 * The browser keeps the scroll position across a client-side route change, and
 * until R.1 that did not show: a deal was appended under the board and scrolled
 * itself into view. Now that each screen is its own page, going back to the
 * board landed mid-page with its title and controls above the fold — reported
 * from a screenshot of exactly that.
 *
 * A URL naming a row inside the screen is the exception: `?entry=`, `?note=`,
 * `?comment=` and `?task=` each scroll their own row into view (D-124, D-170),
 * and a reset here would fight them. `behavior: "instant"` because this is the
 * start of a new screen rather than movement within one.
 */
function useScrollToTopOnNavigate() {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const linked = ["entry", "note", "comment", "task"].some((level) =>
    params.has(level),
  );
  useEffect(() => {
    if (!linked) {
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }, [pathname, linked]);
}

/**
 * Tells the document how much sticky chrome this screen has (milestone R.2).
 *
 * `app/globals.css` turns it into `scroll-padding-top`, which is what keeps a
 * control that has just taken focus from being scrolled underneath the
 * application bar and the record band (WCAG 2.2's 2.4.11). A root attribute
 * rather than a prop, because the scrollport belongs to the document: the
 * same reason `lib/theme.ts` writes `data-theme` and `lib/density.ts` writes
 * `data-density` instead of threading either through the tree.
 */
function useStickyStack() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.documentElement.setAttribute(
      STICKY_ATTRIBUTE,
      stickyStack(pathname),
    );
  }, [pathname]);
}

/**
 * Every navigation also moves the keyboard (milestone R.2).
 *
 * Six screens in one shell means the rail is a persistent set of links, and
 * clicking one left focus on it while the whole screen changed underneath: the
 * next Tab continued through the rail rather than into what had just been
 * opened, and a screen reader was told nothing had happened. Focus moves to
 * the content region, so the next Tab is the first control of the new screen
 * and the screen's own heading is what gets read.
 *
 * Two things about it. **Not on the first render** — focus belongs to the
 * document on a page load, and taking it would interrupt a reader who has not
 * navigated anywhere. And `preventScroll`, because
 * `useScrollToTopOnNavigate` above and a `?entry=` link below both decide
 * where the screen sits; focus moving the viewport as well is how a reader
 * arriving at a linked row gets taken away from it.
 */
function useFocusOnNavigate(target: React.RefObject<HTMLElement | null>) {
  const { pathname } = useLocation();
  const landed = useRef(false);
  useEffect(() => {
    if (!landed.current) {
      landed.current = true;
      return;
    }
    target.current?.focus({ preventScroll: true });
  }, [pathname, target]);
}

type ShellContext = { user: User };

/**
 * The signed-in user, for the screen inside the shell. The shell has already
 * refused to render anything without one, which is what makes this non-null
 * where every page used to carry its own `if (!session.data)` branch.
 */
export function useShellUser(): User {
  return useOutletContext<ShellContext>().user;
}

function NavRail({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const location = useLocation();
  // The one count worth carrying in the rail: a task is the only thing in this
  // app with a deadline, so it is the only destination that can be late.
  const tasks = useMyTasks();
  const openTasks = (tasks.data ?? []).filter(
    (task) => task.completed_at === null,
  ).length;

  return (
    <nav className="nav-rail" aria-label="Sections">
      <Link className="nav-brand" to="/">
        <span className="brand-mark" aria-hidden="true">
          OT
        </span>
        <span className="nav-brand-name">OppTrail</span>
      </Link>

      <ul className="nav-list">
        {navItems.map((item) => {
          const active = isNavActive(item.path, location.pathname);
          return (
            <li key={item.path}>
              <Link
                className={active ? "nav-item is-active" : "nav-item"}
                to={item.path}
                aria-current={active ? "page" : undefined}
                title={collapsed ? item.label : undefined}
              >
                <span className="nav-label">{item.label}</span>
                {item.path === "/tasks" && openTasks > 0 && (
                  <span className="nav-count" aria-label={`${openTasks} open`}>
                    {openTasks}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        className="nav-toggle"
        onClick={onToggle}
        aria-expanded={!collapsed}
      >
        {collapsed ? "Expand navigation" : "Collapse navigation"}
      </button>
    </nav>
  );
}

/**
 * A screen names itself and carries its own controls (the idiom the dashboard
 * has had since 2.7, now the one every screen uses). The title is an `h1`
 * because the shell has none: the rail is navigation and the bar is chrome.
 */
export function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div className="page-title">
        <h1>{title}</h1>
        {subtitle}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}
