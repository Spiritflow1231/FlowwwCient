import sys
import platform
import os
from pathlib import Path

# ── Smoke test ────────────────────────────────────────────────────────────────
# Run with --smoke-test to verify all modules are importable in the frozen
# build. Used by build scripts and the updater before swapping the binary.
# Exits 0 on success, 1 on any import failure.
if "--smoke-test" in sys.argv:
    _failed = []
    _modules = [
        "core.auth", "core.config", "core.installer",
        "core.launcher", "core.java_manager", "core.modrinth", "core.updater",
        "ui.main_window", "ui.theme",
        "customtkinter", "certifi",
        "minecraft_launcher_lib",
        "minecraft_launcher_lib.microsoft_account",
    ]
    for _mod in _modules:
        try:
            __import__(_mod)
        except Exception as _e:
            _failed.append(f"{_mod}: {_e}")
    _result = (
        "SMOKE TEST FAILED:\n" + "\n".join(f"  {_failure}" for _failure in _failed)
        if _failed
        else "SMOKE TEST PASSED"
    )
    _diagnostics = os.environ.get("FLOWWWCLIENT_SMOKE_LOG")
    if _diagnostics:
        Path(_diagnostics).write_text(_result + "\n", encoding="utf-8")
    if _failed:
        if sys.stderr is not None:
            print(_result, file=sys.stderr)
        sys.exit(1)
    if sys.stdout is not None:
        print(_result)
    sys.exit(0)
# ─────────────────────────────────────────────────────────────────────────────

from ui.main_window import MainWindow
import tkinter as tk
from core.updater import check_and_update
import customtkinter as ctk

if platform.system() == "Linux":
    root = tk.Tk()
    dpi = root.winfo_fpixels("1i")
    root.destroy()
    scale = max(1.0, dpi / 96.0)  # 96 is the baseline DPI; floor to 1.0
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(scale)


def main():
    # Check for updates first (will exit if an update is applied)
    check_and_update()

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
