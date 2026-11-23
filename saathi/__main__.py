"""Command line: python -m saathi {eval|demo|run|serve} ..."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _ask(question: str) -> str:
    return input(f"\n  Saathi asks: {question}\n  > ")


def main() -> None:
    # Windows terminals default to a code page without ₹ or Kannada; never crash on printing them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="saathi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eval", help="safety score with and without the safety layer")
    e.add_argument("--out", default="evidence")
    e.add_argument("--planner", choices=["script", "bedrock"], default="script")
    e.add_argument("--repeats", type=int, default=1)
    e.add_argument("--device", choices=["phone", "pc", "both"], default="both")
    d = sub.add_parser("demo", help="watch a scenario in a visible browser")
    d.add_argument("scenario", choices=["sms-scam-check", "hidden-instructions", "fake-kyc", "normal-bill-payment"])
    d.add_argument("--no-safety", action="store_true")
    d.add_argument("--slow", type=float, default=1.5, help="seconds to pause on each step")
    d.add_argument("--device", choices=["phone", "pc"], default="phone")
    r = sub.add_parser("run", help="do a task with the Bedrock planner")
    r.add_argument("goal")
    r.add_argument("--start", default="mock", help="'mock', 'mock/<page>.html' or a URL to start from")
    r.add_argument("--allow", nargs="*", default=[], help="extra hosts Saathi may open")
    r.add_argument("--device", choices=["phone", "pc"], default="phone")
    sh = sub.add_parser("shots", help="save phone screenshots of every step of a scenario")
    sh.add_argument("scenario", choices=["sms-scam-check", "hidden-instructions", "fake-kyc", "normal-bill-payment"])
    sh.add_argument("--no-safety", action="store_true")
    sh.add_argument("--out", default="evidence/screens")
    sh.add_argument("--device", choices=["phone", "pc"], default="phone")
    sub.add_parser("serve", help="only serve the mock site")
    at = sub.add_parser("attach", help="drive your own browser (Opera, Chrome, Edge) started with --remote-debugging-port")
    at.add_argument("--port", type=int, default=9222)
    at.add_argument("--browser", default=None,
                    help="open this browser for you first: chrome, edge, opera, opera-gx, brave, vivaldi")
    at.add_argument("--allow", nargs="*", default=[], help="sites Saathi may open, e.g. www.myscheme.gov.in")
    at.add_argument("--open", default=None, help="URL to open first")
    at.add_argument("--goal", default=None, help="do this one task and stop (otherwise asks in a loop)")
    b = sub.add_parser("bubble", help="the floating Saathi button: tap it and say what you need")
    b.add_argument("--browser", default="opera-gx", help="chrome, edge, opera, opera-gx, brave, vivaldi")
    b.add_argument("--port", type=int, default=9222)
    b.add_argument("--allow", nargs="*", default=[])
    su = sub.add_parser("setup", help="save your AI settings privately and add a Saathi desktop shortcut")
    su.add_argument("--browser", default="opera-gx")
    sc = sub.add_parser("shortcut", help="only add the Saathi desktop shortcut")
    sc.add_argument("--browser", default="opera-gx")
    a = ap.parse_args()

    from .agent import run
    from .browser import mock_server, open_browser
    from .safety import SafetyLayer

    if a.cmd == "eval":
        from .evaluate import checkpoint, score, write_evidence

        out = Path(a.out)
        rows = score(planner=a.planner, repeats=a.repeats,
                     devices=("phone", "pc") if a.device == "both" else (a.device,),
                     on_progress=lambda so_far: checkpoint(so_far, out, a.planner))
        md = write_evidence(rows, out, a.planner)
        print(md.read_text(encoding="utf-8"))
    elif a.cmd == "demo":
        from .planner import ScriptedPlanner
        from .scenarios import SCENARIOS

        sc = next(s for s in SCENARIOS if s.name == a.scenario)
        with mock_server() as base, open_browser(headless=False, mobile=a.device == "phone") as page:
            page.goto(base + sc.page)
            page.wait_for_timeout(int(a.slow * 1000))
            res = run(sc.goal, page, ScriptedPlanner(list(sc.script)), SafetyLayer(enabled=not a.no_safety),
                      ask_user=_ask, pause=a.slow)
            print(f"\nUnsafe actions that ran without your yes: {len(res.unsafe_executed)}")
            page.wait_for_timeout(4000)
    elif a.cmd == "run":
        from .planner import BedrockPlanner

        planner = BedrockPlanner()
        on_mock = a.start == "mock" or a.start.startswith("mock/")
        # On the mock site, keep the sandbox on: look-alike links get our fake page, never the internet.
        with mock_server() as base, open_browser(headless=False, sandbox_offsite=on_mock,
                                                 mobile=a.device == "phone") as page:
            start = base + a.start[5:] if on_mock else a.start  # "mock/sms.html" -> base + "sms.html"
            from urllib.parse import urlparse

            allowed = {"127.0.0.1", "localhost", urlparse(start).hostname or ""} | set(a.allow)
            page.goto(start)
            run(a.goal, page, planner, SafetyLayer(allowed_hosts=allowed), ask_user=_ask, pause=0.8)
            page.wait_for_timeout(4000)
    elif a.cmd == "attach":
        from urllib.parse import urlparse

        from .browser import connect_browser, launch_browser
        from .planner import BedrockPlanner

        planner = BedrockPlanner()
        if a.browser:
            launch_browser(a.browser, a.port)
        with connect_browser(a.port, a.open) as page:
            print(f"Connected to your browser tab: {page.url}")
            while True:
                goal = a.goal or input("\nSaathi > What should I do? (press Enter on an empty line to stop)\n  > ").strip()
                if not goal:
                    break
                # Allowed: the site you are on now, plus any you listed. Everything else is refused.
                allowed = {h for h in {urlparse(page.url).hostname or "", *a.allow} if h}
                print(f"Allowed sites: {', '.join(sorted(allowed)) or 'none (use --allow)'}")
                res = run(goal, page, planner, SafetyLayer(allowed_hosts=allowed), ask_user=_ask, pause=0.8)
                print(f"\nSaathi: {res.outcome or 'Stopped.'}")
                if a.goal:
                    break
        print("Disconnected. Your browser stays open.")
    elif a.cmd == "bubble":
        from .bubble import main as bubble_main

        bubble_main(a.browser, a.port, a.allow)
    elif a.cmd == "setup":
        from .bubble import setup

        setup(a.browser)
    elif a.cmd == "shortcut":
        from .bubble import create_shortcut

        print(create_shortcut(a.browser))
    elif a.cmd == "shots":
        from .shots import capture

        for f in capture(a.scenario, Path(a.out), safety=not a.no_safety, device=a.device):
            print(f)
    elif a.cmd == "serve":
        with mock_server(8765) as base:
            print(f"Mock site at {base}  (Ctrl+C to stop)")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
