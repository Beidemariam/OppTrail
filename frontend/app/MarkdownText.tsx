import { Link } from "react-router";
import ReactMarkdown from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { linkProtocols } from "../lib/markdown";

/**
 * Note and comment bodies are user-written Markdown, so they are sanitized
 * before they are rendered.
 *
 * The protocol allowlist is the part that matters: without it, `[click](javascript:...)`
 * survives into an anchor. Keep `http`/`https`/`mailto` if this pipeline is
 * ever touched (CLAUDE.md, Frontend) — the list is `lib/markdown.ts`'s, shared
 * with the composer so the editor cannot produce a link this strips.
 *
 * A link to somewhere in this app is followed *in* this app (milestone 3.2,
 * **D-124**). The `#` trigger writes a relative href — `/opportunities/3?entry=17`
 * — and a plain anchor to one would reload the whole SPA to reach a route the
 * client router already holds, so a href with no protocol is rendered as a
 * router `Link`. The sanitizer's allowlist is what decides whether the href
 * survives at all, and it is unchanged: a relative href carries no protocol, so
 * it was always kept (`lib/markdown.ts`'s `isAllowedLinkHref` says the same
 * thing from the editor's side).
 *
 * The allowlist is **unchanged** by the rich composer (milestone 3.1), which
 * is what `docs/FEATURES.md` §4 asks: every node the editor can produce was
 * already renderable here. The one that had to be checked rather than assumed
 * is the checklist — `- [x] done` renders as a disabled checkbox, and the
 * ticked state survives this schema (`renders a checklist's boxes with the
 * state the writer gave them`), so nothing needed widening for it.
 */
export const markdownSanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [
      ...(defaultSchema.attributes?.a ?? []),
      "href",
      "title",
      "target",
      "rel",
    ],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: linkProtocols,
  },
};

export function MarkdownText({ content }: { content: string }) {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, markdownSanitizeSchema]]}
        components={{
          a: ({ children, href }) =>
            href && href.startsWith("/") ? (
              <Link to={href}>{children}</Link>
            ) : (
              <a href={href} rel="noreferrer" target="_blank">
                {children}
              </a>
            ),
          // A checklist's box is the only control this renderer draws, and
          // `remark-gfm` emits it with no name at all — which axe fails as
          // "Form elements must have labels", critically, for the whole
          // screen. What the box carries is the state, so that is what it is
          // named; the item's own words are read beside it as content.
          input: ({ node: _node, ...props }) => (
            <input
              {...props}
              aria-label={props.checked ? "Done" : "Not done"}
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
