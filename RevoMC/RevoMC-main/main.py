import sys
import platform

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
    if _failed:
        if sys.stderr is not None:
            print("SMOKE TEST FAILED:", file=sys.stderr)
            for _f in _failed:
                print(f"  {_f}", file=sys.stderr)
        sys.exit(1)
    if sys.stdout is not None:
        print("SMOKE TEST PASSED")
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
