import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { entryTypes } from "../lib/domain";
import { EntryTypeBadge } from "./EntryTypeBadge";

describe("EntryTypeBadge", () => {
  it.each(entryTypes)(
    "pairs the $value icon with its label, not colour alone",
    ({ value, label }) => {
      render(<EntryTypeBadge type={value} />);

      const badge = screen.getByText(label);
      expect(badge).toHaveClass("type-badge", value);

      const icon = badge.querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("aria-hidden", "true");
    },
  );

  it("gives every entry type its own icon shape", () => {
    const shapes = entryTypes.map(({ value }) => {
      const { container, unmount } = render(<EntryTypeBadge type={value} />);
      const markup = container.querySelector("svg")?.innerHTML;
      unmount();
      return markup;
    });

    expect(new Set(shapes).size).toBe(entryTypes.length);
  });
});
