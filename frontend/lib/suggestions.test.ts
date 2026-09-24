import type { ChainedCommands } from "@tiptap/core";
import { describe, expect, it } from "vitest";

import {
  commandItems,
  entryHref,
  entryItems,
  peopleItems,
  slashCommands,
  suggestionTriggers,
  SUGGESTION_LIMIT,
  type SuggestionSources,
} from "./suggestions";

const sources: SuggestionSources = {
  opportunityId: 7,
  people: [
    { email: "alex@opptrail.test", name: "Alex Owner", role: "owner" },
    { email: "blair@opptrail.test", name: "Blair Editor", role: "editor" },
    { email: "casey@opptrail.test", name: "Casey Viewer", role: "viewer" },
  ],
  entries: [
    { id: 11, title: "Pricing pushback", type: "call" },
    { id: 12, title: "Security review", type: "meeting" },
  ],
};

/** A chain that records what was asked of it, so a slash command can be tested
 * without an editor — the same trick the toolbar's controls would need. */
function recordingChain(): { chain: ChainedCommands; calls: string[] } {
  const calls: string[] = [];
  const chain = new Proxy(
    {},
    {
      get:
        (_target, name) =>
        (...args: unknown[]) => {
          calls.push(
            `${String(name)}(${args.map((arg) => JSON.stringify(arg)).join(",")})`,
          );
          return chain;
        },
    },
  ) as ChainedCommands;
  return { chain, calls };
}

describe("people", () => {
  it("matches on the name as well as on the address", () => {
    expect(peopleItems("blair", sources).map((item) => item.id)).toEqual([
      "blair@opptrail.test",
    ]);
    // The point of the feature: the reader knows the name, the address is what
    // has to be written.
    expect(peopleItems("Casey V", sources).map((item) => item.id)).toEqual([
      "casey@opptrail.test",
    ]);
    expect(peopleItems("nobody", sources)).toEqual([]);
  });

  it("inserts the address the backend looks for, with a trailing space", () => {
    const [item] = peopleItems("alex", sources);
    expect(item).toMatchObject({
      label: "Alex Owner",
      detail: "alex@opptrail.test | owner",
      insert: "text",
      text: "@alex@opptrail.test ",
    });
  });

  it("offers everyone when nothing has been typed yet", () => {
    expect(peopleItems("", sources)).toHaveLength(3);
  });

  it("stops at the popup's limit", () => {
    const crowd = Array.from(
      { length: SUGGESTION_LIMIT + 4 },
      (_value, index) => ({
        email: `person${index}@opptrail.test`,
        name: `Person ${index}`,
        role: "editor",
      }),
    );
    expect(peopleItems("person", { ...sources, people: crowd })).toHaveLength(
      SUGGESTION_LIMIT,
    );
  });
});

describe("blocks", () => {
  it("offers the blocks matching what was typed", () => {
    expect(commandItems("list").map((item) => item.label)).toEqual([
      "Bulleted list",
      "Numbered list",
      // "Checklist" is a match for "list" too, which is the point of matching
      // on the label a reader sees rather than on a command name.
      "Checklist",
    ]);
    expect(commandItems("")).toHaveLength(slashCommands.length);
  });

  it("carries a command rather than text, and runs it on the chain", () => {
    const [quote] = commandItems("quote");
    expect(quote.insert).toBe("command");
    const { chain, calls } = recordingChain();
    if (quote.insert === "command") {
      quote.run(chain);
    }
    expect(calls).toEqual(["toggleBlockquote()"]);
  });

  it("only offers blocks the renderer can read back", () => {
    // The node set is `lib/markdown.ts`'s, and every slash command has to be a
    // command over one of them (D-108): a block the editor can write and
    // `MarkdownText` cannot render is a document that cannot be read.
    const { chain, calls } = recordingChain();
    slashCommands.forEach((command) => command.run(chain));
    expect(calls).toEqual([
      'setNode("heading",{"level":1})',
      'setNode("heading",{"level":2})',
      "toggleBulletList()",
      "toggleOrderedList()",
      "toggleTaskList()",
      "toggleBlockquote()",
      "toggleCodeBlock()",
      "setHorizontalRule()",
    ]);
  });
});

describe("entries", () => {
  it("matches on the title and on the id as it is written", () => {
    expect(entryItems("secur", sources).map((item) => item.label)).toEqual([
      "Security review",
    ]);
    expect(entryItems("11", sources).map((item) => item.label)).toEqual([
      "Pricing pushback",
    ]);
  });

  it("inserts a link into this opportunity's own timeline", () => {
    const [item] = entryItems("pricing", sources);
    expect(item).toMatchObject({
      label: "Pricing pushback",
      detail: "Call",
      insert: "link",
      text: "Pricing pushback",
      href: "/opportunities/7?entry=11",
    });
  });

  it("offers nothing with no opportunity in scope", () => {
    // A link to an entry is a link into one deal's timeline, so a composer
    // outside one has nothing to point at.
    expect(entryItems("", { ...sources, opportunityId: null })).toEqual([]);
  });
});

describe("the triggers", () => {
  it("are the three characters, each reading its own source", () => {
    expect(suggestionTriggers.map((trigger) => trigger.char)).toEqual([
      "@",
      "/",
      "#",
    ]);
    expect(
      suggestionTriggers.map((trigger) => trigger.items("", sources).length),
    ).toEqual([3, slashCommands.length, 2]);
  });
});

describe("entryHref", () => {
  it("is a relative path, so the sanitizer keeps it and the router follows it", () => {
    expect(entryHref(3, 17)).toBe("/opportunities/3?entry=17");
  });
});
