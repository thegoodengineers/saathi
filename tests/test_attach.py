"""`saathi attach`: drive a browser the user started themselves, over its remote-debugging port.

This starts a separate headless Chromium-family browser with its own throwaway profile and a
remote-debugging port (exactly how a user starts Opera for Saathi), attaches to it, and runs the
scam-check scenario through it.
"""
import os
import shutil
import socket
import subprocess
import time
import urllib.request

import pytest

from saathi.agent import run
from saathi.browser import connect_browser, mock_server
from saathi.planner import ScriptedPlanner
from saathi.safety import SafetyLayer
from saathi.scenarios import SCENARIOS


def _browser_exe() -> str | None:
    candidates = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  shutil.which("chromium"), shutil.which("google-chrome"), shutil.which("chromium-browser")]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    try:  # Playwright's own Chromium (what CI installs)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
        return path if os.path.exists(path) else None
    except Exception:
        return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def users_browser(tmp_path):
    exe = _browser_exe()
    if not exe:
        pytest.skip("no Chromium-family browser found")
    port = _free_port()
    proc = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={tmp_path}",
                             "--no-first-run", "--no-default-browser-check", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            break
        except OSError:
            time.sleep(0.3)
    else:
        proc.kill()
        pytest.fail("browser did not open its debugging port")
    yield port, proc
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_attach_runs_the_scam_check_in_the_users_own_browser(users_browser):
    port, proc = users_browser
    sc = next(s for s in SCENARIOS if s.name == "sms-scam-check")
    with mock_server() as base, connect_browser(port, base + sc.page) as page:
        res = run(sc.goal, page, ScriptedPlanner(list(sc.script)), SafetyLayer(),
                  ask_user=lambda q: "no", narrate=lambda m: None)
        assert res.steps[0].decision.verdict == "block" and not res.steps[0].executed
        assert res.unsafe_executed == []
        assert page.url.startswith(base) and page.is_visible("#bill")
    assert proc.poll() is None  # disconnecting leaves the user's browser running


def test_attach_explains_how_to_start_the_browser_when_none_is_running():
    with pytest.raises(SystemExit) as e:
        with connect_browser(_free_port()):
            pass
    assert "--remote-debugging-port" in str(e.value)
