"""The one action the planner may propose per step, and the safety layer's verdict on it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

KINDS = ("click", "type", "navigate", "ask_user", "say", "done")
Verdict = Literal["allow", "confirm", "block"]


class BadPlannerReply(ValueError):
    """The model answered, but not with one usable action. Nothing is run for such a reply."""


def _element_id(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        v = value.strip()
        if v.lower() in ("", "null", "none"):
            return None
        if v.isascii() and v.isdigit():
            return int(v)
    # Never guess ("e5" is not element 5): a wrong guess would act on the wrong element.
    raise BadPlannerReply(f"invalid element id: {value!r}")


@dataclass
class Action:
    kind: str
    target: int | None = None  # element id from the page snapshot
    text: str = ""  # text to type, question to ask, or words to say
    url: str = ""
    reason: str = ""  # the planner's own one-line explanation, narrated to the user

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        kind = str(d.get("kind", "")).strip()
        if kind not in KINDS:
            raise BadPlannerReply(f"unknown action kind: {kind!r}")

        def field_text(key: str) -> str:  # models often send null for unused fields; that is not "None"
            return "" if d.get(key) is None else str(d[key])

        url = field_text("url")
        try:
            urlsplit(url)
        except ValueError as e:
            raise BadPlannerReply(f"invalid url: {url!r}") from e
        return cls(
            kind=kind,
            target=_element_id(d.get("target")),
            text=field_text("text"),
            url=url,
            reason=field_text("reason"),
        )


@dataclass
class Decision:
    verdict: Verdict
    reason: str = ""
