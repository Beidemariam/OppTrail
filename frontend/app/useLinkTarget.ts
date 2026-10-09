import { RefObject, useEffect, useRef } from "react";

/**
 * Scroll this element into view while a link is pointing at it.
 *
 * The behaviour shipped on the timeline card in milestone 3.2 (D-124) and was
 * written there, inline, because an entry was the only thing a URL could
 * name. Milestone 6.0 gives notes and comments the same treatment, so it is
 * one definition with three callers rather than three copies -- the same
 * reasoning as `useInlineEditor` and `useOpportunityItem`.
 *
 * `block: "center"` rather than `"start"`: the thing a reader followed a link
 * to is usually inside something larger, and putting a comment at the top of
 * the viewport hides the note and the entry that give it its meaning.
 */
export function useLinkTarget<T extends HTMLElement>(
  linked: boolean,
): RefObject<T | null> {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (linked) {
      ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [linked]);
  return ref;
}
