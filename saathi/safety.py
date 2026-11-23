"""Safety layer: every action the planner proposes passes through `SafetyLayer.check`.

Rules, in order:
1. Never type into a secret field (password, OTP, PIN, CVV, card, Aadhaar).
2. Never type a value that looks like a secret (Aadhaar or card number), whatever the field.
3. Only type what the user said: every word and number typed must come from the user's own words.
   Pages cannot supply values, so instructions hidden in a page cannot make Saathi type anything.
4. Only go to sites the user allowed or named ("open flipkart"). A site that imitates a known one is
   flagged as a likely scam, even if the user named something similar. Only web pages (http, https)
   are opened: never local files, data: pages or browser settings. Phone, SMS and email links ask first.
5. Ask before anything irreversible (pay, confirm, submit, delete, send, transfer).
6. On a page that shows scam signs (urgency + KYC/blocked/password), ask before any action.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from .actions import Action, Decision

SECRET_FIELD = re.compile(
    r"otp|one[\s-]?time|passcode|password|passwd|\b[mt]?pin\b|upi[\s-]?pin|cvv|cvc|security[\s-]?code|card[\s-]?number|aadhaa?r",
    re.I,
)
SECRET_AUTOCOMPLETE = {"one-time-code", "current-password", "new-password", "cc-number", "cc-csc"}
IRREVERSIBLE = re.compile(
    r"\b(pay|confirm|submit|place order|buy|transfer|send money|send|delete|remove|verify and pay)\b", re.I
)
# 12 digits (optionally 4-4-4), but not part of a longer number such as a card number.
AADHAAR = re.compile(r"(?<![\d-])(?<!\d )\d{4}[ -]?\d{4}[ -]?\d{4}(?![ -]?\d)")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SCAM_URGENCY = re.compile(r"urgent|immediately|within \d+ hours?|in \d+ hours?|will be (?:blocked|suspended)", re.I)
SCAM_ASK = re.compile(r"\bkyc\b|aadhaa?r|password|\botp\b|refund", re.I)
WEB_SCHEMES = {"http", "https"}
CONTACT_SCHEMES = {"tel": "call", "sms": "send an SMS to", "mailto": "email"}
HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "@": "a"})


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def looks_like_secret(text: str) -> bool:
    if AADHAAR.search(text):
        return True
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return True
    return False


def is_secret_field(el: dict) -> bool:
    if (el.get("type") or "").lower() == "password":
        return True
    if (el.get("autocomplete") or "").lower() in SECRET_AUTOCOMPLETE:
        return True
    words = " ".join(str(el.get(k) or "") for k in ("name", "id_attr", "label", "placeholder"))
    return bool(SECRET_FIELD.search(words))


def is_irreversible(el: dict) -> bool:
    return bool(IRREVERSIBLE.search(str(el.get("text") or el.get("label") or "")))


def _norm_host(host: str) -> str:
    host = host.lower().removeprefix("www.")
    return host.translate(HOMOGLYPHS).replace("rn", "m").replace("vv", "w").replace("-", "")


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def imitates(host: str, allowed: set[str]) -> str | None:
    """Return the allowed host that `host` imitates, if any."""
    n = _norm_host(host)
    for good in allowed:
        g = _norm_host(good)
        if host != good and (n == g or (len(g) > 5 and _edit_distance(n, g) <= 2)):
            return good
    return None


WORD = re.compile(r"[^\W\d_]+|\d+")  # runs of letters (any script, so Kannada works) or of digits
GENERIC_LABELS = {"www", "m", "com", "in", "org", "net", "co", "gov", "nic", "edu", "ac", "info", "io"}


def _words(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


def scam_signs(page_text: str) -> bool:
    return bool(SCAM_URGENCY.search(page_text) and SCAM_ASK.search(page_text))


@dataclass
class SafetyLayer:
    allowed_hosts: set[str] = field(default_factory=lambda: {"127.0.0.1", "localhost"})
    # Names users would recognise, used only to spot imitations (e.g. a look-alike of the real board).
    known_brands: set[str] = field(default_factory=lambda: {"nammapower.in"})
    user_words: list[str] = field(default_factory=list)  # the goal + every answer the user gave
    enabled: bool = True

    def hear(self, text: str) -> None:
        """Record something the user said; only these words may be typed."""
        self.user_words.append(text)

    def _said_words(self) -> set[str]:
        return set().union(*(_words(w) for w in self.user_words))

    def _user_said(self, text: str) -> bool:
        """Every word and number in `text` must be one the user said (order and spacing may differ:
        "atta 1kg" is fine after "add 1 kg atta"). A number written on a page never qualifies."""
        t = _words(text)
        return bool(t) and t <= self._said_words()

    def _user_named(self, host: str) -> bool:
        """The user named this site: every meaningful part of its address is a word they said.
        "open flipkart" allows www.flipkart.com, but not flipkart-offers.shop or flipkart.scam.in."""
        labels = [lab for lab in host.lower().split(".") if lab and lab not in GENERIC_LABELS]
        return bool(labels) and all(lab in self._said_words() for lab in labels)

    def _host_decision(self, url: str) -> Decision | None:
        parts = urlparse(url)
        if parts.scheme.lower() not in WEB_SCHEMES:  # file:, data:, javascript:, chrome:... have no host to check
            return Decision("block", "That is not a web page (it could be a file on this device or a hidden page), so I won't open it.")
        host = parts.hostname or ""
        if not host or host in self.allowed_hosts:
            return None
        fake_of = imitates(host, self.allowed_hosts | self.known_brands)
        if fake_of:
            return Decision("block", f"{host} imitates {fake_of}; this looks like a scam site, so I won't open it.")
        if self._user_named(host):
            return None
        return Decision("block", f"{host} is not a site you named or allowed, so I won't open it.")

    def check(self, action: Action, snapshot: dict) -> Decision:
        if not self.enabled:
            return Decision("allow", "safety layer off")
        if action.kind in ("say", "ask_user", "done"):
            return Decision("allow")
        if action.kind == "navigate":
            target_url = urljoin(snapshot.get("url", ""), action.url)
            return self._host_decision(target_url) or Decision("allow")

        el = next((e for e in snapshot.get("elements", []) if e.get("id") == action.target), None)
        if el is None:
            return Decision("block", "That element is not on this page.")

        if action.kind == "type":
            if is_secret_field(el):
                return Decision("block", "This box asks for a secret (OTP, password, PIN or card). Please type it yourself; I never do.")
            if looks_like_secret(action.text):
                return Decision("block", "That looks like an Aadhaar or card number. I never type those.")
            if not self._user_said(action.text):
                return Decision("block", f"You did not tell me '{action.text}', so I won't type it.")
        if action.kind == "click":
            href = (el.get("href") or "").strip()
            scheme = urlparse(href).scheme.lower()
            if scheme in CONTACT_SCHEMES:  # a scam page's "call our helpline" link
                target = href.split(":", 1)[1].split("?")[0]
                return Decision("confirm", f"This will {CONTACT_SCHEMES[scheme]} {target}. Shall I go ahead?")
            if href and scheme != "javascript":  # javascript: links only run the page's own script, like a button
                hd = self._host_decision(urljoin(snapshot.get("url", ""), href))
                if hd:
                    return hd
            if is_irreversible(el):
                return Decision("confirm", f"This will '{el.get('text') or el.get('label')}'. Shall I go ahead?")
        if scam_signs(snapshot.get("text", "")):
            return Decision("confirm", "Careful: this page shows signs of a scam (urgent threats, asks for KYC or passwords). Shall I continue?")
        return Decision("allow")
