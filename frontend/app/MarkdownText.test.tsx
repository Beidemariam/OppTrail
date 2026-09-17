import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownText } from "./MarkdownText";

describe("MarkdownText", () => {
  it("renders Markdown rather than raw text", () => {
    const { container } = render(
      <MarkdownText content={"# Heading\n\n**bold** and `code`"} />,
    );

    expect(
      screen.getByRole("heading", { name: "Heading" }),
    ).toBeInTheDocument();
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("code")).toHaveTextContent("code");
  });

  it("renders GitHub-flavoured tables and strikethrough", () => {
    const { container } = render(
      <MarkdownText content={"| a | b |\n| - | - |\n| 1 | 2 |\n\n~~gone~~"} />,
    );

    expect(container.querySelector("table")).toBeInTheDocument();
    expect(container.querySelector("del")).toHaveTextContent("gone");
  });

  it("keeps links on the allowed protocols", () => {
    const { container } = render(
      <MarkdownText
        content={"[web](https://example.com) [mail](mailto:a@example.com)"}
      />,
    );

    const hrefs = [...container.querySelectorAll("a")].map((anchor) =>
      anchor.getAttribute("href"),
    );
    expect(hrefs).toEqual(["https://example.com", "mailto:a@example.com"]);
  });

  it("strips a javascript: link, which is the reason the allowlist exists", () => {
    const { container } = render(
      // eslint-disable-next-line no-script-url
      <MarkdownText content={"[click](javascript:alert(1))"} />,
    );

    const anchor = container.querySelector("a");
    expect(anchor?.getAttribute("href") ?? "").not.toContain("javascript:");
  });

  it("drops embedded HTML instead of rendering it", () => {
    const { container } = render(
      <MarkdownText
        content={'<img src=x onerror="alert(1)"><script>alert(1)</script>'}
      />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens external links in a new tab without handing over the opener", () => {
    const { container } = render(
      <MarkdownText content={"[web](https://example.com)"} />,
    );
    const anchor = container.querySelector("a");

    expect(anchor).toHaveAttribute("target", "_blank");
    expect(anchor).toHaveAttribute("rel", "noreferrer");
  });
});
