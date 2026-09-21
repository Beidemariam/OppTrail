import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  AA_LARGE_RATIO,
  AA_TEXT_RATIO,
  contrastRatio,
  parseHex,
  relativeLuminance,
} from "./contrast";

/**
 * The contrast audit `docs/DESIGN-SYSTEM.md` asks for, run against the tokens
 * themselves rather than against a screenshot — in both themes, because the
 * document is explicit that inversion does not preserve a ratio.
 *
 * The pairs below are the ones the stylesheet actually paints. Adding a token
 * is not enough to be covered here; putting text on a surface is what puts a
 * row in this table.
 */

const css = readFileSync(
  path.join(__dirname, "..", "app", "globals.css"),
  "utf8",
);

/** The declarations inside one selector's block, as a token map. */
function tokenBlock(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  expect(start, `${selector} must declare the palette`).toBeGreaterThan(-1);
  const block = css.slice(start, css.indexOf("\n}", start));
  const tokens: Record<string, string> = {};
  for (const [, name, value] of block.matchAll(
    /^\s*(--[a-z0-9-]+):\s*([^;]+);/gm,
  )) {
    tokens[name] = value.trim();
  }
  return tokens;
}

const light = tokenBlock(":root");
const dark = { ...light, ...tokenBlock('[data-theme="dark"]') };

/** Resolves one level of `var(--x)` indirection, which is all the palette uses. */
function resolve(tokens: Record<string, string>, name: string): string {
  const value = tokens[name];
  expect(value, `token ${name} is declared`).toBeDefined();
  const reference = /^var\((--[a-z0-9-]+)\)$/.exec(value);
  return reference ? resolve(tokens, reference[1]) : value;
}

/** Every text-on-surface pair the stylesheet paints. */
const textPairs: Array<[string, string, string]> = [
  ["body copy on the app background", "--text-primary", "--bg-app"],
  ["body copy on a card", "--text-primary", "--bg-surface"],
  ["body copy on a sunken panel", "--text-primary", "--bg-sunken"],
  ["body copy on a hovered row", "--text-primary", "--bg-hover"],
  ["body copy on a selected card", "--text-primary", "--bg-selected"],
  ["a search highlight", "--text-primary", "--bg-highlight"],
  ["meta text on the app background", "--text-secondary", "--bg-app"],
  ["meta text on a card", "--text-secondary", "--bg-surface"],
  ["meta text on a sunken panel", "--text-secondary", "--bg-sunken"],
  ["meta text on a selected card", "--text-secondary", "--bg-selected"],
  ["body copy on a checked card", "--text-primary", "--bg-accent-soft"],
  ["meta text on a checked card", "--text-secondary", "--bg-accent-soft"],
  ["a link on the app background", "--text-link", "--bg-app"],
  ["a link on a card", "--text-link", "--bg-surface"],
  ["a link on a sunken panel", "--text-link", "--bg-sunken"],
  ["error text on a card", "--text-danger", "--bg-surface"],
  ["error text on a sunken panel", "--text-danger", "--bg-sunken"],
  ["the danger button's label", "--text-danger", "--bg-surface"],
  ["the stalled badge", "--text-warning", "--bg-warning"],
  ["the primary button", "--fill-accent-text", "--fill-accent"],
  ["the notification count", "--fill-danger-text", "--fill-danger"],
  ["a stage column's count", "--fill-neutral-text", "--fill-neutral"],
  ["a call badge", "--badge-text", "--badge-call"],
  ["an email badge", "--badge-text", "--badge-email"],
  ["a meeting badge", "--badge-text", "--badge-meeting"],
  ["a demo badge", "--badge-text", "--badge-demo"],
  ["a proposal badge", "--badge-text", "--badge-proposal"],
  ["a contract badge", "--badge-text", "--badge-contract"],
  ["a stage-change badge", "--badge-text", "--badge-stage"],
  ["an other badge", "--badge-text", "--badge-other"],
  ["a site-visit badge", "--badge-text", "--badge-site-visit"],
  ["an objection badge", "--badge-text", "--badge-objection"],
  ["a competitor-intel badge", "--badge-text", "--badge-competitor-intel"],
];

/** Pairs carrying meaning without text: focus rings, markers, borders. */
const nonTextPairs: Array<[string, string, string]> = [
  ["the focus ring on the app background", "--focus-ring", "--bg-app"],
  ["the focus ring on a card", "--focus-ring", "--bg-surface"],
  ["the focus ring on a sunken panel", "--focus-ring", "--bg-sunken"],
  ["the focus ring on a modal", "--focus-ring", "--bg-surface"],
  ["a timeline marker on a card", "--marker", "--bg-surface"],
  ["a selected card's border", "--border-accent", "--bg-surface"],
  ["the column a card would drop into", "--border-accent", "--bg-app"],
];

describe.each([
  ["light", light],
  ["dark", dark],
])("the %s palette", (_theme, tokens) => {
  it.each(textPairs)("keeps %s readable", (_what, foreground, background) => {
    expect(
      contrastRatio(resolve(tokens, foreground), resolve(tokens, background)),
    ).toBeGreaterThanOrEqual(AA_TEXT_RATIO);
  });

  it.each(nonTextPairs)("keeps %s visible", (_what, foreground, background) => {
    expect(
      contrastRatio(resolve(tokens, foreground), resolve(tokens, background)),
    ).toBeGreaterThanOrEqual(AA_LARGE_RATIO);
  });
});

describe("the ratio itself", () => {
  it("is 21 for black on white and 1 for a colour on itself", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#0b7c6e", "#0b7c6e")).toBeCloseTo(1, 5);
  });

  it("is symmetric, because an ordering of two colours is not a ratio", () => {
    expect(contrastRatio("#0b7c6e", "#ffffff")).toBeCloseTo(
      contrastRatio("#ffffff", "#0b7c6e"),
      10,
    );
  });

  it("reproduces the audit in docs/DESIGN-SYSTEM.md", () => {
    // The three pairs the document measures as failures, and the corrected
    // values that replace them.
    expect(contrastRatio("#0f9d8c", "#ffffff")).toBeCloseTo(3.38, 2);
    expect(contrastRatio("#d64545", "#ffffff")).toBeCloseTo(4.38, 2);
    expect(contrastRatio("#0b7c6e", "#ffffff")).toBeCloseTo(5.09, 2);
    expect(contrastRatio("#b33838", "#ffffff")).toBeCloseTo(5.93, 2);
  });

  it("reads both hex forms and rejects anything else", () => {
    expect(parseHex("#fff")).toEqual([255, 255, 255]);
    expect(parseHex("#0B2540")).toEqual([11, 37, 64]);
    expect(() => parseHex("teal")).toThrow(/not a hex colour/);
    expect(relativeLuminance("#000")).toBe(0);
  });
});
