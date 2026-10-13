"""Show an offline account's skin and cape in the game (CustomSkinLoader).

CustomSkinLoader's default "Legacy" local source reads
``<game dir>/CustomSkinLoader/LocalSkin/skins/<username>.png`` (and ``capes/``),
so the launcher installs the mod once and copies the account's images there at
launch.  Offline skins are only visible on your own client.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from core import modrinth

CSL_SLUG = "customskinloader"
CSL_PROJECT_ID = "idMHQ4n2"


def ensure_installed(profile: dict, mods_dir: Path, log: Callable[[str], None] | None = None) -> bool:
    """Install CustomSkinLoader into a Fabric profile if missing. Returns True when present."""
    say = log or (lambda _m: None)
    if profile.get("type") != "fabric":
        return False
    if CSL_PROJECT_ID in modrinth.installed_mod_project_ids(profile):
        return True
    versions = modrinth.compatible_versions(
        CSL_SLUG, "mods", profile.get("mc_version", ""), "fabric"
    )
    if not versions:
        say(f"CustomSkinLoader has no release for Minecraft {profile.get('mc_version')}.")
        return False
    mods_dir.mkdir(parents=True, exist_ok=True)
    say("Installing CustomSkinLoader (so your skin shows in game)…")
    records, _warnings = modrinth.install_mod_project_with_dependencies(
        CSL_PROJECT_ID, "CustomSkinLoader", versions[0], "mods", mods_dir, profile
    )
    profile.setdefault("installed_content", {}).setdefault("mods", []).extend(records)
    return True


def sync_local_skin(game_dir: Path, username: str, skin: Path | None, cape: Path | None) -> list[str]:
    """Copy (or remove) the skin/cape files CustomSkinLoader reads. Returns what was copied."""
    if not username or any(char in username for char in '/\\:*?"<>|'):
        return []
    root = game_dir / "CustomSkinLoader" / "LocalSkin"
    done = []
    for kind, source in (("skins", skin), ("capes", cape)):
        target = root / kind / f"{username}.png"
        if source is not None and source.is_file() and not source.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            done.append(kind)
        else:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
    return done
