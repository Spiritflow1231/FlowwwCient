"""
core/launcher.py
Builds the JVM classpath and launches Minecraft, with or without Fabric.
"""

import os
import json
import re
import zipfile
from core.auth import CLIENT_ID
import subprocess
import platform
import shlex
from pathlib import Path
from typing import Callable

from core.installer import get_launcher_dir, get_shared_assets_dir
from core.config import get_minecraft_dir


from core.java_manager import get_java_executable, get_required_java_version


def _find_java(mc_version: str) -> str:
    java_version = get_required_java_version(mc_version)
    return get_java_executable(java_version)


def _set_windows_gpu_preference(java_path: str, log: Callable) -> None:
    r"""
    Register the Java executable for 'High Performance' GPU rendering
    via the Windows Graphics Settings registry key.

    HKCU\Software\Microsoft\DirectX\UserGpuPreferences
    Value: <java_path> = "GpuPreference=2;"
      0 = let Windows decide, 1 = power saving, 2 = high performance

    No admin elevation required -- this writes to HKEY_CURRENT_USER.
    """
    import winreg
    key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path,
            0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, java_path, 0, winreg.REG_SZ, "GpuPreference=2;")
    except Exception as e:
        log(f"⚠  Could not set GPU preference in registry: {e}")


def _maven_path(name: str) -> str:
    parts = name.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"


def _collect_classpath(
    base: Path, version_json: dict, fabric_profile: dict | None, mc_version: str
) -> list[str]:
    libs_dir = base / "libraries"
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        sys_name = "osx"
    jars = []

    def add_libs(lib_list):
        for lib in lib_list:
            rules = lib.get("rules", [])
            if rules:
                allowed = False
                for rule in rules:
                    os_rule = rule.get("os", {})
                    os_name = os_rule.get("name", "")
                    if not os_name or os_name == sys_name:
                        allowed = rule["action"] == "allow"
                if not allowed:
                    continue
            artifact = lib.get("downloads", {}).get("artifact")
            if artifact:
                p = libs_dir / artifact["path"]
            elif "name" in lib:
                p = libs_dir / _maven_path(lib["name"])
            else:
                continue
            if p.exists():
                jars.append(str(p))
            else:
                print(f"[WARN] Missing lib: {p}")

    # Fabric libs first if present
    if fabric_profile:
        add_libs(fabric_profile.get("libraries", []))

    add_libs(version_json.get("libraries", []))

    client_jar = base / "versions" / mc_version / f"{mc_version}.jar"
    jars.append(str(client_jar))
    return jars


def _parse_minecraft_version(version: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:[-+][A-Za-z0-9.-]+)?", version)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _version_constraint_matches(version: str, constraint: str) -> bool | None:
    """Evaluate the common Fabric semver constraints used for Minecraft."""
    version_parts = _parse_minecraft_version(version)
    if version_parts is None or not isinstance(constraint, str):
        return None

    def compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
        size = max(len(left), len(right))
        left += (0,) * (size - len(left))
        right += (0,) * (size - len(right))
        return (left > right) - (left < right)

    alternatives = constraint.split("||")
    for alternative in alternatives:
        terms = [term for term in re.split(r"[\s,]+", alternative.strip()) if term]
        if not terms:
            return None
        accepted = True
        for term in terms:
            match = re.fullmatch(r"(>=|<=|>|<|=|\^|~)?(\d+(?:\.\d+)*(?:\.[xX*])?)", term)
            if not match:
                return None
            operator, required_text = match.groups()
            wildcard = required_text.endswith((".x", ".X", ".*"))
            if wildcard:
                prefix = tuple(int(part) for part in required_text.rsplit(".", 1)[0].split("."))
                if version_parts[:len(prefix)] != prefix:
                    accepted = False
                    break
                continue

            required = tuple(int(part) for part in required_text.split("."))
            order = compare(version_parts, required)
            if operator in (None, "=") and order != 0:
                accepted = False
            elif operator == ">=" and order < 0:
                accepted = False
            elif operator == "<=" and order > 0:
                accepted = False
            elif operator == ">" and order <= 0:
                accepted = False
            elif operator == "<" and order >= 0:
                accepted = False
            elif operator == "^":
                upper = (required[0] + 1,) if required[0] else (0, required[1] + 1)
                if order < 0 or compare(version_parts, upper) >= 0:
                    accepted = False
            elif operator == "~":
                upper = required[:-1] + (required[-1] + 1,)
                if order < 0 or compare(version_parts, upper) >= 0:
                    accepted = False
            if not accepted:
                break
        if accepted:
            return True
    return False


def disable_incompatible_mods(
    mods_dir: Path, mc_version: str, log: Callable[[str], None]
) -> list[str]:
    """Disable Fabric mods that explicitly reject the selected Minecraft version."""
    mods_dir = Path(mods_dir)
    if not mods_dir.exists():
        return []
    if mods_dir.is_symlink() or not mods_dir.is_dir():
        raise ValueError("The profile mods path must be a regular directory.")

    disabled = []
    for jar_path in sorted(mods_dir.iterdir(), key=lambda path: path.name.casefold()):
        if not jar_path.name.lower().endswith(".jar"):
            continue
        if jar_path.is_symlink() or not jar_path.is_file():
            log(f"⚠ Skipping unsafe or non-file mod entry: {jar_path.name}")
            continue
        if not jar_path.resolve().is_relative_to(mods_dir.resolve()):
            log(f"⚠ Skipping mod outside the profile mods folder: {jar_path.name}")
            continue
        try:
            with zipfile.ZipFile(jar_path) as jar:
                metadata = json.loads(jar.read("fabric.mod.json"))
        except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
            continue

        dependencies = metadata.get("depends", {}) if isinstance(metadata, dict) else {}
        minecraft_dependency = dependencies.get("minecraft") if isinstance(dependencies, dict) else None
        constraints = minecraft_dependency if isinstance(minecraft_dependency, list) else [minecraft_dependency]
        results = [
            _version_constraint_matches(mc_version, constraint)
            for constraint in constraints
            if isinstance(constraint, str)
        ]
        if not results or any(result is None for result in results) or any(results):
            continue

        disabled_path = jar_path.with_name(f"{jar_path.name}.disabled")
        if disabled_path.exists():
            log(
                f"⚠ {jar_path.name} does not support Minecraft {mc_version}, "
                f"but {disabled_path.name} already exists; left the original unchanged."
            )
            continue
        jar_path.rename(disabled_path)
        disabled.append(jar_path.name)
        log(
            f"⚠ Disabled {jar_path.name}: its fabric.mod.json Minecraft dependency "
            f"{minecraft_dependency!r} does not match {mc_version}."
        )
    return disabled


def build_jvm_args(
    java_version: int,
    ram_gb: int,
    performance_boost: bool = True,
    user_args: list[str] | None = None,
    fabric_args: list[str] | None = None,
) -> list[str]:
    """Build supported memory and performance arguments for the selected Java."""
    if java_version not in {8, 17, 21, 25}:
        raise ValueError(f"Unsupported Java version: {java_version}")
    max_ram = max(1, int(ram_gb))
    min_ram = min(max(1, max_ram // 2), max_ram)
    max_arg = f"-Xmx{max_ram}G"
    min_arg = f"-Xms{min_ram}G"
    max_bytes = max_ram * 1024**3
    min_bytes = min_ram * 1024**3
    if performance_boost:
        performance_args = [
            "-XX:+UseG1GC",
            "-XX:+ParallelRefProcEnabled",
            "-XX:MaxGCPauseMillis=200",
        ]
    else:
        performance_args = []

    obsolete_flags = {
        "-XX:+UseConcMarkSweepGC",
        "-XX:+UseParNewGC",
        "-XX:+CMSIncrementalMode",
        "-XX:+CMSClassUnloadingEnabled",
        "-XX:+CMSParallelRemarkEnabled",
        "-XX:+UseCMSCompactAtFullCollection",
        "-XX:+UseBiasedLocking",
        "-XX:+UseFastAccessorMethods",
    }
    remaining_args = []
    for source in (user_args or [], fabric_args or []):
        for arg in source:
            if arg in obsolete_flags or arg.startswith(
                ("-XX:InitialHeapSize=", "-XX:MaxHeapSize=")
            ):
                continue
            match = re.fullmatch(r"-Xm([sx])(\d+)([kKmMgGtT]?)", arg)
            if match:
                kind, amount_text, unit = match.groups()
                multiplier = {
                    "": 1,
                    "k": 1024,
                    "m": 1024**2,
                    "g": 1024**3,
                    "t": 1024**4,
                }[unit.lower()]
                amount = int(amount_text) * multiplier
                if kind == "x":
                    max_arg = arg
                    max_bytes = amount
                else:
                    min_arg = arg
                    min_bytes = amount
                continue
            if arg.startswith(("-Xms", "-Xmx")):
                raise ValueError(f"Invalid JVM memory argument: {arg}")
            remaining_args.append(arg)
    if min_bytes > max_bytes:
        min_arg = max_arg.replace("-Xmx", "-Xms", 1)
    return [max_arg, min_arg, *performance_args, *remaining_args]


def launch(
    mc_version: str,
    profile_type: str,  # "vanilla" or "fabric"
    fabric_profile_id: str | None,
    username: str,
    ram_gb: int,
    log: Callable,
    auth_data: dict | None = None,
    use_dgpu: bool = False,
    game_dir: Path | None = None,
    offline_uuid: str | None = None,
    java_args: str = "",
    performance_boost: bool = True,
) -> subprocess.Popen:
    if profile_type not in {"vanilla", "fabric"}:
        raise ValueError(f"Unsupported Minecraft profile type: {profile_type}")
    if profile_type == "fabric" and not fabric_profile_id:
        raise ValueError("Fabric profile ID missing.")
    try:
        user_java_args = shlex.split(java_args)
    except ValueError as exc:
        raise ValueError(f"Invalid profile Java arguments: {exc}") from exc
    if any(arg in {"-cp", "-classpath", "-jar"} for arg in user_java_args):
        raise ValueError("Profile Java arguments cannot override the game classpath.")

    base = get_launcher_dir()
    game_dir = game_dir or get_minecraft_dir()
    game_dir.mkdir(parents=True, exist_ok=True)

    java = _find_java(mc_version)
    java_version = get_required_java_version(mc_version)
    sep = ";" if platform.system() == "Windows" else ":"

    # Load vanilla version JSON
    version_json_path = base / "versions" / mc_version / f"{mc_version}.json"
    if not version_json_path.exists():
        raise FileNotFoundError(f"Version JSON not found — please install first.")
    version_json = json.loads(version_json_path.read_text())

    # Load Fabric profile if applicable
    fabric_profile = None
    if profile_type == "fabric":
        fabric_json_path = (
            base / "versions" / fabric_profile_id / f"{fabric_profile_id}.json"
        )
        if not fabric_json_path.exists():
            raise FileNotFoundError(f"Fabric profile not found — please install first.")
        fabric_profile = json.loads(fabric_json_path.read_text())

    # Build classpath
    jars = _collect_classpath(base, version_json, fabric_profile, mc_version)
    classpath = sep.join(jars)

    # Main class
    if fabric_profile:
        main_class = fabric_profile.get("mainClass", "net.minecraft.client.main.Main")
    else:
        main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")

    # Asset index
    asset_index_id = version_json["assetIndex"]["id"]
    assets_dir = get_shared_assets_dir()

    # JVM args from Fabric profile
    extra_jvm = []
    if fabric_profile:
        for arg in fabric_profile.get("arguments", {}).get("jvm", []):
            if isinstance(arg, str):
                extra_jvm.append(arg)

    # Game args
    args_source = fabric_profile if fabric_profile else version_json
    game_args_raw = args_source.get("arguments", {}).get(
        "game", version_json.get("arguments", {}).get("game", [])
    )
    game_args = [a for a in game_args_raw if isinstance(a, str)]

    version_name = fabric_profile_id if fabric_profile else mc_version

    substitutions = {
        "${auth_player_name}": username,
        "${version_name}": version_name,
        "${game_directory}": str(game_dir),
        "${assets_root}": str(assets_dir),
        "${assets_index_name}": asset_index_id,
        "${auth_uuid}": auth_data["id"] if auth_data else (offline_uuid or "00000000-0000-0000-0000-000000000000"),
        "${auth_access_token}": auth_data["access_token"] if auth_data else "0",
        "${user_type}": "msa" if auth_data else "legacy",
        "${version_type}": "release",
        "${resolution_width}": "854",
        "${resolution_height}": "480",
        "${clientid}": CLIENT_ID if auth_data else "0",
        "${auth_xuid}": "0",
    }

    def sub(s: str) -> str:
        for k, v in substitutions.items():
            s = s.replace(k, v)
        return s

    game_args = [sub(a) for a in game_args]

    if not game_args:
        game_args = [
            "--username",
            username,
            "--version",
            version_name,
            "--gameDir",
            str(game_dir),
            "--assetsDir",
            str(assets_dir),
            "--assetIndex",
            asset_index_id,
            "--uuid",
            auth_data["id"] if auth_data else (offline_uuid or "00000000-0000-0000-0000-000000000000"),
            "--accessToken",
            auth_data["access_token"] if auth_data else "0",
            "--userType",
            "msa" if auth_data else "legacy",
        ]

    natives_path = base / "versions" / mc_version / "natives"

    extra_mac = ["-XstartOnFirstThread"] if platform.system() == "Darwin" else []
    jvm_args = build_jvm_args(
        java_version,
        ram_gb,
        performance_boost,
        user_java_args,
        extra_jvm,
    )
    cmd = [
        java,
        *extra_mac,
        *jvm_args,
        f"-Djava.library.path={natives_path}",
        f"-Djna.tmpdir={natives_path}",
        "-cp",
        classpath,
        main_class,
        *game_args,
    ]

    log(
        f"🚀 Launching Minecraft {mc_version} ({'Fabric' if profile_type == 'fabric' else 'Vanilla'})…"
    )
    log(f"   Main class: {main_class}")
    log(f"   Game dir:   {game_dir}")
    log(f"   RAM:        {ram_gb}GB")

    env = os.environ.copy()
    if use_dgpu:
        system = platform.system()
        if system == "Linux":
            env["__NV_PRIME_RENDER_OFFLOAD"] = "1"
            env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
            env["DRI_PRIME"] = "1"
            log("🎮 Running with Discrete GPU enabled (Linux)")
        elif system == "Windows":
            _set_windows_gpu_preference(java, log)
            log("🎮 Running with Discrete GPU enabled (Windows)")

    log_dir = game_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    game_log = log_dir / "launcher-game.log"
    log(f"   Game output: {game_log}")
    popen_kwargs = dict(
        cwd=str(game_dir),
        stdout=None,
        stderr=subprocess.STDOUT,
        env=env,
    )

    if platform.system() == "Windows":
        CREATE_NO_WINDOW = 0x08000000
        popen_kwargs["creationflags"] = CREATE_NO_WINDOW

    with game_log.open("w", encoding="utf-8", errors="replace") as output:
        popen_kwargs["stdout"] = output
        return subprocess.Popen(cmd, **popen_kwargs)
