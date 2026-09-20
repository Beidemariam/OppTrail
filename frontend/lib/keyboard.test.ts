import { describe, expect, it, vi } from "vitest";

import {
  chordFor,
  isTypingTarget,
  shortcutGroups,
  submitFormOnModEnter,
  submitOnModEnter,
  type KeyStroke,
} from "./keyboard";

function stroke(overrides: Partial<KeyStroke> & { key: string }): KeyStroke {
  return {
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    shiftKey: false,
    target: null,
    ...overrides,
  };
}

describe("isTypingTarget", () => {
  it.each(["input", "textarea", "select"])("is true for a %s", (tag) => {
    expect(isTypingTarget(document.createElement(tag))).toBe(true);
  });

  it("is true for a contenteditable element", () => {
    const element = document.createElement("div");
    element.contentEditable = "true";
    // jsdom does not derive isContentEditable from the attribute.
    Object.defineProperty(element, "isContentEditable", { value: true });
    expect(isTypingTarget(element)).toBe(true);
  });

  it("is false for an ordinary element and for nothing at all", () => {
    expect(isTypingTarget(document.createElement("article"))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});

describe("chordFor", () => {
  it("reads Ctrl K and Cmd K as the same chord", () => {
    expect(chordFor(stroke({ key: "k", ctrlKey: true }), "")).toBe("mod+k");
    expect(chordFor(stroke({ key: "K", metaKey: true }), "")).toBe("mod+k");
  });

  it("still answers Ctrl K and Escape while the user is typing", () => {
    const target = document.createElement("input");
    expect(chordFor(stroke({ key: "k", ctrlKey: true, target }), "")).toBe(
      "mod+k",
    );
    expect(chordFor(stroke({ key: "Escape", target }), "")).toBe("Escape");
  });

  it("ignores single keys typed into a field", () => {
    const target = document.createElement("textarea");
    expect(chordFor(stroke({ key: "c", target }), "")).toBeNull();
    expect(chordFor(stroke({ key: "/", target }), "")).toBeNull();
  });

  it("completes a g sequence against the pending prefix", () => {
    expect(chordFor(stroke({ key: "g" }), "")).toBe("g");
    expect(chordFor(stroke({ key: "d" }), "g")).toBe("g d");
  });

  it("leaves Alt-modified and shifted keys to the browser", () => {
    expect(chordFor(stroke({ key: "c", altKey: true }), "")).toBeNull();
    expect(chordFor(stroke({ key: "J", shiftKey: true }), "")).toBeNull();
  });

  it("does not claim Enter from something that already answers it", () => {
    const button = document.createElement("button");
    expect(chordFor(stroke({ key: "Enter", target: button }), "")).toBeNull();
    const card = document.createElement("article");
    expect(chordFor(stroke({ key: "Enter", target: card }), "")).toBe("Enter");
  });

  it("reads Ctrl Enter as the composer submit", () => {
    expect(chordFor(stroke({ key: "Enter", metaKey: true }), "")).toBe(
      "mod+Enter",
    );
  });

  it("means nothing for an unbound modified key", () => {
    expect(chordFor(stroke({ key: "s", ctrlKey: true }), "")).toBeNull();
  });
});

describe("the published map", () => {
  it("documents each chord once", () => {
    const chords = shortcutGroups.flatMap((group) =>
      group.shortcuts.map((shortcut) => shortcut.chord),
    );
    expect(new Set(chords).size).toBe(chords.length);
  });

  it("describes every chord it lists", () => {
    for (const group of shortcutGroups) {
      for (const shortcut of group.shortcuts) {
        expect(shortcut.keys.length).toBeGreaterThan(0);
        expect(shortcut.description.length).toBeGreaterThan(0);
      }
    }
  });
});

describe("submitOnModEnter", () => {
  it("submits on Ctrl Enter and on Cmd Enter, and not on Enter alone", () => {
    const submit = vi.fn();
    const preventDefault = vi.fn();
    const handler = submitOnModEnter(submit);

    handler({
      key: "Enter",
      metaKey: false,
      ctrlKey: false,
      preventDefault,
    } as never);
    expect(submit).not.toHaveBeenCalled();

    handler({
      key: "Enter",
      metaKey: false,
      ctrlKey: true,
      preventDefault,
    } as never);
    handler({
      key: "Enter",
      metaKey: true,
      ctrlKey: false,
      preventDefault,
    } as never);
    expect(submit).toHaveBeenCalledTimes(2);
    expect(preventDefault).toHaveBeenCalledTimes(2);
  });
});

describe("submitFormOnModEnter", () => {
  it("submits the form the keystroke happened in", () => {
    const form = document.createElement("form");
    const field = document.createElement("textarea");
    form.append(field);
    document.body.append(form);
    form.requestSubmit = vi.fn();

    const preventDefault = vi.fn();
    submitFormOnModEnter()({
      key: "Enter",
      metaKey: true,
      ctrlKey: false,
      currentTarget: field,
      preventDefault,
    } as never);

    expect(form.requestSubmit).toHaveBeenCalledOnce();
    expect(preventDefault).toHaveBeenCalledOnce();
    form.remove();
  });

  it("does nothing outside a form", () => {
    const loose = document.createElement("textarea");
    const preventDefault = vi.fn();
    submitFormOnModEnter()({
      key: "Enter",
      ctrlKey: true,
      metaKey: false,
      currentTarget: loose,
      preventDefault,
    } as never);
    expect(preventDefault).not.toHaveBeenCalled();
  });
});
