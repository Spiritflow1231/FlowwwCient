import os
import re
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH).resolve()
VERSION_FILE = PROJECT_ROOT / "version_info.txt"
DEBUG_BUILD = os.environ.get("FLOWWWCLIENT_DEBUG", "").lower() in {"1", "true", "yes"}
BUILD_NAME = "FlowwwClient-debug" if DEBUG_BUILD else "FlowwwClient"

# Fail before analysis when the selected Python installation cannot build the
# Tkinter UI. This avoids producing an apparently successful but unusable app.
try:
    import tkinter
except ImportError as exc:
    raise RuntimeError("Tkinter is required to build FlowwwClient; install the OS Tkinter package.") from exc

# ---------------------------------------------------------------------------
# Auto-collect every package listed in requirements.txt.
# This means adding a new dependency to requirements.txt is the ONLY thing
# needed — the spec never has to be manually updated again.
# ---------------------------------------------------------------------------
auto_datas      = []
auto_hiddenimps = []

_req_text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
for line in _req_text.splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    # Strip version specifiers: customtkinter>=5.2.0 -> customtkinter
    pkg_name = re.split(r'[><=!;\[]', line)[0].strip()
    # Normalise pip name to importable name (hyphens -> underscores)
    import_name = pkg_name.replace('-', '_')
    try:
        d, b, h = collect_all(import_name)
        auto_datas      += d
        auto_hiddenimps += h
        print(f'[spec] collected {import_name}: {len(h)} hidden imports, {len(d)} data files')
    except Exception as exc:
        raise RuntimeError(f'Could not collect required dependency {import_name}: {exc}') from exc

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=auto_datas,
    hiddenimports=[
        # Core app modules — explicit so PyInstaller never misses them
        # even if the import chain gets refactored.
        'core.auth',
        'core.updater',
        'core.installer',
        'core.modrinth',
        'core.launcher',
        'core.config',
        'core.java_manager',
        'ui.main_window',
        'ui.theme',
        # Merge auto-collected hidden imports from requirements.txt
        *auto_hiddenimps,
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
              name=BUILD_NAME, debug=DEBUG_BUILD, strip=True, upx=False,
              console=DEBUG_BUILD, windowed=not DEBUG_BUILD, target_arch='universal2')
    coll = COLLECT(exe, a.binaries, a.datas, strip=True, upx=False, name='FlowwwClient')
    app = BUNDLE(coll, name='FlowwwClient.app',
                 bundle_identifier='com.flowwwclient.launcher',
                 info_plist={
                     'NSHighResolutionCapable': True,
                     'NSPrincipalClass': 'NSApplication',
                     'NSAppleScriptEnabled': False,
                     'CFBundleShortVersionString': '1.0.7',
                 })
elif sys.platform.startswith('linux'):
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
              name=BUILD_NAME, debug=DEBUG_BUILD, strip=True, upx=False,
              console=DEBUG_BUILD)
    coll = COLLECT(exe, a.binaries, a.datas, strip=True, upx=False, name='FlowwwClient')
else:
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(f"Windows version resource not found: {VERSION_FILE}")

    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
              name=BUILD_NAME, debug=DEBUG_BUILD, strip=False, upx=False,
              console=DEBUG_BUILD, windowed=not DEBUG_BUILD,
              disable_windowed_traceback=not DEBUG_BUILD, icon=None,
              version=str(VERSION_FILE))