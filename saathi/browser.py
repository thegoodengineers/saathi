"""Serve the mock site locally and open a browser that can never reach a real look-alike site."""
from __future__ import annotations

import contextlib
import functools
import http.server
import os
import threading
from pathlib import Path

MOCK_DIR = Path(__file__).resolve().parent.parent / "mock_site"
FAKE_OFFSITE = ("<html><body style='font:20px sans-serif;padding:40px;background:#fdecea'>"
                "<h1>Fake look-alike site (test)</h1><p>A real scam site would be here.</p></body></html>")


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
def open_browser(headless: bool = True, sandbox_offsite: bool = True):
    """Launch Edge (or Playwright's Chromium). With sandbox_offsite, any request that leaves
    127.0.0.1/localhost gets a fake page instead of touching the real internet."""
    from playwright.sync_api import sync_playwright

    channel = os.environ.get("SAATHI_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel=channel or None)
        context = browser.new_context(viewport={"width": 1100, "height": 760})
        if sandbox_offsite:
            def _route(route):
                host = route.request.url.split("/")[2].split(":")[0] if "://" in route.request.url else ""
                if host in ("127.0.0.1", "localhost"):
                    route.continue_()
                else:
                    route.fulfill(status=200, content_type="text/html", body=FAKE_OFFSITE)
            context.route("**/*", _route)
        try:
            yield context.new_page()
        finally:
            context.close()
            browser.close()
