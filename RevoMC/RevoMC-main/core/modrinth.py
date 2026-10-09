"""Modrinth project discovery and safe, profile-isolated content installation."""

import hashlib
import ipaddress
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable

from core.installer import MODRINTH_API

USER_AGENT = "FlowwwClient/1.0 (https://github.com/Spiritflow1231/FlowwwCient)"
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024

CATEGORIES = {
    "mods": ("mod", ".jar"),
    "resourcepacks": ("resourcepack", ".zip"),
    "modpacks": ("modpack", ".mrpack"),
    "datapacks": ("datapack", ".zip"),
    "shaderpacks": ("shader", ".zip"),
}


class DownloadCancelled(Exception):
    """Raised when a user cancels an active download."""


def _request_json(url: str) -> dict | list:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read(8 * 1024 * 1024 + 1)
            if len(payload) > 8 * 1024 * 1024:
                raise RuntimeError("Modrinth returned an oversized response.")
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Modrinth returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Modrinth: {exc.reason}") from exc
    except (TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read the Modrinth response: {exc}") from exc


def _validate_download_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("Modrinth returned an unsafe download URL.")
    if host != "modrinth.com" and not host.endswith(".modrinth.com"):
        raise ValueError(f"Refusing a download from an untrusted host: {host}")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Refusing a download from a private network address.")


def _safe_relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("The content package contains an invalid file path.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("The content package contains an unsafe file path.")
    if path.parts and re.match(r"^[a-zA-Z]:", path.parts[0]):
        raise ValueError("The content package contains an unsafe file path.")
    return path


def profile_instance_dir(profile: dict) -> Path:
    instance_id = profile.get("instance_id", "")
    if not isinstance(instance_id, str) or not re.fullmatch(r"[a-f0-9]{32}", instance_id):
        raise ValueError("This profile has an invalid instance ID.")
    instances_root = Path.home() / ".revomc" / "instances"
    instance = instances_root / instance_id
    if instance.is_symlink() or not instance.resolve().is_relative_to(instances_root.resolve()):
        raise ValueError("The profile instance path is outside the launcher instances folder.")
    return instance


def search_projects(
    category: str, query: str, game_version: str, loader: str
) -> list[dict]:
    if category not in CATEGORIES:
        raise ValueError("Unsupported Modrinth category.")
    project_type = CATEGORIES[category][0]
    facets = [[f"project_type:{project_type}"], [f"versions:{game_version}"]]
    if category in ("mods", "modpacks") and loader == "fabric":
        facets.append(["categories:fabric"])
    if category == "mods" and loader != "fabric":
        return []

    params = urllib.parse.urlencode({
        "query": query,
        "facets": json.dumps(facets, separators=(",", ":")),
        "limit": "40",
        "index": "relevance",
    })
    result = _request_json(f"{MODRINTH_API}/search?{params}")
    if not isinstance(result, dict) or not isinstance(result.get("hits"), list):
        raise RuntimeError("Modrinth returned an unexpected project-search response.")
    return [hit for hit in result["hits"] if isinstance(hit, dict)]


def compatible_versions(project_id: str, category: str, game_version: str, loader: str) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", project_id):
        raise ValueError("Modrinth returned an invalid project ID.")
    if category not in CATEGORIES:
        raise ValueError("Unsupported Modrinth category.")
    if category == "mods" and loader != "fabric":
        return []

    params = {"game_versions": json.dumps([game_version])}
    if category in ("mods", "modpacks") and loader == "fabric":
        params["loaders"] = json.dumps(["fabric"])
    url = f"{MODRINTH_API}/project/{urllib.parse.quote(project_id, safe='')}/version?{urllib.parse.urlencode(params)}"
    versions = _request_json(url)
    if not isinstance(versions, list):
        raise RuntimeError("Modrinth returned an unexpected version response.")

    compatible = []
    for version in versions:
        if not isinstance(version, dict) or game_version not in version.get("game_versions", []):
            continue
        loaders = version.get("loaders", [])
        if category in ("mods", "modpacks"):
            if loader == "fabric" and "fabric" not in loaders:
                continue
            if loader == "vanilla" and loaders and not set(loaders).issubset({"minecraft"}):
                continue
        compatible.append(version)
    return compatible


def _download_stream(
    url: str,
    destination: Path,
    *,
    expected_hashes: dict | None = None,
    cancel_event=None,
    progress: Callable[[int, int | None], None] | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> None:
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Download cancelled.")
    if destination.exists():
        raise FileExistsError(f"{destination.name} is already installed.")
    _validate_download_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    temp_path = None
    completed = False
    created_destination = False
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            _validate_download_url(response.geturl())
            length_header = response.headers.get("Content-Length")
            total = int(length_header) if length_header and length_header.isdigit() else None
            if total is not None and total > max_bytes:
                raise ValueError("The download exceeds the allowed file-size limit.")
            digesters = {}
            for algorithm in ("sha1", "sha512"):
                if expected_hashes and expected_hashes.get(algorithm):
                    digesters[algorithm] = hashlib.new(algorithm)
            fd, temp_name = tempfile.mkstemp(prefix=".flowww-download-", dir=destination.parent)
            temp_path = Path(temp_name)
            downloaded = 0
            with os.fdopen(fd, "wb") as output:
                while True:
                    if cancel_event and cancel_event.is_set():
                        raise DownloadCancelled("Download cancelled.")
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise ValueError("The download exceeds the allowed file-size limit.")
                    output.write(chunk)
                    for digester in digesters.values():
                        digester.update(chunk)
                    if progress:
                        progress(downloaded, total)
                output.flush()
                os.fsync(output.fileno())

        if total is not None and downloaded != total:
            raise RuntimeError("The download was incomplete.")
        for algorithm, digester in digesters.items():
            if digester.hexdigest().lower() != expected_hashes[algorithm].lower():
                raise RuntimeError(f"The downloaded file failed its {algorithm.upper()} integrity check.")

        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        descriptor = os.open(destination, flags, 0o600)
        created_destination = True
        with os.fdopen(descriptor, "wb") as output, temp_path.open("rb") as source:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        completed = True
        if progress:
            progress(downloaded, total)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Download server returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download the file: {exc.reason}") from exc
    except FileExistsError as exc:
        raise FileExistsError(f"{destination.name} is already installed.") from exc
    except (TimeoutError, OSError) as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
        if created_destination and not completed and destination.exists():
            destination.unlink()


def _version_file(version: dict, extension: str) -> dict:
    files = version.get("files")
    if not isinstance(files, list):
        raise RuntimeError("This Modrinth version has no downloadable files.")
    matching = [
        entry for entry in files
        if isinstance(entry, dict)
        and isinstance(entry.get("filename"), str)
        and entry["filename"].lower().endswith(extension)
        and "/" not in entry["filename"]
        and "\\" not in entry["filename"]
    ]
    if not matching:
        raise RuntimeError(f"This Modrinth version does not contain a {extension} file.")
    return next((entry for entry in matching if entry.get("primary")), matching[0])


def download_project_file(
    version: dict,
    category: str,
    destination: Path,
    cancel_event=None,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    if category not in CATEGORIES:
        raise ValueError("Unsupported Modrinth category.")
    entry = _version_file(version, CATEGORIES[category][1])
    filename = entry["filename"]
    if not re.fullmatch(r"[A-Za-z0-9._+() -]{1,180}", filename) or filename in (".", ".."):
        raise ValueError("Modrinth returned an invalid filename.")
    url = entry.get("url")
    if not isinstance(url, str):
        raise RuntimeError("Modrinth did not provide a download URL.")
    target = destination / filename
    _download_stream(
        url, target, expected_hashes=entry.get("hashes"),
        cancel_event=cancel_event, progress=progress,
    )
    if category != "mods":
        if not zipfile.is_zipfile(target):
            target.unlink()
            raise RuntimeError("The downloaded content is not a valid ZIP archive.")
    elif not zipfile.is_zipfile(target):
        target.unlink()
        raise RuntimeError("The downloaded mod is not a valid JAR archive.")
    return target


def install_modpack(
    archive_path: Path,
    destination: Path,
    cancel_event=None,
    progress: Callable[[int, int | None], None] | None = None,
) -> dict:
    """Safely import a Modrinth .mrpack into a new, empty profile instance."""
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Modpack import cancelled.")
    if destination.exists():
        raise FileExistsError("The new profile instance already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}-{uuid.uuid4().hex}.tmp"
    staging.mkdir()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            try:
                index_data = archive.read("modrinth.index.json")
            except KeyError as exc:
                raise RuntimeError("This archive is not a Modrinth modpack (.mrpack).") from exc
            if len(index_data) > 4 * 1024 * 1024:
                raise RuntimeError("The modpack manifest is too large.")
            index = json.loads(index_data)
            if not isinstance(index, dict):
                raise RuntimeError("The modpack manifest has an invalid structure.")
            if index.get("formatVersion") != 1:
                raise RuntimeError("This modpack uses an unsupported manifest format.")
            dependencies = index.get("dependencies", {})
            if not isinstance(dependencies, dict):
                raise RuntimeError("The modpack manifest has invalid dependencies.")
            mc_version = dependencies.get("minecraft")
            if not isinstance(mc_version, str):
                raise RuntimeError("The modpack does not specify a Minecraft version.")
            loader_dependencies = {
                "fabric-loader": "fabric",
                "quilt-loader": "quilt",
                "forge": "forge",
                "neoforge": "neoforge",
                "liteloader": "liteloader",
            }
            loaders = {
                loader_dependencies[key]
                for key, value in dependencies.items()
                if key in loader_dependencies and value
            }
            if not loaders:
                profile_type = "vanilla"
            elif loaders == {"fabric"}:
                profile_type = "fabric"
            else:
                raise RuntimeError(
                    "This launcher can import vanilla and Fabric modpacks only; "
                    f"the pack requires {', '.join(sorted(loaders))}."
                )

            archive_infos = archive.infolist()
            total_archive_size = sum(info.file_size for info in archive_infos)
            if total_archive_size > MAX_ARCHIVE_BYTES:
                raise RuntimeError("The modpack archive expands beyond the allowed size.")
            extracted = 0
            for info in archive_infos:
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Modpack import cancelled.")
                if info.is_dir():
                    continue
                if info.filename == "modrinth.index.json":
                    continue
                info_path = _safe_relative_path(info.filename)
                if info.file_size > MAX_ARCHIVE_BYTES:
                    raise RuntimeError("The modpack contains an oversized file.")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise RuntimeError("Symbolic links are not allowed in modpacks.")
                if not info_path.parts or info_path.parts[0] != "overrides":
                    continue
                relative = PurePosixPath(*info_path.parts[1:])
                if not relative.parts:
                    continue
                target = staging.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    while chunk := source.read(64 * 1024):
                        if cancel_event and cancel_event.is_set():
                            raise DownloadCancelled("Modpack import cancelled.")
                        extracted += len(chunk)
                        if extracted > MAX_ARCHIVE_BYTES:
                            raise RuntimeError("The modpack overrides expand beyond the allowed size.")
                        output.write(chunk)

            listed_files = index.get("files", [])
            if not isinstance(listed_files, list):
                raise RuntimeError("The modpack manifest contains an invalid files list.")
            total_files = len(listed_files)
            for number, entry in enumerate(listed_files, 1):
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Modpack import cancelled.")
                if not isinstance(entry, dict) or not isinstance(entry.get("downloads"), list):
                    raise RuntimeError("The modpack manifest contains an invalid file entry.")
                environment = entry.get("env", {})
                if not isinstance(environment, dict):
                    environment = {}
                if environment.get("client") == "unsupported":
                    continue
                relative = _safe_relative_path(entry.get("path"))
                target = staging.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(staging.resolve()):
                    raise RuntimeError("The modpack contains an unsafe file path.")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise RuntimeError("The modpack contains conflicting override and download paths.")
                hashes = entry.get("hashes", {})
                if not hashes.get("sha1") and not hashes.get("sha512"):
                    raise RuntimeError("A modpack file has no supported integrity hash.")
                urls = entry["downloads"]
                if not urls or not isinstance(urls[0], str):
                    raise RuntimeError("A modpack file has no download URL.")
                _download_stream(
                    urls[0], target,
                    expected_hashes=hashes,
                    cancel_event=cancel_event,
                    progress=progress,
                )
                if progress:
                    progress(number, total_files)

        os.rename(staging, destination)
        return {
            "name": index.get("name") or "Imported Modpack",
            "mc_version": mc_version,
            "type": profile_type,
            "fabric_loader_version": dependencies.get("fabric-loader"),
            "manifest_version": 1,
        }
    except (zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise RuntimeError("The modpack archive or manifest is invalid.") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def list_installed_files(profile: dict, category: str, world_name: str | None = None) -> list[Path]:
    if category not in CATEGORIES:
        raise ValueError("Unsupported Modrinth category.")
    instance = profile_instance_dir(profile)
    if category == "modpacks":
        return []
    if category == "datapacks":
        if not world_name:
            return []
        world_path = _safe_relative_path(world_name)
        if len(world_path.parts) != 1:
            raise ValueError("Invalid world name.")
        directory = instance / "saves" / world_path.parts[0] / "datapacks"
    else:
        directory = instance / category
    if not directory.is_dir() or not directory.resolve().is_relative_to(instance.resolve()):
        return []
    extension = CATEGORIES[category][1]
    return sorted(
        (path for path in directory.iterdir()
         if path.is_file() and path.suffix.lower() == extension),
        key=lambda path: path.name.lower(),
    )


def remove_installed_file(profile: dict, category: str, file_path: Path, world_name: str | None = None) -> None:
    allowed = list_installed_files(profile, category, world_name)
    if file_path not in allowed:
        raise ValueError("The selected file is not installed in this profile.")
    file_path.unlink()
