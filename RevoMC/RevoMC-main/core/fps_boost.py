"""One-click FPS boost for a Fabric profile.

* removes HUD / client-style extras that cost frames (HUD+, motion blur, fullbright, ...) — only files this launcher recognises, nothing else;
* installs the proven FPS mods (Sodium, Lithium, FerriteCore, Entity Culling,
  ImmediatelyFast) for the profile's Minecraft version.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Callable

from core import modrinth
from core.installer import install_mods

FPS_MODS = ["sodium", "lithium", "ferrite-core", "entityculling", "immediatelyfast"]

# Modrinth project IDs of extras that earlier launcher builds could install.
EXTRA_PROJECT_IDS = {
    "EqwpK4rm",  # HUD+
    "DOUqoosl",  # True Fullbright
    "uPsBC39O",  # ToggleSprint
    "PCwWGWFu",  # AutoSprint
    "dYSXVJhc",  # ToggleSP
    "M5szsQT4",  # Smooth Motion Blur
    "FCCkAXG3",  # Cubing's Motion Blur
    "JIabgpiD",  # ModuloGUI
    "PE656UHx",  # Simple HUD Enhanced
}
# Fabric mod ids (fabric.mod.json "id") for the same extras, when no Modrinth id is embedded.
EXTRA_MOD_IDS = {
    "hudplus", "hud-plus", "hud_plus", "true-fullbright", "truefullbright",
    "resolutetogglesprint", "autosprint", "autosprint-mod", "togglesp",
    "motionblur", "smooth-motion-blur", "smoothmotionblur", "cubings-motion-blur",
    "modulogui", "simple-hud-enhanced", "simplehudenhanced",
}


def _jar_identity(path: Path) -> tuple[str | None, str | None]:
    try:
        with zipfile.ZipFile(path) as jar:
            meta = json.loads(jar.read("fabric.mod.json"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        return None, None
    if not isinstance(meta, dict):
        return None, None
    mod_id = meta.get("id") if isinstance(meta.get("id"), str) else None
    custom = meta.get("custom", {})
    modrinth_data = custom.get("modrinth", {}) if isinstance(custom, dict) else {}
    project_id = modrinth_data.get("project_id") if isinstance(modrinth_data, dict) else None
    return mod_id, project_id if isinstance(project_id, str) else None


def find_extras(mods_dir: Path) -> list[Path]:
    """Jars (enabled or disabled) in ``mods_dir`` that are known performance-costly extras."""
    found = []
    if not mods_dir.is_dir() or mods_dir.is_symlink():
        return found
    for path in sorted(mods_dir.iterdir()):
        name = path.name.lower()
        if path.is_symlink() or not path.is_file() or not (
            name.endswith(".jar") or name.endswith(".jar.disabled")
        ):
            continue
        mod_id, project_id = _jar_identity(path)
        if project_id in EXTRA_PROJECT_IDS or (mod_id or "").lower() in EXTRA_MOD_IDS:
            found.append(path)
    return found


def remove_extras(profile: dict, instance_dir: Path) -> list[str]:
    """Delete the extras and forget their records. Returns the removed file names."""
    mods_dir = instance_dir / "mods"
    removed = []
    for path in find_extras(mods_dir):
        try:
            if path.resolve().is_relative_to(mods_dir.resolve()):
                path.unlink()
                removed.append(path.name)
        except OSError:
            continue
    removed_set = {name.removesuffix(".disabled") for name in removed}
    content = profile.get("installed_content")
    if isinstance(content, dict) and isinstance(content.get("mods"), list):
        content["mods"] = [
            record for record in content["mods"]
            if not (
                isinstance(record, dict)
                and (record.get("filename") in removed_set
                     or record.get("project_id") in EXTRA_PROJECT_IDS)
            )
        ]
    profile.pop("client_pack", None)
    return removed


def apply(profile: dict, log: Callable[[str], None] | None = None, max_ram_gb: int = 4) -> dict:
    """Remove extras, install FPS mods, switch the JVM tuning on. Returns a summary."""
    say = log or (lambda _m: None)
    if profile.get("type") != "fabric":
        raise RuntimeError("FPS Boost mods need a Fabric profile (vanilla has no mod support).")
    instance = modrinth.profile_instance_dir(profile)
    removed = remove_extras(profile, instance)
    if removed:
        say("Removed: " + ", ".join(removed))
    mods_dir = instance / "mods"
    before = set(p.name for p in mods_dir.glob("*.jar")) if mods_dir.is_dir() else set()
    install_mods(
        profile["mc_version"], FPS_MODS, log=say, progress=lambda _t, _p: None,
        mods_dir=mods_dir, profile=profile,
    )
    after = set(p.name for p in mods_dir.glob("*.jar"))
    # 2 GB is too little for a modern modded client: lift it to 4 GB when the PC allows
    try:
        current = int(profile.get("memory_gb") or 2)
    except (TypeError, ValueError):
        current = 2
    target = max(current, min(4, max(1, int(max_ram_gb))))
    if target != current:
        profile["memory_gb"] = target
        say(f"Memory raised to {target} GB.")
    profile["performance_boost"] = True
    profile["launcher_mods_initialized"] = True
    return {"removed": removed, "installed": sorted(after - before)}
