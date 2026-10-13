"""The model's JSON, read as a filter this board actually has.

Milestone 6.4, `docs/FEATURES.md` §14's "natural-language filter
construction -- 'deals stuck in negotiation over 50k' produces a filter the
user sees and applies. This is the safest high-value AI feature here, because
its output is a query the user can inspect."

**The inspection is only worth something if what is shown is what would be
applied** (**D-186**), which is what this module is for. Everything here
treats the model's answer as untrusted text in exactly the way ADR 0006
treats a custom value read back from a JSON column: parse it against what the
application actually offers, keep what fits, and *name* what did not. A
proposal that quietly dropped half of a request is a proposal somebody would
accept believing it did more.

Nothing here applies anything. The answer goes to the screen, the reader
presses Apply or does not, and applying is the ordinary URL write the filter
bar already does -- so the AI is not the actor in anything, which is ADR
0012's rule read for a feature that produces a query rather than a sentence.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .schemas import FILTER_SORT_FIELDS, STAGES, AiFilterProposal, AiFilterResponse

# Everything the proposal can carry. A key outside this set is reported as
# ignored rather than silently dropped -- the model inventing `region` is
# worth telling somebody about, because it usually means the request asked
# for something this board cannot express.
KNOWN_KEYS: tuple[str, ...] = tuple(AiFilterProposal.model_fields)

MAX_TEXT = 100


def parse_filter_answer(answer: str) -> AiFilterResponse:
    """The model's reply, as a proposal plus what was thrown away."""
    payload = _json_object(answer)
    if payload is None:
        return AiFilterResponse(
            proposal=AiFilterProposal(),
            ignored=["the answer was not JSON"],
            empty=True,
        )

    kept: dict[str, Any] = {}
    ignored: list[str] = []

    # What the model says it could not express, in the person's own words.
    # Asked for explicitly because the alternative is silence: `ignored`
    # below only names keys the model *sent* and this dropped, so a model
    # that obeys the prompt and omits an unexpressible request reports
    # nothing at all. Found by asking the running system "Gavin deals
    # closing before December in EMEA" and watching two thirds of it
    # disappear without a word.
    ignored.extend(_phrases(payload.pop("unused", None)))

    for key, raw in payload.items():
        if key not in KNOWN_KEYS:
            ignored.append(key)
            continue
        value = _value_for(key, raw)
        if value is None:
            ignored.append(key)
            continue
        kept[key] = value

    # A direction with nothing to sort says nothing: the board's own default
    # sort would apply and the reader would see a chip that changed no rows.
    if "direction" in kept and "sort" not in kept:
        del kept["direction"]
        ignored.append("direction")

    return AiFilterResponse(
        proposal=AiFilterProposal(**kept),
        ignored=sorted(set(ignored)),
        empty=not kept,
    )


MAX_UNUSED = 5


def _phrases(raw: Any) -> list[str]:
    """The model's own list of what it could not express.

    Bounded and flattened like any other text from this answer: it is shown
    on screen, so a newline would break the row it sits in and an unbounded
    list would be a paragraph where a note belongs.
    """
    if not isinstance(raw, list):
        return []
    phrases = []
    for item in raw[:MAX_UNUSED]:
        if isinstance(item, str) and item.strip():
            phrases.append(" ".join(item.split())[:MAX_TEXT])
    return phrases


def _json_object(answer: str) -> dict[str, Any] | None:
    """The JSON object in the answer, however it was wrapped.

    The prompt says "JSON only - no prose, no code fence" and a model will
    sometimes answer with one anyway. Stripping a fence is not defensiveness
    about a hypothetical: it is the single most common way this call fails,
    and the alternative is telling a person their request was not understood
    when it was understood perfectly and dressed up.
    """
    text = answer.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _value_for(key: str, raw: Any) -> Any | None:
    """One value, or `None` if this board cannot use it."""
    if key == "stage":
        return raw if raw in STAGES else None
    if key == "sort":
        return raw if raw in FILTER_SORT_FIELDS else None
    if key == "direction":
        return raw if raw in ("asc", "desc") else None
    if key == "stalled":
        return raw if isinstance(raw, bool) else None
    if key in ("min_value", "max_value"):
        return _number(raw)
    # `q`: free text, bounded and flattened. A newline in a filter chip is a
    # chip that breaks the row it sits in.
    if not isinstance(raw, str) or not raw.strip():
        return None
    return " ".join(raw.split())[:MAX_TEXT]


def _number(raw: Any) -> str | None:
    """A money bound as the string the URL carries.

    Accepts what a model actually answers with -- `50000`, `50000.0`,
    `"50000"` -- and refuses `"50k"`, which is the request's own wording
    rather than a number. Returned as a string because that is what the view
    state holds and what the board compares; `Decimal` here would be a type
    that exists for three lines.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    return format(value.normalize(), "f") if value >= 0 else None
