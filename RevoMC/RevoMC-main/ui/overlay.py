"""In-window modal overlays (dimmed backdrop + card that slides up)."""
import tkinter as tk
from tkinter import TclError

import customtkinter as ctk
from PIL import Image, ImageGrab

from ui.motion import ease_in_cubic, ease_out_cubic


class _Backdrop(ctk.CTkFrame):
    """Covers the whole window; shows a dimmed snapshot when one can be taken."""

    STEPS = (0.18, 0.34, 0.5)

    def __init__(self, window, theme: dict):
        super().__init__(window, fg_color=theme["BG_PRIMARY"], corner_radius=0)
        self.window = window
        self._snapshot = None
        self._frames: list[ctk.CTkImage] = []
        self._label = ctk.CTkLabel(self, text="", corner_radius=0)
        self._label.place(x=0, y=0, relwidth=1, relheight=1)
        for sequence in ("<Button-1>", "<Button-2>", "<Button-3>", "<MouseWheel>"):
            self._label.bind(sequence, lambda _event: "break")
        self._grab_snapshot()
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()

    def _grab_snapshot(self) -> None:
        try:
            self.window.update_idletasks()
            x, y = self.window.winfo_rootx(), self.window.winfo_rooty()
            w, h = self.window.winfo_width(), self.window.winfo_height()
            if w < 50 or h < 50:
                return
            self._snapshot = ImageGrab.grab(bbox=(x, y, x + w, y + h)).convert("RGB")
            black = Image.new("RGB", self._snapshot.size, (8, 6, 22))
            self._frames = [
                ctk.CTkImage(
                    light_image=Image.blend(self._snapshot, black, amount),
                    dark_image=Image.blend(self._snapshot, black, amount),
                    size=(w, h),
                )
                for amount in self.STEPS
            ]
        except Exception:  # screen capture unavailable (permissions, headless, …)
            self._snapshot = None
            self._frames = []

    def set_dim(self, progress: float) -> None:
        if not self._frames:
            return
        index = min(len(self._frames) - 1, int(progress * len(self._frames)))
        if progress <= 0.02:
            self._label.configure(image=None)
        else:
            self._label.configure(image=self._frames[index])


class OverlayDialog(ctk.CTkFrame):
    """A modal card that slides up over the main window.

    Subclasses build their widgets directly inside ``self`` (like a Toplevel) and
    may call ``self.wait_window(self)`` to block until the card has closed.
    """

    SLIDE = 44

    def __init__(self, window, width: int, height: int, theme: dict | None = None):
        theme = theme or window.theme
        self._window = window
        self._backdrop = _Backdrop(window, theme)
        self._closing = False
        self._final = False
        super().__init__(
            self._backdrop,
            width=width,
            height=height,
            corner_radius=16,
            fg_color=theme["BG_SECONDARY"],
            border_width=1,
            border_color=theme["BORDER_COL"],
        )
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.place(relx=0.5, rely=0.5, anchor="center", y=self.SLIDE)
        self._motion = window.motion
        self._motion.run(
            ("overlay", str(self)), 220,
            self._open_step, easing=ease_out_cubic, force=True,
        )
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(30, self.focus_set)

    def _open_step(self, progress: float) -> None:
        self.place_configure(y=round(self.SLIDE * (1 - progress)))
        self._backdrop.set_dim(progress)

    def _close_step(self, progress: float) -> None:
        self.place_configure(y=round(self.SLIDE * progress))
        self._backdrop.set_dim(1 - progress)

    def destroy(self):
        if self._final:
            super().destroy()
            return
        if self._closing:
            return
        self._closing = True
        self._motion.run(
            ("overlay", str(self)), 160,
            self._close_step, done=self._finish, easing=ease_in_cubic, force=True,
        )

    def _finish(self):
        self._final = True
        try:
            self._backdrop.destroy()
        except TclError:
            pass

    # ── Toplevel-compatibility shims (dialogs were Toplevel windows before) ───

    def title(self, *_args, **_kwargs):
        return ""

    def geometry(self, *_args, **_kwargs):
        return ""

    def minsize(self, *_args, **_kwargs):
        return None

    def resizable(self, *_args, **_kwargs):
        return None

    def transient(self, *_args, **_kwargs):
        return None
