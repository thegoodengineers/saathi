"""Save a phone screenshot after every step of a scenario (for slides and the video storyboard)."""
from __future__ import annotations

from pathlib import Path

from .agent import run
from .browser import mock_server, open_browser
from .planner import ScriptedPlanner
from .safety import SafetyLayer
from .scenarios import SCENARIOS


def capture(name: str, out: Path, safety: bool = True, device: str = "phone") -> list[Path]:
    sc = next(s for s in SCENARIOS if s.name == name)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    tag = f"{device}-" + ("safe" if safety else "nosafety")

    def snap(_msg: str) -> None:
        f = out / f"{name}-{tag}-{len(saved) + 1:02d}.png"
        page.screenshot(path=str(f))
        saved.append(f)

    with mock_server() as base, open_browser(headless=True, mobile=device == "phone") as page:
        page.goto(base + sc.page)
        snap("start")
        run(sc.goal, page, ScriptedPlanner(list(sc.script)), SafetyLayer(enabled=safety),
            ask_user=lambda q: sc.answer, narrate=snap)
    return saved
