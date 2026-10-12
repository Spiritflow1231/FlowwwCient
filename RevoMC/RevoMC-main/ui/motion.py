"""Small, cheap animation helpers for the FlowwwClient interface.

Everything here runs on the Tk event loop with ``after`` (never ``sleep``), keeps at
most one running animation per key, and falls back to an instant change when
animations are disabled or the launcher is busy.
"""
import time
from tkinter import TclError


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    return t ** 3


def ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(char * 2 for char in color)
    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))


def lerp_color(start: str, end: str, t: float) -> str:
    a, b = _hex_to_rgb(start), _hex_to_rgb(end)
    return "#" + "".join(f"{round(lerp(x, y, t)):02x}" for x, y in zip(a, b))


class Motion:
    """Run keyed, cancellable animations on a Tk root."""

    FRAME_MS = 15

    def __init__(self, root, enabled: bool = True, is_busy=None):
        self.root = root
        self.enabled = enabled
        self._is_busy = is_busy or (lambda: False)
        self._jobs: dict = {}

    # ── core ──────────────────────────────────────────────────────────────────

    def active(self) -> bool:
        return bool(self.enabled and not self._is_busy())

    def cancel(self, key) -> None:
        job = self._jobs.pop(key, None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except (TclError, ValueError):
                pass

    def cancel_all(self) -> None:
        for key in list(self._jobs):
            self.cancel(key)

    def run(self, key, duration_ms: int, step, done=None, easing=ease_out_cubic,
            force: bool = False) -> None:
        """Call ``step(progress)`` with eased progress 0..1, then ``done()``."""
        self.cancel(key)
        if duration_ms <= 0 or (not force and not self.active()):
            self._safe(step, 1.0)
            if done:
                self._safe(done)
            return
        start = time.monotonic()

        def tick():
            elapsed = (time.monotonic() - start) * 1000
            progress = min(1.0, elapsed / duration_ms)
            if not self._safe(step, easing(progress)):
                self._jobs.pop(key, None)
                return
            if progress < 1.0:
                self._jobs[key] = self.root.after(self.FRAME_MS, tick)
            else:
                self._jobs.pop(key, None)
                if done:
                    self._safe(done)

        tick()

    @staticmethod
    def _safe(function, *args) -> bool:
        try:
            function(*args)
            return True
        except TclError:
            return False  # widget destroyed mid-animation

    # ── ready-made effects ────────────────────────────────────────────────────

    def slide_up(self, widget, distance: int = 24, duration_ms: int = 220,
                 key=None, relx: float = 0.0, relwidth: float = 1.0,
                 relheight: float = 1.0, done=None) -> None:
        """Show ``widget`` with place() and slide it up into position."""
        key = key or ("slide", str(widget))
        widget.place(x=0, y=distance if self.active() else 0, relx=relx,
                     relwidth=relwidth, relheight=relheight)

        def step(progress):
            widget.place_configure(y=round(distance * (1 - progress)))

        self.run(key, duration_ms, step, done=done)

    def color(self, widget, option: str, start: str, end: str,
              duration_ms: int = 120) -> None:
        key = ("color", str(widget), option)

        def step(progress):
            widget.configure(**{option: lerp_color(start, end, progress)})

        self.run(key, duration_ms, step, easing=ease_in_out)

    def stagger_rows(self, rows, base_pady=(5, 5), offset: int = 16,
                     delay_ms: int = 30, duration_ms: int = 160,
                     max_rows: int = 8) -> None:
        """Slide pack()-managed rows up one after another (first ``max_rows``)."""
        if not self.active():
            return
        top, bottom = base_pady
        for index, row in enumerate(list(rows)[:max_rows]):
            try:
                row.pack_configure(pady=(top + offset, bottom))
            except TclError:
                continue

            def begin(widget=row, number=index):
                def step(progress, widget=widget):
                    widget.pack_configure(
                        pady=(round(top + offset * (1 - progress)), bottom)
                    )
                self.run(("row", str(widget)), duration_ms, step)

            self.root.after(index * delay_ms, begin)
