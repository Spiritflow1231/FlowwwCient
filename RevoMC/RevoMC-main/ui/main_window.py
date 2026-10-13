"""
ui/main_window.py  –  CustomTkinter UI for FlowwwClient
All program logic is identical to the original PyQt6 version.
"""
import json
import io
import urllib.parse
import urllib.request
import webbrowser
import os
import platform
import ctypes
import shutil
import sys
import struct
import subprocess
import threading
import tempfile
import time
import uuid
import copy
import zipfile
import re
import queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps
import customtkinter as ctk
from tkinter import TclError, filedialog, messagebox, simpledialog

import core.config as config
import core.auth as auth
import core.modrinth as modrinth
import core.profiles as profile_store
import core.accounts as account_store
import core.skins as skin_store
from core import client_mods
from ui.client_mods_page import ClientModsPanel
from core import skin_render
from core.skins import validate_cosmetic_image
from ui.motion import Motion
from ui.overlay import OverlayDialog
from ui.stage import HeroStage, default_steve
from ui.theme import (
    DEFAULT_THEME, apply_customtkinter_palette, color_map, get_theme,
    is_light, normalize_theme_name, retheme_widget_tree,
)
from core.installer import (
    fetch_release_versions,
    fetch_fabric_versions,
    install_minecraft,
    install_fabric,
    install_mods,
    has_fabric_api,
    AVAILABLE_MODS,
)
from core.launcher import disable_incompatible_mods, launch
from core.java_manager import get_required_java_version

# ── Appearance ────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Colour tokens — loaded from the active theme at module level (defaults).
# MainWindow.__init__ reloads from config and _apply_theme() updates live.
_t = get_theme(config.load().get("theme", DEFAULT_THEME))
apply_customtkinter_palette(_t)
BG_PRIMARY   = _t["BG_PRIMARY"]
BG_SECONDARY = _t["BG_SECONDARY"]
BG_CONSOLE   = _t["BG_CONSOLE"]
BG_CARD      = _t["BG_CARD"]
BORDER_COL   = _t["BORDER_COL"]
GREEN        = _t["ACCENT"]
GREEN_DARK   = _t["ACCENT_DARK"]
BLUE         = _t["ACCENT_ALT"]
RED          = _t["RED"]
MS_BLUE      = _t["MS_BLUE"]
MS_BLUE_DARK = _t["MS_BLUE_DARK"]
TEXT_FG      = _t["TEXT_FG"]
TEXT_MUTED   = _t["TEXT_MUTED"]
TEXT_LABEL   = _t["TEXT_LABEL"]
ACCENT_TEXT  = _t["ACCENT_TEXT"]
_ICON_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="project-icons")


def _resource_path(relative_path: str) -> Path:
    """Resolve an application asset from source or a PyInstaller bundle."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return bundle_root / relative_path


def _download_project_icon(url: str):
    modrinth._validate_download_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": modrinth.USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        modrinth._validate_download_url(response.geturl())
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("The project icon exceeds the allowed size.")
    with Image.open(io.BytesIO(data)) as source:
        if source.format not in {"PNG", "JPEG", "WEBP"} or max(source.size) > 4096:
            raise ValueError("Modrinth returned an unsupported project icon.")
        image = source.convert("RGBA")
        image.thumbnail((48, 48))
        return image


def _project_card_content(project: dict, category: str, game_version: str) -> tuple[str, str, str]:
    title = project.get("title") or project.get("slug") or "Untitled project"
    description = project.get("description") or "No description provided."
    author = project.get("author") or "Unknown author"
    category_label = ProfileEditorWindow.CATEGORY_LABELS.get(
        category, category.title()
    )
    details = f"by {author}  ·  {category_label}  ·  MC {game_version}"
    categories = project.get("display_categories") or project.get("categories") or []
    if categories:
        details += f"  ·  Loaders/categories: {', '.join(str(value) for value in categories[:3])}"
    supported_versions = project.get("versions")
    if isinstance(supported_versions, list) and supported_versions:
        details += f"  ·  Versions: {', '.join(map(str, supported_versions[:4]))}"
    downloads = project.get("downloads")
    if isinstance(downloads, int) and downloads >= 0:
        details += f"  ·  {downloads:,} downloads"
    return title, description, details


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_system_ram_gb() -> int:
    """Detect total system RAM in GB. Returns at least 2."""
    try:
        system = platform.system()
        if system == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return max(2, int(stat.ullTotalPhys / (1024 ** 3)))
        elif system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            return max(2, int(int(out.strip()) / (1024 ** 3)))
        else:  # Linux
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return max(2, int(kb / (1024 ** 2)))
    except Exception:
        pass
    return 16  # safe fallback


def _section_label(master, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master, text=text.upper(),
        text_color=TEXT_LABEL,
        font=ctk.CTkFont(size=10, weight="bold"),
    )


def _default_steve_skin() -> Image.Image:
    """Create the standard Steve-color texture as a local preview fallback."""
    from PIL import ImageDraw

    skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    skin.paste((198, 145, 105, 255), (8, 8, 16, 16))
    ImageDraw.Draw(skin).rectangle((9, 11, 10, 12), fill=(37, 71, 151, 255))
    ImageDraw.Draw(skin).rectangle((13, 11, 14, 12), fill=(37, 71, 151, 255))
    ImageDraw.Draw(skin).rectangle((11, 13, 12, 14), fill=(151, 92, 65, 255))
    ImageDraw.Draw(skin).rectangle((11, 15, 13, 15), fill=(96, 52, 42, 255))
    ImageDraw.Draw(skin).rectangle((40, 8, 47, 9), fill=(76, 49, 33, 255))
    ImageDraw.Draw(skin).rectangle((40, 10, 41, 13), fill=(76, 49, 33, 255))
    ImageDraw.Draw(skin).rectangle((46, 10, 47, 13), fill=(76, 49, 33, 255))
    skin.paste((76, 49, 33, 255), (42, 8, 46, 9))
    skin.paste((57, 174, 168, 255), (20, 20, 28, 32))
    skin.paste((57, 174, 168, 255), (20, 36, 28, 48))
    skin.paste((198, 145, 105, 255), (44, 20, 48, 32))
    skin.paste((198, 145, 105, 255), (44, 36, 48, 48))
    skin.paste((198, 145, 105, 255), (36, 52, 40, 64))
    skin.paste((54, 91, 171, 255), (4, 20, 8, 32))
    skin.paste((54, 91, 171, 255), (20, 52, 24, 64))
    return skin


def _render_skin_preview(skin: Image.Image) -> Image.Image:
    """Compose front-facing skin texture regions into a pixel-art bust."""
    source = skin.convert("RGBA")
    factor = source.width // 64
    if factor < 1 or source.width % 64 or source.height not in (32 * factor, 64 * factor):
        raise ValueError("Expected a standard 64×64 or 64×32 Minecraft skin texture.")

    def crop(box):
        return source.crop(tuple(value * factor for value in box))

    def scale(image, size):
        return image.resize(size, Image.Resampling.NEAREST)

    canvas = Image.new("RGBA", (116, 174), (0, 0, 0, 0))
    head = crop((8, 8, 16, 16))
    if source.height >= 64 * factor:
        head = Image.alpha_composite(head, crop((40, 8, 48, 16)))
    canvas.alpha_composite(scale(head, (48, 48)), (34, 2))

    body = crop((20, 20, 28, 32))
    arm_right = crop((44, 20, 48, 32))
    leg_right = crop((4, 20, 8, 32))
    if source.height >= 64 * factor:
        body = Image.alpha_composite(body, crop((20, 36, 28, 48)))
        arm_right = Image.alpha_composite(arm_right, crop((44, 36, 48, 48)))
        leg_right = Image.alpha_composite(leg_right, crop((4, 36, 8, 48)))
        arm_left = crop((36, 52, 40, 64))
        leg_left = crop((20, 52, 24, 64))
    else:
        arm_left = arm_right.copy()
        leg_left = leg_right.copy()
    canvas.alpha_composite(scale(arm_left, (16, 52)), (19, 53))
    canvas.alpha_composite(scale(arm_right, (16, 52)), (81, 53))
    canvas.alpha_composite(scale(body, (46, 58)), (35, 51))
    canvas.alpha_composite(scale(leg_left, (21, 50)), (37, 107))
    canvas.alpha_composite(scale(leg_right, (21, 50)), (58, 107))

    from PIL import ImageDraw

    shading = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shading)
    for left, top, right, bottom in (
        (78, 54, 81, 104), (80, 4, 82, 49), (77, 109, 79, 157),
    ):
        draw.rectangle((left, top, right, bottom), fill=(0, 0, 0, 45))
    canvas.alpha_composite(shading)
    return canvas


class ProfileEditorWindow(ctk.CTkFrame):
    """Profile-specific content manager for FlowwwClient."""

    CATEGORIES = [
        ("Overview", "overview"),
        ("Mods", "mods"),
        ("Resource Packs", "resourcepacks"),
        ("Shader Packs", "shaderpacks"),
        ("Datapacks", "datapacks"),
        ("Modpacks", "modpacks"),
        ("Client Mods", "client_mods"),
    ]
    CATEGORY_LABELS = {key: label for label, key in CATEGORIES}

    def __init__(self, parent, profile, initial_category="overview"):
        super().__init__(parent.page_container, fg_color="transparent")

        self.parent = parent
        self.profile = profile
        self.theme = parent.theme
        categories = {key for _, key in self.CATEGORIES}
        self.category = initial_category if initial_category in categories else "mods"
        self.tab = "Installed"
        self._working = False
        self._cancel_event = None
        self._request_serial = 0
        self._browse_projects = []
        self._project_buttons = {}
        self._project_images = {}
        self._active_install_project_id = None
        self.page_offset = 0
        self._latest_version_mode = False
        self._ui_callbacks = queue.SimpleQueue()

        self._build_ui()

    def _build_ui(self):
        loader_version = self.profile.get("fabric_loader_version") or getattr(
            self.parent, "latest_fabric_loader_versions", {}
        ).get(self.profile.get("mc_version"))
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 12))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Edit Profile",
            text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=23, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=f"Minecraft {self.profile.get('mc_version', '?')}  ·  "
                 f"{self.profile.get('type', 'vanilla').title()}"
                 + (
                     f"  ·  Fabric {loader_version}"
                     if self.profile.get("type") == "fabric" and loader_version else ""
                 ),
            text_color=self.theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=12),
        ).pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.parent._show_profile_editor_navigation(self)
        self.category_buttons = self.parent._profile_category_buttons

        # Right content panel
        self.content = ctk.CTkFrame(
            body,
            fg_color=self.theme["BG_SECONDARY"],
            corner_radius=12,
            border_width=1,
            border_color=self.theme["BORDER_COL"],
        )
        self.content.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(4, weight=1)

        self.heading = ctk.CTkLabel(
            self.content,
            text=self.CATEGORY_LABELS[self.category],
            text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.heading.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 12))

        search_row = ctk.CTkFrame(self.content, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        search_row.grid_columnconfigure(0, weight=1)
        self.search = ctk.CTkEntry(
            search_row,
            placeholder_text=f"Search {self.category}…",
            height=38,
            border_color=self.theme["BORDER_COL"],
            fg_color=self.theme["BG_PRIMARY"],
        )
        self.search_row = search_row
        self.search.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search.bind("<Return>", lambda _event: self._on_search())
        self.search_button = ctk.CTkButton(
            search_row,
            text="Search",
            width=82,
            height=38,
            fg_color=self.theme["ACCENT"],
            text_color=self.theme["ACCENT_TEXT"],
            hover_color=self.theme["ACCENT_DARK"],
            command=self._on_search,
        )
        self.search_button.grid(row=0, column=1)

        self.world_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.world_frame.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        ctk.CTkLabel(
            self.world_frame,
            text="Datapack target world",
            text_color=self.theme["TEXT_MUTED"],
        ).pack(side="left", padx=(0, 10))
        self.world_var = ctk.StringVar(value="")
        self.world_menu = ctk.CTkOptionMenu(
            self.world_frame,
            variable=self.world_var,
            values=["No worlds found"],
            fg_color=self.theme["BG_PRIMARY"],
            button_color=self.theme["ACCENT"],
            button_hover_color=self.theme["ACCENT_DARK"],
            text_color=self.theme["TEXT_FG"],
            command=lambda _value: self._refresh_content(),
        )
        self.world_menu.pack(side="left", fill="x", expand=True)
        self.world_frame.grid_remove()

        tabs = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs = tabs
        tabs.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10))
        tabs.grid_columnconfigure(0, weight=1)
        tab_choices = ctk.CTkFrame(tabs, fg_color="transparent")
        tab_choices.grid(row=0, column=0, sticky="w")

        self.installed_btn = ctk.CTkButton(
            tab_choices,
            text="Installed",
            width=100,
            fg_color=self.theme["ACCENT"],
            text_color=self.theme["ACCENT_TEXT"],
            command=lambda: self._select_tab("Installed"),
        )
        self.installed_btn.pack(side="left", padx=(0, 8))

        self.browse_btn = ctk.CTkButton(
            tab_choices,
            text="Browse",
            width=100,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=lambda: self._select_tab("Browse"),
        )
        self.browse_btn.pack(side="left")
        tab_actions = ctk.CTkFrame(tabs, fg_color="transparent")
        tab_actions.grid(row=0, column=1, sticky="e")
        self.refresh_content_btn = ctk.CTkButton(
            tab_actions, text="Refresh", width=76,
            fg_color="transparent", border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=self._refresh_content,
        )
        self.refresh_content_btn.pack(side="left", padx=(0, 6))
        self.import_content_btn = ctk.CTkButton(
            tab_actions, text="Import file", width=100,
            fg_color=self.theme["ACCENT"], text_color=self.theme["ACCENT_TEXT"],
            hover_color=self.theme["ACCENT_DARK"],
            command=self._import_local_content,
        )
        self.import_content_btn.pack(side="left")

        self.results = ctk.CTkScrollableFrame(
            self.content,
            fg_color=self.theme["BG_PRIMARY"],
            corner_radius=10,
        )
        self.results.grid(
            row=4, column=0, sticky="nsew", padx=18, pady=(0, 8)
        )
        footer = ctk.CTkFrame(self.content, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(
            footer,
            text="",
            text_color=self.theme["TEXT_MUTED"],
            anchor="w",
            justify="left",
            wraplength=600,
        )
        self.status.grid(row=0, column=0, sticky="ew")
        self.page_status = ctk.CTkLabel(
            footer, text="", text_color=self.theme["TEXT_MUTED"]
        )
        self.page_status.grid(row=0, column=1, padx=(8, 0))
        self.previous_page_btn = ctk.CTkButton(
            footer, text="‹", width=32, state="disabled",
            command=lambda: self._change_page(-1),
        )
        self.previous_page_btn.grid(row=0, column=2, padx=(8, 0))
        self.next_page_btn = ctk.CTkButton(
            footer, text="›", width=32,
            command=lambda: self._change_page(1),
        )
        self.next_page_btn.grid(row=0, column=3, padx=(4, 0))
        self.cancel_btn = ctk.CTkButton(
            footer,
            text="Cancel download",
            width=112,
            state="disabled",
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=self._cancel_install,
        )
        self.cancel_btn.grid(row=0, column=4, padx=(8, 0))
        self.install_progress = ctk.CTkProgressBar(
            footer,
            height=4,
            progress_color=self.theme["ACCENT"],
            fg_color=self.theme["BG_PRIMARY"],
        )
        self.install_progress.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        self.install_progress.set(0)
        self.install_progress.grid_remove()

        self._refresh_content()
        self.after(20, self._drain_ui_callbacks)

    def _back_to_profiles(self):
        if self._working:
            self._cancel_install()
            return
        self.parent._leave_profile_editor()

    def _select_category(self, category):
        if category not in self.CATEGORY_LABELS:
            return
        self.category = category
        self.page_offset = 0

        for key, button in self.category_buttons.items():
            active = key == category
            self.parent._animate_widget_color(
                button, self.theme["ACCENT"] if active else "transparent"
            )
            button.configure(
                text_color=self.theme["ACCENT_TEXT"] if active else self.theme["TEXT_FG"]
            )

        self._refresh_content()
        self._slide_content()

    def _select_tab(self, tab):
        self.tab = tab

        self.installed_btn.configure(
            fg_color=self.theme["ACCENT"] if tab == "Installed" else "transparent",
            text_color=self.theme["ACCENT_TEXT"] if tab == "Installed" else self.theme["TEXT_FG"],
        )
        self.browse_btn.configure(
            fg_color=self.theme["ACCENT"] if tab == "Browse" else "transparent",
            text_color=self.theme["ACCENT_TEXT"] if tab == "Browse" else self.theme["TEXT_FG"],
        )

        self._refresh_content()
        self._slide_content()

    def _slide_content(self):
        """Slide the content area up a little whenever the section or tab changes."""
        target = (
            getattr(self, "client_mods_panel", None)
            if self.category == "client_mods" else self.results
        )
        if target is None:
            return
        motion = self.parent.motion
        distance = 26

        # a CTkScrollableFrame is laid out through its outer frame
        outer = getattr(target, "_parent_frame", target)

        def step(progress):
            outer.grid_configure(pady=(round(distance * (1 - progress)), 8))

        motion.run(("editor-section", str(self)), 200, step)

    def _on_search(self):
        if self.category == "overview":
            return
        self.page_offset = 0
        self._latest_version_mode = False
        self.tab = "Browse"
        self.installed_btn.configure(
            fg_color="transparent",
            text_color=self.theme["TEXT_FG"],
        )
        self.browse_btn.configure(
            fg_color=self.theme["ACCENT"],
            text_color=self.theme["ACCENT_TEXT"],
        )
        self._search_projects()

    def _refresh_content(self):
        self._request_serial += 1
        self.heading.configure(text=self.CATEGORY_LABELS[self.category])
        if self.category == "client_mods":
            self.search_row.grid_remove()
            self.world_frame.grid_remove()
            self.tabs.grid_remove()
            self._clear_results()
            if getattr(self, "client_mods_panel", None) is None:
                self.client_mods_panel = ClientModsPanel(self.content, self)
                self.client_mods_panel.grid(row=4, column=0, sticky="nsew",
                                            padx=18, pady=(0, 8))
            else:
                self.client_mods_panel.grid()
                self.client_mods_panel.refresh()
            self.client_mods_panel.tkraise()
            return
        panel = getattr(self, "client_mods_panel", None)
        if panel is not None:
            panel.grid_remove()
        if self.category != "overview":
            category_names = {
                "mods": "mods",
                "resourcepacks": "resource packs",
                "shaderpacks": "shaders",
                "datapacks": "datapacks",
                "modpacks": "modpacks",
            }
            search_action = "Filter installed" if self.tab == "Installed" else "Search"
            self.search.configure(
                placeholder_text=f"{search_action} {category_names[self.category]}…"
            )
        if self.category == "overview":
            self.search_row.grid_remove()
            self.world_frame.grid_remove()
            self.tabs.grid_remove()
            self._show_profile_overview()
            return
        self.search_row.grid()
        self.tabs.grid()
        if self.category == "datapacks":
            self.world_frame.grid()
            self._refresh_worlds()
        else:
            self.world_frame.grid_remove()
        self._clear_results()
        if self.tab == "Installed":
            self._show_installed()
        elif self.category == "datapacks" and not self.world_var.get():
            self._show_state(
                "No worlds found in this profile. Launch it once to copy existing "
                ".minecraft worlds, or create a world, then reopen the editor."
            )
        else:
            self._search_projects()

    def _show_profile_overview(self):
        self._clear_results()
        profile = self.profile
        loader_version = profile.get("fabric_loader_version") or getattr(
            self.parent, "latest_fabric_loader_versions", {}
        ).get(profile.get("mc_version"))
        ctk.CTkLabel(
            self.results,
            text=f"Minecraft {profile.get('mc_version', '?')}  ·  "
                 f"{profile.get('type', 'vanilla').title()}"
                 + (
                     f"  ·  Fabric loader {loader_version}"
                     if profile.get("type") == "fabric" and loader_version else ""
                 ),
            text_color=self.theme["TEXT_MUTED"],
        ).pack(anchor="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(
            self.results, text="Profile name", text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(6, 2))
        name_var = ctk.StringVar(value=profile.get("name", ""))
        name_entry = ctk.CTkEntry(self.results, textvariable=name_var, height=36)
        name_entry.pack(fill="x", padx=12)
        memory_var = ctk.IntVar(
            value=max(1, int(profile.get("memory_gb", self.parent.cfg.get("ram_gb", 2))))
        )
        ctk.CTkLabel(
            self.results,
            text=f"Memory allocation · {memory_var.get()} GB",
            text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(14, 2))
        memory_label = self.results.winfo_children()[-1]
        memory = ctk.CTkSlider(
            self.results, from_=1, to=self.parent.max_ram_gb,
            number_of_steps=max(1, self.parent.max_ram_gb - 1),
            variable=memory_var, progress_color=self.theme["ACCENT"],
            button_color=self.theme["ACCENT"],
        )
        memory.pack(fill="x", padx=12, pady=(0, 8))
        memory.configure(
            command=lambda value: memory_label.configure(
                text=f"Memory allocation · {int(value)} GB"
            )
        )
        ctk.CTkLabel(
            self.results, text="Java arguments", text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(8, 2))
        java_args_var = ctk.StringVar(value=profile.get("java_args", ""))
        ctk.CTkEntry(
            self.results, textvariable=java_args_var,
            placeholder_text="Optional JVM arguments",
        ).pack(fill="x", padx=12)
        boost_var = ctk.BooleanVar(
            value=bool(profile.get("performance_boost", profile.get("type") == "fabric"))
        )
        ctk.CTkCheckBox(
            self.results, text="Performance Boost (optimized G1GC settings)",
            variable=boost_var, text_color=self.theme["TEXT_FG"],
            fg_color=self.theme["ACCENT"], hover_color=self.theme["ACCENT_DARK"],
        ).pack(anchor="w", padx=12, pady=(14, 5))
        ctk.CTkLabel(
            self.results,
            text="This tunes JVM garbage collection and does not repair poor Wi-Fi or server latency.",
            text_color=self.theme["TEXT_MUTED"], wraplength=610, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        def save_overview():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Invalid profile name", "A profile name cannot be empty.", parent=self)
                return
            if any(
                other is not profile and other.get("name") == name
                for other in self.parent.cfg.get("profiles", [])
            ):
                messagebox.showerror("Duplicate profile name", "That profile name is already in use.", parent=self)
                return
            try:
                import shlex
                shlex.split(java_args_var.get())
            except ValueError as exc:
                messagebox.showerror("Invalid Java arguments", str(exc), parent=self)
                return
            previous_name = profile.get("name")
            previous_active = self.parent.cfg.get("active_profile")
            previous = {
                key: profile.get(key)
                for key in ("name", "memory_gb", "java_args", "performance_boost")
            }
            profile.update({
                "name": name,
                "memory_gb": int(memory_var.get()),
                "java_args": java_args_var.get().strip(),
                "performance_boost": bool(boost_var.get()),
            })
            if previous_active == previous_name:
                self.parent.cfg["active_profile"] = name
            try:
                config.save(self.parent.cfg)
                profile_store.save_manifest(profile)
                profile_store.sync_profiles(self.parent.cfg.get("profiles", []))
            except (OSError, ValueError, RuntimeError) as exc:
                for key, value in previous.items():
                    if value is None:
                        profile.pop(key, None)
                    else:
                        profile[key] = value
                self.parent.cfg["active_profile"] = previous_active
                messagebox.showerror("Could not save profile", str(exc), parent=self)
                return
            self.parent._refresh_profile_list()
            self.parent._update_home_profile(self.parent._current_profile())
            self.title(f"Edit Profile — {name}")
            self.status.configure(text="Profile settings saved.")

        ctk.CTkButton(
            self.results, text="Save Changes",
            fg_color=self.theme["ACCENT"], text_color=self.theme["ACCENT_TEXT"],
            hover_color=self.theme["ACCENT_DARK"], command=save_overview,
        ).pack(anchor="w", padx=12, pady=(4, 16))

    def _clear_results(self):
        for widget in self.results.winfo_children():
            widget.destroy()
        self._project_images.clear()

    def _show_state(self, text: str):
        ctk.CTkLabel(
            self.results,
            text=text,
            text_color=self.theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=13),
            wraplength=650,
            justify="left",
        ).pack(anchor="w", padx=14, pady=16)

    def _instance_dir(self) -> Path:
        return modrinth.profile_instance_dir(self.profile)

    def _refresh_worlds(self):
        saves = self._instance_dir() / "saves"
        worlds = []
        if (
            saves.is_dir()
            and saves.resolve().is_relative_to(self._instance_dir().resolve())
        ):
            for path in saves.iterdir():
                if path.is_dir() and path.resolve().is_relative_to(saves.resolve()):
                    worlds.append(path.name)
        current = self.world_var.get()
        self.world_menu.configure(values=worlds or ["No worlds found"])
        if current not in worlds:
            self.world_var.set(worlds[0] if worlds else "")

    def _category_directory(self) -> Path:
        instance = self._instance_dir()
        if self.category == "datapacks":
            world = self.world_var.get()
            if not world:
                raise RuntimeError("Select a world that already exists in this profile.")
            world_path = Path(world)
            if world_path.name != world or world in (".", "..") or "/" in world or "\\" in world:
                raise ValueError("Invalid world name.")
            return instance / "saves" / world / "datapacks"
        return instance / self.category

    def _is_shader_supported(self) -> bool:
        instance = self._instance_dir()
        mods_dir = instance / "mods"
        if not mods_dir.is_dir() or not mods_dir.resolve().is_relative_to(instance.resolve()):
            return False
        return any(
            path.is_file()
            and path.name.lower().startswith(("iris", "optifine"))
            for path in mods_dir.glob("*.jar")
        )

    def _show_installed(self):
        if self.category == "modpacks":
            query = self.search.get().strip().casefold()
            profiles = [
                profile for profile in self.parent.cfg.get("profiles", [])
                if isinstance(profile, dict)
                and (
                    isinstance(profile.get("source_modpack"), dict)
                    and profile["source_modpack"].get("project_id")
                    or isinstance(profile.get("imported_modpack"), dict)
                )
                and (
                    not query
                    or query in str(profile.get("name", "")).casefold()
                    or query in str(
                        profile.get("source_modpack", profile.get("imported_modpack", {})).get("title", "")
                    ).casefold()
                )
            ]
            if not profiles:
                self._show_state("No Modrinth modpacks have been imported yet.")
                return
            for profile in profiles:
                self._render_modpack_profile(profile)
            return

        if self.category == "datapacks" and not self.world_var.get():
            self._show_state("Select a world with an existing datapacks folder to view its packs.")
            return

        installed_content = self.profile.get("installed_content", {})
        raw_records = installed_content.get(self.category, []) if isinstance(installed_content, dict) else []
        records = [record for record in raw_records if isinstance(record, dict)]
        if self.category == "datapacks":
            records = [
                record for record in records
                if not record.get("world") or record.get("world") == self.world_var.get()
            ]
        query = self.search.get().strip().casefold()
        known = set()
        for record in records:
            filename = record.get("filename")
            if isinstance(filename, str):
                known.add(filename)
                if self.category == "mods" and filename.lower().endswith(".jar"):
                    known.add(f"{filename}.disabled")
        try:
            files = modrinth.list_installed_files(
                self.profile,
                self.category,
                self.world_var.get() if self.category == "datapacks" else None,
            )
        except (OSError, ValueError) as exc:
            self._show_state(f"Could not read installed content: {exc}")
            return

        found = False
        for record in records:
            filename = record.get("filename")
            if not isinstance(filename, str) or Path(filename).name != filename:
                continue
            if query and query not in filename.casefold() and query not in str(record.get("title", "")).casefold():
                continue
            target = self._category_directory() / filename
            disabled_target = target.with_name(target.name + ".disabled")
            if not target.is_file() and not disabled_target.is_file():
                continue
            self._render_installed_record(record, target, disabled_target)
            found = True
        for path in files:
            if path.name not in known and (not query or query in path.name.casefold()):
                self._render_installed_file(path)
                found = True
        if not found:
            self._show_state("Nothing is installed in this category for this profile yet.")

    def _open_content_folder(self, path: Path):
        try:
            folder = path.parent.resolve()
            if os.name == "nt":
                os.startfile(str(folder))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except (OSError, AttributeError) as exc:
            messagebox.showerror("Could not open folder", str(exc), parent=self)

    def _import_local_content(self):
        if self._working:
            return
        category = self.category
        if category == "modpacks":
            source_name = filedialog.askopenfilename(
                parent=self, title="Import Modrinth modpack",
                filetypes=[("Modrinth modpack", "*.mrpack")],
            )
            if not source_name:
                return
            source = Path(source_name)
            if source.suffix.lower() != ".mrpack":
                messagebox.showerror("Invalid modpack", "Choose a .mrpack file.", parent=self)
                return
            self._working = True
            self._set_manager_busy(True)
            self.status.configure(text="Validating and importing .mrpack…")

            def import_pack():
                profile = {
                    "instance_id": uuid.uuid4().hex,
                    "name": source.stem,
                    "mc_version": "",
                    "type": "vanilla",
                    "mods": [],
                }
                try:
                    manifest = modrinth.install_modpack(
                        source, modrinth.profile_instance_dir(profile)
                    )
                    profile.update({
                        "name": manifest["name"],
                        "mc_version": manifest["mc_version"],
                        "type": manifest["type"],
                        "imported_modpack": {
                            "title": manifest["name"],
                            "manifest_version": manifest["manifest_version"],
                        },
                    })
                    if manifest.get("fabric_loader_version"):
                        profile["fabric_loader_version"] = manifest["fabric_loader_version"]
                    self._post(lambda p=profile: self._finish_modpack_install(p))
                except Exception as exc:
                    self._post(lambda error=str(exc): self._finish_install_error(error))

            threading.Thread(target=import_pack, daemon=True).start()
            return

        source_name = filedialog.askopenfilename(
            parent=self,
            title=f"Import {category}",
            filetypes=[("Minecraft content", "*.jar" if category == "mods" else "*.zip")],
        )
        if not source_name:
            return
        source = Path(source_name)
        if category == "datapacks" and not self.world_var.get():
            messagebox.showinfo("Choose a world", "Select an existing world first.", parent=self)
            return
        try:
            destination = self._category_directory()
            if not destination.resolve().is_relative_to(self._instance_dir().resolve()):
                raise ValueError("The selected installation directory is outside this profile.")
        except (OSError, ValueError, RuntimeError) as exc:
            self._set_status(str(exc))
            return
        self._working = True
        self._set_manager_busy(True)
        self.status.configure(text=f"Validating {source.name}…")
        world = self.world_var.get() if category == "datapacks" else None

        def import_file():
            target = destination / source.name
            created_target = False
            try:
                modrinth.validate_content_archive(source, category)
                destination.mkdir(parents=True, exist_ok=True)
                if not destination.resolve().is_relative_to(self._instance_dir().resolve()):
                    raise ValueError("The selected installation directory is outside this profile.")
                with source.open("rb") as input_file, target.open("xb") as output_file:
                    created_target = True
                    shutil.copyfileobj(input_file, output_file, length=64 * 1024)
                record = {
                    "title": source.stem,
                    "filename": target.name,
                    "version": "Imported",
                    "imported_locally": True,
                }
                self._post(lambda r=record, w=world: self._finish_file_install(r, w))
            except Exception as exc:
                if created_target:
                    try:
                        target.unlink(missing_ok=True)
                    except OSError as cleanup_error:
                        exc = RuntimeError(f"{exc} (partial import cleanup failed: {cleanup_error})")
                self._post(lambda error=str(exc): self._finish_install_error(error))

        threading.Thread(target=import_file, daemon=True).start()

    def _card(self, title: str, description: str = ""):
        card = ctk.CTkFrame(
            self.results,
            fg_color=self.theme["BG_SECONDARY"],
            corner_radius=10,
            border_width=1,
            border_color=self.theme["BORDER_COL"],
        )
        card.pack(fill="x", padx=7, pady=5)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=title,
            text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=13, pady=(10, 2))
        if description:
            ctk.CTkLabel(
                card,
                text=description,
                text_color=self.theme["TEXT_MUTED"],
                font=ctk.CTkFont(size=11),
                anchor="w",
                justify="left",
                wraplength=640,
            ).grid(row=1, column=0, sticky="ew", padx=13, pady=(0, 10))
        card.bind(
            "<Enter>",
            lambda _event, widget=card:
            self.parent._animate_widget_color(widget, self.theme["BG_PRIMARY"]),
            add="+",
        )
        card.bind(
            "<Leave>",
            lambda _event, widget=card:
            self.parent._animate_widget_color(widget, self.theme["BG_SECONDARY"]),
            add="+",
        )
        return card

    def _render_installed_file(self, path: Path):
        if self.category == "mods":
            disabled_suffix = ".disabled"
            if path.name.lower().endswith(f".jar{disabled_suffix}"):
                enabled_path = path.with_name(path.name[:-len(disabled_suffix)])
                disabled_path = path
            else:
                enabled_path = path
                disabled_path = path.with_name(f"{path.name}{disabled_suffix}")
            title = enabled_path.stem
            version = "Installed"
            try:
                with zipfile.ZipFile(path) as jar:
                    metadata = json.loads(jar.read("fabric.mod.json"))
                if isinstance(metadata, dict):
                    title = metadata.get("name") or title
                    version = metadata.get("version") or version
            except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
                pass
            record = {
                "filename": enabled_path.name,
                "title": title,
                "version": version,
            }
            self._render_installed_record(record, enabled_path, disabled_path)
            return

        try:
            details = "Folder" if path.is_dir() else f"{path.stat().st_size:,} bytes"
            if path.is_file():
                try:
                    modrinth.validate_content_archive(path, self.category)
                    details += " · Archive validated"
                except (OSError, ValueError, zipfile.BadZipFile) as exc:
                    details += f" · Validation warning: {exc}"
        except OSError as exc:
            details = f"Could not inspect this content: {exc}"
        card = self._card(path.name, details)
        button = ctk.CTkButton(
            card,
            text="Remove",
            width=76,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["RED"],
            text_color=self.theme["RED"],
            hover_color=self.theme["BG_PRIMARY"],
            command=lambda p=path: self._remove_file(p),
        )
        button.grid(row=0, column=2, rowspan=2, padx=(0, 12), pady=10)
        ctk.CTkButton(
            card, text="Open folder", width=88,
            fg_color="transparent", border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=lambda p=path: self._open_content_folder(p),
        ).grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=10)

    def _render_installed_record(self, record: dict, path: Path, disabled_path: Path):
        filename = record.get("filename", path.name)
        title = record.get("title") or filename
        details = f"{record.get('version', 'Installed')}  ·  {filename}"
        card = self._card(title, details)
        column = 1
        if self.category == "mods":
            enabled = path.is_file()
            toggle = ctk.CTkButton(
                card,
                text="Enabled" if enabled else "Disabled",
                width=82,
                fg_color=self.theme["ACCENT"] if enabled else "transparent",
                border_width=0 if enabled else 1,
                border_color=self.theme["BORDER_COL"],
                text_color=self.theme["ACCENT_TEXT"] if enabled else self.theme["TEXT_FG"],
                hover_color=self.theme["ACCENT_DARK"],
                command=lambda r=record: self._toggle_mod(r),
            )
            toggle.grid(row=0, column=column, rowspan=2, padx=(0, 8), pady=10)
            column += 1
        ctk.CTkButton(
            card,
            text="Folder",
            width=68,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=lambda p=path: self._open_content_folder(p),
        ).grid(row=0, column=column, rowspan=2, padx=(0, 8), pady=10)
        column += 1
        ctk.CTkButton(
            card,
            text="Remove",
            width=76,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["RED"],
            text_color=self.theme["RED"],
            hover_color=self.theme["BG_PRIMARY"],
            command=lambda p=path, d=disabled_path: self._remove_file(p, d),
        ).grid(row=0, column=column, rowspan=2, padx=(0, 12), pady=10)

    def _render_modpack_profile(self, profile: dict):
        source = profile.get("source_modpack") or profile.get("imported_modpack", {})
        query = self.search.get().strip().casefold()
        if query and query not in str(profile.get("name", "")).casefold() and query not in str(source.get("title", "")).casefold():
            return
        card = self._card(
            profile.get("name", "Imported Modpack"),
            f"Minecraft {profile.get('mc_version', '?')} · "
            f"{profile.get('type', 'vanilla').title()} · Isolated profile",
        )
        ctk.CTkButton(
            card,
            text="Select profile",
            width=104,
            fg_color=self.theme["ACCENT"],
            text_color=self.theme["ACCENT_TEXT"],
            hover_color=self.theme["ACCENT_DARK"],
            command=lambda p=profile: self._select_imported_profile(p),
        ).grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=10)
        ctk.CTkButton(
            card,
            text="Remove",
            width=76,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["RED"],
            text_color=self.theme["RED"],
            hover_color=self.theme["BG_PRIMARY"],
            command=lambda p=profile: self._remove_modpack_profile(p),
        ).grid(row=0, column=2, rowspan=2, padx=(0, 12), pady=10)

    def _render_project(self, project: dict):
        game_version = project.get(
            "_flowww_game_version", self.profile.get("mc_version", "?")
        )
        title, description, details = _project_card_content(
            project, self.category, game_version
        )
        card = ctk.CTkFrame(
            self.results, fg_color=self.theme["BG_SECONDARY"],
            corner_radius=10, border_width=1,
            border_color=self.theme["BORDER_COL"],
        )
        card.pack(fill="x", padx=7, pady=5)
        card.grid_columnconfigure(1, weight=1)
        icon = ctk.CTkLabel(
            card, text="◇", width=52, height=52,
            fg_color=self.theme["BG_PRIMARY"], corner_radius=8,
            text_color=self.theme["ACCENT"],
            font=ctk.CTkFont(size=25, weight="bold"),
        )
        icon.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=12)
        ctk.CTkLabel(
            card, text=title, text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 2))
        ctk.CTkLabel(
            card, text=f"{details}\n{description}",
            text_color=self.theme["TEXT_MUTED"], font=ctk.CTkFont(size=11),
            anchor="w", justify="left", wraplength=620,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 10))
        project_id = project.get("project_id")
        installed = self._project_installed(project_id)
        can_install = self._can_install_category()
        if project_id == self._active_install_project_id:
            label, state = "Installing…", "disabled"
        elif installed:
            label, state = "Installed", "disabled"
        elif not can_install:
            label, state = "Unavailable", "disabled"
        else:
            label, state = "Install", "normal"
        button = ctk.CTkButton(
            card,
            text=label,
            width=88,
            state=state,
            fg_color=self.theme["ACCENT"] if state == "normal" else "transparent",
            border_width=0 if state == "normal" else 1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["ACCENT_TEXT"] if state == "normal" else self.theme["TEXT_MUTED"],
            hover_color=self.theme["ACCENT_DARK"],
            command=lambda p=project: self._install_project(p),
        )
        button.grid(row=0, column=2, rowspan=2, padx=12, pady=10)
        if isinstance(project_id, str):
            self._project_buttons[project_id] = button
        self._load_project_icon(project, icon, self._request_serial)

    def _load_project_icon(self, project: dict, label, serial: int):
        icon_url = project.get("icon_url")
        if not isinstance(icon_url, str) or not icon_url:
            return

        def load():
            try:
                image = _download_project_icon(icon_url)
            except Exception:
                return

            def apply():
                try:
                    if serial != self._request_serial or not label.winfo_exists():
                        return
                except TclError:
                    return
                rendered = ctk.CTkImage(
                    light_image=image, dark_image=image, size=(48, 48)
                )
                self._project_images[project.get("project_id", icon_url)] = rendered
                label.configure(image=rendered, text="")

            self._post(apply)

        _ICON_WORKERS.submit(load)

    def _can_install_category(self) -> bool:
        if self.category == "mods" and self.profile.get("type") != "fabric":
            return False
        if self.category == "datapacks" and not self.world_var.get():
            return False
        if self.category == "shaderpacks" and not self._is_shader_supported():
            return False
        return True

    def _project_installed(self, project_id) -> bool:
        if not project_id:
            return False
        if self.category == "modpacks":
            return any(
                isinstance(p, dict)
                and isinstance(p.get("source_modpack"), dict)
                and p["source_modpack"].get("project_id") == project_id
                for p in self.parent.cfg.get("profiles", [])
            )
        if self.category == "mods":
            return project_id in modrinth.installed_mod_project_ids(self.profile)
        installed_content = self.profile.get("installed_content", {})
        records = installed_content.get(self.category, []) if isinstance(installed_content, dict) else []
        return any(
            isinstance(record, dict) and record.get("project_id") == project_id
            for record in records
        )

    def _search_projects(self, latest_versions: bool = False):
        query = self.search.get().strip()
        self._request_serial += 1
        serial = self._request_serial
        category = self.category
        self._latest_version_mode = latest_versions
        self._clear_results()
        self._browse_projects = []
        self._project_buttons.clear()

        if self.category == "mods" and self.profile.get("type") != "fabric":
            self._set_status("Mods require Fabric in this launcher. Create or select a Fabric profile first.")
            self._show_state("Mods can only be installed in a Fabric profile.")
            return
        self._set_status("Searching Modrinth…")
        self._show_state("Searching Modrinth…")

        game_versions = (
            list(dict.fromkeys(self.parent.all_versions[:3]))
            if latest_versions
            else [self.profile.get("mc_version", "")]
        )
        if not game_versions or any(
            not isinstance(version, str) or not version
            for version in game_versions
        ):
            self._show_browse_state(
                "The launcher could not determine supported Minecraft versions.",
                retry=True,
            )
            return

        def worker():
            try:
                if latest_versions:
                    projects_by_id = {}
                    for game_version in game_versions:
                        for project in modrinth.search_projects(
                            category,
                            query,
                            game_version,
                            self.profile.get("type", "vanilla"),
                        ):
                            project_id = project.get("project_id") or project.get("slug")
                            if project_id and project_id not in projects_by_id:
                                project = dict(project)
                                project["_flowww_game_version"] = game_version
                                projects_by_id[project_id] = project
                    projects = list(projects_by_id.values())
                else:
                    projects = modrinth.search_projects(
                        category,
                        query,
                        game_versions[0],
                        self.profile.get("type", "vanilla"),
                        self.page_offset,
                    )
                result = (projects, None)
            except Exception as exc:
                result = (None, str(exc))

            def update():
                if not self.winfo_exists() or serial != self._request_serial:
                    return
                projects, error = result
                self._clear_results()
                if error:
                    self._set_status(f"Could not search Modrinth: {error}")
                    self._show_browse_state(
                        f"Could not search Modrinth: {error}",
                        retry=True,
                    )
                elif not projects:
                    self._show_browse_state(
                        f"No compatible projects were found for "
                        f"Minecraft {self.profile.get('mc_version', '?')}.",
                        latest_versions=not latest_versions,
                    )
                    self.page_status.configure(text="")
                    self.previous_page_btn.configure(state="disabled")
                    self.next_page_btn.configure(state="disabled")
                else:
                    self._browse_projects = projects
                    version_label = (
                        " across the latest 3 supported versions"
                        if latest_versions else ""
                    )
                    self.status.configure(
                        text=f"Found {len(projects)} compatible projects{version_label}."
                    )
                    self.page_status.configure(
                        text="Latest 3 versions" if latest_versions
                        else f"Page {self.page_offset // 20 + 1}"
                    )
                    self.previous_page_btn.configure(
                        state="normal" if self.page_offset and not latest_versions
                        else "disabled"
                    )
                    self.next_page_btn.configure(
                        state="normal" if len(projects) == 20 and not latest_versions
                        else "disabled"
                    )
                    for project in projects:
                        self._render_project(project)

            self._post(update)

        threading.Thread(target=worker, daemon=True).start()

    def _show_browse_state(
        self,
        text: str,
        *,
        retry: bool = False,
        latest_versions: bool = False,
    ):
        self._clear_results()
        ctk.CTkLabel(
            self.results,
            text=text,
            text_color=self.theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=13),
            wraplength=650,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(18, 10))
        actions = ctk.CTkFrame(self.results, fg_color="transparent")
        actions.pack(anchor="w", padx=14, pady=(0, 14))
        if retry:
            ctk.CTkButton(
                actions,
                text="Retry",
                width=90,
                command=self._search_projects,
            ).pack(side="left", padx=(0, 8))
        if latest_versions:
            ctk.CTkButton(
                actions,
                text="Show results for the latest 3 supported versions",
                width=300,
                fg_color="transparent",
                border_width=1,
                border_color=self.theme["BORDER_COL"],
                text_color=self.theme["TEXT_FG"],
                command=lambda: self._search_projects(latest_versions=True),
            ).pack(side="left")

    def _change_page(self, direction: int):
        next_offset = self.page_offset + direction * 20
        if next_offset < 0:
            return
        self.page_offset = next_offset
        self._search_projects()

    def _install_project(self, project: dict):
        if self._working:
            return
        if self.category == "shaderpacks" and not self._is_shader_supported():
            messagebox.showinfo(
                "Shader support required",
                "Install Iris or OptiFine in this profile before adding shader packs.",
                parent=self,
            )
            return
        if self.category == "datapacks" and not self.world_var.get():
            messagebox.showinfo("Choose a world", "Select an existing world first.", parent=self)
            return

        project_id = project.get("project_id")
        if not isinstance(project_id, str):
            self._set_status("Modrinth returned a project without a valid ID.")
            return
        self._working = True
        self._active_install_project_id = project_id
        self._cancel_event = threading.Event()
        button = self._project_buttons.get(project_id)
        if button:
            button.configure(text="Checking…", state="disabled")
        self.status.configure(text="Finding a compatible release…")
        self._set_manager_busy(True)
        self.cancel_btn.configure(state="normal")
        category = self.category
        world = self.world_var.get() if category == "datapacks" else None
        try:
            destination = (
                self._instance_dir()
                if self.category == "modpacks"
                else self._category_directory()
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._working = False
            self._active_install_project_id = None
            self._restore_project_button(project_id)
            self._set_manager_busy(False)
            self._set_status(str(exc))
            return
        if not destination.resolve().is_relative_to(self._instance_dir().resolve()):
            self._working = False
            self._active_install_project_id = None
            self._set_manager_busy(False)
            self._restore_project_button(project_id)
            self._set_status("The selected installation directory is outside this profile.")
            return
        if self.category != "modpacks":
            try:
                destination.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._working = False
                self._active_install_project_id = None
                self._set_manager_busy(False)
                self._restore_project_button(project_id)
                self._set_status(f"Could not prepare the install directory: {exc}")
                return
        title = project.get("title") or project.get("slug") or "Modrinth project"
        cancel_event = self._cancel_event
        last_progress_update = [0.0]

        def progress(done, total):
            now = time.monotonic()
            if total and done < total and now - last_progress_update[0] < 0.2:
                return
            last_progress_update[0] = now
            total_text = f" / {total:,}" if total else ""
            text = f"Downloading {title}: {done:,}{total_text}"
            self._post(lambda: self._set_status(text))

        def worker():
            try:
                versions = modrinth.compatible_versions(
                    project_id,
                    category,
                    self.profile.get("mc_version", ""),
                    self.profile.get("type", "vanilla"),
                )
                if not versions:
                    raise RuntimeError("No compatible release exists for this profile.")
                if category == "modpacks":
                    profile = self._import_modpack(project, versions[0], cancel_event, progress)
                    self._post(lambda p=profile: self._finish_modpack_install(p))
                elif category == "mods":
                    records, warnings = modrinth.install_mod_project_with_dependencies(
                        project_id,
                        title,
                        versions[0],
                        category,
                        destination,
                        self.profile,
                        cancel_event=cancel_event,
                        progress=progress,
                    )
                    self._post(
                        lambda rs=records, ws=warnings, w=world:
                        self._finish_file_install(rs[0], w, rs[1:], ws)
                    )
                else:
                    installed = modrinth.download_project_file(
                        versions[0], category, destination,
                        cancel_event=cancel_event,
                        progress=progress,
                    )
                    record = {
                        "project_id": project_id,
                        "version_id": versions[0].get("id"),
                        "title": title,
                        "filename": installed.name,
                        "version": versions[0].get("version_number", "latest"),
                        "enabled": True,
                    }
                    self._post(lambda r=record, w=world: self._finish_file_install(r, w))
            except Exception as exc:
                self._post(lambda message=str(exc): self._finish_install_error(message))

        threading.Thread(target=worker, daemon=True).start()

    def _import_modpack(self, project, version, cancel_event, progress):
        instance_id = uuid.uuid4().hex
        imported_profile = {
            "instance_id": instance_id,
            "name": project.get("title") or project.get("slug") or "Imported Modpack",
            "mc_version": self.profile.get("mc_version", ""),
            "type": self.profile.get("type", "vanilla"),
            "mods": [],
        }
        instance = modrinth.profile_instance_dir(imported_profile)
        downloads_dir = Path.home() / ".revomc" / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="modrinth-pack-", dir=downloads_dir) as temp_dir:
            archive = modrinth.download_project_file(
                version,
                "modpacks",
                Path(temp_dir),
                cancel_event=cancel_event,
                progress=progress,
            )
            manifest = modrinth.install_modpack(archive, instance, cancel_event, progress)
        if manifest["mc_version"] != imported_profile["mc_version"]:
            shutil.rmtree(instance)
            raise RuntimeError("The modpack manifest version does not match the selected profile version.")
        if manifest["type"] != imported_profile["type"]:
            shutil.rmtree(instance)
            raise RuntimeError("The modpack requires a different loader than the selected profile.")
        imported_profile.update({
            "name": manifest["name"],
            "source_modpack": {
                "project_id": project["project_id"],
                "title": project.get("title", manifest["name"]),
                "version": version.get("version_number", ""),
            },
        })
        if manifest.get("fabric_loader_version"):
            imported_profile["fabric_loader_version"] = manifest["fabric_loader_version"]
        return imported_profile

    def _finish_file_install(
        self,
        record: dict,
        world: str | None,
        additional_records: list[dict] | None = None,
        warnings: list[str] | None = None,
    ):
        all_records = [record, *(additional_records or [])]
        if world:
            for item in all_records:
                item["world"] = world
        records = self.profile.setdefault("installed_content", {}).setdefault(self.category, [])
        records.extend(all_records)
        try:
            config.save(self.parent.cfg)
            profile_store.save_manifest(self.profile)
        except OSError as exc:
            for item in all_records:
                records.remove(item)
            cleanup_message = ""
            cleanup_errors = []
            for item in all_records:
                try:
                    target = self._category_directory() / item["filename"]
                    if target.is_file() and target.resolve().is_relative_to(self._instance_dir().resolve()):
                        target.unlink()
                except (OSError, ValueError, RuntimeError) as cleanup_error:
                    cleanup_errors.append(str(cleanup_error))
            if cleanup_errors:
                cleanup_message = f" Could not remove downloaded files: {'; '.join(cleanup_errors)}"
            self._finish_install_error(
                f"Downloaded, but could not save profile settings: {exc}.{cleanup_message}"
            )
            return
        names = [record.get("title", record["filename"])]
        names.extend(item.get("title", item["filename"]) for item in all_records[1:])
        summary = f"Installed {' + '.join(names)}"
        if warnings:
            summary += f". Warnings: {'; '.join(warnings)}"
        self._finish_install(summary + ".")

    def _finish_modpack_install(self, profile: dict):
        try:
            existing = {p.get("name") for p in self.parent.cfg.get("profiles", [])}
            base_name = profile["name"]
            name = base_name
            suffix = 2
            while name in existing:
                name = f"{base_name} ({suffix})"
                suffix += 1
            profile["name"] = name
            self.parent.cfg.setdefault("profiles", []).append(profile)
            config.save(self.parent.cfg)
        except OSError as exc:
            self.parent.cfg["profiles"].remove(profile)
            try:
                shutil.rmtree(modrinth.profile_instance_dir(profile))
            except OSError:
                pass
            self._finish_install_error(f"Imported the pack, but could not save its profile: {exc}")
            return
        self.parent._refresh_profile_list()
        self._finish_install(f"Imported '{profile['name']}' as an isolated profile.")

    def _finish_install(self, message: str):
        self._working = False
        self._cancel_event = None
        self.cancel_btn.configure(state="disabled")
        self._set_manager_busy(False)
        self.status.configure(text=message)
        project_id = self._active_install_project_id
        self._active_install_project_id = None
        if self.tab == "Browse":
            button = self._project_buttons.get(project_id)
            if button:
                button.configure(
                    text="Installed", state="disabled",
                    fg_color="transparent", border_width=1,
                    border_color=self.theme["BORDER_COL"],
                    text_color=self.theme["TEXT_MUTED"],
                )
        else:
            self._refresh_content()

    def _finish_install_error(self, message: str):
        self._working = False
        self._cancel_event = None
        self.cancel_btn.configure(state="disabled")
        self._set_manager_busy(False)
        self.status.configure(text=message)
        project_id = self._active_install_project_id
        self._active_install_project_id = None
        if self.tab == "Browse":
            self._restore_project_button(project_id)
        else:
            self._refresh_content()

    def _restore_project_button(self, project_id):
        button = self._project_buttons.get(project_id)
        if not button:
            return
        button.configure(
            text="Installed" if self._project_installed(project_id) else "Install",
            state="disabled" if self._project_installed(project_id) else "normal",
        )

    def _set_manager_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.search.configure(state=state)
        self.search_button.configure(state=state)
        self.installed_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        self.refresh_content_btn.configure(state=state)
        self.import_content_btn.configure(state=state)
        self.world_menu.configure(state=state)
        for button in self.category_buttons.values():
            button.configure(state=state)
        if busy:
            self.install_progress.grid()
            self.install_progress.start()
        else:
            self.install_progress.stop()
            self.install_progress.set(0)
            self.install_progress.grid_remove()

    def _set_status(self, message: str):
        if self.winfo_exists():
            self.status.configure(text=message)

    def _post(self, callback):
        self._ui_callbacks.put(callback)

    def _drain_ui_callbacks(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                callback = self._ui_callbacks.get_nowait()
                callback()
        except queue.Empty:
            pass
        self.after(20, self._drain_ui_callbacks)

    def _cancel_install(self):
        if self._cancel_event:
            self._cancel_event.set()
            self.status.configure(text="Cancelling download…")
            self.cancel_btn.configure(state="disabled")

    def _remove_file(self, path: Path, disabled_path: Path | None = None):
        if not messagebox.askyesno(
            "Remove installed content",
            f"Remove {path.name} from this profile?",
            parent=self,
        ):
            return
        try:
            if disabled_path and disabled_path.is_file():
                disabled_path.unlink()
            if path.is_file() or path.is_dir():
                modrinth.remove_installed_file(
                    self.profile,
                    self.category,
                    path,
                    self.world_var.get() if self.category == "datapacks" else None,
                )
            installed_content = self.profile.get("installed_content", {})
            records = installed_content.get(self.category, []) if isinstance(installed_content, dict) else []
            self.profile.setdefault("installed_content", {})[self.category] = [
                record for record in records
                if (
                    not isinstance(record, dict)
                    or record.get("filename") not in {
                        path.name,
                        disabled_path.name if disabled_path else "",
                    }
                    or (
                        self.category == "datapacks"
                        and record.get("world")
                        and record.get("world") != self.world_var.get()
                    )
                )
            ]
            config.save(self.parent.cfg)
            self._refresh_content()
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Could not remove content", str(exc), parent=self)

    def _toggle_mod(self, record: dict):
        filename = record.get("filename", "")
        if Path(filename).name != filename or not filename.lower().endswith(".jar"):
            messagebox.showerror("Invalid mod file", "The installed mod has an invalid filename.", parent=self)
            return
        mods_dir = self._instance_dir() / "mods"
        original = mods_dir / filename
        disabled = original.with_name(f"{original.name}.disabled")
        renamed_to_disabled = False
        renamed_to_enabled = False
        try:
            if original.is_file():
                if disabled.exists():
                    raise FileExistsError(f"{disabled.name} already exists.")
                original.rename(disabled)
                renamed_to_disabled = True
                record["enabled"] = False
            elif disabled.is_file():
                if original.exists():
                    raise FileExistsError(f"{original.name} already exists.")
                disabled.rename(original)
                renamed_to_enabled = True
                record["enabled"] = True
            else:
                raise FileNotFoundError("The installed mod file is missing.")
            config.save(self.parent.cfg)
            self._refresh_content()
        except (OSError, ValueError) as exc:
            if renamed_to_disabled and disabled.exists() and not original.exists():
                try:
                    disabled.rename(original)
                    record["enabled"] = True
                except OSError as rollback_error:
                    exc = RuntimeError(f"{exc} (could not restore the mod file: {rollback_error})")
            elif renamed_to_enabled and original.exists() and not disabled.exists():
                try:
                    original.rename(disabled)
                    record["enabled"] = False
                except OSError as rollback_error:
                    exc = RuntimeError(f"{exc} (could not restore the disabled mod file: {rollback_error})")
            messagebox.showerror("Could not change mod state", str(exc), parent=self)

    def _select_imported_profile(self, profile: dict):
        profiles = self.parent.cfg.get("profiles", [])
        try:
            index = profiles.index(profile)
        except ValueError:
            return
        self.parent._on_profile_selected(index)

    def _remove_modpack_profile(self, profile: dict):
        if not messagebox.askyesno(
            "Remove imported modpack",
            f"Remove '{profile.get('name')}' and permanently delete its isolated instance, "
            "including worlds and settings?",
            parent=self,
        ):
            return
        try:
            instance = modrinth.profile_instance_dir(profile)
            expected_root = (Path.home() / ".revomc" / "instances").resolve()
            if not instance.resolve().is_relative_to(expected_root):
                raise ValueError("Refusing to remove a profile outside the launcher instances folder.")
            profiles = self.parent.cfg["profiles"]
            index = profiles.index(profile)
            previous_active = self.parent.cfg.get("active_profile")
            profiles.pop(index)
            if self.parent.cfg.get("active_profile") == profile.get("name"):
                self.parent.cfg["active_profile"] = profiles[0].get("name") if profiles else None
            try:
                config.save(self.parent.cfg)
            except OSError:
                profiles.insert(index, profile)
                self.parent.cfg["active_profile"] = previous_active
                raise
            try:
                if instance.exists():
                    shutil.rmtree(instance)
            except OSError as exc:
                messagebox.showerror(
                    "Profile removed; files remain",
                    f"The profile was removed from the launcher, but its isolated files "
                    f"could not be deleted:\n{instance}\n\n{exc}",
                    parent=self,
                )
            self.parent._refresh_profile_list()
            self._refresh_content()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not remove modpack", str(exc), parent=self)

    def _on_close(self):
        if self._working:
            self._cancel_install()
            return
        self._request_serial += 1
        self.parent._leave_profile_editor()
# ── New Profile Dialog ─────────────────────────────────────────────────────────

class NewProfileDialog(OverlayDialog):
    """Modal card for creating a new profile (slides up over the launcher)."""

    def __init__(self, parent, all_versions: list[str], fabric_versions: list[str],
                 existing_profile_names: set[str] | None = None):
        super().__init__(parent, 500, 640)
        self.parent = parent
        self.all_versions    = all_versions
        self.fabric_versions = fabric_versions
        self._existing_profile_names = existing_profile_names or set()
        self.result: dict | None = None

        self._build()
        self.update_idletasks()
        self.wait_window(self)  # blocks until the card has closed

    # ── Dialog UI ─────────────────────────────────────────────────────────────

    def _build(self):
        pad = {"padx": 20, "pady": (8, 0)}

        # ── Bottom buttons pinned first so they're always visible ─────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=20, pady=12)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent",
                      border_width=1, border_color=BORDER_COL,
                      text_color=TEXT_FG,
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Create", fg_color=GREEN, text_color=ACCENT_TEXT,
                      hover_color=GREEN_DARK,
                      command=self._on_ok).pack(side="right")

        # ── Scrollable body ───────────────────────────────────────────────────
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # Profile name (optional)
        _section_label(body, "Profile Name  (optional)").pack(anchor="w", padx=20, pady=(10, 0))
        self.name_var = ctk.StringVar()
        ctk.CTkEntry(
            body, textvariable=self.name_var,
            placeholder_text="Leave blank for default name…",
            width=420,
        ).pack(padx=20, pady=(4, 0))

        _section_label(body, "Memory").pack(anchor="w", padx=20, pady=(10, 0))
        self.memory_var = ctk.IntVar(
            value=min(
                max(1, int(self.parent.cfg.get("ram_gb", 2))),
                self.parent.max_ram_gb,
            )
        )
        ctk.CTkSlider(
            body, from_=1, to=self.parent.max_ram_gb,
            number_of_steps=max(1, self.parent.max_ram_gb - 1),
            variable=self.memory_var, progress_color=GREEN,
            button_color=GREEN, button_hover_color=GREEN_DARK,
        ).pack(fill="x", padx=20, pady=(5, 0))
        _section_label(body, "Java Arguments").pack(anchor="w", padx=20, pady=(10, 0))
        self.java_args_var = ctk.StringVar()
        ctk.CTkEntry(
            body, textvariable=self.java_args_var,
            placeholder_text="Optional JVM arguments",
        ).pack(fill="x", padx=20, pady=(4, 0))

        # Profile type
        _section_label(body, "Profile Type").pack(anchor="w", padx=20, pady=(10, 0))
        type_row = ctk.CTkFrame(body, fg_color="transparent")
        type_row.pack(anchor="w", padx=20, pady=(4, 0))
        self.type_var = ctk.StringVar(value="fabric")
        ctk.CTkRadioButton(
            type_row, text="Fabric + Mods",
            variable=self.type_var, value="fabric",
            command=self._on_type_changed,
            fg_color=GREEN, hover_color=GREEN_DARK,
        ).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(
            type_row, text="Vanilla",
            variable=self.type_var, value="vanilla",
            command=self._on_type_changed,
            fg_color=GREEN, hover_color=GREEN_DARK,
        ).pack(side="left")

        # Minecraft version list
        _section_label(body, "Minecraft Version").pack(anchor="w", padx=20, pady=(10, 0))
        self.version_frame = ctk.CTkScrollableFrame(body, height=150, width=420)
        self.version_frame.pack(padx=20, pady=(4, 0))
        self._version_buttons: list[ctk.CTkButton] = []
        self._selected_version: str | None = None

        # Mods section
        self.mods_outer = ctk.CTkFrame(body, fg_color="transparent")
        self.mods_outer.pack(fill="x", padx=20, pady=(10, 0))
        _section_label(self.mods_outer, "Mods  (Fabric API always included)").pack(anchor="w")
        self.mod_vars: dict[str, ctk.BooleanVar] = {}
        for key, mod in AVAILABLE_MODS.items():
            var = ctk.BooleanVar(value=True)
            self.mod_vars[key] = var
            ctk.CTkCheckBox(
                self.mods_outer,
                text=f"{mod['label']}  :  {mod['desc']}",
                variable=var,
                fg_color=GREEN,
                hover_color=GREEN_DARK,
            ).pack(anchor="w", pady=2)

        self._on_type_changed()  # initial populate

    def _on_type_changed(self):
        # Clear existing buttons
        for btn in self._version_buttons:
            btn.destroy()
        self._version_buttons.clear()
        self._selected_version = None

        is_fabric = self.type_var.get() == "fabric"
        versions = self.fabric_versions if is_fabric else self.all_versions


        # Toggle mods frame
        if is_fabric:
            self.mods_outer.pack(fill="x", padx=20, pady=(8, 0))
        else:
            self.mods_outer.pack_forget()

        # Populate version list
        for i, v in enumerate(versions):
            btn = ctk.CTkButton(
                self.version_frame, text=v,
                fg_color="transparent", text_color=TEXT_FG,
                hover_color=BG_SECONDARY, anchor="w",
                command=lambda ver=v: self._select_version(ver),
            )
            btn.pack(fill="x", pady=1)
            self._version_buttons.append(btn)
            if i == 0:
                self._select_version(v)

    def _select_version(self, ver: str):
        self._selected_version = ver
        for btn in self._version_buttons:
            if btn.cget("text") == ver:
                btn.configure(fg_color=GREEN, text_color=ACCENT_TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_FG)

    def _on_ok(self):
        if not self._selected_version:
            return
        try:
            import shlex
            shlex.split(self.java_args_var.get())
        except ValueError as exc:
            messagebox.showerror("Invalid Java arguments", str(exc), parent=self)
            return
        profile_type = self.type_var.get()
        name = self.name_var.get().strip()
        if not name:
            # Generate incremental unnamed profile name
            existing_names = self._existing_profile_names
            prefix = (
                "Unnamed Fabric Installation"
                if profile_type == "fabric"
                else "Unnamed Vanilla Installation"
            )
            n = 1
            while f"{prefix} {n}" in existing_names:
                n += 1
            name = f"{prefix} {n}"
        enabled_mods = (
            [k for k, v in self.mod_vars.items() if v.get()]
            if profile_type == "fabric"
            else []
        )
        self.result = {
            "name": name,
            "mc_version": self._selected_version,
            "type": profile_type,
            "mods": enabled_mods,
            "memory_gb": int(self.memory_var.get()),
            "java_args": self.java_args_var.get().strip(),
            "performance_boost": profile_type == "fabric",
        }
        self.destroy()


# ── Settings page ──────────────────────────────────────────────────────────────

class SettingsPage(ctk.CTkFrame):
    """Launcher settings: theme, animations, performance, Java and folders."""

    def __init__(self, parent):
        super().__init__(parent.page_container, fg_color="transparent")
        self.parent = parent
        self.theme = parent.theme
        self.cfg = parent.cfg
        self._build()

    def _card(self, body, title: str):
        card = ctk.CTkFrame(
            body, fg_color=self.theme["BG_SECONDARY"], corner_radius=14,
            border_width=1, border_color=self.theme["BORDER_COL"],
        )
        card.pack(fill="x", pady=(0, 12))
        _section_label(card, title).pack(anchor="w", padx=18, pady=(14, 8))
        return card

    def _build(self):
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        ctk.CTkLabel(
            body, text="Settings", text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w", pady=(0, 12))

        appearance = self._card(body, "Appearance")
        self.animations_var = ctk.BooleanVar(value=bool(self.cfg.get("animations", True)))
        ctk.CTkCheckBox(
            appearance, text="Animations (smooth page and popup transitions)",
            variable=self.animations_var, command=self._on_animations,
        ).pack(anchor="w", padx=18, pady=(0, 16))

        performance = self._card(body, "Performance")
        self.dgpu_var = ctk.BooleanVar(value=self.cfg.get("use_dgpu", False))
        ctk.CTkCheckBox(
            performance, text="Run on Discrete GPU (NVIDIA/AMD)  —  Linux & Windows",
            variable=self.dgpu_var, command=self._on_dgpu,
        ).pack(anchor="w", padx=18, pady=(0, 10))
        ctk.CTkLabel(
            performance,
            text="Performance Boost installs FPS mods (Sodium, Lithium, …) and tuned Java flags. "
                 "Krypton lowers the game's own networking overhead, but nothing in a launcher "
                 "can fix a slow or unstable Wi-Fi connection.",
            text_color=self.theme["TEXT_MUTED"], wraplength=640, justify="left", anchor="w",
        ).pack(anchor="w", padx=18, pady=(0, 16))

        java = self._card(body, "Java runtime")
        self.java_label = ctk.CTkLabel(
            java, text="", text_color=self.theme["TEXT_MUTED"],
            wraplength=640, justify="left", anchor="w",
        )
        self.java_label.pack(anchor="w", padx=18, pady=(0, 4))
        ctk.CTkLabel(
            java,
            text=f"RAM is capped at {self.parent.max_ram_gb} GB to leave memory for the operating system.",
            text_color=self.theme["TEXT_MUTED"], wraplength=640, justify="left", anchor="w",
        ).pack(anchor="w", padx=18, pady=(0, 16))

        self.directories = self._card(body, "Directories")
        self.directory_rows = ctk.CTkFrame(self.directories, fg_color="transparent")
        self.directory_rows.pack(fill="x", padx=18, pady=(0, 14))
        self.on_show()

    def on_show(self):
        """Refresh the parts that depend on the selected profile."""
        profile = self.parent._current_profile()
        if profile:
            try:
                java_version = get_required_java_version(profile.get("mc_version", ""))
                from core.java_manager import is_runtime_installed
                text = (
                    f"Java {java_version} bundled runtime is installed."
                    if is_runtime_installed(java_version)
                    else f"Java {java_version} will be downloaded on first launch."
                )
            except (ValueError, TypeError) as exc:
                text = f"Could not determine the required Java runtime: {exc}"
        else:
            text = "Select a profile to see its required Java runtime."
        self.java_label.configure(text=text)
        for widget in self.directory_rows.winfo_children():
            widget.destroy()
        directories = [
            ("Launcher data", Path.home() / ".revomc"),
            ("Minecraft data", config.get_minecraft_dir()),
        ]
        if profile:
            try:
                directories.append(
                    ("Selected profile instance", modrinth.profile_instance_dir(profile))
                )
            except (OSError, ValueError, RuntimeError) as exc:
                ctk.CTkLabel(
                    self.directory_rows, text=f"Invalid profile directory: {exc}",
                    text_color=self.theme["RED"], wraplength=640, justify="left",
                ).pack(anchor="w")
        for label, path in directories:
            row = ctk.CTkFrame(self.directory_rows, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row, text=f"{label}: {path}", text_color=self.theme["TEXT_MUTED"],
                anchor="w", justify="left", wraplength=520,
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                row, text="Open", width=64, height=30,
                fg_color="transparent", border_width=1,
                border_color=self.theme["BORDER_COL"],
                text_color=self.theme["TEXT_FG"],
                hover_color=self.theme["BG_CARD"],
                command=lambda folder=path: self._open_directory(folder),
            ).pack(side="right", padx=(8, 0))

    def _save(self) -> bool:
        try:
            config.save(self.cfg)
        except OSError as exc:
            messagebox.showerror(
                "Could not save settings", str(exc), parent=self.winfo_toplevel()
            )
            return False
        return True

    def _on_animations(self):
        enabled = bool(self.animations_var.get())
        self.cfg["animations"] = enabled
        self.parent.motion.enabled = enabled
        self._save()

    def _on_dgpu(self):
        self.cfg["use_dgpu"] = bool(self.dgpu_var.get())
        self._save()

    def _open_directory(self, path: Path):
        parent = self.winfo_toplevel()
        if not path.is_dir():
            messagebox.showinfo(
                "Directory not created",
                f"This directory does not exist yet:\n{path}",
                parent=parent,
            )
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except (OSError, AttributeError) as exc:
            messagebox.showerror("Could not open directory", str(exc), parent=parent)


class AccountsPage(ctk.CTkFrame):
    """Account controls backed by the launcher's existing auth implementation."""

    def __init__(self, parent):
        super().__init__(parent.page_container, fg_color="transparent")
        self.parent = parent
        self.theme = parent.theme
        self._cosmetic_images = {}
        self._account_image_paths = {}
        try:
            self.accounts = account_store.load_accounts()
        except RuntimeError as exc:
            self.accounts = []
            messagebox.showerror("Could not load accounts", str(exc), parent=self.winfo_toplevel())

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        ctk.CTkLabel(
            body,
            text="Accounts",
            text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            body,
            text="Offline usernames are local profiles and do not authenticate with Mojang.",
            text_color=self.theme["TEXT_MUTED"],
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(4, 18))

        self.mode_menu = ctk.CTkSegmentedButton(
            body,
            values=["Offline", "Microsoft"],
            variable=parent.auth_mode_var,
            command=parent._on_auth_mode_changed,
            selected_color=self.theme["BORDER_COL"],
            selected_hover_color=self.theme["BORDER_COL"],
            unselected_color=self.theme["BG_SECONDARY"],
        )
        self.mode_menu.pack(anchor="w", pady=(0, 18))

        offline = ctk.CTkFrame(
            body,
            fg_color=self.theme["BG_SECONDARY"],
            corner_radius=10,
            border_width=1,
            border_color=self.theme["BORDER_COL"],
        )
        offline.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            offline,
            text="LOCAL OFFLINE PROFILE",
            text_color=self.theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 5))
        self.offline_choice = ctk.StringVar(
            value=parent.cfg.get("active_offline_profile") or parent.username_var.get()
        )
        self.offline_menu = ctk.CTkOptionMenu(
            offline,
            variable=self.offline_choice,
            values=["No saved profiles"],
            fg_color=self.theme["BG_PRIMARY"],
            button_color=self.theme["ACCENT"],
            button_hover_color=self.theme["ACCENT_DARK"],
            command=self._select_offline_profile,
        )
        self.offline_menu.pack(fill="x", padx=14, pady=(0, 8))
        self.account_list = ctk.CTkFrame(offline, fg_color="transparent")
        self.account_list.pack(fill="x", padx=14, pady=(0, 8))
        self._render_account_cards()
        local_actions = ctk.CTkFrame(offline, fg_color="transparent")
        local_actions.pack(fill="x", padx=14, pady=(0, 8))
        for label, command in (
            ("Add", self._add_offline_profile),
            ("Rename", self._rename_offline_profile),
            ("Remove", self._remove_offline_profile),
        ):
            ctk.CTkButton(
                local_actions, text=label, width=78,
                fg_color="transparent", border_width=1,
                border_color=self.theme["BORDER_COL"],
                text_color=self.theme["TEXT_FG"],
                hover_color=self.theme["BG_PRIMARY"],
                command=command,
            ).pack(side="left", padx=(0, 7))
        ctk.CTkEntry(
            offline,
            textvariable=parent.username_var,
            placeholder_text="Enter an offline username",
        ).pack(fill="x", padx=14, pady=(0, 14))

        online = ctk.CTkFrame(
            body,
            fg_color=self.theme["BG_SECONDARY"],
            corner_radius=10,
            border_width=1,
            border_color=self.theme["BORDER_COL"],
        )
        online.pack(fill="x")
        ctk.CTkLabel(
            online,
            text="MICROSOFT ACCOUNT",
            text_color=self.theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 4))
        self.status = ctk.CTkLabel(
            online, text="", text_color=self.theme["TEXT_FG"], anchor="w"
        )
        self.status.pack(fill="x", padx=14, pady=(0, 8))
        buttons = ctk.CTkFrame(online, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            buttons,
            text="Sign in with Microsoft",
            fg_color=self.theme["MS_BLUE"],
            hover_color=self.theme["MS_BLUE_DARK"],
            command=parent._on_ms_signin,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="Sign out",
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=parent._on_ms_signout,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            body,
            text="Offline skins and capes are visible on your own client (singleplayer, LAN, offline servers). "
                 "Other players on online-mode servers will not see them. Microsoft accounts use their own skin.",
            text_color=self.theme["TEXT_MUTED"],
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(18, 8))
        self._build_cosmetic_card(body, "skin", "Skin", (150, 200))
        self._build_cosmetic_card(body, "cape", "Cape", (128, 64))
        self.skin_model = ctk.StringVar(value="classic")
        ctk.CTkSegmentedButton(
            body, values=["classic", "slim"], variable=self.skin_model,
            command=self._save_skin_model,
            selected_color=self.theme["BORDER_COL"],
            selected_hover_color=self.theme["BORDER_COL"],
        ).pack(anchor="w", pady=(0, 12))
        self._refresh_offline_profiles()
        self._refresh_cosmetics()
        self._refresh_status()

    def on_show(self):
        """Called whenever the page becomes visible."""
        try:
            self.accounts = account_store.load_accounts()
        except RuntimeError:
            pass
        self._refresh_offline_profiles()
        self._refresh_cosmetics()

    def _build_cosmetic_card(self, parent, cosmetic: str, title: str, size: tuple[int, int]):
        card = ctk.CTkFrame(
            parent, fg_color=self.theme["BG_SECONDARY"], corner_radius=10,
            border_width=1, border_color=self.theme["BORDER_COL"],
        )
        card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            card, text=title, text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 4))
        preview_row = ctk.CTkFrame(card, fg_color="transparent")
        preview_row.pack(fill="x", padx=14, pady=(0, 8))
        preview = ctk.CTkLabel(
            preview_row, text="No image saved", text_color=self.theme["TEXT_MUTED"],
            width=size[0], height=size[1], fg_color=self.theme["BG_PRIMARY"],
            corner_radius=8,
        )
        preview.pack(side="left", padx=(0, 12))
        setattr(self, f"{cosmetic}_preview", preview)
        state = ctk.CTkLabel(
            preview_row, text="Local preview only.", text_color=self.theme["TEXT_MUTED"],
            anchor="w", justify="left", wraplength=330,
        )
        state.pack(side="left", fill="x", expand=True)
        setattr(self, f"{cosmetic}_state", state)
        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            action_row, text="Import / replace", width=126,
            fg_color=self.theme["ACCENT"], text_color=self.theme["ACCENT_TEXT"],
            hover_color=self.theme["ACCENT_DARK"],
            command=lambda kind=cosmetic: self._import_cosmetic(kind),
        ).pack(side="left")
        ctk.CTkButton(
            action_row, text="Remove", width=82,
            fg_color="transparent", border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=lambda kind=cosmetic: self._remove_cosmetic(kind),
        ).pack(side="left", padx=(8, 0))

    def _refresh_offline_profiles(self):
        profiles = self.parent.cfg.setdefault("offline_profiles", [])
        if not isinstance(profiles, list):
            profiles = []
            self.parent.cfg["offline_profiles"] = profiles
        current = self.parent.username_var.get().strip()
        if current and current not in profiles:
            profiles.append(current)
            self.parent.cfg["active_offline_profile"] = current
            try:
                config.save(self.parent.cfg)
            except OSError as exc:
                profiles.remove(current)
                messagebox.showerror("Could not save offline profile", str(exc), parent=self.winfo_toplevel())
        values = [name for name in profiles if isinstance(name, str) and name.strip()]
        known = {account.get("username") for account in self.accounts}
        for name in values:
            if name not in known:
                self.accounts.append({
                    "username": name,
                    "uuid": account_store.offline_uuid(name),
                    "type": "offline",
                    "skin_model": "classic",
                })
        self._save_accounts()
        selected = self.parent.cfg.get("active_offline_profile")
        if selected not in values:
            selected = current if current in values else (values[0] if values else "No saved profiles")
        self.offline_choice.set(selected)
        self.offline_menu.configure(values=values or ["No saved profiles"])
        self._render_account_cards()

    def _save_accounts(self):
        try:
            account_store.save_accounts(self.accounts)
        except OSError as exc:
            messagebox.showerror("Could not save accounts", str(exc), parent=self.winfo_toplevel())
            return False
        return True

    def _render_account_cards(self):
        if not hasattr(self, "account_list"):
            return
        for widget in self.account_list.winfo_children():
            widget.destroy()
        for account in self.accounts:
            username = account.get("username", "Unknown")
            account_id = account.get("uuid") or account_store.offline_uuid(username)
            card = ctk.CTkFrame(
                self.account_list, fg_color=self.theme["BG_PRIMARY"],
                corner_radius=8,
            )
            card.pack(fill="x", pady=3)
            head_image = None
            try:
                skin_path = skin_store.account_cosmetic_dir(account_id) / "skin.png"
                if skin_path.is_file() and not skin_path.is_symlink():
                    with Image.open(skin_path) as skin:
                        factor = skin.width // 64
                        head = skin.crop((8 * factor, 8 * factor, 16 * factor, 16 * factor))
                        head = head.resize((32, 32), Image.Resampling.NEAREST)
                    head_image = ctk.CTkImage(
                        light_image=head, dark_image=head, size=(32, 32)
                    )
                    self._account_image_paths[account_id] = head_image
            except (OSError, ValueError):
                head_image = None
            ctk.CTkLabel(
                card,
                text=f"{username}  ·  {account.get('type', 'offline').title()}",
                image=head_image,
                compound="left",
                text_color=self.theme["TEXT_FG"], anchor="w",
            ).pack(side="left", padx=10, pady=8, fill="x", expand=True)
            ctk.CTkButton(
                card, text="Delete", width=58,
                fg_color="transparent", border_width=1,
                border_color=self.theme["RED"], text_color=self.theme["RED"],
                hover_color=self.theme["BG_SECONDARY"],
                command=lambda name=username: self._remove_named_account(name),
            ).pack(side="right", padx=(4, 8), pady=5)
            ctk.CTkButton(
                card, text="Rename", width=66,
                fg_color="transparent", border_width=1,
                border_color=self.theme["BORDER_COL"], text_color=self.theme["TEXT_FG"],
                hover_color=self.theme["BG_SECONDARY"],
                command=lambda name=username: self._rename_named_account(name),
            ).pack(side="right", padx=(4, 0), pady=5)
            ctk.CTkButton(
                card, text="Select", width=62,
                fg_color=self.theme["ACCENT"], text_color=self.theme["ACCENT_TEXT"],
                hover_color=self.theme["ACCENT_DARK"],
                command=lambda name=username: self._select_offline_profile(name),
            ).pack(side="right", padx=(4, 8), pady=5)

    def _save_offline_profiles(self, profiles, selected: str | None):
        previous = self.parent.cfg.get("offline_profiles", [])
        previous_active = self.parent.cfg.get("active_offline_profile")
        previous_username = self.parent.username_var.get()
        self.parent.cfg["offline_profiles"] = profiles
        self.parent.cfg["active_offline_profile"] = selected
        self.parent.cfg["username"] = selected or ""
        try:
            config.save(self.parent.cfg)
        except OSError as exc:
            self.parent.cfg["offline_profiles"] = previous
            self.parent.cfg["active_offline_profile"] = previous_active
            self.parent.cfg["username"] = previous_username
            messagebox.showerror("Could not save offline profiles", str(exc), parent=self.winfo_toplevel())
            return False
        self.parent.username_var.set(selected or "")
        if selected and not any(item.get("username") == selected for item in self.accounts):
            self.accounts.append({
                "username": selected,
                "uuid": account_store.offline_uuid(selected),
                "type": "offline",
                "skin_model": "classic",
            })
        self._save_accounts()
        self._render_account_cards()
        self.parent._refresh_buttons()
        self._refresh_offline_profiles()
        return True

    def _select_offline_profile(self, name: str):
        profiles = self.parent.cfg.get("offline_profiles", [])
        if name not in profiles:
            return
        self._save_offline_profiles(profiles, name)

    def _add_offline_profile(self):
        name = simpledialog.askstring(
            "Add offline profile", "Minecraft username:", parent=self.winfo_toplevel()
        )
        if name is None:
            return
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", name):
            messagebox.showerror(
                "Invalid username", "Use 1–16 letters, numbers or underscores.", parent=self.winfo_toplevel()
            )
            return
        profiles = list(self.parent.cfg.get("offline_profiles", []))
        if any(existing.casefold() == name.casefold() for existing in profiles):
            messagebox.showerror("Profile exists", "That offline profile already exists.", parent=self.winfo_toplevel())
            return
        profiles.append(name)
        self.accounts.append({
            "username": name,
            "uuid": account_store.offline_uuid(name),
            "type": "offline",
            "skin_model": "classic",
        })
        self._save_accounts()
        self._save_offline_profiles(profiles, name)

    def _rename_offline_profile(self):
        old_name = self.offline_choice.get()
        profiles = list(self.parent.cfg.get("offline_profiles", []))
        if old_name not in profiles:
            return
        name = simpledialog.askstring(
            "Rename offline profile", "Minecraft username:",
            initialvalue=old_name, parent=self.winfo_toplevel(),
        )
        if name is None:
            return
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", name):
            messagebox.showerror(
                "Invalid username", "Use 1–16 letters, numbers or underscores.", parent=self.winfo_toplevel()
            )
            return
        if any(existing.casefold() == name.casefold() for existing in profiles if existing != old_name):
            messagebox.showerror("Profile exists", "That offline profile already exists.", parent=self.winfo_toplevel())
            return
        profiles[profiles.index(old_name)] = name
        account = next(
            (item for item in self.accounts if item.get("username") == old_name), None
        )
        if account:
            account["username"] = name
            account["uuid"] = account_store.offline_uuid(name)
            self._save_accounts()
        self._save_offline_profiles(profiles, name)

    def _rename_named_account(self, name: str):
        self.offline_choice.set(name)
        self._rename_offline_profile()

    def _remove_named_account(self, name: str):
        self.offline_choice.set(name)
        self._remove_offline_profile()

    def _remove_offline_profile(self):
        name = self.offline_choice.get()
        profiles = list(self.parent.cfg.get("offline_profiles", []))
        if name not in profiles:
            return
        if not messagebox.askyesno(
            "Remove offline profile", f"Remove the local username '{name}'?", parent=self.winfo_toplevel()
        ):
            return
        profiles.remove(name)
        self.accounts = [
            account for account in self.accounts
            if account.get("username") != name
        ]
        self._save_accounts()
        selected = profiles[0] if profiles else None
        self._save_offline_profiles(profiles, selected)

    @staticmethod
    def _cosmetic_root() -> Path:
        return Path.home() / ".revomc" / "cosmetics"

    def _safe_cosmetic_path(self, value) -> Path | None:
        if not isinstance(value, str) or not value:
            return None
        launcher_root = Path.home() / ".revomc"
        root = self._cosmetic_root()
        if launcher_root.is_symlink() or root.is_symlink():
            return None
        root = root.resolve()
        path = Path(value)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            return None
        return path

    def _refresh_cosmetics(self):
        username = self.parent.username_var.get().strip()
        account = next(
            (item for item in self.accounts if item.get("username") == username),
            None,
        )
        account_id = account.get("uuid") if account else None
        if account and hasattr(self, "skin_model"):
            self.skin_model.set(account.get("skin_model", "classic"))
        for cosmetic, size in (("skin", (150, 200)), ("cape", (128, 64))):
            preview = getattr(self, f"{cosmetic}_preview")
            state = getattr(self, f"{cosmetic}_state")
            path = None
            if account_id:
                try:
                    candidate = skin_store.account_cosmetic_dir(account_id) / f"{cosmetic}.png"
                    if candidate.is_file() and not candidate.is_symlink():
                        path = candidate
                except (OSError, ValueError):
                    path = None
            if path is None:
                preview.configure(image=None, text="No image saved")
                state.configure(text="No local image for this offline account.")
                continue
            try:
                validate_cosmetic_image(path, cosmetic)
                with Image.open(path) as source:
                    image = source.convert("RGBA")
                if cosmetic == "skin":
                    slim = bool(account and account.get("skin_model") == "slim")
                    hero = skin_render.render_player(
                        image, slim=slim, size=(size[0] * 2, size[1] * 2)
                    ).image
                    rendered = ctk.CTkImage(light_image=hero, dark_image=hero, size=size)
                else:
                    rendered = ctk.CTkImage(
                        light_image=image, dark_image=image, size=size
                    )
                self._cosmetic_images[cosmetic] = rendered
                preview.configure(image=rendered, text="")
                state.configure(
                    text=f"{path.name}\nSaved for {username}. It is shown in-game on your own client "
                         "(singleplayer, LAN, offline servers)."
                )
            except (OSError, ValueError) as exc:
                preview.configure(image=None, text="Invalid saved image")
                state.configure(text=f"Saved cosmetic could not be loaded: {exc}")

    def _import_cosmetic(self, cosmetic: str):
        source_name = filedialog.askopenfilename(
            parent=self.winfo_toplevel(), title=f"Import {cosmetic}",
            filetypes=[("PNG image", "*.png")],
        )
        if not source_name:
            return
        source = Path(source_name)
        try:
            username = self.parent.username_var.get().strip()
            account = next(
                (item for item in self.accounts if item.get("username") == username),
                None,
            )
            if not account:
                raise ValueError("Create or select an offline account before adding cosmetics.")
            dimensions = validate_cosmetic_image(source, cosmetic)
            destination = skin_store.store_cosmetic(account["uuid"], source, cosmetic)
            self._refresh_cosmetics()
            if cosmetic == "skin":
                self.parent._refresh_home_skin()
            messagebox.showinfo(
                f"{cosmetic.title()} saved",
                f"Saved {cosmetic} ({dimensions[0]} × {dimensions[1]}) for {username}. "
                "It is applied when you launch a Fabric profile as this offline account. "
                "Other players on online-mode servers will not see it.",
                parent=self.winfo_toplevel(),
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror(f"Could not import {cosmetic}", str(exc), parent=self.winfo_toplevel())

    def _remove_cosmetic(self, cosmetic: str):
        if not messagebox.askyesno(
            f"Remove {cosmetic} preview",
            f"Remove the saved local {cosmetic} preview?",
            parent=self.winfo_toplevel(),
        ):
            return
        username = self.parent.username_var.get().strip()
        account = next(
            (item for item in self.accounts if item.get("username") == username),
            None,
        )
        if account:
            try:
                folder = skin_store.account_cosmetic_dir(account["uuid"])
                path = folder / f"{cosmetic}.png"
                path.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Could not remove cosmetic", str(exc), parent=self.winfo_toplevel())
                return
        self._refresh_cosmetics()
        if cosmetic == "skin":
            self.parent._refresh_home_skin()

    def _save_skin_model(self, model: str):
        username = self.parent.username_var.get().strip()
        account = next(
            (item for item in self.accounts if item.get("username") == username),
            None,
        )
        if account:
            account["skin_model"] = model
            self._save_accounts()
            self._refresh_cosmetics()
            self.parent._refresh_home_skin()

    def _refresh_status(self):
        if not self.winfo_exists():
            return
        account = self.parent._ms_account
        if account:
            self.status.configure(text=f"Signed in as {account.get('name', 'Microsoft account')}")
        else:
            self.status.configure(
                text="Not signed in. Microsoft sign-in uses the official browser flow."
            )
        self.after(500, self._refresh_status)


# ── Main Window ───────────────────────────────────────────────────────────────


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg              = config.load()
        offline_profiles = self.cfg.get("offline_profiles", [])
        if not isinstance(offline_profiles, list):
            offline_profiles = []
        offline_profiles = list(dict.fromkeys(
            name for name in offline_profiles if isinstance(name, str) and name.strip()
        ))
        username = self.cfg.get("username", "")
        active_offline = self.cfg.get("active_offline_profile")
        if isinstance(username, str) and username.strip() and username not in offline_profiles:
            offline_profiles.append(username)
        if isinstance(username, str) and username in offline_profiles:
            active_offline = username
        elif active_offline not in offline_profiles:
            active_offline = offline_profiles[0] if offline_profiles else None
            if active_offline:
                username = active_offline
        self.cfg["offline_profiles"] = offline_profiles
        self.cfg["active_offline_profile"] = active_offline
        self.cfg["username"] = username if isinstance(username, str) else ""
        self.max_ram_gb = max(1, _get_system_ram_gb() - 1)
        instance_ids = set()
        profiles_changed = False
        for profile in self.cfg.get("profiles", []):
            instance_id = profile.get("instance_id")
            if (
                not isinstance(instance_id, str)
                or len(instance_id) != 32
                or any(character not in "0123456789abcdef" for character in instance_id)
                or instance_id in instance_ids
            ):
                profile["instance_id"] = uuid.uuid4().hex
                profiles_changed = True
            instance_ids.add(profile["instance_id"])
        if profiles_changed:
            config.save(self.cfg)
        self.theme            = get_theme(self.cfg.get("theme", DEFAULT_THEME))
        self.all_versions: list[str]    = []
        self.fabric_versions: list[str] = []
        self.latest_fabric_loader_versions: dict[str, str] = {}
        self._busy            = False
        self.motion           = Motion(
            self,
            enabled=bool(self.cfg.get("animations", True)),
            is_busy=lambda: self._busy,
        )
        self._current_page    = "home"
        self._color_animations = {}
        self._selected_profile_idx: int = -1
        self._ms_account: dict | None = None
        self._username_trace_id = None
        self._profile_editor = None
        self._profile_category_buttons = {}

        self._setup_ui()
        self._check_java()
        self._load_versions()
        self._try_restore_session()

    # ── Java check (same as original) ─────────────────────────────────────────

    def _check_java(self):
        from core.updater import CURRENT_VERSION
        self._log(f"🚀 FlowwwClient Launcher Version: {CURRENT_VERSION}")
        self._log("☕ Java runtimes are downloaded on demand (Java 8 / 17 / 21 / 25).")

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        self.title("FlowwwClient")
        self.geometry("1360x820")
        self.minsize(1040, 660)
        self.configure(fg_color=BG_PRIMARY)
        with Image.open(_resource_path("assets/bg.jpg")) as source:
            self._background_source = source.convert("RGB")
        self._background_image = None
        self._background_resize_job = None
        self._background_label = ctk.CTkLabel(self, text="", corner_radius=0)
        self._background_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._background_label.lower()
        self.bind("<Configure>", self._schedule_background_render, add="+")

        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=24, pady=18)
        root.grid_columnconfigure(0, weight=0)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(1, weight=1)

        navigation = ctk.CTkFrame(
            root, fg_color=BG_SECONDARY, corner_radius=14,
            border_width=1, border_color=BORDER_COL, width=184,
        )
        self.navigation = navigation
        navigation.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 18))
        navigation.grid_propagate(False)
        ctk.CTkLabel(
            navigation, text="NAVIGATION", text_color=TEXT_LABEL,
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(20, 10))

        self.nav_buttons = {}
        nav_items = (
            ("home", "▶   Play", lambda: self._show_page("home")),
            ("profiles", "▦   Profiles", lambda: self._show_page("profiles")),
            ("accounts", "◎   Accounts", self._open_accounts),
            ("settings", "⚙   Settings", self._open_settings_page),
            ("console", "≡   Logs", lambda: self._show_page("console")),
        )
        for key, label, command in nav_items:
            button = ctk.CTkButton(
                navigation, text=label, height=40, corner_radius=9,
                fg_color="transparent", hover_color=BG_PRIMARY,
                text_color=TEXT_FG, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                command=command,
            )
            button.pack(fill="x", padx=9, pady=3)
            button.bind(
                "<Enter>",
                lambda _event, w=button, k=key: self._animate_widget_color(
                    w,
                    self.theme["ACCENT"] if self._current_page == k else self.theme["BG_SECONDARY"],
                ),
                add="+",
            )
            button.bind(
                "<Leave>",
                lambda _event, w=button, k=key: self._animate_widget_color(
                    w,
                    self.theme["ACCENT"] if self._current_page == k else "transparent",
                ),
                add="+",
            )
            self.nav_buttons[key] = button
        ctk.CTkFrame(navigation, height=1, fg_color=BORDER_COL).pack(
            fill="x", padx=14, pady=(14, 10)
        )
        ctk.CTkLabel(
            navigation, text="FLOWWWCLIENT", text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(0, 3))
        ctk.CTkLabel(
            navigation, text="Minecraft Launcher", text_color=TEXT_LABEL,
            font=ctk.CTkFont(size=10),
        ).pack(anchor="w", padx=16, pady=(0, 16))

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(1, weight=1)

        wordmark = ctk.CTkFrame(header, fg_color="transparent")
        wordmark.grid(row=0, column=0, sticky="w")
        with Image.open(_resource_path("assets/Minecraft.jpg")) as source:
            brand_art = source.convert("RGB")
        self.brand_art = brand_art
        self.brand_image = ctk.CTkImage(
            light_image=brand_art, dark_image=brand_art, size=(42, 42),
        )
        ctk.CTkLabel(wordmark, text="", image=self.brand_image).pack(
            side="left", padx=(0, 9)
        )
        ctk.CTkLabel(
            wordmark,
            text="FlowwwClient",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color=self.theme["TEXT_FG"],
        ).pack(side="left")

        auth_block = ctk.CTkFrame(header, fg_color="transparent")
        auth_block.grid(row=0, column=2, sticky="e")

        # Auth mode toggle
        mode_row = ctk.CTkFrame(auth_block, fg_color="transparent")
        mode_row.pack(anchor="e", pady=(0, 4))
        _section_label(mode_row, "Account").pack(side="left", padx=(0, 8))
        self.auth_mode_var = ctk.StringVar(value=self.cfg.get("auth_mode", "offline"))
        self.auth_mode_menu = ctk.CTkSegmentedButton(
            mode_row,
            values=["Offline", "Microsoft"],
            variable=self.auth_mode_var,
            command=self._on_auth_mode_changed,
            font=ctk.CTkFont(size=11),
            selected_color=BORDER_COL,
            selected_hover_color=BORDER_COL,
            unselected_color=BG_SECONDARY,
            unselected_hover_color=BG_CARD,
        )
        self.auth_mode_menu.pack(side="left")
        self.auth_mode_var.set(self.cfg.get("auth_mode", "offline").title())

        # Offline panel: username entry
        self.offline_panel = ctk.CTkFrame(auth_block, fg_color="transparent")
        self.username_var = ctk.StringVar(value=self.cfg.get("username", ""))
        self._username_trace_id = self.username_var.trace_add("write", self._on_username_changed)
        ctk.CTkEntry(
            self.offline_panel, textvariable=self.username_var,
            placeholder_text="Enter username…", width=220,
        ).pack(side="left")

        # Microsoft panel: sign-in button / account label
        self.ms_panel = ctk.CTkFrame(auth_block, fg_color="transparent")
        self.ms_signin_btn = ctk.CTkButton(
            self.ms_panel, text="  Sign in with Microsoft",
            fg_color=MS_BLUE, hover_color=MS_BLUE_DARK,
            text_color=ACCENT_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=220, height=32,
            command=self._on_ms_signin,
        )
        self.ms_loggedin_frame = ctk.CTkFrame(self.ms_panel, fg_color="transparent")
        self.ms_gamertag_lbl = ctk.CTkLabel(
            self.ms_loggedin_frame, text="",
            text_color=self.theme["ACCENT"],
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.ms_gamertag_lbl.pack(side="left", padx=(0, 8))
        self.ms_signout_btn = ctk.CTkButton(
            self.ms_loggedin_frame, text="Sign Out",
            fg_color="transparent", border_width=1, border_color=BORDER_COL,
            text_color=TEXT_MUTED, hover_color=BG_SECONDARY,
            width=72, height=28,
            font=ctk.CTkFont(size=11),
            command=self._on_ms_signout,
        )
        self.ms_signout_btn.pack(side="left")
        self._refresh_auth_panel()

        content = ctk.CTkFrame(root, fg_color="transparent")
        content.grid(row=1, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.page_container = content

        self._build_left(content)
        self._build_right(content)
        self._build_home(content)
        self._pages = {
            "home": self.home_panel,
            "profiles": self.left_panel,
            "console": self.right_panel,
        }
        self._lazy_pages = {"accounts": AccountsPage, "settings": SettingsPage}
        self._global_navigation_widgets = [
            (widget, widget.pack_info()) for widget in navigation.winfo_children()
        ]
        self._show_page("home")
        self.after(0, self._render_background)

    def _schedule_background_render(self, event):
        if event.widget is not self:
            return
        if self._background_resize_job:
            self.after_cancel(self._background_resize_job)
        self._background_resize_job = self.after(150, self._render_background)

    def _render_background(self):
        self._background_resize_job = None
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1 or height <= 1:
            return
        background = ImageOps.fit(
            self._background_source,
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        if is_light(self.cfg.get("theme", DEFAULT_THEME)):
            # wash the gradient out into a soft lavender so dark text stays readable
            wash = Image.new("RGB", background.size, (238, 234, 252))
            background = Image.blend(ImageEnhance.Color(background).enhance(1.35), wash, 0.68)
        else:
            background = ImageEnhance.Brightness(background).enhance(0.70)
        self._background_image = ctk.CTkImage(
            light_image=background,
            dark_image=background,
            size=(width, height),
        )
        self._background_label.configure(image=self._background_image)
        self._background_label.lower()

    def _show_profile_editor_navigation(self, editor):
        for widget, _pack_info in self._global_navigation_widgets:
            widget.pack_forget()
        for widget in self._profile_nav_widgets if hasattr(self, "_profile_nav_widgets") else []:
            widget.destroy()

        self._profile_nav_widgets = []
        self._profile_category_buttons = {}

        def add(widget, **pack_options):
            widget.pack(**pack_options)
            self._profile_nav_widgets.append(widget)
            return widget

        add(
            ctk.CTkLabel(
                self.navigation,
                text="PROFILE CONTENTS",
                text_color=self.theme["TEXT_MUTED"],
                font=ctk.CTkFont(size=10, weight="bold"),
            ),
            anchor="w",
            padx=14,
            pady=(18, 10),
        )
        add(
            ctk.CTkLabel(
                self.navigation,
                text=editor.profile.get("name", "Profile"),
                text_color=self.theme["TEXT_FG"],
                font=ctk.CTkFont(size=13, weight="bold"),
                wraplength=148,
                justify="left",
            ),
            anchor="w",
            padx=14,
            pady=(0, 3),
        )
        loader_version = editor.profile.get("fabric_loader_version") or (
            self.latest_fabric_loader_versions.get(editor.profile.get("mc_version"))
        )
        profile_details = (
            f"Minecraft {editor.profile.get('mc_version', '?')} · "
            f"{editor.profile.get('type', 'vanilla').title()}"
        )
        if editor.profile.get("type") == "fabric" and loader_version:
            profile_details += f" {loader_version}"
        add(
            ctk.CTkLabel(
                self.navigation,
                text=profile_details,
                text_color=self.theme["TEXT_MUTED"],
                font=ctk.CTkFont(size=10),
                wraplength=148,
                justify="left",
            ),
            anchor="w",
            padx=14,
            pady=(0, 12),
        )
        add(
            ctk.CTkButton(
                self.navigation,
                text="←  Back to Profiles",
                height=36,
                fg_color="transparent",
                border_width=1,
                border_color=self.theme["BORDER_COL"],
                text_color=self.theme["TEXT_FG"],
                hover_color=self.theme["BG_PRIMARY"],
                command=editor._back_to_profiles,
            ),
            fill="x",
            padx=8,
            pady=(0, 10),
        )
        for label, key in editor.CATEGORIES:
            button = add(
                ctk.CTkButton(
                    self.navigation,
                    text=label,
                    anchor="w",
                    height=38,
                    corner_radius=8,
                    fg_color=(
                        self.theme["ACCENT"] if key == editor.category else "transparent"
                    ),
                    text_color=(
                        self.theme["ACCENT_TEXT"] if key == editor.category
                        else self.theme["TEXT_FG"]
                    ),
                    hover_color=self.theme["ACCENT_DARK"],
                    command=lambda category=key: editor._select_category(category),
                ),
                fill="x",
                padx=8,
                pady=2,
            )
            self._profile_category_buttons[key] = button

    def _restore_global_navigation(self):
        for widget in getattr(self, "_profile_nav_widgets", []):
            widget.destroy()
        self._profile_nav_widgets = []
        for widget, pack_info in self._global_navigation_widgets:
            options = dict(pack_info)
            options["in_"] = options.pop("in")
            widget.pack(**options)

    def _open_profile_editor(self, profile, initial_category="overview"):
        if self._profile_editor is not None:
            self._profile_editor.destroy()
        for frame in self._pages.values():
            frame.grid_forget()
            frame.place_forget()
        editor = ProfileEditorWindow(self, profile, initial_category)
        self._profile_editor = editor
        self._pages["profile_editor"] = editor
        self._current_page = "profile_editor"
        self._set_active_navigation("profile_editor")
        self.motion.slide_up(editor, key="page")

    def _leave_profile_editor(self):
        editor = self._profile_editor
        self._profile_editor = None
        self._pages.pop("profile_editor", None)
        if editor is not None:
            editor._request_serial += 1
            editor.destroy()
        self._restore_global_navigation()
        self._show_page("profiles")

    def _show_page(self, page):
        if not hasattr(self, "_pages"):
            return
        page = "home" if page == "dashboard" else page
        if page not in self._pages:
            factory = getattr(self, "_lazy_pages", {}).get(page)
            if factory is None:
                return
            self._pages[page] = factory(self)
        target = self._pages[page]
        for name, frame in self._pages.items():
            if frame is not target:
                frame.grid_forget()
                frame.place_forget()
        self._current_page = page
        self._set_active_navigation(page)
        refresh = getattr(target, "on_show", None)
        if callable(refresh):
            refresh()
        self.motion.slide_up(target, distance=24, duration_ms=220, key="page")

    def _animate_widget_color(self, widget, target: str, duration_ms: int = 120):
        if self._busy:
            return
        try:
            current = widget.cget("fg_color")
            if isinstance(current, (tuple, list)):
                current = current[-1]
            end_color = target
            start_color = self.theme["BG_SECONDARY"] if current == "transparent" else current
            finish_color = self.theme["BG_SECONDARY"] if target == "transparent" else target
            if not (
                isinstance(start_color, str) and start_color.startswith("#")
                and isinstance(finish_color, str) and finish_color.startswith("#")
            ):
                widget.configure(fg_color=target)
                return
            if len(start_color) == 4:
                start_color = "#" + "".join(char * 2 for char in start_color[1:])
            if len(finish_color) == 4:
                finish_color = "#" + "".join(char * 2 for char in finish_color[1:])
            start = tuple(int(start_color[index:index + 2], 16) for index in (1, 3, 5))
            finish = tuple(int(finish_color[index:index + 2], 16) for index in (1, 3, 5))
            previous = self._color_animations.pop(widget, None)
            if previous:
                self.after_cancel(previous)

            steps = max(1, duration_ms // 20)

            def animate(step=1):
                if not widget.winfo_exists() or self._busy:
                    self._color_animations.pop(widget, None)
                    return
                fraction = min(step / steps, 1)
                color = "#" + "".join(
                    f"{round(a + (b - a) * fraction):02x}"
                    for a, b in zip(start, finish)
                )
                widget.configure(
                    fg_color=target if step >= steps and target == "transparent" else color
                )
                if step < steps:
                    self._color_animations[widget] = self.after(20, lambda: animate(step + 1))
                else:
                    self._color_animations.pop(widget, None)

            animate()
        except (TclError, ValueError):
            return

    def _set_active_navigation(self, page):
        for key, button in self.nav_buttons.items():
            active = key == page
            self._animate_widget_color(
                button, self.theme["ACCENT"] if active else "transparent"
            )
            button.configure(
                hover_color=self.theme["ACCENT_DARK"] if active else self.theme["BG_PRIMARY"],
                text_color=self.theme["ACCENT_TEXT"] if active else self.theme["TEXT_FG"],
            )

    def _open_profile_content(self, category):
        profile = self._current_profile()
        if not profile:
            messagebox.showinfo(
                "Select a profile",
                "Create or select a profile before managing its content.",
                parent=self,
            )
            return
        self._open_profile_editor(profile, initial_category=category)

    def _open_accounts(self):
        self._show_page("accounts")

    def _open_settings_page(self):
        self._show_page("settings")

    def _build_left(self, parent):
        left = ctk.CTkFrame(parent, fg_color="transparent")
        self.left_panel = left
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        ph = ctk.CTkFrame(left, fg_color="transparent")
        ph.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            ph, text="Profiles", text_color=TEXT_FG,
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        self.new_btn = ctk.CTkButton(
            ph, text="+ New profile", width=125,
            fg_color=GREEN, text_color=ACCENT_TEXT, hover_color=GREEN_DARK,
            command=self._on_new_profile,
        )
        self.new_btn.pack(side="right")

        self.profile_list_frame = ctk.CTkScrollableFrame(
            left, label_text="", fg_color="transparent",
        )
        self.profile_list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        self.info_card = ctk.CTkFrame(
            left, fg_color=BG_CARD,
            border_color=BORDER_COL, border_width=1, corner_radius=12,
        )
        self.info_card.grid(row=2, column=0, sticky="ew")
        self.info_version_lbl = ctk.CTkLabel(
            self.info_card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
        )
        self.info_version_lbl.pack(anchor="w", padx=16, pady=(12, 2))
        self.info_mods_lbl = ctk.CTkLabel(
            self.info_card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            wraplength=780, justify="left",
        )
        self.info_mods_lbl.pack(anchor="w", padx=16, pady=(0, 12))
        self._profile_buttons = []

    def _build_right(self, parent):
        right = ctk.CTkFrame(parent, fg_color="transparent")
        self.right_panel = right
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(right, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            header, text="Logs", text_color=TEXT_FG,
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        self.console_status = ctk.CTkLabel(
            header, text="● READY", text_color=GREEN,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.console_status.pack(side="right")

        self.log_box = ctk.CTkTextbox(
            right, state="disabled", fg_color=BG_CONSOLE,
            border_color=BORDER_COL, border_width=1, corner_radius=12,
            font=ctk.CTkFont(family="monospace", size=11),
            text_color=TEXT_MUTED,
        )
        self.log_box.grid(row=1, column=0, sticky="nsew")

    def _build_home(self, parent):
        self.home_panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel = self.home_panel
        panel.grid_columnconfigure(0, weight=3, uniform="home", minsize=250)
        panel.grid_columnconfigure(1, weight=7, uniform="home", minsize=420)
        panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            panel, text="Play", text_color=TEXT_FG,
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        def glass(**options):
            return ctk.CTkFrame(
                panel, fg_color=BG_SECONDARY, corner_radius=16,
                border_width=1, border_color=BORDER_COL, **options,
            )

        # ── left: profile + quick access ─────────────────────────────────────
        left = glass()
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        _section_label(left, "Active profile").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 6))
        self.home_profile_name = ctk.CTkLabel(
            left, text="Select a profile to get started", text_color=TEXT_FG,
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w", justify="left",
            wraplength=230,
        )
        self.home_profile_name.grid(row=1, column=0, sticky="ew", padx=18)
        self.home_profile_details = ctk.CTkLabel(
            left, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            anchor="w", justify="left", wraplength=230,
        )
        self.home_profile_details.grid(row=2, column=0, sticky="ew", padx=18, pady=(4, 8))
        self.home_status_badge = ctk.CTkLabel(
            left, text="", corner_radius=8, height=22, width=120,
            fg_color=self.theme["NEUTRAL"], text_color=ACCENT_TEXT,
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.home_status_badge.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 12))
        self.home_profile_menu = ctk.CTkOptionMenu(
            left, values=["No profiles"], height=36,
            fg_color=BG_PRIMARY, text_color=TEXT_FG,
            button_color=self.theme["ACCENT"],
            button_hover_color=self.theme["ACCENT_DARK"],
            command=self._select_home_profile,
        )
        self.home_profile_menu.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 6))
        self.home_profile_count = ctk.CTkLabel(
            left, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=11), anchor="w",
        )
        self.home_profile_count.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 10))
        ctk.CTkFrame(left, height=1, fg_color=BORDER_COL).grid(
            row=6, column=0, sticky="ew", padx=18, pady=(0, 12))
        _section_label(left, "Quick access").grid(
            row=7, column=0, sticky="w", padx=18, pady=(0, 8))
        action_items = (
            ("Edit profile", self._on_edit_profile),
            ("Browse mods", lambda: self._open_profile_content("mods")),
            ("Settings", self._open_settings_page),
            ("View logs", lambda: self._show_page("console")),
        )
        for row, (title, command) in enumerate(action_items, start=8):
            button = ctk.CTkButton(
                left, text=title, anchor="w", height=34, corner_radius=10,
                fg_color=BG_CARD, hover_color=BORDER_COL, text_color=TEXT_FG,
                border_width=1, border_color=BORDER_COL,
                font=ctk.CTkFont(size=12, weight="bold"), command=command,
            )
            button.grid(row=row, column=0, sticky="ew", padx=18, pady=3)
        ctk.CTkButton(
            left, text="+  New profile", height=34, corner_radius=10,
            command=self._on_new_profile,
        ).grid(row=12, column=0, sticky="ew", padx=18, pady=(10, 18))

        # ── centre: hero stage with the PLAY button below ────────────────────
        centre = glass()
        centre.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        centre.grid_columnconfigure(0, weight=1)
        centre.grid_rowconfigure(0, weight=1)
        scene = None
        try:
            with Image.open(_resource_path("assets/stage_bg.jpg")) as source:
                scene = source.convert("RGB")
        except OSError:
            scene = None
        self.stage = HeroStage(
            centre, self.theme, motion=self.motion,
            on_create_account=lambda: self._show_page("accounts"),
            scene=scene,
        )
        self.stage.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 8))
        self.play_btn = ctk.CTkButton(
            centre, text="▶  PLAY", height=52, corner_radius=12, width=320,
            fg_color=self.theme["ACCENT"], text_color=ACCENT_TEXT,
            hover_color=self.theme["ACCENT_DARK"],
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._on_play_btn,
        )
        self.play_btn.grid(row=1, column=0, pady=(0, 18))
        centre.bind(
            "<Configure>",
            lambda event: self.play_btn.configure(
                width=max(180, min(360, event.width - 56))
            ),
            add="+",
        )

        # progress + status live under the PLAY button (the old "Launch settings"
        # card is gone: memory is a per-profile setting now, in Edit profile)
        self.progress_bar = ctk.CTkProgressBar(
            centre, progress_color=GREEN, fg_color=BORDER_COL,
            height=8, corner_radius=6,
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 6))
        self.status_lbl = ctk.CTkLabel(
            centre, text="Ready to launch Minecraft.",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            anchor="center", justify="center", wraplength=520,
        )
        self.status_lbl.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 14))
        self.play_btn.grid_configure(pady=(0, 12))

        # memory widgets are kept off-screen: they mirror the active profile's
        # memory so launching and the profile editor stay in sync
        self._hidden_launch = ctk.CTkFrame(panel, fg_color="transparent")
        self.ram_label_lbl = ctk.CTkLabel(
            self._hidden_launch,
            text=f"Memory allocation · {self.cfg.get('ram_gb', 2)} GB",
        )
        try:
            configured_ram = int(self.cfg.get("ram_gb", 2))
        except (TypeError, ValueError):
            configured_ram = 2
        configured_ram = min(max(1, configured_ram), self.max_ram_gb)
        if self.cfg.get("ram_gb") != configured_ram:
            self.cfg["ram_gb"] = configured_ram
            try:
                config.save(self.cfg)
            except OSError as exc:
                messagebox.showerror("Could not save RAM setting", str(exc), parent=self)
        self.ram_var = ctk.IntVar(value=configured_ram)
        self.ram_slider = ctk.CTkSlider(
            self._hidden_launch, from_=1, to=self.max_ram_gb,
            number_of_steps=max(1, self.max_ram_gb - 1),
            variable=self.ram_var, command=self._on_ram_changed,
        )
        # account line sits in the profile card
        self.home_account_label = ctk.CTkLabel(
            left, text="", text_color=TEXT_MUTED, anchor="w",
            font=ctk.CTkFont(size=11), wraplength=230, justify="left",
        )
        self.home_account_label.grid(row=13, column=0, sticky="ew", padx=18, pady=(0, 14))
        left.grid_rowconfigure(13, weight=0)
        left.grid_rowconfigure(14, weight=1)

        self._refresh_profile_list()
        self._refresh_home_skin()
        self._update_home_profile(self._current_profile())

    def _bind_card_motion(self, card):
        """Kept for compatibility; cards no longer change colour on hover."""
        return None

    # ── Version loading ────────────────────────────────────────────────────────

    def _load_versions(self):
        self._log("🌐 Fetching Minecraft versions…")

        def _task():
            try:
                all_v = fetch_release_versions()
                self.all_versions = [v["id"] for v in all_v]
                self.after(0, lambda: self._log(f"✅ {len(self.all_versions)} total MC releases found."))
            except Exception as e:
                self.after(0, lambda error=e: self._log(f"❌ Could not fetch MC versions: {error}"))

            try:
                self.fabric_versions = fetch_fabric_versions()
                self.after(0, lambda: self._log(f"✅ {len(self.fabric_versions)} versions supported by Fabric."))
            except Exception as e:
                self.after(0, lambda error=e: self._log(f"❌ Could not fetch Fabric versions: {error}"))

            try:
                from core.installer import fetch_latest_stable_fabric_loader

                profiles = [
                    profile for profile in self.cfg.get("profiles", [])
                    if isinstance(profile, dict) and profile.get("type") == "fabric"
                ]
                minecraft_versions = {
                    profile["mc_version"]
                    for profile in profiles
                    if isinstance(profile.get("mc_version"), str)
                }
                if self.fabric_versions:
                    minecraft_versions.add(self.fabric_versions[0])
                self.latest_fabric_loader_versions = {
                    version: fetch_latest_stable_fabric_loader(version)
                    for version in minecraft_versions
                }
                if profiles:
                    self.after(0, self._upgrade_fabric_profiles)
            except Exception as e:
                self.after(
                    0,
                    lambda error=e: self._log(
                        f"❌ Could not fetch stable Fabric loader versions: {error}"
                    ),
                )

            self.after(0, self._maybe_create_default_profiles)
            self.after(0, self._auto_update_latest_profiles)
            self.after(0, self._refresh_buttons)

        threading.Thread(target=_task, daemon=True).start()

    def _upgrade_fabric_profiles(self):
        changed = False
        for profile in self.cfg.get("profiles", []):
            if not isinstance(profile, dict) or profile.get("type") != "fabric":
                continue
            mc_version = profile.get("mc_version")
            latest = self.latest_fabric_loader_versions.get(mc_version)
            if (
                not latest
                or profile.get("fabric_loader_pinned")
                or profile.get("source_modpack")
                or profile.get("imported_modpack")
            ):
                continue
            if profile.get("fabric_loader_version") != latest:
                previous = profile.get("fabric_loader_version")
                profile["fabric_loader_version"] = latest
                changed = True
                self._log(
                    f"⬆ Upgraded Fabric loader for '{profile.get('name', 'Profile')}' "
                    f"from {previous or 'default'} to {latest}."
                )
            entry = self.cfg.get("installed_versions", {}).get(mc_version)
            expected_id = f"fabric-loader-{latest}-{mc_version}"
            if isinstance(entry, dict) and entry.get("fabric_profile_id") != expected_id:
                entry["fabric_profile_id"] = expected_id
                changed = True
        if changed:
            config.save(self.cfg)
            self._refresh_profile_list()

    def _maybe_create_default_profiles(self):
        """On first launch, auto-create two default profiles."""
        if not self.cfg.get("first_run", True):
            return
        if self.cfg.get("profiles"):
            # Already has profiles — not first run
            self.cfg["first_run"] = False
            config.save(self.cfg)
            return

        profiles_created = []

        # 1. "Latest Release Vanilla" — latest MC version
        if self.all_versions:
            vanilla_profile = {
                "name": "Latest Release Vanilla",
                "mc_version": self.all_versions[0],
                "type": "vanilla",
                "mods": [],
                "instance_id": uuid.uuid4().hex,
            }
            profiles_created.append(vanilla_profile)

        # 2. "Latest Release Fabric" — latest Fabric-supported version
        if self.fabric_versions:
            fabric_profile = {
                "name": "Latest Release Fabric",
                "mc_version": self.fabric_versions[0],
                "type": "fabric",
                "mods": list(AVAILABLE_MODS.keys()),
                "instance_id": uuid.uuid4().hex,
            }
            loader_version = self.latest_fabric_loader_versions.get(
                self.fabric_versions[0]
            )
            if loader_version:
                fabric_profile["fabric_loader_version"] = loader_version
            profiles_created.append(fabric_profile)

        if profiles_created:
            self.cfg.setdefault("profiles", []).extend(profiles_created)
            self.cfg["active_profile"] = profiles_created[0]["name"]
            self.cfg["first_run"] = False
            config.save(self.cfg)
            self._refresh_profile_list()
            for p in profiles_created:
                self._log(f"✅ Default profile created: '{p['name']}' ({p['mc_version']}, {p['type']})")
        else:
            self.cfg["first_run"] = False
            config.save(self.cfg)

    def _auto_update_latest_profiles(self):
        """Silently keep 'Latest Release' profiles on the newest MC version.

        Runs every startup after version lists are fetched.
        - If a Latest Release profile exists but is stale, update its mc_version.
        - If a Latest Release profile was deleted, re-create it only when a
          genuinely NEW MC version has dropped since it was last seen.
        - Completely silent: no console output, no user notifications.
        """
        if not self.all_versions:
            return  # no version data available (offline?)

        latest_vanilla = self.all_versions[0]
        latest_fabric  = self.fabric_versions[0] if self.fabric_versions else None
        profiles       = self.cfg.setdefault("profiles", [])
        changed        = False

        # ── Vanilla ───────────────────────────────────────────────────────────
        vanilla_profile    = next((p for p in profiles if p["name"] == "Latest Release Vanilla"), None)
        prev_known_vanilla = self.cfg.get("last_known_latest_vanilla")

        if vanilla_profile:
            if vanilla_profile["mc_version"] != latest_vanilla:
                vanilla_profile["mc_version"] = latest_vanilla
                changed = True
        else:
            # Only re-create when a NEW version has appeared since last seen
            if latest_vanilla != prev_known_vanilla:
                profiles.append({
                    "name": "Latest Release Vanilla",
                    "mc_version": latest_vanilla,
                    "type": "vanilla",
                    "mods": [],
                    "instance_id": uuid.uuid4().hex,
                })
                changed = True

        self.cfg["last_known_latest_vanilla"] = latest_vanilla

        # ── Fabric ────────────────────────────────────────────────────────────
        if latest_fabric:
            fabric_profile    = next((p for p in profiles if p["name"] == "Latest Release Fabric"), None)
            prev_known_fabric = self.cfg.get("last_known_latest_fabric")

            if fabric_profile:
                if fabric_profile["mc_version"] != latest_fabric:
                    fabric_profile["mc_version"] = latest_fabric
                    changed = True
            else:
                if latest_fabric != prev_known_fabric:
                    profiles.append({
                        "name": "Latest Release Fabric",
                        "mc_version": latest_fabric,
                        "type": "fabric",
                        "mods": list(AVAILABLE_MODS.keys()),
                        "instance_id": uuid.uuid4().hex,
                        **(
                            {"fabric_loader_version": self.latest_fabric_loader_versions[latest_fabric]}
                            if latest_fabric in self.latest_fabric_loader_versions else {}
                        ),
                    })
                    changed = True

            self.cfg["last_known_latest_fabric"] = latest_fabric

        # ── Persist ───────────────────────────────────────────────────────────
        config.save(self.cfg)  # always persist the tracking keys
        if changed:
            self._refresh_profile_list()

    # ── Profiles ──────────────────────────────────────────────────────────────

    def _refresh_profile_list(self):
        for w in self.profile_list_frame.winfo_children():
            w.destroy()
        self._profile_buttons = []

        profiles = self.cfg.get("profiles", [])
        active = self.cfg.get("active_profile")

        for i, p in enumerate(profiles):
            profile_type = p.get("type", "vanilla").title()
            try:
                mod_count = sum(
                    path.name.casefold().endswith(".jar")
                    for path in modrinth.list_installed_files(p, "mods")
                )
            except (OSError, ValueError, RuntimeError):
                mod_count = None
            loader_version = p.get("fabric_loader_version") or getattr(
                self, "latest_fabric_loader_versions", {}
            ).get(p.get("mc_version"))

            card = ctk.CTkFrame(
                self.profile_list_frame, fg_color=BG_CARD,
                border_width=1,
                border_color=self.theme["ACCENT"] if p.get("name") == active else BORDER_COL,
                corner_radius=12,
            )
            card.pack(fill="x", pady=5, padx=2)
            card.configure(height=80)
            card.grid_propagate(False)
            card.grid_columnconfigure(0, weight=1)
            card.grid_rowconfigure(0, weight=1)
            loader_detail = (
                f"Fabric {loader_version}"
                if p.get("type") == "fabric" and loader_version
                else profile_type
            )
            details = (
                f"{p.get('mc_version', 'Unknown version')}  ·  "
                f"{loader_detail}  ·  "
                f"{mod_count} mods" if mod_count is not None else
                f"{p.get('mc_version', 'Unknown version')}  ·  "
                f"{loader_detail}  ·  Mod count unavailable"
            )
            select_area = ctk.CTkFrame(card, fg_color="transparent")
            select_area.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=8)
            select_area.grid_columnconfigure(0, weight=1)
            select_area.grid_rowconfigure(0, weight=1)
            select = ctk.CTkButton(
                select_area,
                text=p.get("name", "Unnamed profile"),
                anchor="w", height=25, corner_radius=8,
                fg_color="transparent", hover_color=BG_SECONDARY,
                text_color=TEXT_FG, font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda idx=i: self._on_profile_selected(idx),
            )
            select.grid(row=0, column=0, sticky="ew")
            details_label = ctk.CTkLabel(
                select_area,
                text=details,
                text_color=TEXT_MUTED,
                anchor="w",
                font=ctk.CTkFont(size=10),
                wraplength=480,
            )
            details_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)
            if p.get("name") == active:
                ctk.CTkLabel(
                    select_area,
                    text="ACTIVE",
                    fg_color=self.theme["ACCENT"],
                    text_color=self.theme["TEXT_FG"],
                    corner_radius=7,
                    font=ctk.CTkFont(size=9, weight="bold"),
                ).grid(row=0, column=1, padx=(6, 4))
            self._profile_buttons.append(select)
            ctk.CTkButton(
                card, text="Edit", width=58, height=30,
                fg_color="transparent", border_width=1,
                border_color=BORDER_COL, text_color=TEXT_FG,
                hover_color=BG_SECONDARY,
                command=lambda idx=i: self._on_profile_selected(idx) or self._on_edit_profile(),
            ).grid(row=0, column=1, padx=4)
            ctk.CTkButton(
                card, text="Delete", width=62, height=30,
                fg_color="transparent", border_width=1,
                border_color=self.theme["RED"], text_color=self.theme["RED"],
                hover_color=BG_SECONDARY,
                command=lambda idx=i: self._on_delete_profile(idx),
            ).grid(row=0, column=3, padx=(4, 8))
            ctk.CTkButton(
                card, text="Show Folder", width=92, height=30,
                fg_color="transparent", border_width=1,
                border_color=BORDER_COL, text_color=TEXT_FG,
                hover_color=BG_SECONDARY,
                command=lambda p=p: self._open_profile_folder(p),
            ).grid(row=0, column=2, padx=4)
            card.bind(
                "<Enter>",
                lambda _event, widget=card:
                self._animate_widget_color(widget, self.theme["BG_SECONDARY"]),
                add="+",
            )
            card.bind(
                "<Leave>",
                lambda _event, widget=card:
                self._animate_widget_color(widget, BG_CARD),
                add="+",
            )
            for child in (select_area, select, details_label):
                child.bind(
                    "<Button-1>",
                    lambda _event, idx=i: self._on_profile_selected(idx),
                    add="+",
                )

        if active:
            for i, p in enumerate(profiles):
                if p.get("name") == active:
                    self._selected_profile_idx = i
                    self._update_info_card(p)
                    if hasattr(self, "ram_var"):
                        try:
                            profile_ram = min(
                                max(1, int(p.get("memory_gb", self.cfg.get("ram_gb", 2)))),
                                self.max_ram_gb,
                            )
                        except (TypeError, ValueError):
                            profile_ram = self.cfg.get("ram_gb", 2)
                        self.ram_var.set(profile_ram)
                        self.ram_label_lbl.configure(
                            text=f"Memory allocation · {profile_ram} GB"
                        )
                    break
        if not profiles:
            self._selected_profile_idx = -1
            ctk.CTkLabel(
                self.profile_list_frame,
                text="No profiles yet. Create one to begin.",
                text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=14, pady=18)
        self._update_home_profile(self._current_profile())
        self._refresh_buttons()

    def _current_profile(self) -> dict | None:
        profiles = self.cfg.get("profiles", [])
        i = self._selected_profile_idx
        return profiles[i] if 0 <= i < len(profiles) else None

    def _on_profile_selected(self, idx: int):
        profiles = self.cfg.get("profiles", [])
        if 0 <= idx < len(profiles):
            self._selected_profile_idx = idx
            previous_active = self.cfg.get("active_profile")
            self.cfg["active_profile"] = profiles[idx]["name"]
            try:
                config.save(self.cfg)
            except OSError as exc:
                self.cfg["active_profile"] = previous_active
                messagebox.showerror("Could not select profile", str(exc), parent=self)
                return
            self._update_info_card(profiles[idx])
            self._update_home_profile(profiles[idx])
            if hasattr(self, "ram_var"):
                try:
                    profile_ram = int(profiles[idx].get(
                        "memory_gb", self.cfg.get("ram_gb", 2)
                    ))
                    profile_ram = min(max(1, profile_ram), self.max_ram_gb)
                    self.ram_var.set(profile_ram)
                    self.ram_label_lbl.configure(
                        text=f"Memory allocation · {profile_ram} GB"
                    )
                except (TypeError, ValueError):
                    pass
            for i, card in enumerate(self.profile_list_frame.winfo_children()):
                if isinstance(card, ctk.CTkFrame):
                    card.configure(
                        border_color=self.theme["ACCENT"] if i == idx else self.theme["BORDER_COL"]
                    )
        self._refresh_buttons()

    def _open_profile_folder(self, profile: dict):
        try:
            folder = profile_store.initialize_profile(profile)
            if os.name == "nt":
                os.startfile(str(folder))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except (OSError, ValueError, RuntimeError, AttributeError) as exc:
            messagebox.showerror("Could not open profile folder", str(exc), parent=self)

    def _update_info_card(self, profile: dict):
        loader = profile.get("fabric_loader_version") or getattr(
            self, "latest_fabric_loader_versions", {}
        ).get(profile.get("mc_version"))
        loader_text = f"  ·  Fabric loader {loader}" if loader and profile.get("type") == "fabric" else ""
        self.info_version_lbl.configure(
            text=f"MC {profile.get('mc_version', '?')}  ·  {profile.get('type', 'vanilla').title()}  ·  "
                 f"{'Installed' if self._is_installed_for_profile(profile) else 'Not installed'}"
                 f"{loader_text}"
        )
        try:
            count = sum(
                path.name.casefold().endswith(".jar")
                for path in modrinth.list_installed_files(profile, "mods")
            )
            self.info_mods_lbl.configure(
                text=f"Installed mods in this profile: {count}"
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.info_mods_lbl.configure(text=f"Could not inspect profile mods: {exc}")

    def _update_home_profile(self, profile: dict | None):
        if not hasattr(self, "home_profile_name"):
            return
        profile_count = len(self.cfg.get("profiles", []))
        profile_names = [
            item.get("name", "Unnamed profile")
            for item in self.cfg.get("profiles", [])
        ]
        self.home_profile_menu.configure(values=profile_names or ["No profiles"])
        count_text = f"{profile_count} profile{'s' if profile_count != 1 else ''} available"
        if profile is None:
            self.home_profile_count.configure(text=count_text)
            self.home_profile_name.configure(text="Select a profile to get started")
            self.home_profile_details.configure(text="Create a profile to install and launch Minecraft.")
            self.home_status_badge.configure(text="NO PROFILE", fg_color=self.theme["NEUTRAL"])
            self.home_account_label.configure(text="Choose an offline username or sign in with Microsoft.")
            self.play_btn.configure(state="disabled", text="▶  PLAY")
            if not profile_names:
                self.home_profile_menu.set("No profiles")
            self._refresh_home_skin()
            return
        installed = self._is_installed_for_profile(profile)
        install_state = "Installed" if installed else "Ready to install"
        self.home_profile_menu.set(profile.get("name", "Unnamed profile"))
        self.play_btn.configure(
            state="normal",
            text="▶  PLAY" if installed else "▶  INSTALL & PLAY",
        )
        loader_version = profile.get("fabric_loader_version") or getattr(
            self, "latest_fabric_loader_versions", {}
        ).get(profile.get("mc_version"))
        loader_text = profile.get("type", "vanilla").title()
        if profile.get("type") == "fabric" and loader_version:
            loader_text += f" {loader_version}"
        self.home_profile_name.configure(text=profile.get("name", "Unnamed profile"))
        self.home_profile_details.configure(
            text=f"Minecraft {profile.get('mc_version', '?')}  ·  {loader_text}"
        )
        self.home_status_badge.configure(
            text=install_state.upper(),
            fg_color=self.theme["ENABLED"] if installed else self.theme["NEUTRAL"],
        )
        self.home_profile_count.configure(text=count_text)
        if self.auth_mode_var.get().lower() == "microsoft":
            account = self._ms_account.get("name", "Signed out") if self._ms_account else "Signed out"
            self.home_account_label.configure(text=f"Microsoft account · {account}")
        else:
            username = self.username_var.get().strip()
            self.home_account_label.configure(text=f"Offline profile · {username or 'No username selected'}")
        self._refresh_home_skin()

    def _select_home_profile(self, name: str):
        for index, profile in enumerate(self.cfg.get("profiles", [])):
            if profile.get("name") == name:
                self._on_profile_selected(index)
                return

    def _load_account_cosmetics(self, username: str):
        """Return (skin image or None, slim flag, cape image or None, signature)."""
        if not username:
            return None, False, None, (username, None, None, None)
        skin = cape = None
        slim = False
        signature = [username]
        try:
            account_id = account_store.offline_uuid(username)
            folder = skin_store.account_cosmetic_dir(account_id)
        except (OSError, ValueError):
            return None, False, None, (username, None, None, None)
        for kind in ("skin", "cape"):
            path = folder / f"{kind}.png"
            try:
                if path.is_file() and not path.is_symlink():
                    stat = path.stat()
                    signature.append((stat.st_mtime_ns, stat.st_size))
                    with Image.open(path) as source:
                        image = source.convert("RGBA")
                    if kind == "skin":
                        skin = image
                    else:
                        cape = image
                else:
                    signature.append(None)
            except (OSError, ValueError):
                signature.append(None)
        try:
            account = next(
                (item for item in account_store.load_accounts()
                 if item.get("username") == username), None,
            )
            slim = bool(account and account.get("skin_model") == "slim")
        except (OSError, RuntimeError, ValueError):
            slim = False
        signature.append(slim)
        return skin, slim, cape, tuple(signature)

    def _refresh_home_skin(self, force: bool = False):
        if not hasattr(self, "stage") or not hasattr(self, "username_var"):
            return
        if self.auth_mode_var.get().lower() == "microsoft":
            name = self._ms_account.get("name", "") if self._ms_account else ""
            skin = cape = None
            slim = False
            signature = ("microsoft", name)
            empty = not name
        else:
            name = self.username_var.get().strip()
            skin, slim, cape, signature = self._load_account_cosmetics(name)
            empty = not name
        signature = (signature, empty, normalize_theme_name(self.cfg.get("theme")))
        if not force and getattr(self, "_home_skin_key", None) == signature:
            return
        self._home_skin_key = signature
        try:
            self.stage.set_player(name or "Player", skin, slim=slim, cape=cape, empty=empty)
        except (ValueError, OSError) as exc:
            self._log(f"Could not render the skin preview: {exc}")
            self.stage.set_player(name or "Player", None, slim=False, cape=None, empty=empty)

    def _on_edit_profile(self):
        profile = self._current_profile()
        if not profile:
            self._log("Select a profile before editing.")
            return

        self._open_profile_editor(profile)

    def _rename_profile(self, idx: int):
        profiles = self.cfg.get("profiles", [])
        if not 0 <= idx < len(profiles):
            return
        old_name = profiles[idx].get("name", "")
        name = simpledialog.askstring(
            "Rename profile", "Profile name:", initialvalue=old_name, parent=self
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror("Invalid profile name", "A profile name cannot be empty.", parent=self)
            return
        if any(i != idx and p.get("name") == name for i, p in enumerate(profiles)):
            messagebox.showerror("Duplicate profile name", "That profile name is already in use.", parent=self)
            return
        if self.cfg.get("active_profile") == old_name:
            self.cfg["active_profile"] = name
        profiles[idx]["name"] = name
        config.save(self.cfg)
        self._refresh_profile_list()

    def _duplicate_profile(self, idx: int):
        profiles = self.cfg.get("profiles", [])
        if not 0 <= idx < len(profiles):
            return
        source = profiles[idx]
        duplicate = copy.deepcopy(source)
        base_name = f"{source.get('name', 'Profile')} Copy"
        name = base_name
        suffix = 2
        used = {profile.get("name") for profile in profiles}
        while name in used:
            name = f"{base_name} {suffix}"
            suffix += 1
        duplicate["name"] = name
        duplicate["instance_id"] = uuid.uuid4().hex
        duplicate.pop("installed_content", None)
        duplicate.pop("launcher_mods_initialized", None)
        duplicate.pop("source_modpack", None)
        duplicate.pop("imported_modpack", None)
        try:
            profiles.append(duplicate)
            config.save(self.cfg)
        except OSError as exc:
            profiles.remove(duplicate)
            messagebox.showerror("Could not duplicate profile", str(exc), parent=self)
            return
        self._refresh_profile_list()
        self._log(f"Duplicated '{source.get('name', 'Profile')}' as an empty isolated profile.")

    def _on_new_profile(self):
        if not self.all_versions:
            self._log("⚠  Still loading versions, try again in a moment.")
            return
        existing_names = {p["name"] for p in self.cfg.get("profiles", [])}
        dlg = NewProfileDialog(self, self.all_versions, self.fabric_versions,
                               existing_profile_names=existing_names)
        profile = dlg.result
        if not profile:
            return
        if not profile.get("name"):
            self._log("⚠  Profile name cannot be empty.")
            return
        if (
            profile.get("type") == "fabric"
            and not profile.get("fabric_loader_version")
            and profile.get("mc_version") in self.latest_fabric_loader_versions
        ):
            profile["fabric_loader_version"] = self.latest_fabric_loader_versions[
                profile["mc_version"]
            ]
        if any(p["name"] == profile["name"] for p in self.cfg.get("profiles", [])):
            self._log(f"⚠  A profile named '{profile['name']}' already exists.")
            return
        profile.setdefault("instance_id", uuid.uuid4().hex)
        try:
            profile_store.initialize_profile(profile)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Could not create profile folder", str(exc), parent=self)
            return
        self.cfg.setdefault("profiles", []).append(profile)
        self.cfg["active_profile"] = profile["name"]
        try:
            config.save(self.cfg)
            profile_store.sync_profiles(self.cfg["profiles"])
            profile_store.save_manifest(profile)
        except OSError as exc:
            self.cfg["profiles"].remove(profile)
            profile_store_dir = modrinth.profile_instance_dir(profile)
            try:
                shutil.rmtree(profile_store_dir)
            except OSError as cleanup_error:
                messagebox.showerror(
                    "Could not save profile",
                    f"{exc}\nThe incomplete profile folder could not be removed: {cleanup_error}",
                    parent=self,
                )
            else:
                messagebox.showerror("Could not save profile", str(exc), parent=self)
            return
        self._refresh_profile_list()
        self._log(f"✅ Profile '{profile['name']}' created  ({profile['mc_version']}, {profile['type']}).")

    def _on_delete_profile(self, idx: int | None = None):
        profiles = self.cfg.get("profiles", [])
        index = self._selected_profile_idx if idx is None else idx
        if not 0 <= index < len(profiles):
            return
        profile = profiles[index]
        if not messagebox.askyesno(
            "Delete profile",
            f"Remove '{profile.get('name', 'Profile')}' from the launcher? "
            "You will choose whether to keep or delete its instance folder next.",
            parent=self,
        ):
            return
        delete_folder = messagebox.askyesno(
            "Delete profile folder",
            "Permanently delete this profile's isolated game directory, including worlds and settings?",
            parent=self,
        )
        try:
            instance = modrinth.profile_instance_dir(profile)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Could not delete profile", str(exc), parent=self)
            return
        previous_active = self.cfg.get("active_profile")
        profiles.pop(index)
        if previous_active == profile.get("name"):
            self.cfg["active_profile"] = profiles[0].get("name") if profiles else None
        self._selected_profile_idx = 0 if profiles else -1
        try:
            config.save(self.cfg)
        except OSError as exc:
            profiles.insert(index, profile)
            self._selected_profile_idx = index
            self.cfg["active_profile"] = previous_active
            messagebox.showerror("Could not delete profile", str(exc), parent=self)
            return
        try:
            profile_store.sync_profiles(self.cfg.get("profiles", []))
        except OSError as exc:
            messagebox.showerror(
                "Profile index not saved",
                f"The launcher config was updated, but profiles.json could not be written: {exc}",
                parent=self,
            )
        if delete_folder and instance.exists():
            try:
                instance_root = (Path.home() / ".revomc" / "instances").resolve()
                if not instance.resolve().is_relative_to(instance_root):
                    raise ValueError("Refusing to delete a directory outside profile instances.")
                shutil.rmtree(instance)
            except (OSError, ValueError) as exc:
                messagebox.showerror(
                    "Profile removed; folder retained",
                    f"The profile was removed from the launcher, but its folder could not be deleted:\n{instance}\n\n{exc}",
                    parent=self,
                )
        self._refresh_profile_list()
        self._log(
            f"Removed '{profile.get('name', 'Profile')}' from the launcher; "
            f"instance data {'was deleted' if delete_folder else 'was retained'}."
        )

    # ── Install & Play (unified) ───────────────────────────────────────────────

    def _is_installed_for_profile(self, profile: dict) -> bool:
        """Verify both recorded installation state and the required version files."""
        mc_version = profile.get("mc_version")
        profile_type = profile.get("type", "vanilla")
        if not isinstance(mc_version, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", mc_version
        ):
            return False
        installed_versions = self.cfg.get("installed_versions", {})
        entry = installed_versions.get(mc_version) if isinstance(installed_versions, dict) else None
        if not isinstance(entry, dict):
            return False
        if entry.get("type") != profile_type:
            return False
        versions = Path.home() / ".revomc" / "versions"
        vanilla = versions / mc_version
        if not (vanilla / f"{mc_version}.json").is_file() or not (vanilla / f"{mc_version}.jar").is_file():
            return False
        if profile_type == "vanilla":
            return True
        if profile_type != "fabric":
            return False
        fabric_profile_id = entry.get("fabric_profile_id")
        pinned_loader = profile.get("fabric_loader_version")
        latest_loader = getattr(self, "latest_fabric_loader_versions", {}).get(mc_version)
        expected_loader = (
            pinned_loader
            if profile.get("fabric_loader_pinned")
            or profile.get("source_modpack")
            or profile.get("imported_modpack")
            else latest_loader or pinned_loader
        )
        if expected_loader and fabric_profile_id != f"fabric-loader-{expected_loader}-{mc_version}":
            return False
        if not isinstance(fabric_profile_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", fabric_profile_id
        ):
            return False
        fabric_json = versions / fabric_profile_id / f"{fabric_profile_id}.json"
        return bool(
            fabric_json.is_file()
            and fabric_json.resolve().is_relative_to(versions.resolve())
        )

    def _migrate_shared_worlds(self, profile: dict) -> None:
        instance = modrinth.profile_instance_dir(profile)
        profile_saves = instance / "saves"
        if profile_saves.is_symlink() or not profile_saves.resolve().is_relative_to(instance.resolve()):
            raise OSError("The profile saves directory points outside the profile instance.")
        shared_saves = config.get_minecraft_dir() / "saves"
        if shared_saves.is_symlink() or not shared_saves.is_dir():
            return
        profile_saves.mkdir(parents=True, exist_ok=True)
        try:
            children = list(shared_saves.iterdir())
            for world in children:
                if world.is_symlink() or not world.is_dir():
                    continue
                target = profile_saves / world.name
                if target.exists():
                    continue

                def ignore_links(directory, names):
                    return [
                        name for name in names
                        if (Path(directory) / name).is_symlink()
                    ]

                shutil.copytree(world, target, ignore=ignore_links)
        except OSError as exc:
            self.after(
                0,
                lambda error=exc: self._log(
                    f"⚠ Could not copy an existing world into this profile: {error}"
                ),
            )

    def _prepare_offline_skin(self, profile, game_dir, username, identity):
        """Make the offline account's skin/cape visible in the game (best effort)."""
        def log(message):
            self.after(0, lambda msg=message: self._log(msg))

        try:
            folder = skin_store.account_cosmetic_dir(identity["id"])
            skin = folder / "skin.png"
            cape = folder / "cape.png"
            skin = skin if skin.is_file() else None
            cape = cape if cape.is_file() else None
            if skin is None and cape is None:
                client_mods.sync_local_skin(game_dir, username, None, None)
                return
            csl = {"slug": client_mods.CSL_SLUG, "title": "CustomSkinLoader"}
            if not client_mods.is_installed(profile, csl):
                log("Installing CustomSkinLoader so your skin shows in game…")
                _records, failures, _warnings = client_mods.install_entries(
                    profile, [csl], game_dir / "mods", log=log
                )
                if failures:
                    log("⚠ CustomSkinLoader: " + "; ".join(failures))
                else:
                    profile_store.save_manifest(profile)
                    config.save(self.cfg)
            done = client_mods.sync_local_skin(game_dir, username, skin, cape)
            if done:
                log(f"Offline {' + '.join(done)} prepared for in-game display.")
        except Exception as exc:  # never block launching over cosmetics
            log(f"⚠ Could not prepare offline skin: {exc}")

    def _on_play_btn(self):
        profile = self._current_profile()
        if not profile:
            return

        is_ms = self.auth_mode_var.get() == "Microsoft"
        auth_data = None

        if is_ms:
            if not self._ms_account:
                self._log("⚠  Please sign in with Microsoft before playing.")
                return
            username = self._ms_account["name"]
            auth_data = self._ms_account
        else:
            username = self.username_var.get().strip()
            if not username:
                self._log("⚠  Please enter a username before playing.")
                return
            try:
                offline_identity = {"id": account_store.offline_uuid(username)}
            except ValueError as exc:
                self._log(f"⚠  {exc}")
                return

        mc_version   = profile["mc_version"]
        profile_type = profile["type"]
        enabled_mods = profile.get("mods", [])
        try:
            ram_gb = max(1, min(int(profile.get("memory_gb") or self.ram_var.get()),
                                self.max_ram_gb))
        except (TypeError, ValueError):
            ram_gb = self.ram_var.get()
        use_dgpu     = self.cfg.get("use_dgpu", False)
        needs_install = not self._is_installed_for_profile(profile)
        needs_profile_mods = (
            profile_type == "fabric"
            and not profile.get("source_modpack")
            and not profile.get("launcher_mods_initialized")
        )
        profile_instance = modrinth.profile_instance_dir(profile)

        self._set_busy(True)
        self._log(f"\n{'─'*40}")
        if needs_install or needs_profile_mods:
            self._log(f"📦 Installing '{profile['name']}' ({mc_version}, {profile_type})…")
        else:
            self._log(f"🚀 Launching '{profile['name']}'…")

        def worker():
            try:
                fabric_profile_id = None
                self._migrate_shared_worlds(profile)
                if profile_type == "fabric":
                    disable_incompatible_mods(
                        profile_instance / "mods",
                        mc_version,
                        log=lambda message: self.after(
                            0, lambda msg=message: self._log(msg)
                        ),
                    )

                if needs_install:
                    from core.java_manager import install_java
                    java_ver = get_required_java_version(mc_version)
                    install_java(
                        java_ver,
                        log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
                        progress=lambda t, p: self.after(0, lambda tt=t, pp=p: self._on_progress(tt, pp)),
                    )
                    install_minecraft(
                        mc_version,
                        log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
                        progress=lambda t, p: self.after(0, lambda tt=t, pp=p: self._on_progress(tt, pp)),
                    )
                    if profile_type == "fabric":
                        fabric_profile_id = install_fabric(
                            mc_version,
                            log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
                            progress=lambda t, p: self.after(0, lambda tt=t, pp=p: self._on_progress(tt, pp)),
                            loader_version=(
                                profile.get("fabric_loader_version")
                                if profile.get("fabric_loader_pinned")
                                or profile.get("source_modpack")
                                or profile.get("imported_modpack")
                                else None
                            ),
                        )
                        profile["fabric_loader_version"] = fabric_profile_id.removeprefix(
                            "fabric-loader-"
                        ).removesuffix(f"-{mc_version}")
                    self.cfg.setdefault("installed_versions", {})[mc_version] = {
                        "fabric_profile_id": fabric_profile_id,
                        "type": profile_type,
                    }
                    config.save(self.cfg)
                    self.after(0, lambda: self._log("✅ Installation complete — launching…"))
                else:
                    fabric_profile_id = (
                        self.cfg.get("installed_versions", {})
                        .get(mc_version, {})
                        .get("fabric_profile_id")
                    )

                needs_fabric_api = (
                    profile_type == "fabric"
                    and not has_fabric_api(profile_instance / "mods")
                )
                if needs_profile_mods or needs_fabric_api:
                    install_mods(
                        mc_version, enabled_mods,
                        log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
                        progress=lambda t, p: self.after(0, lambda tt=t, pp=p: self._on_progress(tt, pp)),
                        mods_dir=profile_instance / "mods",
                        profile=profile,
                    )
                    if needs_profile_mods:
                        profile["launcher_mods_initialized"] = True
                    config.save(self.cfg)

                game_dir = profile_instance
                if profile_type == "fabric":
                    disable_incompatible_mods(
                        game_dir / "mods",
                        mc_version,
                        log=lambda message: self.after(
                            0, lambda msg=message: self._log(msg)
                        ),
                    )
                    if not has_fabric_api(game_dir / "mods"):
                        raise RuntimeError(
                            f"Fabric API could not be verified for Minecraft {mc_version}."
                        )

                if profile_type == "fabric" and not is_ms:
                    self._prepare_offline_skin(profile, game_dir, username, offline_identity)

                self.after(0, lambda: self._log("🚀 Starting game…"))
                proc = launch(
                    mc_version=mc_version,
                    profile_type=profile_type,
                    fabric_profile_id=fabric_profile_id,
                    username=username,
                    ram_gb=ram_gb,
                    log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
                    auth_data=auth_data,
                    use_dgpu=use_dgpu,
                    game_dir=game_dir,
                    offline_uuid=offline_identity["id"] if not is_ms else None,
                    java_args=profile.get("java_args", ""),
                    performance_boost=profile.get(
                        "performance_boost", profile_type == "fabric"
                    ),
                )
                self.after(0, lambda: self._log("🎮 Game launched!"))
                returncode = proc.wait()
                if returncode:
                    diagnostics = []

                    def add_tail(label, path, limit=40):
                        if path.is_file():
                            try:
                                lines = path.read_text(
                                    encoding="utf-8", errors="replace"
                                ).splitlines()
                            except OSError as exc:
                                diagnostics.append(f"Could not read {path}: {exc}")
                            else:
                                diagnostics.append(f"--- {label}: {path} ---")
                                diagnostics.extend(lines[-limit:])

                    game_log = game_dir / "logs" / "launcher-game.log"
                    add_tail("Last 40 lines of launcher-game.log", game_log)
                    add_tail("Last 40 lines of latest.log", game_dir / "logs" / "latest.log")
                    crash_reports = game_dir / "crash-reports"
                    if crash_reports.is_dir():
                        for report in sorted(crash_reports.glob("*.txt")):
                            add_tail("Crash report", report)
                    for fatal_log in sorted(game_dir.glob("hs_err_pid*.log")):
                        add_tail("JVM fatal error log", fatal_log)
                    if diagnostics:
                        self.after(
                            0,
                            lambda lines=diagnostics: [
                                self._log(line) for line in lines
                            ],
                        )
                    self.after(
                        0,
                        lambda code=returncode, path=game_log: self._on_worker_done(
                            False,
                            f"Minecraft exited unexpectedly (code {code}). "
                            f"Game output was saved to {path}.",
                        ),
                    )
                else:
                    self.after(
                        0,
                        lambda: self._on_worker_done(
                            True, f"Game exited normally (code {returncode})"
                        ),
                    )
            except Exception as e:
                self.after(0, lambda err=e: self._on_worker_done(False, str(err)))

        threading.Thread(target=worker, daemon=True).start()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_username_changed(self, *_):
        text = self.username_var.get()
        previous = self.cfg.get("username", "")
        self.cfg["username"] = text
        if text in self.cfg.get("offline_profiles", []):
            self.cfg["active_offline_profile"] = text
        try:
            config.save(self.cfg)
        except OSError as exc:
            self.cfg["username"] = previous
            messagebox.showerror("Could not save username", str(exc), parent=self)
            if self._username_trace_id:
                self.username_var.trace_remove("write", self._username_trace_id)
            self.username_var.set(previous)
            self._username_trace_id = self.username_var.trace_add(
                "write", self._on_username_changed
            )
            return
        self._update_home_profile(self._current_profile())
        self._refresh_buttons()

    def _on_ram_changed(self, val):
        gb = int(val)
        self.cfg["ram_gb"] = gb
        profile = self._current_profile()
        if profile:
            profile["memory_gb"] = gb
        try:
            config.save(self.cfg)
            if profile:
                profile_store.save_manifest(profile)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Could not save memory setting", str(exc), parent=self)
        self.ram_label_lbl.configure(text=f"Memory allocation · {gb} GB")

    def _refresh_buttons(self):
        profile     = self._current_profile()
        has_profile = profile is not None
        installed   = has_profile and self._is_installed_for_profile(profile)

        is_ms = self.auth_mode_var.get() == "Microsoft"
        if is_ms:
            has_identity = self._ms_account is not None
        else:
            has_identity = bool(self.username_var.get().strip())

        if not has_profile:
            btn_text  = "▶  PLAY"
            state_play = "disabled"
        elif not installed:
            btn_text  = "⬇  Install & Play"
            state_play = "normal" if has_identity else "disabled"
        else:
            btn_text  = "▶  PLAY"
            state_play = "normal" if has_identity else "disabled"

        self.play_btn.configure(text=btn_text, state=state_play)
        if hasattr(self, "home_account_label"):
            self._update_home_profile(profile)

    def _on_progress(self, task: str, pct: int):
        if not self._busy:
            self.progress_bar.set(pct / 100)
        self.status_lbl.configure(text=f"{task}: {pct}%")

    def _on_worker_done(self, success: bool, message: str):
        self._set_busy(False)
        self.progress_bar.stop()
        self.progress_bar.set(1.0 if success else 0.0)
        self._log(f"{'✅' if success else '❌'} {message}")
        self.status_lbl.configure(
            text="Ready." if success else message,
            text_color=TEXT_MUTED if success else self.theme["RED"],
        )
        self._refresh_profile_list()
        self._refresh_buttons()

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.play_btn.configure(state=state)
        self.new_btn.configure(state=state)
        if busy:
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self._refresh_buttons()  # restore correct label after busy clears

    def _log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    # ── Settings & Theme ──────────────────────────────────────────────────────

    def _on_open_settings(self):
        self._show_page("settings")

    def _update_module_tokens(self, theme: dict):
        names = {
            "BG_PRIMARY": "BG_PRIMARY", "BG_SECONDARY": "BG_SECONDARY",
            "BG_CONSOLE": "BG_CONSOLE", "BG_CARD": "BG_CARD",
            "BORDER_COL": "BORDER_COL", "GREEN": "ACCENT",
            "GREEN_DARK": "ACCENT_DARK", "BLUE": "ACCENT_ALT", "RED": "RED",
            "MS_BLUE": "MS_BLUE", "MS_BLUE_DARK": "MS_BLUE_DARK",
            "TEXT_FG": "TEXT_FG", "TEXT_MUTED": "TEXT_MUTED",
            "TEXT_LABEL": "TEXT_LABEL", "ACCENT_TEXT": "ACCENT_TEXT",
        }
        module_globals = globals()
        for name, key in names.items():
            module_globals[name] = theme[key]

    def _switch_theme(self, name: str):
        """Switch between the light and dark theme live, without a restart."""
        name = normalize_theme_name(name)
        old = dict(self.theme)
        new = get_theme(name)
        self.cfg["theme"] = name
        try:
            config.save(self.cfg)
        except OSError as exc:
            self._log(f"Could not save the theme: {exc}")
        if old == new:
            return
        mapping = color_map(old, new)
        self.motion.cancel_all()
        self.theme.clear()           # in place: every page shares this dict
        self.theme.update(new)
        apply_customtkinter_palette(new)
        self._update_module_tokens(new)
        retheme_widget_tree(self, mapping)
        self.configure(fg_color=new["BG_PRIMARY"])
        self._render_background()
        self.stage.apply_theme(new)
        self._home_skin_key = None
        self._refresh_home_skin(force=True)
        self._set_active_navigation(self._current_page)
        self._refresh_profile_list()

    # ── Microsoft Auth UI ─────────────────────────────────────────────────────

    def _on_auth_mode_changed(self, value: str):
        # Always store lowercase so _try_restore_session comparison is consistent
        mode = value.lower()
        self.cfg["auth_mode"] = mode
        config.save(self.cfg)
        self._refresh_auth_panel()
        self._refresh_buttons()

    def _refresh_auth_panel(self):
        is_ms = self.auth_mode_var.get().lower() == "microsoft"
        if is_ms:
            self.offline_panel.pack_forget()
            self.ms_panel.pack(anchor="e")
            self._refresh_ms_state()
        else:
            self.ms_panel.pack_forget()
            self.offline_panel.pack(anchor="e")

    def _refresh_ms_state(self):
        if self._ms_account:
            self.ms_signin_btn.pack_forget()
            self.ms_loggedin_frame.pack(anchor="e")
            self.ms_gamertag_lbl.configure(text=f"🟢  {self._ms_account['name']}")
        else:
            self.ms_loggedin_frame.pack_forget()
            self.ms_signin_btn.pack(anchor="e")
            self.ms_signin_btn.configure(text="  Sign in with Microsoft", state="normal")

    def _on_ms_signin(self):
        self.ms_signin_btn.configure(text="  Waiting for browser…", state="disabled")
        self._log(f"\n{'─'*40}")

        def on_success(login_data: dict):
            def _update():
                self._ms_account = login_data
                self._refresh_auth_panel()
                self._refresh_buttons()
            self.after(0, _update)

        def on_error(message: str):
            def _update():
                self._log(f"❌ {message}")
                self._refresh_ms_state()
                self._refresh_buttons()
            self.after(0, _update)

        auth.start_login(
            log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
            on_success=on_success,
            on_error=on_error,
        )

    def _on_ms_signout(self):
        auth.logout(log=self._log)
        self._ms_account = None
        self._refresh_auth_panel()
        self._refresh_buttons()

    def _try_restore_session(self):
        # Normalize stored auth_mode — could be "microsoft" or "Microsoft"
        # depending on whether it was saved by the toggle or by _save_account()
        stored_mode = self.cfg.get("auth_mode", "offline").lower()
        if stored_mode != "microsoft":
            return
        account = auth.get_stored_account()
        if not account:
            # auth_mode says microsoft but no account stored — reset to offline
            self.cfg["auth_mode"] = "offline"
            config.save(self.cfg)
            self.after(0, lambda: self.auth_mode_var.set("Offline"))
            self.after(0, self._refresh_auth_panel)
            return

        def _task():
            refreshed = auth.try_refresh(
                log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
            )
            if refreshed:
                def _update():
                    self._ms_account = refreshed
                    self._refresh_auth_panel()
                    self._refresh_buttons()
                self.after(0, _update)
            else:
                # Refresh failed — reset auth_mode to offline so the UI
                # is consistent and the user knows they need to sign in again
                def _update():
                    self.cfg["auth_mode"] = "offline"
                    config.save(self.cfg)
                    self.auth_mode_var.set("Offline")
                    self._refresh_auth_panel()
                    self._refresh_buttons()
                self.after(0, _update)

        threading.Thread(target=_task, daemon=True).start()
