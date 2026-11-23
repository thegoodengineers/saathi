"""The one action the planner may propose per step, and the safety layer's verdict on it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

KINDS = ("click", "type", "navigate", "ask_user", "say", "done")
Verdict = Literal["allow", "confirm", "block"]


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
            raise ValueError(f"unknown action kind: {kind!r}")
        target = d.get("target")
        return cls(
            kind=kind,
            target=int(target) if target is not None else None,
            text=str(d.get("text", "")),
            url=str(d.get("url", "")),
            reason=str(d.get("reason", "")),
        )


@dataclass
class Decision:
    verdict: Verdict
    reason: str = ""
