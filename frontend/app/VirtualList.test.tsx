import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VirtualList } from "./VirtualList";

// vitest.setup.ts stubs offsetHeight/offsetWidth to a plausible viewport size
// -- jsdom never lays anything out, and without that stub the virtualizer
// (correctly) renders nothing into what it measures as a zero-height
// viewport.

function items(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: index,
    label: `Row ${index}`,
  }));
}

describe("VirtualList", () => {
  it("renders every row when the list is small", () => {
    render(
      <VirtualList
        items={items(5)}
        estimateItemSize={40}
        getItemKey={(item) => item.id}
        renderItem={(item) => <span>{item.label}</span>}
      />,
    );

    for (let i = 0; i < 5; i++) {
      expect(screen.getByText(`Row ${i}`)).toBeInTheDocument();
    }
  });

  it("does not mount every row for a 400-item list (roadmap: VirtualList, 400 opportunities)", () => {
    render(
      <VirtualList
        items={items(400)}
        estimateItemSize={40}
        getItemKey={(item) => item.id}
        renderItem={(item) => <span>{item.label}</span>}
      />,
    );

    // jsdom reports a zero-size viewport, so this is the overscan window
    // rather than a real "what fits on screen" count -- the point of the
    // assertion is that it is nowhere near 400, not the exact number.
    const rendered = screen.queryAllByText(/^Row \d+$/);
    expect(rendered.length).toBeGreaterThan(0);
    expect(rendered.length).toBeLessThan(50);

    // The rows nearest the top of the list are the ones in range; a row deep
    // in the list is not in the DOM at all.
    expect(screen.getByText("Row 0")).toBeInTheDocument();
    expect(screen.queryByText("Row 399")).not.toBeInTheDocument();
  });

  it("passes the item and index through to renderItem", () => {
    render(
      <VirtualList
        items={["a", "b", "c"]}
        estimateItemSize={20}
        getItemKey={(_, index) => index}
        renderItem={(item, index) => <span>{`${index}:${item}`}</span>}
      />,
    );

    expect(screen.getByText("0:a")).toBeInTheDocument();
    expect(screen.getByText("1:b")).toBeInTheDocument();
    expect(screen.getByText("2:c")).toBeInTheDocument();
  });

  it("applies the aria label and class name to the scroll container", () => {
    const { container } = render(
      <VirtualList
        items={items(2)}
        estimateItemSize={20}
        className="my-list"
        ariaLabel="Widgets"
        getItemKey={(item) => item.id}
        renderItem={(item) => <span>{item.label}</span>}
      />,
    );

    const region = container.querySelector(".my-list");
    expect(region).toHaveAttribute("aria-label", "Widgets");
  });
});
