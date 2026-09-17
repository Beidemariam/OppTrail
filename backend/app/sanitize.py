"""Server-side HTML sanitization (brief §4.5).

Today every user field is stored and returned as Markdown and rendered through
the frontend's `rehype-sanitize` pipeline. That client-side pass protects the
browser, not the database: anything that renders the same content elsewhere —
the PDF export, an email body in Phase 5 — sees the raw string. Sanitizing on
the way in is the companion the brief asks for, and the allowlist here is
deliberately the same one `markdownSanitizeSchema` uses in
`frontend/app/page.tsx`, so the two boundaries cannot drift apart silently.
"""

import nh3

ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"alt", "src", "title"},
    "td": {"align"},
    "th": {"align"},
}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_html(value: str) -> str:
    """Strip everything outside the allowlist, including every event-handler
    attribute and every `javascript:`/`data:` URL, and force `rel` on links.
    """
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes={tag: set(names) for tag, names in ALLOWED_ATTRIBUTES.items()},
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
