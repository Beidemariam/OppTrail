"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef, type Key, type ReactNode } from "react";

/**
 * Renders only the rows near the scrollable viewport, so a column of 400
 * opportunities (roadmap Phase 2, "VirtualList") costs the same DOM size as
 * one of ten. `estimateItemSize` only seeds the initial layout — each row is
 * measured after mount (`measureElement`), so cards of different height
 * (a stalled badge, a wrapped title) do not drift out of position.
 *
 * The caller owns markup and keys; this only owns which indices exist in the
 * DOM and where they sit inside the scroll container.
 */
export function VirtualList<T>({
  items,
  estimateItemSize,
  gap = 0,
  activeIndex,
  renderItem,
  getItemKey,
  className,
  ariaLabel,
}: {
  items: T[];
  estimateItemSize: number;
  /** Space reserved below each row. Padding, not margin — a wrapper div with
   * only a margin-bottom child collapses that margin into its own, so it
   * would not be reflected in the measured row height. */
  gap?: number;
  /** The row that must be on screen — the keyboard cursor (milestone 2.4a).
   * Windowing means a row the reader moved to may not be mounted at all, so
   * the list scrolls to it rather than waiting for the caller to. `-1` for a
   * list the cursor is not currently inside. */
  activeIndex?: number;
  renderItem: (item: T, index: number) => ReactNode;
  getItemKey: (item: T, index: number) => Key;
  className?: string;
  ariaLabel?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => estimateItemSize + gap,
    overscan: 6,
  });

  useEffect(() => {
    if (activeIndex === undefined || activeIndex < 0) {
      return;
    }
    virtualizer.scrollToIndex(activeIndex);
  }, [activeIndex, virtualizer]);

  return (
    <div
      ref={scrollRef}
      className={className}
      aria-label={ariaLabel}
      style={{ overflowY: "auto" }}
    >
      <div
        style={{
          position: "relative",
          width: "100%",
          height: virtualizer.getTotalSize(),
        }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => {
          const item = items[virtualItem.index];
          return (
            <div
              key={getItemKey(item, virtualItem.index)}
              ref={virtualizer.measureElement}
              data-index={virtualItem.index}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                paddingBottom: gap,
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              {renderItem(item, virtualItem.index)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
