"""Profile instance initialization and per-profile manifest persistence."""

import json
import os
import tempfile
from pathlib import Path

from core.modrinth import profile_instance_dir

PROFILE_DIRECTORIES = (
    "mods",
    "resourcepacks",
    "shaderpacks",
    "saves",
    "config",
    "datapacks",
)


def initialize_profile(profile: dict) -> Path:
    """Create the isolated profile folders and seed its profile.json manifest."""
    instance = profile_instance_dir(profile)
    instance.mkdir(parents=True, exist_ok=True)
    for name in PROFILE_DIRECTORIES:
        directory = instance / name
        if directory.is_symlink():
            raise ValueError(f"The profile {name} folder cannot be a symbolic link.")
        directory.mkdir(exist_ok=True)
    manifest = instance / "profile.json"
    if manifest.is_symlink():
        raise ValueError("The profile manifest cannot be a symbolic link.")
    if not manifest.exists():
        save_manifest(profile)
    return instance


def save_manifest(profile: dict) -> None:
    instance = profile_instance_dir(profile)
    instance.mkdir(parents=True, exist_ok=True)
    path = instance / "profile.json"
    if path.is_symlink():
        raise ValueError("The profile manifest cannot be a symbolic link.")
    payload = {
        "instance_id": profile.get("instance_id"),
        "name": profile.get("name", ""),
        "mc_version": profile.get("mc_version", ""),
        "loader": profile.get("type", "vanilla"),
        "memory_gb": profile.get("memory_gb"),
        "java_args": profile.get("java_args", ""),
        "performance_boost": bool(profile.get("performance_boost", False)),
        "installed_content": profile.get("installed_content", {}),
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".profile-", suffix=".tmp", dir=instance
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def sync_profiles(profiles: list[dict]) -> None:
    """Write the portable profile index alongside the main launcher config."""
    root = Path.home() / ".revomc"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "profiles.json"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".profiles-", suffix=".tmp", dir=root
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(profiles, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
