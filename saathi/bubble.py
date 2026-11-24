"""Saathi bubble: a round button that floats above every window. Tap it, type what you need, and
Saathi does it in the browser window it opened for you. It asks "Shall I go ahead?" right in the box.

The bubble is a desktop window, not part of any web page, so no website can press it or send it
commands. All browser work runs on one worker thread (Playwright's sync API stays on one thread);
the bubble and the worker talk through queues.
"""
from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path

COLORS = {"idle": "#1f4fa3", "working": "#c2410c", "ask": "#a16207", "done": "#1e7a3c", "block": "#b3261e"}
KEY = "#ff00fe"  # painted transparent on Windows, so the bubble shows as a circle
SETTINGS = Path(os.environ.get("APPDATA") or Path.home()) / "Saathi" / "settings.env"


def load_settings(path: Path = SETTINGS) -> None:
    """Read KEY=VALUE lines (AWS_REGION, SAATHI_MODEL_ID, AWS_BEARER_TOKEN_BEDROCK) from the user's own
    settings file, which lives in their profile and never in the repo. Values already set win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def parse_narration(line: str) -> tuple[str, str]:
    """agent.say() narrates '[kind] message'; map it to a bubble state."""
    kind, msg = "say", line
    if line.startswith("[") and "]" in line:
        kind, msg = line[1:line.index("]")], line[line.index("]") + 1:].strip()
    return {"say": "working", "confirm": "ask", "block": "block", "done": "done"}.get(kind, "working"), msg


@dataclass
class Channel:
    commands: queue.Queue = field(default_factory=queue.Queue)  # bubble -> worker: task text, None = stop
    events: queue.Queue = field(default_factory=queue.Queue)    # worker -> bubble: (state, message)
    answers: queue.Queue = field(default_factory=queue.Queue)   # bubble -> worker: reply to a question

    def ask(self, question: str) -> str:
        self.events.put(("ask", question))
        return self.answers.get()

    def narrate(self, line: str) -> None:
        self.events.put(parse_narration(line))


def worker(ch: Channel, open_page, make_planner, allow: set[str] | None = None) -> None:
    """Runs on its own thread until a None command arrives. open_page() is a context manager that
    yields the browser tab; make_planner() builds the planner on this thread."""
    from .agent import run
    from .safety import SafetyLayer, trusted_tab_host

    try:
        planner = make_planner()
        with open_page() as page:
            ch.events.put(("idle", "Ready. Tap me and tell me what to do."))
            while (goal := ch.commands.get()) is not None:
                allowed = {h for h in {trusted_tab_host(page.url), *(allow or set())} if h}
                ch.events.put(("working", f"Working on: {goal}"))
                try:
                    res = run(goal, page, planner, SafetyLayer(allowed_hosts=allowed),
                              ask_user=ch.ask, narrate=ch.narrate, pause=0.6)
                    ch.events.put(("done", res.outcome or "Done."))
                except Exception as e:  # keep the bubble alive; say what failed
                    ch.events.put(("block", f"Something went wrong: {type(e).__name__}: {str(e)[:160]}"))
    except SystemExit as e:
        ch.events.put(("block", str(e)))
    except Exception as e:
        ch.events.put(("block", f"Could not start: {type(e).__name__}: {str(e)[:160]}"))


class Bubble:
    SIZE = 64

    def __init__(self, ch: Channel):
        import tkinter as tk

        self.tk, self.ch = tk, ch
        self.waiting = False  # True while the worker waits for an answer
        r = self.root = tk.Tk()
        r.title("Saathi")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        try:
            r.attributes("-transparentcolor", KEY)
        except tk.TclError:  # not on Windows: the bubble is drawn on a square
            pass
        s = self.SIZE
        self.canvas = tk.Canvas(r, width=s, height=s, bg=KEY, highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.circle = self.canvas.create_oval(2, 2, s - 2, s - 2, fill=COLORS["idle"], outline="white", width=3)
        self.canvas.create_text(s // 2, s // 2, text="S", fill="white", font=("Segoe UI", 24, "bold"))
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"{s}x{s}+{sw - s - 28}+{sh - s - 90}")
        for ev, fn in (("<ButtonPress-1>", self._press), ("<B1-Motion>", self._drag), ("<ButtonRelease-1>", self._release)):
            self.canvas.bind(ev, fn)
        self._build_panel()
        self._set("working", "Opening your browser...")
        r.after(100, self._poll)

    # -- the box that opens when you tap the bubble --------------------------------------------------
    def _build_panel(self) -> None:
        tk = self.tk
        p = self.panel = tk.Toplevel(self.root)
        p.title("Saathi")
        p.attributes("-topmost", True)
        p.resizable(False, False)
        p.protocol("WM_DELETE_WINDOW", self.hide_panel)
        p.configure(bg="white", padx=16, pady=14)
        tk.Label(p, text="Saathi", font=("Segoe UI", 16, "bold"), bg="white", fg="#111111").pack(anchor="w")
        self.status = tk.Label(p, text="", font=("Segoe UI", 12), bg="white", fg="#333333",
                               wraplength=340, justify="left")
        self.status.pack(anchor="w", pady=(4, 10))
        self.prompt = tk.Label(p, text="What should I do?", font=("Segoe UI", 12, "bold"), bg="white")
        self.prompt.pack(anchor="w")
        self.entry = tk.Entry(p, font=("Segoe UI", 13), width=34, relief="solid", bd=1)
        self.entry.pack(fill="x", pady=(4, 8), ipady=4)
        self.entry.bind("<Return>", lambda e: self.submit())
        row = tk.Frame(p, bg="white")
        row.pack(fill="x")
        self.go = tk.Button(row, text="Do it", font=("Segoe UI", 12, "bold"), bg=COLORS["idle"], fg="white",
                            relief="flat", padx=14, command=self.submit)
        self.go.pack(side="left")
        self.yes = tk.Button(row, text="Yes", font=("Segoe UI", 12, "bold"), bg=COLORS["done"], fg="white",
                             relief="flat", padx=14, command=lambda: self.answer("yes"))
        self.no = tk.Button(row, text="No", font=("Segoe UI", 12, "bold"), bg=COLORS["block"], fg="white",
                            relief="flat", padx=14, command=lambda: self.answer("no"))
        tk.Button(row, text="Quit Saathi", font=("Segoe UI", 10), relief="flat", bg="white", fg="#555555",
                  command=self.quit).pack(side="right")
        self.hide_panel()

    def show_panel(self) -> None:
        self.panel.update_idletasks()
        x = max(self.root.winfo_x() - self.panel.winfo_reqwidth() - 12, 8)
        y = max(self.root.winfo_y() - self.panel.winfo_reqheight() + self.SIZE, 8)
        self.panel.geometry(f"+{x}+{y}")
        self.panel.deiconify()
        self.panel.lift()
        self.entry.focus_set()

    def hide_panel(self) -> None:
        self.panel.withdraw()

    # -- actions -------------------------------------------------------------------------------------
    def submit(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        if self.waiting:  # e.g. "what is your consumer number?" -> the typed reply
            self.answer(text)
        else:
            self.ch.commands.put(text)

    def answer(self, text: str) -> None:
        if not self.waiting:
            return
        self.waiting = False
        self.yes.pack_forget()
        self.no.pack_forget()
        self.prompt.configure(text="What should I do?")
        self.go.configure(text="Do it")
        self.ch.answers.put(text)

    def quit(self) -> None:
        self.ch.commands.put(None)
        if self.waiting:
            self.ch.answers.put("no")
        self.root.destroy()

    # -- bubble dragging and tapping -----------------------------------------------------------------
    def _press(self, e) -> None:
        self._start = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y())
        self._moved = False

    def _drag(self, e) -> None:
        x0, y0, wx, wy = self._start
        dx, dy = e.x_root - x0, e.y_root - y0
        if abs(dx) + abs(dy) > 4:
            self._moved = True
            self.root.geometry(f"+{wx + dx}+{wy + dy}")

    def _release(self, e) -> None:
        if not self._moved:
            self.hide_panel() if self.panel.winfo_viewable() else self.show_panel()

    # -- messages from the worker --------------------------------------------------------------------
    def _set(self, state: str, msg: str) -> None:
        self.canvas.itemconfigure(self.circle, fill=COLORS.get(state, COLORS["working"]))
        self.status.configure(text=msg)

    def _poll(self) -> None:
        try:
            while True:
                state, msg = self.ch.events.get_nowait()
                self._set(state, msg)
                if state == "ask":
                    self.waiting = True
                    self.prompt.configure(text="Your answer:")
                    self.go.configure(text="Send")
                    self.yes.pack(side="left", padx=(8, 0))
                    self.no.pack(side="left", padx=(8, 0))
                    self.show_panel()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def run(self) -> None:
        self.root.mainloop()


def main(browser: str | None, port: int, allow: list[str]) -> None:
    import contextlib

    from .browser import connect_browser, launch_browser
    from .planner import BedrockPlanner

    load_settings()

    @contextlib.contextmanager
    def open_page():
        if browser:
            launch_browser(browser, port)
        with connect_browser(port) as page:
            yield page

    ch = Channel()
    threading.Thread(target=worker, args=(ch, open_page, BedrockPlanner, set(allow)), daemon=True).start()
    Bubble(ch).run()


def create_shortcut(browser: str) -> str:
    """Put a 'Saathi' icon on the Windows desktop that starts the bubble (no terminal window)."""
    import subprocess
    import sys

    if os.name != "nt":
        raise SystemExit("Desktop shortcuts are made for Windows; elsewhere run: python -m saathi bubble")
    pyw = Path(sys.executable).with_name("pythonw.exe")
    repo = Path(__file__).resolve().parent.parent
    ps = ("$p=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Saathi.lnk'; "
          "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p); "
          f"$s.TargetPath='{pyw}'; $s.Arguments='-m saathi bubble --browser {browser}'; "
          f"$s.WorkingDirectory='{repo}'; $s.Description='Saathi, a web helper that cannot be tricked'; "
          "$s.Save(); Write-Output $p")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def setup(browser: str) -> None:
    """One-time setup for this Windows user: save the AI settings privately, then make the shortcut."""
    import getpass

    current = {}
    if SETTINGS.exists():
        for line in SETTINGS.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
    region = input(f"AWS region [{current.get('AWS_REGION', 'ap-south-1')}]: ").strip() or current.get("AWS_REGION", "ap-south-1")
    model = (input(f"Model id [{current.get('SAATHI_MODEL_ID', 'global.amazon.nova-2-lite-v1:0')}]: ").strip()
             or current.get("SAATHI_MODEL_ID", "global.amazon.nova-2-lite-v1:0"))
    key = getpass.getpass("Bedrock API key (hidden while you type; Enter keeps the saved one): ").strip()
    current.update({"AWS_REGION": region, "SAATHI_MODEL_ID": model})
    if key:
        current["AWS_BEARER_TOKEN_BEDROCK"] = key
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text("# Saathi settings for this Windows user. Private: do not share or commit.\n"
                        + "".join(f"{k}={v}\n" for k, v in current.items()), encoding="utf-8")
    print(f"Saved settings to {SETTINGS}")
    print(f"Desktop shortcut: {create_shortcut(browser)}")
