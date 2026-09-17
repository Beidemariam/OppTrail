"""Server-side HTML sanitization (brief §4.5).

`app/sanitize.py` documents why this exists before rich text does: the
frontend's `rehype-sanitize` pass protects the browser, not the stored value,
and the PDF export and Phase 5's email bodies are other renderers of the same
string.
"""

import pytest

from app.sanitize import sanitize_html


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "<iframe src='https://evil.example'></iframe>",
        "<object data='x'></object>",
        "<style>body{display:none}</style>",
        "<form action='https://evil.example'><input name='x'></form>",
    ],
)
def test_dangerous_elements_are_removed(hostile: str) -> None:
    cleaned = sanitize_html(f"<p>Before</p>{hostile}<p>After</p>")

    assert "<script" not in cleaned
    assert "<iframe" not in cleaned
    assert "<object" not in cleaned
    assert "<style" not in cleaned
    assert "<form" not in cleaned
    assert "<p>Before</p>" in cleaned
    assert "<p>After</p>" in cleaned


def test_event_handler_attributes_are_removed() -> None:
    cleaned = sanitize_html('<p onclick="steal()" onmouseover="steal()">Hi</p>')

    assert cleaned == "<p>Hi</p>"


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
    ],
)
def test_only_http_https_and_mailto_links_survive(href: str) -> None:
    cleaned = sanitize_html(f'<a href="{href}">click</a>')

    assert "href" not in cleaned


@pytest.mark.parametrize("href", ["https://example.com/x", "http://example.com", "mailto:a@b.com"])
def test_allowed_link_schemes_are_kept(href: str) -> None:
    cleaned = sanitize_html(f'<a href="{href}">click</a>')

    assert href in cleaned


def test_links_are_given_a_safe_rel() -> None:
    cleaned = sanitize_html('<a href="https://example.com">click</a>')

    assert 'rel="noopener noreferrer"' in cleaned


def test_ordinary_markdown_output_passes_through_unchanged() -> None:
    markup = (
        "<h2>Deal notes</h2>"
        "<p><strong>Budget</strong> confirmed at <em>25k</em>.</p>"
        "<ul><li>Follow up Monday</li></ul>"
        "<pre><code>curl example.com</code></pre>"
        "<blockquote><p>Send the quote</p></blockquote>"
        "<table><thead><tr><th>Stage</th></tr></thead>"
        "<tbody><tr><td>Proposal</td></tr></tbody></table>"
    )

    assert sanitize_html(markup) == markup


def test_plain_text_is_untouched_apart_from_escaping() -> None:
    assert sanitize_html("Budget is < 30k & closing") == "Budget is &lt; 30k &amp; closing"
