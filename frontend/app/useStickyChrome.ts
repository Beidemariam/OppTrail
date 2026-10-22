import { useEffect, type RefObject } from "react";

import { STICKY_CHROME_PROPERTY, stuckBottom } from "../lib/nav";

/**
 * Publishes how far down the screen the sticky chrome reaches, so
 * `scroll-padding-top` can be exactly that and no literal has to be kept in
 * step with a band's rendered height (`lib/nav.ts`'s `stuckBottom` for why
 * three literals were wrong three times).
 *
 * It lives with the element rather than in `app/AppShell.tsx`: the record band
 * is rendered by `OpportunityPanel`, appears and disappears with it, and
 * re-wraps as the window narrows — all facts the component holding the ref
 * already has, and none of which a path-based attribute could see. The
 * property is removed on unmount, so every other screen falls back to
 * `--sticky-bar` without anything having to say so.
 *
 * Two observers, because they answer different questions. `ResizeObserver`
 * catches the band growing a row as its contents wrap, which is the common
 * case. The `resize` listener catches the 900px breakpoint, where the band
 * stops being sticky: that changes `position` and need not change the band's
 * height at all, so the ResizeObserver can legitimately stay silent through
 * the one transition that matters most.
 */
export function useStickyChrome(ref: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const element = ref.current;
    if (element === null) {
      return;
    }

    const root = document.documentElement;
    const publish = () => {
      const style = window.getComputedStyle(element);
      const bottom = stuckBottom(
        style.position,
        style.top,
        element.getBoundingClientRect().height,
      );
      if (bottom === null) {
        root.style.removeProperty(STICKY_CHROME_PROPERTY);
      } else {
        root.style.setProperty(STICKY_CHROME_PROPERTY, `${bottom}px`);
      }
    };

    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(element);
    window.addEventListener("resize", publish);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", publish);
      root.style.removeProperty(STICKY_CHROME_PROPERTY);
    };
  }, [ref]);
}
