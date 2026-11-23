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
    runs as an Android phone (screen size, touch, mobile user agent); otherwise as a PC browser."""
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


_LOCAL = os.environ.get("LOCALAPPDATA", "")
_PF = os.environ.get("PROGRAMFILES", r"C:\Program Files")
_PF86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
# Where each Chromium-family browser usually lives (Windows, macOS, Linux command names).
BROWSERS = {
    "chrome": [rf"{_PF}\Google\Chrome\Application\chrome.exe", rf"{_LOCAL}\Google\Chrome\Application\chrome.exe",
               "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium", "chromium-browser"],
    "edge": [rf"{_PF86}\Microsoft\Edge\Application\msedge.exe", rf"{_PF}\Microsoft\Edge\Application\msedge.exe",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "microsoft-edge"],
    "opera": [rf"{_LOCAL}\Programs\Opera\opera.exe", "/Applications/Opera.app/Contents/MacOS/Opera", "opera"],
    "opera-gx": [rf"{_LOCAL}\Programs\Opera GX\opera.exe", "/Applications/Opera GX.app/Contents/MacOS/Opera"],
    "brave": [rf"{_PF}\BraveSoftware\Brave-Browser\Application\brave.exe",
              rf"{_LOCAL}\BraveSoftware\Brave-Browser\Application\brave.exe",
              "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", "brave-browser"],
    "vivaldi": [rf"{_LOCAL}\Vivaldi\Application\vivaldi.exe", "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi", "vivaldi"],
}
NOT_DRIVABLE = {"firefox", "safari"}


def find_browser(name: str) -> str:
    import shutil

    name = name.lower()
    if name in NOT_DRIVABLE:
        raise SystemExit(f"{name.title()} cannot be driven from outside the browser. Use Chrome, Edge, Opera, "
                         "Brave or Vivaldi for now; a Saathi browser extension is the planned route for it.")
    if name not in BROWSERS:
        raise SystemExit(f"Unknown browser '{name}'. Choose one of: {', '.join(BROWSERS)}.")
    for cand in BROWSERS[name]:
        path = cand if os.path.isabs(cand) else shutil.which(cand)
        if path and os.path.exists(path):
            return path
    raise SystemExit(f"Could not find {name} on this computer.")


def launch_browser(name: str, port: int = 9222):
    """Open the user's browser as its own window with a separate Saathi profile (never the user's normal
    profile, so saved passwords and logins stay out of reach) and a local remote-debugging port.
    The window stays open after Saathi disconnects; closing it is up to the user."""
    import subprocess
    import time
    import urllib.request

    exe = find_browser(name)
    profile = Path(_LOCAL or Path.home()) / "saathi-profiles" / name
    profile.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                             "--no-first-run", "--no-default-browser-check", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            return proc
        except OSError:
            time.sleep(0.4)
    raise SystemExit(f"{name} opened but did not allow Saathi to connect on port {port}.")


@contextlib.contextmanager
def connect_browser(port: int = 9222, open_url: str | None = None):
    """Attach to a browser the user started themselves (Opera, Chrome, Edge: any Chromium browser run with
    --remote-debugging-port=PORT and its own --user-data-dir). Yields its most recent normal tab.
    On exit Saathi only disconnects; the user's browser and tabs stay open."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        except Exception as e:
            raise SystemExit(
                f"Could not reach a browser on port {port}. Start it first, e.g. Opera with:\n"
                f'  opera.exe --remote-debugging-port={port} --user-data-dir="%LOCALAPPDATA%\\saathi-opera"\n'
                f"({type(e).__name__})") from None
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        context.set_default_timeout(10000)
        tabs = [pg for pg in context.pages if pg.url.startswith(("http://", "https://", "about:blank"))]
        page = tabs[-1] if tabs else context.new_page()
        page.bring_to_front()
        if open_url:
            page.goto(open_url)
        yield page
