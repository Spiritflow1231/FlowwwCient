"""
ui/main_window.py  –  CustomTkinter UI for FlowwwClient
All program logic is identical to the original PyQt6 version.
"""
import json
import urllib.parse
import urllib.request
import webbrowser
import os
import platform
import ctypes
import shutil
import struct
import subprocess
import threading
import tempfile
import time
import uuid
from pathlib import Path
import customtkinter as ctk
from tkinter import TclError, messagebox

import core.config as config
import core.auth as auth
import core.modrinth as modrinth
from ui.theme import get_theme
from core.installer import (
    fetch_release_versions,
    fetch_fabric_versions,
    install_minecraft,
    install_fabric,
    install_mods,
    AVAILABLE_MODS,
)
from core.launcher import launch
from core.java_manager import get_required_java_version

# ── Appearance ────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Colour tokens — loaded from the active theme at module level (defaults).
# MainWindow.__init__ reloads from config and _apply_theme() updates live.
_t = get_theme(config.load().get("theme", "overworld"))
BG_PRIMARY   = _t["BG_PRIMARY"]
BG_SECONDARY = _t["BG_SECONDARY"]
BG_CONSOLE   = _t["BG_CONSOLE"]
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


class ProfileEditorWindow(ctk.CTkToplevel):
    """Profile-specific content manager for FlowwwClient."""

    CATEGORIES = [
        ("Mods", "mods"),
        ("Resource Packs", "resourcepacks"),
        ("Modpacks", "modpacks"),
        ("Datapacks", "datapacks"),
        ("Shader Packs", "shaderpacks"),
    ]

    def __init__(self, parent, profile, initial_category="mods"):
        super().__init__(parent)

        self.parent = parent
        self.profile = profile
        self.theme = parent.theme
        categories = {key for _, key in self.CATEGORIES}
        self.category = initial_category if initial_category in categories else "mods"
        self.tab = "Installed"
        self._working = False
        self._cancel_event = None
        self._request_serial = 0

        self.title(f"Edit Profile — {profile.get('name', 'Profile')}")
        self.geometry("1000x650")
        self.minsize(800, 520)
        self.configure(fg_color=self.theme["BG_PRIMARY"])
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 12))

        ctk.CTkLabel(
            header,
            text=self.profile.get("name", "Profile"),
            text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=23, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=f"Minecraft {self.profile.get('mc_version', '?')}  ·  "
                 f"{self.profile.get('type', 'vanilla').title()}",
            text_color=self.theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=12),
        ).pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Left category sidebar
        sidebar = ctk.CTkFrame(
            body,
            width=185,
            fg_color=self.theme["BG_SECONDARY"],
            corner_radius=12,
            border_width=1,
            border_color=self.theme["BORDER_COL"],
        )
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar,
            text="PROFILE CONTENTS",
            text_color=self.theme["TEXT_MUTED"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(18, 12))

        self.category_buttons = {}

        for label, key in self.CATEGORIES:
            button = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                height=38,
                corner_radius=8,
                fg_color=self.theme["ACCENT"] if key == self.category else "transparent",
                text_color=self.theme["BG_PRIMARY"] if key == self.category else self.theme["TEXT_FG"],
                hover_color=self.theme["ACCENT_DARK"],
                command=lambda k=key: self._select_category(k),
            )
            button.pack(fill="x", padx=9, pady=3)
            self.category_buttons[key] = button

        # Right content panel
        self.content = ctk.CTkFrame(
            body,
            fg_color=self.theme["BG_SECONDARY"],
            corner_radius=12,
            border_width=1,
            border_color=self.theme["BORDER_COL"],
        )
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(4, weight=1)

        self.heading = ctk.CTkLabel(
            self.content,
            text="Mods",
            text_color=self.theme["TEXT_FG"],
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.heading.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 12))

        search_row = ctk.CTkFrame(self.content, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        search_row.grid_columnconfigure(0, weight=1)
        self.search = ctk.CTkEntry(
            search_row,
            placeholder_text="Search Modrinth projects...",
            height=38,
            border_color=self.theme["BORDER_COL"],
            fg_color=self.theme["BG_PRIMARY"],
        )
        self.search.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search.bind("<Return>", lambda _event: self._on_search())
        self.search_button = ctk.CTkButton(
            search_row,
            text="Search",
            width=82,
            height=38,
            fg_color=self.theme["ACCENT"],
            text_color=self.theme["BG_PRIMARY"],
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
        tabs.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 10))

        self.installed_btn = ctk.CTkButton(
            tabs,
            text="Installed",
            width=100,
            fg_color=self.theme["ACCENT"],
            text_color=self.theme["BG_PRIMARY"],
            command=lambda: self._select_tab("Installed"),
        )
        self.installed_btn.pack(side="left", padx=(0, 8))

        self.browse_btn = ctk.CTkButton(
            tabs,
            text="Browse",
            width=100,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=lambda: self._select_tab("Browse"),
        )
        self.browse_btn.pack(side="left")

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
        self.cancel_btn.grid(row=0, column=1, padx=(8, 0))

        self._refresh_content()

    def _select_category(self, category):
        self.category = category

        for key, button in self.category_buttons.items():
            active = key == category
            button.configure(
                fg_color=self.theme["ACCENT"] if active else "transparent",
                text_color=self.theme["BG_PRIMARY"] if active else self.theme["TEXT_FG"],
            )

        self._refresh_content()

    def _select_tab(self, tab):
        self.tab = tab

        self.installed_btn.configure(
            fg_color=self.theme["ACCENT"] if tab == "Installed" else "transparent",
            text_color=self.theme["BG_PRIMARY"] if tab == "Installed" else self.theme["TEXT_FG"],
        )
        self.browse_btn.configure(
            fg_color=self.theme["ACCENT"] if tab == "Browse" else "transparent",
            text_color=self.theme["BG_PRIMARY"] if tab == "Browse" else self.theme["TEXT_FG"],
        )

        self._refresh_content()

    def _on_search(self):
        self.tab = "Browse"
        self.installed_btn.configure(
            fg_color="transparent",
            text_color=self.theme["TEXT_FG"],
        )
        self.browse_btn.configure(
            fg_color=self.theme["ACCENT"],
            text_color=self.theme["BG_PRIMARY"],
        )
        self._search_projects()

    def _refresh_content(self):
        self._request_serial += 1
        labels = dict(self.CATEGORIES)
        self.heading.configure(text=labels[self.category])
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

    def _clear_results(self):
        for widget in self.results.winfo_children():
            widget.destroy()

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
                and isinstance(profile.get("source_modpack"), dict)
                and profile["source_modpack"].get("project_id")
                and (
                    not query
                    or query in str(profile.get("name", "")).casefold()
                    or query in str(profile["source_modpack"].get("title", "")).casefold()
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
        known = {record.get("filename") for record in records}
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
        return card

    def _render_installed_file(self, path: Path):
        card = self._card(path.name)
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
        button.grid(row=0, column=1, rowspan=2, padx=12, pady=10)

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
                text_color=self.theme["BG_PRIMARY"] if enabled else self.theme["TEXT_FG"],
                hover_color=self.theme["ACCENT_DARK"],
                command=lambda r=record: self._toggle_mod(r),
            )
            toggle.grid(row=0, column=column, rowspan=2, padx=(0, 8), pady=10)
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
        source = profile.get("source_modpack", {})
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
            text_color=self.theme["BG_PRIMARY"],
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
        title = project.get("title") or project.get("slug") or "Untitled project"
        description = project.get("description") or "No description provided."
        author = project.get("author") or "Unknown author"
        details = f"by {author}  ·  Supports MC {self.profile.get('mc_version', '?')}"
        if project.get("downloads") is not None:
            details += f"  ·  {project['downloads']:,} downloads"
        card = self._card(title, f"{details}\n{description}")
        project_id = project.get("project_id")
        installed = self._project_installed(project_id)
        can_install = self._can_install_category()
        if installed:
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
            text_color=self.theme["BG_PRIMARY"] if state == "normal" else self.theme["TEXT_MUTED"],
            hover_color=self.theme["ACCENT_DARK"],
            command=lambda p=project: self._install_project(p),
        )
        button.grid(row=0, column=1, rowspan=2, padx=12, pady=10)

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
        installed_content = self.profile.get("installed_content", {})
        records = installed_content.get(self.category, []) if isinstance(installed_content, dict) else []
        return any(
            isinstance(record, dict) and record.get("project_id") == project_id
            for record in records
        )

    def _search_projects(self):
        if self.category == "mods" and self.profile.get("type") != "fabric":
            self._show_state("Mods require Fabric in this launcher. Create or select a Fabric profile first.")
            return
        query = self.search.get().strip()
        self._request_serial += 1
        serial = self._request_serial
        category = self.category
        self._show_state("Searching Modrinth…")

        def worker():
            try:
                projects = modrinth.search_projects(
                    category,
                    query,
                    self.profile.get("mc_version", ""),
                    self.profile.get("type", "vanilla"),
                )
                result = (projects, None)
            except Exception as exc:
                result = (None, str(exc))

            def update():
                if not self.winfo_exists() or serial != self._request_serial:
                    return
                self._clear_results()
                projects, error = result
                if error:
                    self._show_state(f"Could not search Modrinth: {error}")
                elif not projects:
                    self._show_state("No compatible projects were found. Try another search.")
                else:
                    for project in projects:
                        self._render_project(project)

            self._post(update)

        threading.Thread(target=worker, daemon=True).start()

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
            self._show_state("Modrinth returned a project without a valid ID.")
            return
        self._working = True
        self._cancel_event = threading.Event()
        self._clear_results()
        self._show_state("Finding a compatible release…")
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
            self._show_state(str(exc))
            return
        if not destination.resolve().is_relative_to(self._instance_dir().resolve()):
            self._working = False
            self._set_manager_busy(False)
            self._show_state("The selected installation directory is outside this profile.")
            return
        if self.category != "modpacks":
            try:
                destination.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._working = False
                self._set_manager_busy(False)
                self._show_state(f"Could not prepare the install directory: {exc}")
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
                else:
                    installed = modrinth.download_project_file(
                        versions[0], category, destination,
                        cancel_event=cancel_event,
                        progress=progress,
                    )
                    record = {
                        "project_id": project_id,
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

    def _finish_file_install(self, record: dict, world: str | None):
        if world:
            record["world"] = world
        records = self.profile.setdefault("installed_content", {}).setdefault(self.category, [])
        records.append(record)
        try:
            config.save(self.parent.cfg)
        except OSError as exc:
            records.remove(record)
            self._finish_install_error(f"Downloaded, but could not save profile settings: {exc}")
            return
        self._finish_install(f"Installed {record['title']} ({record['filename']}).")

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
        self._refresh_content()

    def _finish_install_error(self, message: str):
        self._working = False
        self._cancel_event = None
        self.cancel_btn.configure(state="disabled")
        self._set_manager_busy(False)
        self.status.configure(text=message)
        self._refresh_content()

    def _set_manager_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.search.configure(state=state)
        self.search_button.configure(state=state)
        self.installed_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        self.world_menu.configure(state=state)
        for button in self.category_buttons.values():
            button.configure(state=state)

    def _set_status(self, message: str):
        if self.winfo_exists():
            self.status.configure(text=message)

    def _post(self, callback):
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except TclError:
            pass

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
            if path.is_file():
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
        if Path(filename).name != filename or not filename.endswith(".jar"):
            messagebox.showerror("Invalid mod file", "The installed mod has an invalid filename.", parent=self)
            return
        mods_dir = self._instance_dir() / "mods"
        original = mods_dir / filename
        disabled = mods_dir / f"{filename}.disabled"
        try:
            if original.is_file():
                if disabled.exists():
                    raise FileExistsError(f"{disabled.name} already exists.")
                original.rename(disabled)
                record["enabled"] = False
            elif disabled.is_file():
                if original.exists():
                    raise FileExistsError(f"{original.name} already exists.")
                disabled.rename(original)
                record["enabled"] = True
            else:
                raise FileNotFoundError("The installed mod file is missing.")
            config.save(self.parent.cfg)
            self._refresh_content()
        except (OSError, ValueError) as exc:
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
            if instance.exists():
                shutil.rmtree(instance)
            self.parent.cfg["profiles"].remove(profile)
            if self.parent.cfg.get("active_profile") == profile.get("name"):
                self.parent.cfg["active_profile"] = None
            config.save(self.parent.cfg)
            self.parent._refresh_profile_list()
            self._refresh_content()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not remove modpack", str(exc), parent=self)

    def _on_close(self):
        if self._working:
            self._cancel_install()
            return
        self._request_serial += 1
        self.destroy()
# ── New Profile Dialog ─────────────────────────────────────────────────────────

class NewProfileDialog(ctk.CTkToplevel):
    """Modal dialog for creating a new profile.  Mirrors the original QDialog."""

    def __init__(self, parent, all_versions: list[str], fabric_versions: list[str],
                 existing_profile_names: set[str] | None = None):
        super().__init__(parent)
        self.all_versions    = all_versions
        self.fabric_versions = fabric_versions
        self._existing_profile_names = existing_profile_names or set()
        self.result: dict | None = None

        self.title("New Profile")
        self.geometry("460x600")
        self.resizable(False, True)
        self.minsize(460, 480)
        # Make modal
        self.transient(parent)

        self._build()
        self.update_idletasks()
        self.after(200, self.grab_set)
        self.wait_window(self)  # blocks until dialog closes

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
        ctk.CTkButton(btn_row, text="Create", fg_color=GREEN, text_color=BG_PRIMARY,
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

        # Profile type
        _section_label(body, "Profile Type").pack(anchor="w", padx=20, pady=(10, 0))
        type_row = ctk.CTkFrame(body, fg_color="transparent")
        type_row.pack(anchor="w", padx=20, pady=(4, 0))
        self.type_var = ctk.StringVar(value="fabric")
        ctk.CTkRadioButton(
            type_row, text="Fabric + Mods",
            variable=self.type_var, value="fabric",
            command=self._on_type_changed,
        ).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(
            type_row, text="Vanilla",
            variable=self.type_var, value="vanilla",
            command=self._on_type_changed,
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
                btn.configure(fg_color=GREEN, text_color=BG_PRIMARY)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_FG)

    def _on_ok(self):
        if not self._selected_version:
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
        }
        self.destroy()


# ── Settings Dialog ────────────────────────────────────────────────────────────

class SettingsDialog(ctk.CTkToplevel):
    """Modal dialog for launcher settings (theme, dGPU, etc.)."""

    def __init__(self, parent, theme: dict, cfg: dict):
        super().__init__(parent)
        self.theme = theme
        self.cfg = cfg
        self.result = False  # True if theme changed

        self.title("Settings")
        self.geometry("400x320")
        self.resizable(False, False)
        self.transient(parent)

        self._build()
        self.update_idletasks()
        self.after(200, self.grab_set)
        self.wait_window(self)

    def _build(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        _section_label(body, "Theme").pack(anchor="w", pady=(0, 10))
        self.theme_var = ctk.StringVar(value=self.cfg.get("theme", "overworld"))

        themes_frame = ctk.CTkFrame(body, fg_color="transparent")
        themes_frame.pack(fill="x", pady=(0, 20))

        for t_val, t_name, t_icon in [("overworld", "Overworld", "🌲"), ("nether", "Nether", "🔥"), ("end", "End", "🌌")]:
            ctk.CTkRadioButton(
                themes_frame, text=f"{t_icon} {t_name}",
                variable=self.theme_var, value=t_val,
                text_color=self.theme["TEXT_FG"],
                fg_color=self.theme["ACCENT"],
                hover_color=self.theme["ACCENT_DARK"],
            ).pack(side="left", padx=(0, 15))

        _section_label(body, "Performance").pack(anchor="w", pady=(0, 10))
        self.dgpu_var = ctk.BooleanVar(value=self.cfg.get("use_dgpu", False))
        ctk.CTkCheckBox(
            body, text="Run on Discrete GPU (NVIDIA/AMD)  —  Linux & Windows",
            variable=self.dgpu_var,
            text_color=self.theme["TEXT_FG"],
            hover_color=self.theme["ACCENT_DARK"],
            fg_color=self.theme["ACCENT"],
        ).pack(anchor="w")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=20, pady=12)
        ctk.CTkButton(
            btn_row, text="Cancel", fg_color="transparent",
            border_width=1, border_color=self.theme["BORDER_COL"],
            text_color=self.theme["TEXT_FG"],
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btn_row, text="Save", fg_color=self.theme["ACCENT"],
            text_color=self.theme["BG_PRIMARY"],
            hover_color=self.theme["ACCENT_DARK"],
            command=self._on_save,
        ).pack(side="right")

    def _on_save(self):
        old_theme = self.cfg.get("theme", "overworld")
        new_theme = self.theme_var.get()
        self.cfg["theme"] = new_theme
        self.cfg["use_dgpu"] = self.dgpu_var.get()
        config.save(self.cfg)
        if old_theme != new_theme:
            self.result = True
        self.destroy()


class AccountsWindow(ctk.CTkToplevel):
    """Account controls backed by the launcher's existing auth implementation."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.theme = parent.theme
        self.title("Accounts — FlowwwClient")
        self.geometry("500x390")
        self.minsize(420, 340)
        self.configure(fg_color=self.theme["BG_PRIMARY"])
        self.transient(parent)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=26, pady=24)
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
            selected_color=self.theme["ACCENT"],
            selected_hover_color=self.theme["ACCENT_DARK"],
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
        self._refresh_status()

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
        self.theme            = get_theme(self.cfg.get("theme", "overworld"))
        self.all_versions: list[str]    = []
        self.fabric_versions: list[str] = []
        self._busy            = False
        self._selected_profile_idx: int = -1
        self._ms_account: dict | None = None

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
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.configure(fg_color=BG_PRIMARY)

        # Root vstack
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=0, pady=0)

        # Left navigation sidebar
        sidebar = ctk.CTkFrame(
            root, width=190, fg_color=BG_SECONDARY, corner_radius=0
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        wordmark = ctk.CTkFrame(sidebar, fg_color="transparent")
        wordmark.pack(anchor="w", padx=18, pady=(24, 2))
        ctk.CTkLabel(
            wordmark,
            text="ঌ",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=self.theme["ACCENT"],
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            wordmark,
            text="FlowwwClient",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.theme["TEXT_FG"],
        ).pack(side="left")

        ctk.CTkLabel(
            sidebar,
            text="MINECRAFT CLIENT",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=21, pady=(0, 30))

        ctk.CTkLabel(
            sidebar,
            text="WORKSPACE",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        main_area = ctk.CTkFrame(root, fg_color="transparent")
        main_area.pack(
            side="left", fill="both", expand=True, padx=28, pady=24
        )
        self.nav_buttons = {}

        def nav_button(key, label, command):
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                height=44,
                corner_radius=10,
                fg_color="transparent",
                hover_color=BG_PRIMARY,
                text_color=TEXT_FG,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=command,
            )
            btn.pack(fill="x", padx=12, pady=4)
            self.nav_buttons[key] = btn

        nav_button("home", "⌂   Home", lambda: self._show_page("home"))
        nav_button("profiles", "▤   Profiles / Instances",
                   lambda: self._show_page("profiles"))
        nav_button("mods", "▧   Mods",
                   lambda: self._open_profile_content("mods"))
        nav_button("modpacks", "▣   Modpacks",
                   lambda: self._open_profile_content("modpacks"))
        nav_button("resourcepacks", "▤   Resource Packs",
                   lambda: self._open_profile_content("resourcepacks"))
        nav_button("shaders", "◈   Shaders",
                   lambda: self._open_profile_content("shaderpacks"))
        nav_button("accounts", "◉   Accounts", self._open_accounts)
        nav_button("settings", "⚙   Settings", self._open_settings_page)
        nav_button("console", "⌘   Console / Logs",
                   lambda: self._show_page("console"))


        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(main_area, fg_color="transparent")
        header.pack(fill="x", pady=(0, 18))

        # Title block
        self.title_lbl = ctk.CTkLabel(
            header, text="ঌ  FlowwwClient",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self.theme["ACCENT"],
        )
        self.title_lbl.pack(side="left", anchor="s")
        ctk.CTkLabel(
            header,
            text="   Fabric enabled, performance optimised launcher for Minecraft",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_LABEL,
        ).pack(side="left", anchor="s", pady=(0, 3))

        # Auth block (right side)
        auth_block = ctk.CTkFrame(header, fg_color="transparent")
        auth_block.pack(side="right", anchor="s")

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
            selected_color=GREEN,
            selected_hover_color=GREEN_DARK,
            unselected_color=BG_SECONDARY,
            unselected_hover_color="#1e293b",
        )
        self.auth_mode_menu.pack(side="left")
        self.auth_mode_var.set(self.cfg.get("auth_mode", "offline").title())

        # Offline panel: username entry
        self.offline_panel = ctk.CTkFrame(auth_block, fg_color="transparent")
        self.username_var = ctk.StringVar(value=self.cfg.get("username", ""))
        self.username_var.trace_add("write", self._on_username_changed)
        ctk.CTkEntry(
            self.offline_panel, textvariable=self.username_var,
            placeholder_text="Enter username…", width=220,
        ).pack(side="left")

        # Microsoft panel: sign-in button / account label
        self.ms_panel = ctk.CTkFrame(auth_block, fg_color="transparent")
        self.ms_signin_btn = ctk.CTkButton(
            self.ms_panel, text="  Sign in with Microsoft",
            fg_color=MS_BLUE, hover_color=MS_BLUE_DARK,
            text_color="#ffffff",
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

        # Divider
        ctk.CTkFrame(main_area, height=1, fg_color=BORDER_COL).pack(fill="x", pady=(0, 14))

        # ── Content (left + right columns) ────────────────────────────────────
        content = ctk.CTkFrame(main_area, fg_color="transparent")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._build_left(content)
        self._build_right(content)
        self._show_page("home")

    def _show_page(self, page):
        if not hasattr(self, "left_panel") or not hasattr(self, "right_panel"):
            return

        content = self.left_panel.master

        self.left_panel.grid_forget()
        self.right_panel.grid_forget()

        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)

        if page in ("home", "dashboard"):
            self.left_panel.grid(
                row=0, column=0, sticky="nsew", padx=(0, 8)
            )
            self.right_panel.grid(
                row=0, column=1, sticky="nsew", padx=(8, 0)
            )

        elif page == "profiles":
            content.columnconfigure(1, weight=0)
            self.left_panel.grid(
                row=0, column=0, columnspan=2, sticky="nsew"
            )

        elif page == "console":
            content.columnconfigure(1, weight=0)
            self.right_panel.grid(
                row=0, column=0, columnspan=2, sticky="nsew"
            )

        self._set_active_navigation("home" if page == "dashboard" else page)

    def _set_active_navigation(self, page):
        for key, button in self.nav_buttons.items():
            active = key == page
            button.configure(
                fg_color=self.theme["ACCENT"] if active else "transparent",
                hover_color=self.theme["ACCENT_DARK"] if active else self.theme["BG_PRIMARY"],
                text_color=self.theme["BG_PRIMARY"] if active else self.theme["TEXT_FG"],
            )

    def _open_profile_content(self, category):
        profile = self._current_profile()
        self._set_active_navigation({
            "mods": "mods",
            "modpacks": "modpacks",
            "resourcepacks": "resourcepacks",
            "shaderpacks": "shaders",
        }[category])
        if not profile:
            messagebox.showinfo(
                "Select a profile",
                "Create or select a profile before managing its content.",
                parent=self,
            )
            return
        ProfileEditorWindow(self, profile, initial_category=category)

    def _open_accounts(self):
        self._set_active_navigation("accounts")
        AccountsWindow(self)

    def _open_settings_page(self):
        self._set_active_navigation("settings")
        self._on_open_settings()

    def _build_left(self, parent):
        left = ctk.CTkFrame(parent, fg_color="transparent")
        self.left_panel = left
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)

        # Profile header row
        ph = ctk.CTkFrame(left, fg_color="transparent")
        ph.pack(fill="x", pady=(0, 6))
        _section_label(ph, "Profiles").pack(side="left")
        self.settings_btn = ctk.CTkButton(
            ph, text="⚙ Settings", width=90,
            fg_color="transparent", border_width=1, border_color=TEXT_MUTED,
            text_color=TEXT_MUTED, hover_color=BG_SECONDARY,
            command=self._on_open_settings,
        )
        self.settings_btn.pack(side="right", padx=(6, 0))

        self.edit_btn = ctk.CTkButton(
            ph,
            text="Edit",
            width=58,
            fg_color=BG_SECONDARY,
            border_width=1,
            border_color=BLUE,
            text_color=BLUE,
            hover_color=BG_PRIMARY,
            command=self._on_edit_profile,
        )
        self.edit_btn.pack(side="right", padx=(6, 0))
        self.del_btn = ctk.CTkButton(
            ph, text="Delete", width=72,
            fg_color="transparent", border_width=1, border_color=RED,
            text_color=RED, hover_color=RED,
            command=self._on_delete_profile,
        )
        self.del_btn.pack(side="right", padx=(6, 0))
        self.new_btn = ctk.CTkButton(
            ph, text="+ New", width=72,
            fg_color="transparent", border_width=1, border_color=BLUE,
            text_color=BLUE, hover_color=BLUE,
            command=self._on_new_profile,
        )
        self.new_btn.pack(side="right")

        # Profile list (scrollable frame with radio-style selection)
        self.profile_list_frame = ctk.CTkScrollableFrame(
            left, label_text="", fg_color=BG_SECONDARY,
            border_color=BORDER_COL, border_width=1, corner_radius=12,
        )
        self.profile_list_frame.pack(fill="both", expand=True, pady=(0, 8))

        # Info card
        self.info_card = ctk.CTkFrame(
            left, fg_color=BG_SECONDARY,
            border_color=BORDER_COL, border_width=1, corner_radius=12,
        )
        self.info_card.pack(fill="x", pady=(0, 8))
        self.info_version_lbl = ctk.CTkLabel(
            self.info_card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
        )
        self.info_version_lbl.pack(anchor="w", padx=12, pady=(8, 0))
        self.info_mods_lbl = ctk.CTkLabel(
            self.info_card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            wraplength=380, justify="left",
        )
        self.info_mods_lbl.pack(anchor="w", padx=12, pady=(2, 8))

        # RAM slider
        ram_row = ctk.CTkFrame(left, fg_color="transparent")
        ram_row.pack(fill="x", pady=(0, 4))
        self.ram_label_lbl = _section_label(ram_row, f"RAM — {self.cfg.get('ram_gb', 2)} GB")
        self.ram_label_lbl.pack(side="left")
        system_ram = _get_system_ram_gb()
        self.ram_var = ctk.IntVar(value=self.cfg.get("ram_gb", 2))
        self.ram_slider = ctk.CTkSlider(
            left, from_=1, to=system_ram, number_of_steps=max(1, system_ram - 1),
            variable=self.ram_var, command=self._on_ram_changed,
            progress_color=GREEN, fg_color=BG_SECONDARY,
            button_color=GREEN, button_hover_color=GREEN_DARK,
        )
        self.ram_slider.pack(fill="x", pady=(0, 10))

        # Single smart Play / Install & Play button
        self.play_btn = ctk.CTkButton(
            left, text="▶  PLAY NOW",
            corner_radius=12,
            fg_color=GREEN, text_color=BG_PRIMARY,
            hover_color=GREEN_DARK, font=ctk.CTkFont(size=15, weight="bold"),
            height=48, command=self._on_play_btn,
        )
        self.play_btn.pack(fill="x")

        self._profile_buttons: list[ctk.CTkFrame] = []
        self._refresh_profile_list()

    def _build_right(self, parent):
        right = ctk.CTkFrame(parent, fg_color="transparent")
        self.right_panel = right
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.rowconfigure(1, weight=1)

        # Console header
        header = ctk.CTkFrame(right, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        _section_label(header, "Game Console").pack(side="left")

        self.console_status = ctk.CTkLabel(
            header,
            text="● READY",
            text_color=GREEN,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.console_status.pack(side="right")

        # Log output card
        self.log_box = ctk.CTkTextbox(
            right,
            state="disabled",
            fg_color=BG_CONSOLE,
            border_color=BORDER_COL,
            border_width=1,
            corner_radius=12,
            font=ctk.CTkFont(family="monospace", size=11),
            text_color="#a0aec0",
        )
        self.log_box.pack(fill="both", expand=True, pady=(0, 12))

        # Launch progress
        progress_header = ctk.CTkFrame(right, fg_color="transparent")
        progress_header.pack(fill="x", pady=(0, 6))

        _section_label(progress_header, "LAUNCH PROGRESS").pack(side="left")

        self.progress_bar = ctk.CTkProgressBar(
            right,
            progress_color=GREEN,
            fg_color=BG_SECONDARY,
            height=8,
            corner_radius=6,
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(0, 8))

        self.status_lbl = ctk.CTkLabel(
            right,
            text="Ready to launch Minecraft.",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.status_lbl.pack(anchor="w", pady=(0, 4))
    # ── Version loading ────────────────────────────────────────────────────────

    def _load_versions(self):
        self._log("🌐 Fetching Minecraft versions…")

        def _task():
            try:
                all_v = fetch_release_versions()
                self.all_versions = [v["id"] for v in all_v]
                self.after(0, lambda: self._log(f"✅ {len(self.all_versions)} total MC releases found."))
            except Exception as e:
                self.after(0, lambda: self._log(f"❌ Could not fetch MC versions: {e}"))

            try:
                self.fabric_versions = fetch_fabric_versions()
                self.after(0, lambda: self._log(f"✅ {len(self.fabric_versions)} versions supported by Fabric."))
            except Exception as e:
                self.after(0, lambda: self._log(f"❌ Could not fetch Fabric versions: {e}"))

            self.after(0, self._maybe_create_default_profiles)
            self.after(0, self._auto_update_latest_profiles)
            self.after(0, self._refresh_buttons)

        threading.Thread(target=_task, daemon=True).start()

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
                    })
                    changed = True

            self.cfg["last_known_latest_fabric"] = latest_fabric

        # ── Persist ───────────────────────────────────────────────────────────
        config.save(self.cfg)  # always persist the tracking keys
        if changed:
            self._refresh_profile_list()

    # ── Profiles ──────────────────────────────────────────────────────────────

    def _refresh_profile_list(self):
        # Destroy old widgets
        for w in self.profile_list_frame.winfo_children():
            w.destroy()
        self._profile_buttons = []

        profiles = self.cfg.get("profiles", [])
        active   = self.cfg.get("active_profile")

        for i, p in enumerate(profiles):
            type_tag = "🟢 Fabric" if p["type"] == "fabric" else "🍦 Vanilla"
            install_status = "Installed" if self._is_installed_for_profile(p) else "Not installed"
            label = f"{p['name']}\n{p['mc_version']}  ·  {type_tag}  ·  {install_status}"
            is_active = p["name"] == active

            btn = ctk.CTkButton(
                self.profile_list_frame,
                text=label,
                anchor="w",
                fg_color=self.theme["ACCENT"] if is_active else self.theme["BG_SECONDARY"],
                text_color=self.theme["BG_PRIMARY"] if is_active else self.theme["TEXT_FG"],
                hover_color=self.theme["ACCENT_DARK"] if is_active else "#1e293b",
                font=ctk.CTkFont(size=12),
                command=lambda idx=i: self._on_profile_selected(idx),
            )
            btn.pack(fill="x", pady=2, padx=4)
            self._profile_buttons.append(btn)

        # Restore selection
        if active:
            for i, p in enumerate(profiles):
                if p["name"] == active:
                    self._selected_profile_idx = i
                    self._update_info_card(p)
                    break
        self._refresh_buttons()

    def _current_profile(self) -> dict | None:
        profiles = self.cfg.get("profiles", [])
        i = self._selected_profile_idx
        return profiles[i] if 0 <= i < len(profiles) else None

    def _on_profile_selected(self, idx: int):
        profiles = self.cfg.get("profiles", [])
        if 0 <= idx < len(profiles):
            self._selected_profile_idx = idx
            self.cfg["active_profile"] = profiles[idx]["name"]
            config.save(self.cfg)
            self._update_info_card(profiles[idx])
            # Recolour buttons
            for i, btn in enumerate(self._profile_buttons):
                if i == idx:
                    btn.configure(fg_color=self.theme["ACCENT"], text_color=self.theme["BG_PRIMARY"], hover_color=self.theme["ACCENT_DARK"])
                else:
                    btn.configure(fg_color=self.theme["BG_SECONDARY"], text_color=self.theme["TEXT_FG"], hover_color="#1e293b")
        self._refresh_buttons()

    def _update_info_card(self, profile: dict):
        self.info_version_lbl.configure(
            text=f"MC {profile['mc_version']}  ·  {'Fabric' if profile['type'] == 'fabric' else 'Vanilla'}"
        )
        if profile["type"] == "fabric":
            mods   = profile.get("mods", [])
            labels = [AVAILABLE_MODS[m]["label"] for m in mods if m in AVAILABLE_MODS]
            self.info_mods_lbl.configure(text="Mods: " + (", ".join(labels) if labels else "none"))
        else:
            self.info_mods_lbl.configure(text="No mods installed")

    def _on_edit_profile(self):
        profile = self._current_profile()
        if not profile:
            self._log("Select a profile before editing.")
            return

        ProfileEditorWindow(self, profile)

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
        if any(p["name"] == profile["name"] for p in self.cfg.get("profiles", [])):
            self._log(f"⚠  A profile named '{profile['name']}' already exists.")
            return
        self.cfg.setdefault("profiles", []).append(profile)
        profile.setdefault("instance_id", uuid.uuid4().hex)
        self.cfg["active_profile"] = profile["name"]
        config.save(self.cfg)
        self._refresh_profile_list()
        self._log(f"✅ Profile '{profile['name']}' created  ({profile['mc_version']}, {profile['type']}).")

    def _on_delete_profile(self):
        profile = self._current_profile()
        if not profile:
            return
        if not messagebox.askyesno("Delete Profile", f"Delete '{profile['name']}'?", parent=self):
            return
        self.cfg["profiles"] = [
            p for p in self.cfg.get("profiles", []) if p["name"] != profile["name"]
        ]
        if self.cfg.get("active_profile") == profile["name"]:
            self.cfg["active_profile"] = None
        self._selected_profile_idx = -1
        config.save(self.cfg)
        self._refresh_profile_list()
        self._log(f"🗑  Deleted '{profile['name']}'.")

    # ── Install & Play (unified) ───────────────────────────────────────────────

    def _is_installed_for_profile(self, profile: dict) -> bool:
        """Return True only when the version is installed with the *same* type (fabric/vanilla)."""
        entry = self.cfg.get("installed_versions", {}).get(profile["mc_version"])
        if not entry:
            return False
        if entry.get("type") != profile["type"]:
            return False
        pinned_loader = profile.get("fabric_loader_version")
        if pinned_loader:
            expected_id = f"fabric-loader-{pinned_loader}-{profile['mc_version']}"
            return entry.get("fabric_profile_id") == expected_id
        return True

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

        mc_version   = profile["mc_version"]
        profile_type = profile["type"]
        enabled_mods = profile.get("mods", [])
        ram_gb       = self.ram_var.get()
        use_dgpu     = self.cfg.get("use_dgpu", False)
        needs_install = not self._is_installed_for_profile(profile)
        needs_profile_mods = (
            profile_type == "fabric"
            and not profile.get("source_modpack")
            and not profile.get("launcher_mods_initialized")
        )

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
                            loader_version=profile.get("fabric_loader_version"),
                        )
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

                if needs_profile_mods:
                    install_mods(
                        mc_version, enabled_mods,
                        log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
                        progress=lambda t, p: self.after(0, lambda tt=t, pp=p: self._on_progress(tt, pp)),
                        mods_dir=modrinth.profile_instance_dir(profile) / "mods",
                    )
                    profile["launcher_mods_initialized"] = True
                    config.save(self.cfg)


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
                    game_dir=modrinth.profile_instance_dir(profile),
                )
                self.after(0, lambda: self._log("🎮 Game launched!"))
                for line in proc.stdout:
                    self.after(0, lambda l=line: self._log(l.rstrip()))
                proc.wait()
                self.after(
                    0,
                    lambda: self._on_worker_done(True, f"Game exited (code {proc.returncode})"),
                )
            except Exception as e:
                self.after(0, lambda err=e: self._on_worker_done(False, str(err)))

        threading.Thread(target=worker, daemon=True).start()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_username_changed(self, *_):
        text = self.username_var.get()
        self.cfg["username"] = text
        config.save(self.cfg)
        self._refresh_buttons()

    def _on_ram_changed(self, val):
        gb = int(val)
        self.cfg["ram_gb"] = gb
        config.save(self.cfg)
        self.ram_label_lbl.configure(text=f"RAM — {gb} GB")

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
        self.del_btn.configure(state="normal" if has_profile else "disabled")
        self.edit_btn.configure(state="normal" if has_profile else "disabled")

    def _on_progress(self, task: str, pct: int):
        self.progress_bar.set(pct / 100)
        self.status_lbl.configure(text=f"{task}: {pct}%")

    def _on_worker_done(self, success: bool, message: str):
        self._set_busy(False)
        self.progress_bar.set(1.0 if success else 0.0)
        self._log(f"{'✅' if success else '❌'} {message}")
        self.status_lbl.configure(text="Ready.")
        self._refresh_profile_list()
        self._refresh_buttons()

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.play_btn.configure(state=state)
        self.new_btn.configure(state=state)
        self.del_btn.configure(state=state)
        self.edit_btn.configure(state=state)
        if not busy:
            self._refresh_buttons()  # restore correct label after busy clears

    def _log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    # ── Settings & Theme ──────────────────────────────────────────────────────

    def _on_open_settings(self):
        dlg = SettingsDialog(self, self.theme, self.cfg)
        if dlg.result:
            self.theme = get_theme(self.cfg.get("theme", "overworld"))
            self._apply_theme()

    def _apply_theme(self):
        t = self.theme
        self.configure(fg_color=t["BG_PRIMARY"])
        self.title_lbl.configure(text_color=t["ACCENT"])
        self.ms_gamertag_lbl.configure(text_color=t["ACCENT"])
        self.auth_mode_menu.configure(
            selected_color=t["ACCENT"], selected_hover_color=t["ACCENT_DARK"],
            unselected_color=t["BG_SECONDARY"],
        )
        self.ms_signin_btn.configure(fg_color=t["MS_BLUE"], hover_color=t["MS_BLUE_DARK"])
        self.profile_list_frame.configure(fg_color=t["BG_SECONDARY"], border_color=t["BORDER_COL"])
        self.info_card.configure(fg_color=t["BG_SECONDARY"], border_color=t["BORDER_COL"])
        self.ram_slider.configure(
            progress_color=t["ACCENT"], fg_color=t["BG_SECONDARY"],
            button_color=t["ACCENT"], button_hover_color=t["ACCENT_DARK"],
        )
        self.play_btn.configure(
            fg_color=t["ACCENT"], text_color=t["BG_PRIMARY"], hover_color=t["ACCENT_DARK"],
        )
        self.log_box.configure(fg_color=t["BG_CONSOLE"], border_color=t["BORDER_COL"])
        self.progress_bar.configure(progress_color=t["ACCENT"], fg_color=t["BG_SECONDARY"])
        self.new_btn.configure(
            border_color=t["ACCENT_ALT"], text_color=t["ACCENT_ALT"], hover_color=t["ACCENT_ALT"],
        )
        for key, button in self.nav_buttons.items():
            active = button.cget("fg_color") != "transparent"
            button.configure(
                fg_color=t["ACCENT"] if active else "transparent",
                hover_color=t["ACCENT_DARK"] if active else t["BG_PRIMARY"],
                text_color=t["BG_PRIMARY"] if active else t["TEXT_FG"],
            )
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
