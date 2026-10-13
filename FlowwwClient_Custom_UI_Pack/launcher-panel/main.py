from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from tkinter import filedialog, messagebox, colorchooser, simpledialog
from typing import Any

import customtkinter as ctk

APP_NAME = "FlowwwClient Control Panel"
ACCENT = "#E53945"
ACCENT_HOVER = "#FF4655"
BG = "#0B0D10"
PANEL = "#14171C"
CARD = "#191D23"
CARD_HOVER = "#222832"
BORDER = "#2A3039"
TEXT = "#F4F5F7"
MUTED = "#969DA8"
GREEN = "#36C991"

DEFAULT_CONFIG: dict[str, Any] = {
    "schemaVersion": 1,
    "nametagEnabled": True,
    "nametagSymbol": "ঌ",
    "nametagColor": "#E53945",
    "nametagScale": 1.0,
    "motionBlurEnabled": False,
    "motionBlurStrength": 0.35,
    "modules": [
        {"id": "nametag-marker", "name": "Name-tag Marker", "enabled": True, "kind": "nametag", "custom": False},
        {"id": "motion-blur", "name": "Motion Blur", "enabled": False, "kind": "motion_blur", "custom": False},
        {"id": "fps-hud", "name": "FPS Counter", "enabled": True, "kind": "hud", "custom": False},
        {"id": "coords-hud", "name": "Coordinates", "enabled": False, "kind": "hud", "custom": False},
    ],
}

PANEL_FILE = Path.home() / ".flowwwclient" / "panel_state.json"


class FlowwwPanel(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title(APP_NAME)
        self.geometry("1220x780")
        self.minsize(980, 660)
        self.configure(fg_color=BG)
        self.instance_dir: Path | None = None
        self.mods_dir: Path | None = None
        self.active_page = "Home"
        self.page_frame: ctk.CTkFrame | None = None
        self.animation_enabled = True
        self.config_data = json.loads(json.dumps(DEFAULT_CONFIG))
        self.modules: list[dict[str, Any]] = []
        self.load_panel_state()
        self.load_selected_instance_config()
        self.modules = self.config_data.setdefault("modules", json.loads(json.dumps(DEFAULT_CONFIG["modules"])))
        self._build_shell()
        self.show_page("Home", animate=False)

    def load_panel_state(self) -> None:
        try:
            data = json.loads(PANEL_FILE.read_text(encoding="utf-8"))
            selected = data.get("instance_dir")
            if selected and Path(selected).is_dir():
                self.instance_dir = Path(selected)
                self.mods_dir = self.instance_dir / "mods"
            self.animation_enabled = bool(data.get("animation_enabled", True))
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def save_panel_state(self) -> None:
        try:
            PANEL_FILE.parent.mkdir(parents=True, exist_ok=True)
            PANEL_FILE.write_text(json.dumps({
                "instance_dir": str(self.instance_dir) if self.instance_dir else "",
                "animation_enabled": self.animation_enabled,
            }, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save error", f"Could not save panel preferences.\n{exc}", parent=self)

    def load_selected_instance_config(self) -> None:
        if self.instance_dir is None:
            return
        config_path = self.instance_dir / "config" / "flowwwclient.json"
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            # Do not overwrite fields that the panel doesn't understand.
            self.config_data = {**self.config_data, **existing}
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError):
            messagebox.showwarning("Config not loaded", f"Could not read:\n{config_path}", parent=self)

    def write_shared_config(self) -> None:
        self.config_data["schemaVersion"] = 1
        if self.instance_dir:
            target = self.instance_dir / "config" / "flowwwclient.json"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(self.config_data, indent=2, ensure_ascii=False), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Config write failed", f"Could not write instance config:\n{exc}", parent=self)
                return
        else:
            # Keep an editable copy until a Minecraft instance is selected.
            local_settings = PANEL_FILE.parent / "flowwwclient.json"
            try:
                local_settings.parent.mkdir(parents=True, exist_ok=True)
                local_settings.write_text(json.dumps(self.config_data, indent=2, ensure_ascii=False), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Config write failed", f"Could not save local config:\n{exc}", parent=self)
                return
        self.save_panel_state()

    def _build_shell(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.header = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=82)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.header, text="ঌ", font=ctk.CTkFont(family="Segoe UI Symbol", size=36, weight="bold"), text_color=ACCENT).grid(row=0, column=0, padx=(22, 8), pady=16)
        brand = ctk.CTkFrame(self.header, fg_color="transparent")
        brand.grid(row=0, column=1, sticky="w", pady=16)
        ctk.CTkLabel(brand, text="FlowwwClient", text_color=TEXT, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(brand, text="CLIENT CONTROL CENTER  •  CONFIGURE YOUR INSTANCE", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", pady=(1, 0))
        self.instance_badge = ctk.CTkLabel(self.header, text=self._instance_label(), text_color=MUTED, fg_color=CARD, corner_radius=9, padx=12, pady=8, font=ctk.CTkFont(size=11))
        self.instance_badge.grid(row=0, column=2, padx=22)

        self.nav = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, height=58)
        self.nav.grid(row=1, column=0, sticky="new", pady=(0, 0))
        self.nav.grid_columnconfigure(0, weight=1)
        nav_inner = ctk.CTkFrame(self.nav, fg_color="transparent")
        nav_inner.pack(fill="x", padx=18, pady=8)
        for name in ("Home", "Profiles", "Client Mods", "Game Mods", "Settings"):
            button = ctk.CTkButton(nav_inner, text=name, command=lambda n=name: self.show_page(n), height=38, corner_radius=9, fg_color=ACCENT if name == self.active_page else "transparent", hover_color=CARD_HOVER, text_color=TEXT, border_width=1 if name != self.active_page else 0, border_color=BORDER, font=ctk.CTkFont(size=12, weight="bold"))
            button.pack(side="left", padx=(0, 7))

        self.content_host = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content_host.grid(row=2, column=0, sticky="nsew", padx=18, pady=(2, 18))
        self.grid_rowconfigure(2, weight=1)
        self.footer = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=30)
        self.footer.grid(row=3, column=0, sticky="ew")
        self.footer.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(self.footer, text="●  Ready  •  Settings are saved per instance when one is selected", text_color=MUTED, font=ctk.CTkFont(size=10))
        self.status_label.grid(row=0, column=0, sticky="w", padx=18, pady=6)

    def _instance_label(self) -> str:
        return self.instance_dir.name if self.instance_dir else "No instance selected"

    def refresh_header(self) -> None:
        if hasattr(self, "instance_badge"):
            self.instance_badge.configure(text=self._instance_label())

    def set_status(self, message: str, success: bool = True) -> None:
        self.status_label.configure(text=f"●  {message}", text_color=GREEN if success else ACCENT_HOVER)

    def show_page(self, page: str, animate: bool = True) -> None:
        self.active_page = page
        if self.page_frame is not None:
            self.page_frame.destroy()
        frame = ctk.CTkFrame(self.content_host, fg_color="transparent")
        self.page_frame = frame
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        builders = {
            "Home": self.build_home,
            "Profiles": self.build_profiles,
            "Client Mods": self.build_client_mods,
            "Game Mods": self.build_game_mods,
            "Settings": self.build_settings,
        }
        builders.get(page, self.build_home)(frame)
        if animate and self.animation_enabled:
            frame.place_configure(rely=0.035)
            self._animate_page(frame, 0.035, 0.0)
        self._refresh_nav_state()

    def _animate_page(self, frame: ctk.CTkFrame, start: float, end: float, step: int = 0) -> None:
        if not frame.winfo_exists():
            return
        total = 8
        value = min(step + 1, total)
        # Ease-out cubic; short, restrained slide to avoid a jarring screen swap.
        t = value / total
        eased = 1 - (1 - t) ** 3
        rel_y = start + (end - start) * eased
        frame.place_configure(rely=rel_y)
        if value < total:
            self.after(16, lambda: self._animate_page(frame, start, end, value))

    def _refresh_nav_state(self) -> None:
        # Rebuild only the nav row so the selected state stays in sync.
        for child in self.nav.winfo_children():
            child.destroy()
        nav_inner = ctk.CTkFrame(self.nav, fg_color="transparent")
        nav_inner.pack(fill="x", padx=18, pady=8)
        for name in ("Home", "Profiles", "Client Mods", "Game Mods", "Settings"):
            ctk.CTkButton(nav_inner, text=name, command=lambda n=name: self.show_page(n), height=38, corner_radius=9, fg_color=ACCENT if name == self.active_page else "transparent", hover_color=CARD_HOVER, text_color=TEXT, border_width=1 if name != self.active_page else 0, border_color=BORDER, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 7))

    def page_heading(self, parent: ctk.CTkFrame, title: str, subtitle: str) -> None:
        ctk.CTkLabel(parent, text=title, text_color=TEXT, font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", pady=(18, 2))
        ctk.CTkLabel(parent, text=subtitle, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(0, 18))

    def card(self, parent: ctk.CTkFrame, title: str, subtitle: str | None = None) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        if title:
            ctk.CTkLabel(f, text=title, text_color=TEXT, font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=(14, 2 if subtitle else 12))
        if subtitle:
            ctk.CTkLabel(f, text=subtitle, text_color=MUTED, font=ctk.CTkFont(size=11), wraplength=600, justify="left").pack(anchor="w", padx=16, pady=(0, 12))
        return f

    def build_home(self, parent: ctk.CTkFrame) -> None:
        self.page_heading(parent, "Your client, your style.", "Configure your FlowwwClient client modules and manage the selected Fabric instance.")
        hero = ctk.CTkFrame(parent, fg_color="#170F14", corner_radius=18, border_width=1, border_color="#50232B")
        hero.pack(fill="x", pady=(0, 14))
        hero.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hero, text="ঌ", text_color=ACCENT, font=ctk.CTkFont(size=45, weight="bold")).grid(row=0, column=0, sticky="w", padx=(22, 0), pady=(18, 0))
        ctk.CTkLabel(hero, text="FLOWWWCLIENT", text_color=TEXT, font=ctk.CTkFont(size=24, weight="bold")).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 3))
        ctk.CTkLabel(hero, text="Personalize modules • Tune appearance • Manage profile JARs", text_color="#C4A8AD", font=ctk.CTkFont(size=12)).grid(row=2, column=0, sticky="w", padx=24, pady=(0, 18))
        ctk.CTkButton(hero, text="Choose instance", command=self.choose_instance, fg_color=ACCENT, hover_color=ACCENT_HOVER, height=38, corner_radius=10).grid(row=1, column=1, rowspan=2, padx=22)

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="home")
        a = self.card(grid, "Client modules", "Toggle modules and edit their available values.")
        a.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=5)
        self._mini_stat(a, f"{sum(1 for m in self.modules if m.get('enabled'))} enabled", "Active in your saved configuration")
        ctk.CTkButton(a, text="Manage client modules  →", command=lambda: self.show_page("Client Mods"), fg_color="#2A2026", hover_color="#3A252C", height=36).pack(fill="x", padx=16, pady=(8, 16))
        b = self.card(grid, "Game mods", "Manage JAR files for the selected instance.")
        b.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=5)
        mod_count = len(self.scan_mods()) if self.mods_dir else 0
        self._mini_stat(b, f"{mod_count} detected", "Changes apply on the next game start")
        ctk.CTkButton(b, text="Open game mod manager  →", command=lambda: self.show_page("Game Mods"), fg_color="#2A2026", hover_color="#3A252C", height=36).pack(fill="x", padx=16, pady=(8, 16))
        note = self.card(parent, "Important", "Motion Blur controls in this starter only save settings; they do not add a motion-blur rendering effect. The Fabric companion mod implements the name-tag marker. The panel does not launch Minecraft by itself.")
        note.pack(fill="x", pady=(12, 2))

    def _mini_stat(self, parent: ctk.CTkFrame, value: str, label: str) -> None:
        ctk.CTkLabel(parent, text=value, text_color=ACCENT_HOVER, font=ctk.CTkFont(size=23, weight="bold")).pack(anchor="w", padx=16, pady=(4, 0))
        ctk.CTkLabel(parent, text=label, text_color=MUTED, font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(0, 10))

    def build_profiles(self, parent: ctk.CTkFrame) -> None:
        self.page_heading(parent, "Profiles & instances", "Select the game instance whose mods and FlowwwClient settings you want to manage.")
        box = self.card(parent, "Selected instance", "Choose the actual game directory used by your launcher. Usually it contains folders such as config, mods, resourcepacks and versions.")
        box.pack(fill="x", pady=5)
        path_text = str(self.instance_dir) if self.instance_dir else "No instance selected yet"
        self.path_label = ctk.CTkLabel(box, text=path_text, text_color=TEXT if self.instance_dir else MUTED, wraplength=900, justify="left")
        self.path_label.pack(anchor="w", padx=16, pady=(0, 12))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(row, text="Select instance folder", command=self.choose_instance, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Open folder", command=self.open_instance, fg_color="#2A2026", hover_color="#3A252C").pack(side="left")
        ctk.CTkLabel(parent, text="This panel keeps the instance path you select; it does not modify your launcher's profile database.", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", pady=12)

    def build_client_mods(self, parent: ctk.CTkFrame) -> None:
        self.page_heading(parent, "Client modules", "Switch modules on/off and customize their settings. Changes are saved to the selected instance config.")
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)
        listing = ctk.CTkScrollableFrame(body, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        listing.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        detail = ctk.CTkFrame(body, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        detail.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(listing, text="MODULES", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=12, pady=(12, 5))
        self.selected_module_id = getattr(self, "selected_module_id", "nametag-marker")
        for module in self.modules:
            self._module_card(listing, module, detail)
        self._build_module_editor(detail, self._find_module(self.selected_module_id))
        ctk.CTkButton(listing, text="＋ Add custom module", command=self.add_module, fg_color="#2A2026", hover_color="#3A252C", height=38).pack(fill="x", padx=10, pady=10)

    def _find_module(self, module_id: str) -> dict[str, Any] | None:
        return next((m for m in self.modules if m.get("id") == module_id), None)

    def _module_card(self, parent: ctk.CTkFrame, module: dict[str, Any], detail: ctk.CTkFrame) -> None:
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=8, pady=5)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=9)
        ctk.CTkLabel(row, text="◈", text_color=ACCENT, font=ctk.CTkFont(size=18)).pack(side="left", padx=(0, 10))
        labels = ctk.CTkFrame(row, fg_color="transparent")
        labels.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(labels, text=module.get("name", "Unnamed module"), text_color=TEXT, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        status = "Settings-only in this starter" if module.get("kind") == "motion_blur" else ("Custom module config" if module.get("custom") else "Client module")
        ctk.CTkLabel(labels, text=status, text_color=MUTED, font=ctk.CTkFont(size=10)).pack(anchor="w")
        switch = ctk.CTkSwitch(row, text="", width=42, command=lambda m=module: self.toggle_module(m), progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER)
        if module.get("enabled"):
            switch.select()
        else:
            switch.deselect()
        switch.pack(side="right", padx=(8, 0))
        ctk.CTkButton(row, text="Edit", width=55, height=28, fg_color="#2A2026", hover_color="#3A252C", command=lambda m=module: self.select_module(m)).pack(side="right", padx=(8, 0))
        if module.get("custom"):
            ctk.CTkButton(row, text="×", width=28, height=28, fg_color="#3A1D23", hover_color="#5A202A", command=lambda m=module: self.remove_module(m)).pack(side="right", padx=(0, 5))

    def toggle_module(self, module: dict[str, Any]) -> None:
        module["enabled"] = not bool(module.get("enabled"))
        self._apply_module_to_shared_config(module)
        self.write_shared_config()
        self.set_status(f"{module['name']} {'enabled' if module['enabled'] else 'disabled'}")
        self.show_page("Client Mods", animate=False)

    def _apply_module_to_shared_config(self, module: dict[str, Any]) -> None:
        kind = module.get("kind")
        if kind == "nametag":
            self.config_data["nametagEnabled"] = bool(module.get("enabled"))
        elif kind == "motion_blur":
            self.config_data["motionBlurEnabled"] = bool(module.get("enabled"))

    def select_module(self, module: dict[str, Any]) -> None:
        self.selected_module_id = module["id"]
        self.show_page("Client Mods", animate=False)

    def _build_module_editor(self, parent: ctk.CTkFrame, module: dict[str, Any] | None) -> None:
        for child in parent.winfo_children():
            child.destroy()
        if module is None:
            ctk.CTkLabel(parent, text="Select a module to edit", text_color=MUTED).pack(pady=30)
            return
        kind = module.get("kind")
        ctk.CTkLabel(parent, text="MODULE SETTINGS", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=16, pady=(16, 4))
        ctk.CTkLabel(parent, text=module.get("name", "Module"), text_color=TEXT, font=ctk.CTkFont(size=18, weight="bold"), wraplength=260).pack(anchor="w", padx=16, pady=(0, 14))
        if kind == "nametag":
            ctk.CTkLabel(parent, text="Marker text", text_color=MUTED).pack(anchor="w", padx=16)
            symbol_entry = ctk.CTkEntry(parent, placeholder_text="ঌ", height=36)
            symbol_entry.insert(0, str(self.config_data.get("nametagSymbol", "ঌ")))
            symbol_entry.pack(fill="x", padx=16, pady=(5, 12))
            ctk.CTkLabel(parent, text="Marker color", text_color=MUTED).pack(anchor="w", padx=16)
            color_row = ctk.CTkFrame(parent, fg_color="transparent")
            color_row.pack(fill="x", padx=16, pady=(5, 12))
            swatch = ctk.CTkLabel(color_row, text=str(self.config_data.get("nametagColor", ACCENT)), fg_color=str(self.config_data.get("nametagColor", ACCENT)), text_color=TEXT, corner_radius=8, width=100, height=34)
            swatch.pack(side="left", padx=(0, 8))
            def pick_color() -> None:
                chosen = colorchooser.askcolor(color=self.config_data.get("nametagColor", ACCENT), parent=self)
                if chosen and chosen[1]:
                    self.config_data["nametagColor"] = chosen[1]
                    swatch.configure(text=chosen[1], fg_color=chosen[1])
                    self.write_shared_config()
            ctk.CTkButton(color_row, text="Choose", command=pick_color, width=78, height=34, fg_color="#2A2026", hover_color="#3A252C").pack(side="left")
            ctk.CTkLabel(parent, text="Name-tag scale", text_color=MUTED).pack(anchor="w", padx=16)
            scale_val = ctk.CTkLabel(parent, text=f"{float(self.config_data.get('nametagScale', 1.0)):.2f}×", text_color=TEXT)
            scale_val.pack(anchor="e", padx=16)
            slider = ctk.CTkSlider(parent, from_=0.6, to=1.8, number_of_steps=24, progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER, command=lambda v: scale_val.configure(text=f"{float(v):.2f}×"))
            slider.set(float(self.config_data.get("nametagScale", 1.0)))
            slider.pack(fill="x", padx=16, pady=(0, 12))
            def save_tag() -> None:
                symbol = symbol_entry.get().strip() or "ঌ"
                self.config_data["nametagSymbol"] = symbol[:8]
                self.config_data["nametagScale"] = round(float(slider.get()), 2)
                module["enabled"] = True
                self.config_data["nametagEnabled"] = True
                self.write_shared_config()
                self.set_status("Name-tag marker settings saved")
                self.show_page("Client Mods", animate=False)
            ctk.CTkButton(parent, text="Save settings", command=save_tag, fg_color=ACCENT, hover_color=ACCENT_HOVER, height=38).pack(fill="x", padx=16, pady=(2, 12))
            ctk.CTkLabel(parent, text="Color and scale apply to the companion Fabric mod's name labels.", text_color=MUTED, wraplength=270, justify="left", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(0, 12))
        elif kind == "motion_blur":
            ctk.CTkLabel(parent, text="Strength", text_color=MUTED).pack(anchor="w", padx=16)
            val = ctk.CTkLabel(parent, text=f"{float(self.config_data.get('motionBlurStrength', .35)):.2f}", text_color=TEXT)
            val.pack(anchor="e", padx=16)
            slider = ctk.CTkSlider(parent, from_=0.0, to=1.0, number_of_steps=20, progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER, command=lambda v: val.configure(text=f"{float(v):.2f}"))
            slider.set(float(self.config_data.get("motionBlurStrength", .35)))
            slider.pack(fill="x", padx=16, pady=(0, 12))
            def save_blur() -> None:
                self.config_data["motionBlurEnabled"] = bool(module.get("enabled"))
                self.config_data["motionBlurStrength"] = round(float(slider.get()), 2)
                self.write_shared_config()
                self.set_status("Motion Blur setting saved (effect not included in starter)", success=False)
            ctk.CTkButton(parent, text="Save setting", command=save_blur, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(fill="x", padx=16, pady=(0, 12))
            ctk.CTkLabel(parent, text="Heads-up: this starter stores the toggle and strength, but does not render a blur effect.", text_color="#E8A4AA", wraplength=270, justify="left", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(0, 12))
        else:
            ctk.CTkLabel(parent, text="Module enabled state is stored in the configuration. A game-side renderer/module implementation is required for the effect.", text_color=MUTED, wraplength=270, justify="left").pack(anchor="w", padx=16, pady=6)
            ctk.CTkButton(parent, text="Rename", command=lambda: self.rename_module(module), fg_color="#2A2026", hover_color="#3A252C").pack(fill="x", padx=16, pady=6)
            if module.get("custom"):
                ctk.CTkButton(parent, text="Remove module", command=lambda: self.remove_module(module), fg_color="#4A1E26", hover_color="#70232D").pack(fill="x", padx=16, pady=6)

    def add_module(self) -> None:
        name = simpledialog.askstring("Add custom module", "Module name:", parent=self)
        if not name or not name.strip():
            return
        module_id = "custom-" + "".join(c.lower() if c.isalnum() else "-" for c in name.strip()).strip("-")
        if self._find_module(module_id):
            messagebox.showwarning("Already exists", "A module with that name already exists.", parent=self)
            return
        module = {"id": module_id, "name": name.strip()[:50], "enabled": False, "kind": "custom", "custom": True}
        self.modules.append(module)
        self.selected_module_id = module_id
        self.config_data["modules"] = self.modules
        self.write_shared_config()
        self.show_page("Client Mods", animate=False)

    def remove_module(self, module: dict[str, Any]) -> None:
        if not module.get("custom"):
            messagebox.showinfo("Built-in module", "Built-in entries cannot be removed. You can switch them off.", parent=self)
            return
        if not messagebox.askyesno("Remove module", f"Remove '{module['name']}' from this panel config?", parent=self):
            return
        self.modules[:] = [m for m in self.modules if m.get("id") != module.get("id")]
        self.config_data["modules"] = self.modules
        self.selected_module_id = "nametag-marker"
        self.write_shared_config()
        self.show_page("Client Mods", animate=False)

    def rename_module(self, module: dict[str, Any]) -> None:
        name = simpledialog.askstring("Rename module", "New name:", initialvalue=module.get("name", ""), parent=self)
        if name and name.strip():
            module["name"] = name.strip()[:50]
            self.config_data["modules"] = self.modules
            self.write_shared_config()
            self.show_page("Client Mods", animate=False)

    def build_game_mods(self, parent: ctk.CTkFrame) -> None:
        self.page_heading(parent, "Game mods", "Manage .jar files in the selected profile. Enable/disable takes effect after restarting Minecraft.")
        path_card = self.card(parent, "Mods folder", "Choose the exact mods folder for your selected Fabric instance. This tool only acts inside that folder.")
        path_card.pack(fill="x", pady=(0, 10))
        path_row = ctk.CTkFrame(path_card, fg_color="transparent")
        path_row.pack(fill="x", padx=16, pady=(0, 14))
        self.mods_path_entry = ctk.CTkEntry(path_row, placeholder_text="Select a mods folder…", height=36)
        if self.mods_dir:
            self.mods_path_entry.insert(0, str(self.mods_dir))
        self.mods_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(path_row, text="Browse", command=self.choose_mods_folder, fg_color=ACCENT, hover_color=ACCENT_HOVER, width=90).pack(side="left")
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(actions, text="＋ Import JAR", command=self.import_mods, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Refresh", command=self.refresh_game_mod_list, fg_color="#2A2026", hover_color="#3A252C").pack(side="left")
        self.mod_list = ctk.CTkScrollableFrame(parent, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        self.mod_list.pack(fill="both", expand=True)
        self.refresh_game_mod_list()

    def scan_mods(self) -> list[Path]:
        if not self.mods_dir or not self.mods_dir.is_dir():
            return []
        try:
            return sorted([p for p in self.mods_dir.iterdir() if p.is_file() and (p.name.lower().endswith(".jar") or p.name.lower().endswith(".jar.disabled"))], key=lambda p: p.name.casefold())
        except OSError:
            return []

    def choose_instance(self) -> None:
        selected = filedialog.askdirectory(title="Select Minecraft instance/game directory", parent=self)
        if not selected:
            return
        self.instance_dir = Path(selected)
        self.mods_dir = self.instance_dir / "mods"
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        self.load_selected_instance_config()
        self.modules = self.config_data.setdefault("modules", json.loads(json.dumps(DEFAULT_CONFIG["modules"])))
        self.write_shared_config()
        self.refresh_header()
        self.save_panel_state()
        self.set_status(f"Selected instance: {self.instance_dir.name}")
        self.show_page("Profiles", animate=False)

    def open_instance(self) -> None:
        target = self.instance_dir
        if not target or not target.exists():
            messagebox.showinfo("No instance", "Select an instance folder first.", parent=self)
            return
        self.open_path(target)

    @staticmethod
    def open_path(path: Path) -> None:
        import subprocess
        import os
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Open folder failed", str(exc))

    def choose_mods_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select mods folder", initialdir=str(self.instance_dir or Path.home()), parent=self)
        if not selected:
            return
        folder = Path(selected)
        if folder.name.lower() != "mods":
            if not messagebox.askyesno("Confirm folder", "The selected folder is not named 'mods'. Use it anyway?", parent=self):
                return
        self.mods_dir = folder
        self.mods_path_entry.delete(0, "end")
        self.mods_path_entry.insert(0, str(folder))
        if self.instance_dir is None:
            self.instance_dir = folder.parent
            self.load_selected_instance_config()
            self.refresh_header()
            self.save_panel_state()
        self.refresh_game_mod_list()

    def import_mods(self) -> None:
        paths = filedialog.askopenfilenames(title="Import mod JAR(s)", filetypes=[("Minecraft mod JAR", "*.jar"), ("All files", "*.*")], parent=self)
        if not paths:
            return
        if self.mods_dir is None:
            messagebox.showwarning("Choose mods folder", "Select a mods folder first.", parent=self)
            return
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        imported = 0
        try:
            for item in paths:
                src = Path(item)
                if src.suffix.lower() != ".jar":
                    continue
                dest = self.mods_dir / src.name
                if dest.exists():
                    if not messagebox.askyesno("File exists", f"{src.name} already exists. Replace it?", parent=self):
                        continue
                shutil.copy2(src, dest)
                imported += 1
        except OSError as exc:
            messagebox.showerror("Import failed", str(exc), parent=self)
        self.refresh_game_mod_list()
        self.set_status(f"Imported {imported} mod JAR(s)")

    def refresh_game_mod_list(self) -> None:
        if not hasattr(self, "mod_list"):
            return
        for child in self.mod_list.winfo_children():
            child.destroy()
        if not self.mods_dir or not self.mods_dir.is_dir():
            ctk.CTkLabel(self.mod_list, text="Select a mods folder to discover installed JARs.", text_color=MUTED).pack(pady=30)
            return
        files = self.scan_mods()
        if not files:
            ctk.CTkLabel(self.mod_list, text="No .jar mods found in this folder.", text_color=MUTED).pack(pady=30)
            return
        for path in files:
            disabled = path.name.lower().endswith(".jar.disabled")
            card = ctk.CTkFrame(self.mod_list, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
            card.pack(fill="x", padx=8, pady=5)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=10)
            ctk.CTkLabel(row, text="▣", text_color=MUTED if disabled else ACCENT, font=ctk.CTkFont(size=19)).pack(side="left", padx=(0, 10))
            text_box = ctk.CTkFrame(row, fg_color="transparent")
            text_box.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(text_box, text=path.name, text_color=TEXT if not disabled else MUTED, font=ctk.CTkFont(size=12, weight="bold"), wraplength=500, justify="left").pack(anchor="w")
            ctk.CTkLabel(text_box, text="DISABLED — not loaded by Fabric" if disabled else "Enabled for next game start", text_color=MUTED, font=ctk.CTkFont(size=10)).pack(anchor="w")
            ctk.CTkButton(row, text="Enable" if disabled else "Disable", width=80, fg_color=ACCENT if disabled else "#2A2026", hover_color=ACCENT_HOVER if disabled else "#3A252C", command=lambda p=path: self.toggle_jar(p)).pack(side="right", padx=(8, 0))
            ctk.CTkButton(row, text="Remove", width=72, fg_color="#3A1D23", hover_color="#5A202A", command=lambda p=path: self.remove_jar(p)).pack(side="right")
            ctk.CTkButton(row, text="Folder", width=65, fg_color="#20252C", hover_color=CARD_HOVER, command=lambda: self.open_path(self.mods_dir)).pack(side="right", padx=(0, 8))

    def toggle_jar(self, path: Path) -> None:
        try:
            if path.name.lower().endswith(".jar.disabled"):
                target = path.with_name(path.name[:-len(".disabled")])
            elif path.name.lower().endswith(".jar"):
                target = path.with_name(path.name + ".disabled")
            else:
                return
            if target.exists():
                messagebox.showerror("Name conflict", f"Cannot rename because this already exists:\n{target.name}", parent=self)
                return
            path.rename(target)
            self.refresh_game_mod_list()
            self.set_status(f"{target.name}: change applies next game start")
        except OSError as exc:
            messagebox.showerror("Could not change mod state", str(exc), parent=self)

    def remove_jar(self, path: Path) -> None:
        if not messagebox.askyesno("Remove mod file", f"Permanently delete this file?\n\n{path.name}", parent=self):
            return
        try:
            path.unlink()
            self.refresh_game_mod_list()
            self.set_status(f"Removed {path.name}")
        except OSError as exc:
            messagebox.showerror("Remove failed", str(exc), parent=self)

    def build_settings(self, parent: ctk.CTkFrame) -> None:
        self.page_heading(parent, "Settings", "Panel preferences and config export.")
        card = self.card(parent, "UI behavior", "Choose whether page transitions should animate.")
        card.pack(fill="x", pady=5)
        switch = ctk.CTkSwitch(card, text="Smooth page transitions", command=lambda: self.set_animation(switch.get()), progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER)
        switch.pack(anchor="w", padx=16, pady=(0, 16))
        switch.select() if self.animation_enabled else switch.deselect()
        cfg_card = self.card(parent, "Shared game config", "Write settings to config/flowwwclient.json in the selected instance. The companion Fabric mod reads this file when it starts; in-game edits are saved there too.")
        cfg_card.pack(fill="x", pady=5)
        row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(row, text="Save/export config", command=self.export_config, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Open config folder", command=self.open_config_folder, fg_color="#2A2026", hover_color="#3A252C").pack(side="left")

    def set_animation(self, value: int) -> None:
        self.animation_enabled = bool(value)
        self.save_panel_state()

    def export_config(self) -> None:
        self.write_shared_config()
        if self.instance_dir:
            self.set_status("Config saved to selected instance")
        else:
            messagebox.showinfo("Saved locally", "Panel preferences were saved, but choose a Minecraft instance to export the game config.", parent=self)

    def open_config_folder(self) -> None:
        if not self.instance_dir:
            messagebox.showinfo("No instance selected", "Choose an instance first.", parent=self)
            return
        folder = self.instance_dir / "config"
        folder.mkdir(parents=True, exist_ok=True)
        self.open_path(folder)


if __name__ == "__main__":
    app = FlowwwPanel()
    app.mainloop()
