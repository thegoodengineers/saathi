"""Serve the mock site locally and open a browser that can never reach a real look-alike site."""
from __future__ import annotations

import contextlib
import functools
import http.server
import os
import threading
from pathlib import Path

MOCK_DIR = Path(__file__).resolve().parent.parent / "mock_site"


def _fake_offsite(url: str) -> tuple[str, str]:
    """Any off-site request is answered locally with our fake scam page, never the real internet."""
    if url.split("?")[0].endswith(".css"):
        return "text/css", (MOCK_DIR / "style.css").read_text(encoding="utf-8")
    return "text/html", (MOCK_DIR / "trap-kyc.html").read_text(encoding="utf-8")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def mock_server(port: int = 0):
    """Serve mock_site/ on 127.0.0.1; yields the base URL. Port 0 picks a free port."""
    handler = functools.partial(_Quiet, directory=str(MOCK_DIR))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/"
    finally:
        srv.shutdown()


@contextlib.contextmanager
def open_browser(headless: bool = True, sandbox_offsite: bool = True, mobile: bool = True):
    """Launch Edge (or Playwright's Chromium). With sandbox_offsite, any request that leaves
    127.0.0.1/localhost gets a fake page instead of touching the real internet. With mobile, the page
    runs as an Android phone (screen size, touch, mobile user agent): Saathi is phone-first."""
    from playwright.sync_api import sync_playwright

    channel = os.environ.get("SAATHI_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel=channel or None)
        if mobile:
            context = browser.new_context(**p.devices["Pixel 7"])
        else:
            context = browser.new_context(viewport={"width": 1100, "height": 760})
        context.set_default_timeout(5000)  # a missing element fails fast instead of hanging
        if sandbox_offsite:
            def _route(route):
                host = route.request.url.split("/")[2].split(":")[0] if "://" in route.request.url else ""
                if host in ("127.0.0.1", "localhost"):
                    route.continue_()
                else:
                    ctype, body = _fake_offsite(route.request.url)
                    route.fulfill(status=200, content_type=ctype, body=body)
            context.route("**/*", _route)
        try:
            yield context.new_page()
        finally:
            context.close()
            browser.close()
