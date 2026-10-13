"""Client Mods: a card grid of fair-play PvP / performance mods for a profile."""
from __future__ import annotations

import threading
import tkinter as tk

import customtkinter as ctk

import core.config as config
import core.modrinth as modrinth
import core.profiles as profile_store
from core import client_mods


class ClientModsPanel(ctk.CTkFrame):
    COLUMNS = 3

    def __init__(self, master, editor):
        theme = editor.theme
        super().__init__(master, fg_color=theme["BG_PRIMARY"], corner_radius=10)
        self.editor = editor
        self.theme = theme
        self.catalog = client_mods.load_catalog()
        self._busy = False
        self._cancel = None
        self._cards: dict[str, dict] = {}
        self._build_job = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self.grid_area = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.grid_area.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        for column in range(self.COLUMNS):
            self.grid_area.grid_columnconfigure(column, weight=1, uniform="cm")
        self.refresh()

    # ── header: presets ───────────────────────────────────────────────────────

    def _build_header(self):
        theme = self.theme
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        header.grid_columnconfigure(0, weight=1)
        self.note = ctk.CTkLabel(
            header, text="", text_color=theme["TEXT_MUTED"], anchor="w",
            justify="left", wraplength=520, font=ctk.CTkFont(size=12),
        )
        self.note.grid(row=0, column=0, sticky="w")
        buttons = ctk.CTkFrame(header, fg_color="transparent")
        buttons.grid(row=0, column=1, sticky="e")
        self.preset_buttons = []
        for preset in self.catalog["presets"]:
            if preset.get("id") == "skins":
                continue
            button = ctk.CTkButton(
                buttons, text=f"Install {preset['title']}", height=34,
                fg_color=theme["ACCENT"], hover_color=theme["ACCENT_DARK"],
                text_color=theme["ACCENT_TEXT"],
                command=lambda p=preset["id"]: self._install_preset(p),
            )
            button.pack(side="left", padx=(6, 0))
            self.preset_buttons.append(button)

    # ── grid ──────────────────────────────────────────────────────────────────

    def refresh(self):
        supported = client_mods.supports_profile(self.editor.profile)
        if supported:
            self.note.configure(
                text="Fair-play mods only (no cheats). Installs the newest release that "
                     "matches this profile, plus required dependencies."
            )
        else:
            self.note.configure(
                text="Client Mods need a Fabric profile. Create or switch to a Fabric profile."
            )
        for button in self.preset_buttons:
            button.configure(state="normal" if supported and not self._busy else "disabled")
        if self._build_job is not None:
            try:
                self.after_cancel(self._build_job)
            except (tk.TclError, ValueError):
                pass
            self._build_job = None
        for widget in self.grid_area.winfo_children():
            widget.destroy()
        self._cards.clear()
        self._build_cards(0, supported)

    def _build_cards(self, index: int, supported: bool):
        self._build_job = None
        mods = self.catalog["mods"]
        if index >= len(mods) or not self.winfo_exists():
            return
        self._make_card(index, mods[index], supported)
        # pop the cards in one after another instead of all at once
        delay = 18 if self.editor.parent.motion.active() else 0
        self._build_job = self.after(delay, self._build_cards, index + 1, supported)

    def _make_card(self, index: int, entry: dict, supported: bool):
        theme = self.theme
        installed = supported and client_mods.is_installed(self.editor.profile, entry)
        card = ctk.CTkFrame(
            self.grid_area, fg_color=theme["BG_SECONDARY"], corner_radius=12,
            border_width=1, border_color=theme["BORDER_COL"],
        )
        card.grid(row=index // self.COLUMNS, column=index % self.COLUMNS,
                  sticky="nsew", padx=5, pady=5)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 0))
        badge = ctk.CTkLabel(
            top, text=entry.get("title", "?")[:1].upper(), width=34, height=34,
            corner_radius=9, fg_color=theme["ACCENT"], text_color=theme["ACCENT_TEXT"],
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        badge.pack(side="left")
        ctk.CTkLabel(
            top, text=entry.get("category", ""), text_color=theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(side="right")
        ctk.CTkLabel(
            card, text=entry.get("title", entry["slug"]), text_color=theme["TEXT_FG"],
            anchor="w", font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(
            card, text=entry.get("description", ""), text_color=theme["TEXT_MUTED"],
            anchor="w", justify="left", wraplength=190, font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(2, 8))
        button = ctk.CTkButton(
            card, height=30, text="Installed ✓" if installed else "Install",
            state="disabled" if installed or not supported or self._busy else "normal",
            fg_color=theme["BORDER_COL"] if installed else theme["ACCENT"],
            hover_color=theme["ACCENT_DARK"],
            text_color=theme["TEXT_FG"] if installed else theme["ACCENT_TEXT"],
            text_color_disabled=theme["TEXT_FG"] if installed else theme["TEXT_MUTED"],
            command=lambda e=entry: self._install([e], e.get("title", "mod")),
        )
        button.pack(fill="x", padx=12, pady=(0, 12))
        self._cards[entry["slug"]] = {"button": button}

    # ── installing ────────────────────────────────────────────────────────────

    def _install_preset(self, preset_id: str):
        entries = client_mods.preset_entries(self.catalog, preset_id)
        pending = [e for e in entries if not client_mods.is_installed(self.editor.profile, e)]
        title = next((p["title"] for p in self.catalog["presets"] if p["id"] == preset_id), "pack")
        if not pending:
            self.editor._set_status(f"{title} is already installed.")
            return
        self._install(pending, title)

    def _install(self, entries: list[dict], label: str):
        editor = self.editor
        if self._busy or editor._working or not client_mods.supports_profile(editor.profile):
            return
        try:
            destination = editor._instance_dir() / "mods"
        except (OSError, ValueError) as exc:
            editor._set_status(str(exc))
            return
        self._busy = True
        editor._working = True
        self._cancel = threading.Event()
        editor._cancel_event = self._cancel
        editor.cancel_btn.configure(state="normal")
        editor.install_progress.grid()
        editor.install_progress.configure(mode="indeterminate")
        editor.install_progress.start()
        for button in self.preset_buttons:
            button.configure(state="disabled")
        for card in self._cards.values():
            card["button"].configure(state="disabled")
        editor._set_status(f"Installing {label}…")
        cancel = self._cancel
        profile = editor.profile

        def worker():
            try:
                _records, failures, warnings = client_mods.install_entries(
                    profile, entries, destination, cancel_event=cancel,
                    log=lambda m: editor._post(lambda t=m: editor._set_status(t)),
                )
                editor._post(lambda: self._done(label, len(entries), failures, warnings))
            except modrinth.DownloadCancelled:
                editor._post(lambda: self._done(label, 0, ["cancelled"], []))
            except Exception as exc:
                editor._post(lambda m=str(exc): self._done(label, 0, [m], []))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, label, attempted, failures, warnings):
        editor = self.editor
        self._busy = False
        editor._working = False
        editor._cancel_event = None
        editor.cancel_btn.configure(state="disabled")
        editor.install_progress.stop()
        editor.install_progress.grid_remove()
        editor.install_progress.configure(mode="determinate")
        try:
            config.save(editor.parent.cfg)
            profile_store.save_manifest(editor.profile)
        except OSError as exc:
            failures = [*failures, f"could not save profile: {exc}"]
        ok = max(0, attempted - len(failures))
        message = f"{label}: {ok} installed" if attempted else f"{label}: stopped"
        if failures:
            message += f" · {len(failures)} problem(s): " + "; ".join(failures[:3])
        elif warnings:
            message += " · " + "; ".join(warnings[:2])
        editor._set_status(message)
        if self.winfo_exists():
            self.refresh()
