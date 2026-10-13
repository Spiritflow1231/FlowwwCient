"""Built-in "Client Mods" catalog: one-click PvP / performance packs from Modrinth.

Only fair-play mods are listed.  Slugs are resolved to real Modrinth projects and
compatible versions at install time (nothing is hard-coded to a version), and
required dependencies are installed through the normal mod pipeline.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Callable

from core import modrinth

CSL_SLUG = "customskinloader"
CSL_PROJECT_ID = "idMHQ4n2"  # CustomSkinLoader on Modrinth


def _catalog_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / "client_mods.json"


def load_catalog(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or _catalog_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"presets": [], "mods": []}
    mods = [m for m in data.get("mods", []) if isinstance(m, dict) and m.get("slug")]
    return {"presets": data.get("presets", []), "mods": mods, "note": data.get("note", "")}


def preset_entries(catalog: dict, preset: str) -> list[dict]:
    return [m for m in catalog["mods"] if preset in m.get("presets", [])]


def supports_profile(profile: dict) -> bool:
    return profile.get("type") == "fabric"


def is_installed(profile: dict, entry: dict) -> bool:
    """True when the mod was installed (or adopted) and its jar is still present."""
    mapping = profile.get("client_pack", {})
    project_id = mapping.get(entry["slug"]) if isinstance(mapping, dict) else None
    if not project_id:
        return False
    try:
        return project_id in modrinth.installed_mod_project_ids(profile)
    except (OSError, ValueError):
        return False


def install_entries(
    profile: dict,
    entries: list[dict],
    destination: Path,
    cancel_event=None,
    progress: Callable[[int, int | None], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[list[dict], list[str], list[str]]:
    """Install ``entries`` into ``destination``.

    Returns (new records, failures, warnings).  ``profile`` is updated in memory
    (installed_content and client_pack); the caller saves it.
    """
    say = log or (lambda _m: None)
    game_version = profile.get("mc_version", "")
    loader = profile.get("type", "vanilla")
    records_out: list[dict] = []
    failures: list[str] = []
    warnings: list[str] = []
    pack = profile.setdefault("client_pack", {})
    mod_records = profile.setdefault("installed_content", {}).setdefault("mods", [])
    destination.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        slug, title = entry["slug"], entry.get("title", entry["slug"])
        if cancel_event is not None and cancel_event.is_set():
            raise modrinth.DownloadCancelled("Installation cancelled.")
        try:
            versions = modrinth.compatible_versions(slug, "mods", game_version, loader)
        except Exception as exc:  # network / unknown slug
            failures.append(f"{title}: {exc}")
            continue
        if not versions:
            failures.append(f"{title}: no release for Minecraft {game_version} ({loader})")
            continue
        version = versions[0]
        project_id = version.get("project_id")
        if not isinstance(project_id, str):
            failures.append(f"{title}: Modrinth returned no project ID")
            continue
        if project_id in modrinth.installed_mod_project_ids(profile):
            pack[slug] = project_id
            say(f"{title} is already installed.")
            continue
        say(f"Installing {title} {version.get('version_number', '')}…")
        try:
            records, extra = modrinth.install_mod_project_with_dependencies(
                project_id, title, version, "mods", destination, profile,
                cancel_event=cancel_event, progress=progress,
            )
        except modrinth.DownloadCancelled:
            raise
        except Exception as exc:
            failures.append(f"{title}: {exc}")
            continue
        for record in records:
            if record.get("project_id") == project_id:
                record["slug"] = slug
        mod_records.extend(records)
        records_out.extend(records)
        warnings.extend(extra)
        pack[slug] = project_id
    return records_out, failures, warnings


# ── offline skin / cape for the player's own client (CustomSkinLoader) ─────────

def sync_local_skin(game_dir: Path, username: str, skin: Path | None, cape: Path | None) -> list[str]:
    """Copy the offline account's skin/cape where CustomSkinLoader's default
    ``Legacy`` local source reads them:

        <game dir>/CustomSkinLoader/LocalSkin/skins/<username>.png
        <game dir>/CustomSkinLoader/LocalSkin/capes/<username>.png

    Files for a missing skin/cape are removed so an old cape never lingers.
    """
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
