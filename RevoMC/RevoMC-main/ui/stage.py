"""Centre stage of the Play page: the player's skin in a hero pose with a nametag."""
import math
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageEnhance, ImageOps, ImageTk

from core import skin_render


def _hex(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def make_stage_background(width: int, height: int, source: Image.Image | None,
                          top: str, bottom: str, outer: str,
                          radius: int = 18) -> Image.Image:
    """Cover-fit scene image with a dark vignette and rounded corners.

    Falls back to a vertical gradient when no scene image is available.  Corners are
    filled with ``outer`` so the canvas blends into the surrounding card.
    """
    width, height = max(2, width), max(2, height)
    if source is not None:
        image = ImageOps.fit(source, (width, height), Image.LANCZOS, centering=(0.5, 0.5))
        image = ImageEnhance.Brightness(image).enhance(0.95)
    else:
        t, b = _hex(top), _hex(bottom)
        column = Image.new("RGB", (1, height))
        for y in range(height):
            f = y / max(1, height - 1)
            column.putpixel((0, y), tuple(round(t[i] + (b[i] - t[i]) * f) for i in range(3)))
        image = column.resize((width, height))
    # vignette: darker at the bottom (floor) and edges so skin + nametag stay readable
    vignette = Image.new("L", (1, height))
    for y in range(height):
        f = y / max(1, height - 1)
        vignette.putpixel((0, y), round(40 + 120 * f * f))
    vignette = vignette.resize((width, height))
    image = Image.composite(Image.new("RGB", (width, height), (6, 4, 16)), image, vignette)
    mask = Image.new("L", (width * 2, height * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * 2 - 1, height * 2 - 1), radius=radius * 2, fill=255
    )
    mask = mask.resize((width, height), Image.LANCZOS)
    result = Image.new("RGB", (width, height), outer)
    result.paste(image, (0, 0), mask)
    return result


class HeroStage(tk.Canvas):
    """Canvas that shows nametag, 3D skin render, floor shadow and a soft glow."""

    BASE_SIZE = (360, 480)
    BOB_PERIOD = 2.4
    BOB_PX = 3.0

    def __init__(self, master, theme: dict, motion=None, on_create_account=None,
                 scene: Image.Image | None = None):
        super().__init__(master, highlightthickness=0, bd=0, bg=theme["BG_SECONDARY"])
        self._scene = scene
        self.theme = dict(theme)
        self.motion = motion
        self._on_create_account = on_create_account
        self._render_cache: dict = {}
        self._name = ""
        self._skin = None
        self._slim = False
        self._cape = None
        self._dimmed = False
        self._empty = False
        self._result = None
        self._photo_refs: dict = {}
        self._scaled_key = None
        self._bg_key = None
        self._figure_h = 0
        self._bob_job = None
        self._phase0 = time.monotonic()
        self._items = {}
        self._hint_window = None
        self._shadow_frames: list = []
        self._shadow_index = -1
        self._configure_job = None
        self.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", lambda _e: self.stop_idle(), add="+")

    # ── public API ────────────────────────────────────────────────────────────

    def set_player(self, name: str, skin: Image.Image | None, slim: bool = False,
                   cape: Image.Image | None = None, empty: bool = False) -> None:
        self._name = name or ""
        self._slim = bool(slim)
        self._cape = cape
        self._empty = empty
        self._dimmed = empty
        if skin is None:
            skin = default_steve()
        self._skin = skin
        self._result = None
        self._scaled_key = None
        self._redraw()

    def apply_theme(self, theme: dict) -> None:
        self.theme = dict(theme)
        self.configure(bg=theme["BG_SECONDARY"])
        self._bg_key = None
        self._scaled_key = None
        self._render_cache.clear()
        self._shadow_frames = []
        self._redraw()
        if self._hint_window is not None:
            try:
                self._hint_window.configure(fg_color=theme["BG_SECONDARY"])
            except tk.TclError:
                pass

    def start_idle(self) -> None:
        if self._bob_job is None:
            self._tick()

    def stop_idle(self) -> None:
        if self._bob_job is not None:
            try:
                self.after_cancel(self._bob_job)
            except (tk.TclError, ValueError):
                pass
            self._bob_job = None

    # ── layout ────────────────────────────────────────────────────────────────

    def _on_configure(self, _event=None):
        if self._configure_job is not None:
            try:
                self.after_cancel(self._configure_job)
            except (tk.TclError, ValueError):
                pass
        self._configure_job = self.after(60, self._redraw)

    def _render_player(self):
        key = (id(self._skin), self._slim, id(self._cape))
        cached = self._render_cache.get(key)
        if cached is None:
            try:
                cached = skin_render.render_player(
                    self._skin, slim=self._slim, cape=self._cape, size=self.BASE_SIZE
                )
            except ValueError:
                cached = skin_render.render_player(
                    default_steve(), slim=False, size=self.BASE_SIZE
                )
            self._render_cache = {key: cached}
            self._cache_refs = (self._skin, self._cape)
        return cached

    def _redraw(self):
        self._configure_job = None
        width, height = self.winfo_width(), self.winfo_height()
        if width < 40 or height < 80 or self._skin is None:
            return
        theme = self.theme
        bg_key = (width, height, theme["STAGE_TOP"], theme["STAGE_BOTTOM"], theme["BG_SECONDARY"])
        if bg_key != self._bg_key:
            background = make_stage_background(
                width, height, self._scene, theme["STAGE_TOP"], theme["STAGE_BOTTOM"],
                theme["BG_SECONDARY"],
            )
            self._photo_refs["bg"] = ImageTk.PhotoImage(background)
            if "bg" in self._items:
                self.itemconfigure(self._items["bg"], image=self._photo_refs["bg"])
            else:
                self._items["bg"] = self.create_image(0, 0, anchor="nw",
                                                      image=self._photo_refs["bg"])
            self.tag_lower(self._items["bg"])
            self._bg_key = bg_key

        result = self._render_player()
        tag_h = 40
        figure_h = int(min(height - tag_h - 34, (width - 24) / 0.75))
        figure_h = max(120, figure_h // 6 * 6)
        scale = figure_h / self.BASE_SIZE[1]
        figure_w = round(self.BASE_SIZE[0] * scale)
        scaled_key = (id(result), figure_h, self._name, theme["NAMETAG_BG"], self._dimmed)
        feet_x = width / 2
        feet_y = height - 26
        top_y = feet_y - figure_h
        if scaled_key != self._scaled_key:
            figure = result.image.resize((figure_w, figure_h), Image.LANCZOS)
            if self._dimmed:
                alpha = figure.getchannel("A").point(lambda v: int(v * 0.42))
                figure.putalpha(alpha)
            self._photo_refs["figure"] = ImageTk.PhotoImage(figure)
            tag = skin_render.make_nametag(self._name or "Player", bg=theme["NAMETAG_BG"])
            tag_w = max(40, round(tag.width * 0.5))
            tag = tag.resize((tag_w, round(tag.height * 0.5)), Image.LANCZOS)
            if self._dimmed:
                tag.putalpha(tag.getchannel("A").point(lambda v: int(v * 0.5)))
            self._photo_refs["tag"] = ImageTk.PhotoImage(tag)
            self._shadow_frames = [
                ImageTk.PhotoImage(skin_render.make_floor_shadow(
                    round(figure_w * 0.62 * (0.94 + 0.06 * step / 5)),
                    accent=theme["ACCENT"], strength=0.85 + 0.15 * step / 5))
                for step in range(6)
            ]
            self._scaled_key = scaled_key
            self._shadow_index = -1
            self._figure_h = figure_h
            for name in ("shadow", "figure", "tag"):
                if name in self._items:
                    self.delete(self._items.pop(name))
            self._items["shadow"] = self.create_image(
                feet_x, feet_y, anchor="center", image=self._shadow_frames[5])
            self._items["figure"] = self.create_image(
                feet_x, feet_y, anchor="s", image=self._photo_refs["figure"])
            head_y = top_y + result.head_top[1] * scale
            self._tag_rest_y = head_y - 6
            self._figure_rest_y = feet_y
            self._items["tag"] = self.create_image(
                feet_x + (result.head_top[0] - self.BASE_SIZE[0] / 2) * scale,
                self._tag_rest_y, anchor="s", image=self._photo_refs["tag"])
        else:
            self.coords(self._items["shadow"], feet_x, feet_y)
        self._update_hint(width, height)
        self.start_idle()

    def _update_hint(self, width: int, height: int) -> None:
        if not self._empty:
            if self._hint_window is not None:
                self.itemconfigure(self._items["hint"], state="hidden")
            return
        if self._hint_window is None:
            self._hint_window = ctk.CTkFrame(
                self, fg_color=self.theme["BG_SECONDARY"], corner_radius=14,
                border_width=1, border_color=self.theme["BORDER_COL"],
            )
            ctk.CTkLabel(
                self._hint_window, text="Create an account to see your skin",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(padx=18, pady=(14, 6))
            ctk.CTkButton(
                self._hint_window, text="Open Accounts", height=34,
                command=lambda: self._on_create_account and self._on_create_account(),
            ).pack(padx=18, pady=(0, 14))
            self._items["hint"] = self.create_window(
                width / 2, height * 0.45, window=self._hint_window)
        self.coords(self._items["hint"], width / 2, height * 0.45)
        self.itemconfigure(self._items["hint"], state="normal")
        self.tag_raise(self._items["hint"])

    # ── idle motion ───────────────────────────────────────────────────────────

    def _tick(self):
        self._bob_job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        animate = (
            self.motion is None or self.motion.active()
        ) and self.winfo_ismapped() and "figure" in self._items
        if animate:
            t = time.monotonic() - self._phase0
            angle = 2 * math.pi * t / self.BOB_PERIOD
            wave = math.sin(angle)
            offset = wave * self.BOB_PX * max(0.6, self._figure_h / 480)
            self.coords(self._items["figure"], self.winfo_width() / 2,
                        self._figure_rest_y + offset)
            tag_x, _ = self.coords(self._items["tag"])
            self.coords(self._items["tag"], tag_x, self._tag_rest_y + offset)
            index = min(5, max(0, round((1 - (wave + 1) / 2) * 5)))
            if self._shadow_frames and index != self._shadow_index:
                self.itemconfigure(self._items["shadow"], image=self._shadow_frames[index])
                self._shadow_index = index
        self._bob_job = self.after(33 if animate else 250, self._tick)


_STEVE = None


def default_steve() -> Image.Image:
    """A Steve-like fallback texture so the stage never shows an empty frame."""
    global _STEVE
    if _STEVE is None:
        skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(skin)

        def box(u, v, w, h, d, colors):
            for face, (x, y, ww, hh) in skin_render._uv_rects(u, v, w, h, d).items():
                draw.rectangle((x, y, x + ww - 1, y + hh - 1), fill=colors[face])

        def shades(base):
            lighter = tuple(min(255, c + 22) for c in base[:3]) + (255,)
            darker = tuple(max(0, c - 28) for c in base[:3]) + (255,)
            return {"top": lighter, "bottom": darker, "right": darker,
                    "front": base, "left": darker, "back": darker}

        skin_color = (198, 145, 105, 255)
        box(0, 0, 8, 8, 8, shades(skin_color))
        draw.rectangle((8, 0, 15, 7), fill=(76, 49, 33, 255))
        draw.rectangle((8, 8, 15, 9), fill=(76, 49, 33, 255))
        draw.rectangle((0, 8, 7, 15), fill=(76, 49, 33, 255))
        draw.rectangle((16, 8, 23, 15), fill=(76, 49, 33, 255))
        draw.rectangle((24, 8, 31, 15), fill=(76, 49, 33, 255))
        draw.rectangle((9, 11, 10, 12), fill=(255, 255, 255, 255))
        draw.rectangle((13, 11, 14, 12), fill=(255, 255, 255, 255))
        draw.rectangle((9, 11, 9, 12), fill=(80, 60, 160, 255))
        draw.rectangle((14, 11, 14, 12), fill=(80, 60, 160, 255))
        draw.rectangle((11, 13, 12, 14), fill=(151, 92, 65, 255))
        draw.rectangle((11, 15, 12, 15), fill=(96, 52, 42, 255))
        box(16, 16, 8, 12, 4, shades((57, 174, 168, 255)))
        box(40, 16, 4, 12, 4, shades(skin_color))
        box(32, 48, 4, 12, 4, shades(skin_color))
        box(0, 16, 4, 12, 4, shades((54, 91, 171, 255)))
        box(16, 48, 4, 12, 4, shades((54, 91, 171, 255)))
        _STEVE = skin
    return _STEVE.copy()
