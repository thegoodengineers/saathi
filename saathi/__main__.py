"""Command line: python -m saathi {eval|demo|run|serve} ..."""
from __future__ import annotations

import argparse
import time
from pathlib import Path


def _ask(question: str) -> str:
    return input(f"\n  Saathi asks: {question}\n  > ")


def main() -> None:
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
    a = ap.parse_args()

    from .agent import run
    from .browser import mock_server, open_browser
    from .safety import SafetyLayer

    if a.cmd == "eval":
        from .evaluate import score, write_evidence

        md = write_evidence(score(planner=a.planner, repeats=a.repeats, devices=("phone", "pc") if a.device == "both" else (a.device,)), Path(a.out), a.planner)
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
