"""Mask secrets in a page snapshot before it leaves the device for the planner model."""
from __future__ import annotations

import copy
import re

from .safety import AADHAAR, CARD, _luhn_ok, is_secret_field

OTP_WORDS = r"(?:otp|one[\s-]?time (?:password|code)|verification code)"
OTP_NEAR = re.compile(rf"(\b{OTP_WORDS}\b[^0-9]{{0,20}})(\d{{4,8}})\b", re.I)
# "482913 is your OTP", the usual SMS wording: the code comes before the word.
OTP_BEFORE = re.compile(rf"\b\d{{4,8}}(\s+(?:is|as)\s+(?:your|the)\s+{OTP_WORDS}\b)", re.I)
# Element fields the planner sees besides the value; any of them can show a number from the page.
ELEMENT_TEXT = ("text", "label", "placeholder", "href")


def mask_text(text: str) -> str:
    def _card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group())
        return "[card hidden]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else m.group()

    text = CARD.sub(_card, text)  # cards first: their digits would otherwise look like an Aadhaar
    text = AADHAAR.sub("[aadhaar hidden]", text)
    text = OTP_NEAR.sub(lambda m: m.group(1) + "[otp hidden]", text)
    return OTP_BEFORE.sub(lambda m: "[otp hidden]" + m.group(1), text)


def mask_snapshot(snapshot: dict) -> dict:
    out = copy.deepcopy(snapshot)
    for el in out.get("elements", []):
        if el.get("value"):
            el["value"] = "[hidden]" if is_secret_field(el) else mask_text(el["value"])
        for key in ELEMENT_TEXT:
            if el.get(key):
                el[key] = mask_text(el[key])
    for key in ("text", "title", "url"):
        out[key] = mask_text(out.get(key) or "")
    return out
