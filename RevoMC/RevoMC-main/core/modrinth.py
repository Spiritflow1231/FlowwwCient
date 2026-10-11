"""Modrinth project discovery and safe, profile-isolated content installation."""

import hashlib
import ipaddress
import json
import os
import re
import shutil
import tempfile
import time
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
_SEARCH_CACHE_TTL = 120
_search_cache: dict[tuple, tuple[float, list[dict]]] = {}
_SEARCH_PAGE_SIZE = 20

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
    category: str, query: str, game_version: str, loader: str, offset: int = 0
) -> list[dict]:
    if category not in CATEGORIES:
        raise ValueError("Unsupported Modrinth category.")
    project_type = CATEGORIES[category][0]
    facets = [[f"project_type:{project_type}"], [f"versions:{game_version}"]]
    if category in ("mods", "modpacks"):
        supported_loaders = {"fabric", "forge", "neoforge", "quilt"}
        if loader not in supported_loaders:
            return []
        facets.append([f"categories:{loader}"])
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("Search offset must be a non-negative integer.")
    cache_key = (category, query, game_version, loader, offset)
    cached = _search_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _SEARCH_CACHE_TTL:
        return [dict(hit) for hit in cached[1]]
    params = urllib.parse.urlencode({
        "query": query,
        "facets": json.dumps(facets, separators=(",", ":")),
        "limit": str(_SEARCH_PAGE_SIZE),
        "offset": str(offset),
        "index": "relevance",
    })
    result = _request_json(f"{MODRINTH_API}/search?{params}")
    if not isinstance(result, dict) or not isinstance(result.get("hits"), list):
        raise RuntimeError("Modrinth returned an unexpected project-search response.")
    hits = [hit for hit in result["hits"] if isinstance(hit, dict)]
    _search_cache[cache_key] = (time.monotonic(), hits)
    return [dict(hit) for hit in hits]


def compatible_versions(project_id: str, category: str, game_version: str, loader: str) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", project_id):
        raise ValueError("Modrinth returned an invalid project ID.")
    if category not in CATEGORIES:
        raise ValueError("Unsupported Modrinth category.")
    if category in ("mods", "modpacks") and loader not in {
        "fabric", "forge", "neoforge", "quilt", "vanilla"
    }:
        return []

    params = {"game_versions": json.dumps([game_version])}
    if category in ("mods", "modpacks") and loader != "vanilla":
        params["loaders"] = json.dumps([loader])
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
            if loader != "vanilla" and loader not in loaders:
                continue
            if loader == "vanilla" and loaders and not set(loaders).issubset({"minecraft"}):
                continue
        compatible.append(version)
    return compatible


def resolve_required_mod_dependencies(
    version: dict,
    game_version: str,
    loader: str,
    installed_project_ids: set[str] | None = None,
) -> tuple[list[tuple[str, str, dict]], list[str]]:
    """Resolve compatible required mod dependencies recursively."""
    installed = set(installed_project_ids or ())
    visiting: set[str] = set()
    resolved: list[tuple[str, str, dict]] = []
    warnings: list[str] = []

    def fetch_version(dependency: dict, project_id: str) -> dict | None:
        version_id = dependency.get("version_id")
        if version_id:
            if not isinstance(version_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,80}", version_id
            ):
                warnings.append(f"Dependency {project_id} has an invalid version ID.")
                return None
            candidate = _request_json(
                f"{MODRINTH_API}/version/{urllib.parse.quote(version_id, safe='')}"
            )
            if not isinstance(candidate, dict):
                return None
            loaders = candidate.get("loaders", [])
            if (
                game_version not in candidate.get("game_versions", [])
                or loader not in loaders
            ):
                warnings.append(
                    f"Required dependency {project_id} has no version compatible "
                    f"with Minecraft {game_version} and {loader}."
                )
                return None
            return candidate

        matches = compatible_versions(project_id, "mods", game_version, loader)
        if not matches:
            warnings.append(
                f"Required dependency {project_id} has no compatible version "
                f"for Minecraft {game_version} and {loader}."
            )
            return None
        return matches[0]

    def visit(parent_version: dict, depth: int):
        if depth > 64:
            raise RuntimeError("Mod dependencies exceed the maximum nesting depth.")
        dependencies = parent_version.get("dependencies", [])
        if not isinstance(dependencies, list):
            return
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                continue
            dependency_type = dependency.get("dependency_type")
            project_id = dependency.get("project_id")
            if dependency_type == "incompatible":
                if isinstance(project_id, str):
                    warnings.append(
                        f"{project_id} is marked incompatible with "
                        f"{parent_version.get('name', 'the selected mod')}."
                    )
                continue
            if dependency_type != "required":
                continue
            if not isinstance(project_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,80}", project_id
            ):
                warnings.append("A required dependency has no valid Modrinth project ID.")
                continue
            if project_id in installed or project_id in visiting:
                continue

            selected = fetch_version(dependency, project_id)
            if selected is None:
                continue
            visiting.add(project_id)
            visit(selected, depth + 1)
            visiting.remove(project_id)
            installed.add(project_id)
            project = _request_json(
                f"{MODRINTH_API}/project/{urllib.parse.quote(project_id, safe='')}"
            )
            title = project.get("title", project_id) if isinstance(project, dict) else project_id
            resolved.append((project_id, title, selected))

    root_project = version.get("project_id")
    if isinstance(root_project, str):
        visiting.add(root_project)
    visit(version, 0)
    return resolved, warnings


def installed_mod_project_ids(profile: dict) -> set[str]:
    """Read known project IDs from records and local Fabric jar metadata."""
    project_ids = set()
    installed_content = profile.get("installed_content", {})
    records = (
        installed_content.get("mods", [])
        if isinstance(installed_content, dict) else []
    )
    if isinstance(records, list):
        project_ids.update(
            record["project_id"]
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("project_id"), str)
        )
    mods_dir = profile_instance_dir(profile) / "mods"
    if not mods_dir.is_dir() or mods_dir.is_symlink():
        return project_ids
    for jar_path in mods_dir.iterdir():
        if (
            jar_path.is_symlink()
            or not jar_path.is_file()
            or not jar_path.name.lower().endswith(".jar")
            or not jar_path.resolve().is_relative_to(mods_dir.resolve())
        ):
            continue
        try:
            with zipfile.ZipFile(jar_path) as jar:
                metadata = json.loads(jar.read("fabric.mod.json"))
        except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
            continue
        custom = metadata.get("custom", {}) if isinstance(metadata, dict) else {}
        modrinth_data = custom.get("modrinth", {}) if isinstance(custom, dict) else {}
        project_id = modrinth_data.get("project_id") if isinstance(modrinth_data, dict) else None
        if isinstance(project_id, str):
            project_ids.add(project_id)
    return project_ids


def install_mod_project_with_dependencies(
    project_id: str,
    title: str,
    version: dict,
    category: str,
    destination: Path,
    profile: dict,
    cancel_event=None,
    progress: Callable[[int, int | None], None] | None = None,
) -> tuple[list[dict], list[str]]:
    """Install one Modrinth mod and its required compatible dependencies."""
    if category != "mods":
        raise ValueError("Dependency installation is supported for mods only.")
    game_version = profile.get("mc_version")
    loader = profile.get("type")
    dependencies, warnings = resolve_required_mod_dependencies(
        version,
        game_version,
        loader,
        installed_mod_project_ids(profile),
    )
    install_queue = [(project_id, title, version), *dependencies]
    records = []
    for mod_project_id, mod_title, mod_version in install_queue:
        installed_path = download_project_file(
            mod_version,
            "mods",
            destination,
            cancel_event=cancel_event,
            progress=progress,
        )
        records.append({
            "project_id": mod_project_id,
            "version_id": mod_version.get("id"),
            "title": mod_title,
            "filename": installed_path.name,
            "version": mod_version.get("version_number", "latest"),
            "enabled": True,
        })

    if loader == "fabric":
        from core.installer import has_fabric_api, install_mods

        if not has_fabric_api(destination):
            api_records = []
            install_mods(
                game_version,
                [],
                log=lambda _message: None,
                progress=lambda _task, _pct: None,
                mods_dir=destination,
                profile={"installed_content": {"mods": api_records}},
            )
            records.extend(api_records)
    return records, warnings


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
    try:
        if category == "modpacks":
            if not zipfile.is_zipfile(target):
                raise RuntimeError("The downloaded modpack is not a valid ZIP archive.")
        else:
            validate_content_archive(target, category)
    except Exception as exc:
        try:
            target.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise RuntimeError(
                f"Downloaded content failed validation: {exc} "
                f"(could not remove the invalid file: {cleanup_error})"
            ) from exc
        raise
    return target


def validate_content_archive(archive_path: Path, category: str) -> None:
    """Validate a local Minecraft content archive before adding it to an instance."""
    if category not in {"mods", "resourcepacks", "datapacks", "shaderpacks"}:
        raise ValueError("This category does not accept a content archive.")
    if not archive_path.is_file() or archive_path.is_symlink():
        raise ValueError("Select a regular content file.")
    expected_extension = ".jar" if category == "mods" else ".zip"
    if archive_path.suffix.lower() != expected_extension:
        raise ValueError(f"{category.title()} must use the {expected_extension} file extension.")
    if archive_path.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise ValueError("The selected archive exceeds the allowed file-size limit.")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > 100_000:
                raise ValueError("The archive contains too many entries.")
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
                raise ValueError("The archive expands beyond the allowed size.")
            names = set()
            for info in infos:
                if info.is_dir():
                    continue
                safe_path = _safe_relative_path(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError("Symbolic links are not allowed in content archives.")
                names.add(safe_path.as_posix())
            invalid = archive.testzip()
            if invalid is not None:
                raise ValueError(f"The archive contains a damaged file: {invalid}")
            if category in {"resourcepacks", "datapacks"} and "pack.mcmeta" not in names:
                raise ValueError("This ZIP is missing the Minecraft pack.mcmeta manifest.")
            if category == "datapacks" and not any(
                name.startswith("data/") for name in names
            ):
                raise ValueError("This ZIP does not contain a datapack data/ directory.")
            if category == "shaderpacks" and not any(
                name.startswith("shaders/") or name == "shader.properties"
                for name in names
            ):
                raise ValueError("This ZIP does not appear to contain a shader pack.")
    except zipfile.BadZipFile as exc:
        raise ValueError("The selected file is not a valid ZIP/JAR archive.") from exc


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
    if directory.is_symlink():
        raise ValueError("The profile content directory must not be a symbolic link.")
    if not directory.is_dir():
        return []
    if not directory.resolve().is_relative_to(instance.resolve()):
        raise ValueError("The profile content directory resolves outside this instance.")
    extension = CATEGORIES[category][1]
    found = []
    for path in directory.iterdir():
        if path.is_symlink():
            raise ValueError(f"Refusing to follow symbolic link in profile content: {path.name}")
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError(f"Profile content points outside its category directory: {path.name}")
        if category == "mods":
            matches = path.is_file() and (
                path.name.lower().endswith(extension)
                or path.name.lower().endswith(f"{extension}.disabled")
            )
        else:
            matches = path.is_file() and path.suffix.lower() == extension
            if category in {"resourcepacks", "datapacks"} and path.is_dir():
                matches = True
        if matches:
            found.append(path)
    return sorted(found, key=lambda path: path.name.casefold())


def remove_installed_file(profile: dict, category: str, file_path: Path, world_name: str | None = None) -> None:
    allowed = list_installed_files(profile, category, world_name)
    if file_path not in allowed:
        raise ValueError("The selected file is not installed in this profile.")
    if file_path.is_symlink():
        raise ValueError("Refusing to remove a symbolic link.")
    if file_path.is_dir():
        shutil.rmtree(file_path)
    else:
        file_path.unlink()
