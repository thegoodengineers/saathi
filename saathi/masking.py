"""Mask secrets in a page snapshot before it leaves the device for the planner model."""
from __future__ import annotations

import copy
import re

from .safety import AADHAAR, CARD, _luhn_ok, is_secret_field

OTP_NEAR = re.compile(r"(\b(?:otp|one[\s-]?time (?:password|code)|verification code)\b[^0-9]{0,20})(\d{4,8})\b", re.I)


def mask_text(text: str) -> str:
    def _card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group())
        return "[card hidden]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else m.group()

    text = CARD.sub(_card, text)  # cards first: their digits would otherwise look like an Aadhaar
    text = AADHAAR.sub("[aadhaar hidden]", text)
    return OTP_NEAR.sub(lambda m: m.group(1) + "[otp hidden]", text)


def mask_snapshot(snapshot: dict) -> dict:
    out = copy.deepcopy(snapshot)
    for el in out.get("elements", []):
        if el.get("value"):
            el["value"] = "[hidden]" if is_secret_field(el) else mask_text(el["value"])
    out["text"] = mask_text(out.get("text", ""))
    return out
