"""The floating Saathi button: the worker that does the browser work, settings, and the window itself."""
import contextlib
import os
import queue
import threading

import pytest

from saathi.browser import mock_server, open_browser
from saathi.bubble import COLORS, Channel, load_settings, parse_narration, worker
from saathi.planner import ScriptedPlanner
from saathi.scenarios import SCENARIOS


def test_narration_maps_to_bubble_states():
    assert parse_narration("[block] no") == ("block", "no")
    assert parse_narration("[say] Opening the site.") == ("working", "Opening the site.")
    assert parse_narration("[confirm] Pay?") == ("ask", "Pay?")
    assert parse_narration("[done] All done") == ("done", "All done")


def test_settings_file_fills_only_missing_values(tmp_path, monkeypatch):
    f = tmp_path / "settings.env"
    f.write_text("# private\nSAATHI_MODEL_ID=model-from-file\nAWS_REGION=ap-south-1\n", encoding="utf-8")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("SAATHI_MODEL_ID", raising=False)
    load_settings(f)
    assert os.environ["SAATHI_MODEL_ID"] == "model-from-file"
    assert os.environ["AWS_REGION"] == "us-east-1"  # already set wins


def _start(scenario: str):
    sc = next(s for s in SCENARIOS if s.name == scenario)

    @contextlib.contextmanager
    def open_page():
        with mock_server() as base, open_browser(headless=True) as page:
            page.goto(base + sc.page)
            yield page

    ch = Channel()
    t = threading.Thread(target=worker, args=(ch, open_page, lambda: ScriptedPlanner(list(sc.script))), daemon=True)
    t.start()
    assert ch.events.get(timeout=60)[0] == "idle"  # browser ready
    ch.commands.put(sc.goal)
    return ch, t


def _events_until_done(ch, answer=None):
    """Collect bubble events for one task; reply to questions; stop once it is done and quiet."""
    seen = []
    while True:
        state, msg = ch.events.get(timeout=60)
        seen.append((state, msg))
        if state == "ask" and answer:
            ch.answers.put(answer)
        if state == "done":
            with contextlib.suppress(queue.Empty):
                while True:
                    seen.append(ch.events.get(timeout=2))
            return seen


def test_bubble_worker_refuses_the_scam_link_and_reports_the_real_bill():
    ch, t = _start("sms-scam-check")
    seen = _events_until_done(ch)
    assert any(s == "block" and "imitates" in m for s, m in seen)
    assert any(s == "done" and "that SMS was a scam" in m for s, m in seen)
    ch.commands.put(None)
    t.join(30)
    assert not t.is_alive()


def test_bubble_worker_asks_before_paying_and_uses_the_answer():
    ch, t = _start("normal-bill-payment")
    seen = _events_until_done(ch, answer="yes")
    asks = [m for s, m in seen if s == "ask"]
    assert asks and any("Pay" in m for m in asks)
    ch.commands.put(None)
    t.join(30)


def test_bubble_window_shows_state_and_sends_commands():
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no screen available")
    from saathi.bubble import Bubble

    ch = Channel()
    b = Bubble(ch)
    try:
        ch.events.put(("block", "namma-p0wer.in imitates nammapower.in"))
        b._poll()
        b.root.update()
        assert b.canvas.itemcget(b.circle, "fill") == COLORS["block"]
        assert "imitates" in b.status.cget("text")
        b.entry.insert(0, "open flipkart")
        b.submit()
        assert ch.commands.get_nowait() == "open flipkart"
        ch.events.put(("ask", "Shall I go ahead?"))
        b._poll()
        b.answer("no")
        assert ch.answers.get_nowait() == "no" and not b.waiting
    finally:
        b.root.destroy()
