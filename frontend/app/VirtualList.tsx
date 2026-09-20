"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef, type Key, type ReactNode } from "react";

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
