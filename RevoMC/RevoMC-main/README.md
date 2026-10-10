# FlowwwClient

A custom, lightweight Minecraft Java launcher that auto-installs **Sodium**, **Iris Shaders**, **Lithium** and **FerriteCore** so you never have to hunt for mods manually again. Optimised for low end computers and gamers trying to squeeze the maximum performance out of the game with minimal setup.

FlowwwClient provides a premium-style interface while preserving the real Minecraft install and launch flow.

<img width="2018" height="1492" alt="image" src="https://github.com/user-attachments/assets/09829429-8c4c-4a16-a8aa-db97e608f1b5" />




---

## Features

- 🟢 One-click install of Minecraft + Fabric + mods
- 🟢 Sodium (high-performance renderer — replaces OptiFine's FPS boost)
- 🟢 Iris Shaders (shader pack support)
- 🟢 Lithium (server-side logic optimisation)
- 🟢 FerriteCore (RAM usage reduction)
- 🟢 Auto-downloads Java (Java 8/17/21/25 based on MC version) — no manual Java install needed
- 🟢 Dedicated GPU Support: Automatically enables dGPU mode on hybrid graphics systems (Windows Registry & Linux Prime)
- 🟢 Multiple profiles — run vanilla and modded side by side
- 🟢 Dedicated navigation for Home, Profiles, Mods, Modpacks, Resource Packs, Shaders, Accounts, Settings, and Console
- 🟢 Per-profile mod toggles — enable or disable individual mods per profile
- 🟢 Profile content manager with live Modrinth search for mods, resource packs, modpacks, datapacks, and shader packs
- 🟢 Per-profile game directories for mods, resource packs, shaders, worlds, and settings
- 🟢 Imports vanilla and Fabric `.mrpack` modpacks as separate isolated profiles
- 🟢 Vanilla profiles support all MC versions including the latest
- 🟢 Fabric profiles only show versions with confirmed Fabric support
- 🟢 Automatic retry on failed downloads
- 🟢 Configurable RAM allocation
- 🟢 Console log so you can see exactly what's happening
- 🟢 Safe Auto-Updater: Built-in self-updating mechanism that verifies new binaries before replacing them
- 🟢 Available for Windows, macOS, and Linux

---

## Download

Grab the latest release for your platform from the [Releases](https://github.com/revolution737/RevoMC/releases) page — no Python or Java install required, just download and run.

- **Windows** — download `RevoMC-windows.zip`, extract, run `RevoMC.exe`
- **macOS** — download `RevoMC-macos.zip`, extract, run `RevoMC.app`
- **Linux** — download `RevoMC-linux.zip`, extract, run `./RevoMC/RevoMC`

---

## ⚠️ Security Warning

When you first run RevoMC you may see a security warning from Windows or macOS — this is because the app is not yet code signed.

**Windows:** Click **More info** → **Run anyway**
**macOS:** Go to **System Settings → Privacy & Security** → Click **Open Anyway**

This is safe to do — RevoMC is fully open source and you can inspect every line of code in this repo.

---

## Running from Source

If you'd prefer to run from source instead of the pre-built executable:
```bash
# 1. Clone the repo
git clone https://github.com/revolution737/RevoMC.git
cd RevoMC

# Linux only — tkinter is not bundled with system Python
# Fedora:  sudo dnf install python3-tkinter
# Ubuntu:  sudo apt install python3-tk

# 2. Install Python dependencies (Python 3.11+ required)
pip install -r requirements.txt

# 3. Run the launcher
python main.py
```

## Windows Executable Builds

The project uses `main.py` as its application entry point and PyInstaller's
`revomc.spec` to build a single-file Windows GUI executable. The spec
collects dependency data and hidden imports from `requirements.txt`, including
the CustomTkinter UI assets; the project does not currently include a custom
application icon. The Windows release is windowed.

To build locally on Windows:

```powershell
builds\build_windows.bat
```

The script uses Python 3.12 and writes the single-file executable to
`dist/release/FlowwwClient.exe`. On Linux, `builds/build_linux.sh` builds the
Linux app; it requires Python 3.12 with Tkinter installed.

For a console-enabled troubleshooting executable, run this in PowerShell:

```powershell
$env:FLOWWWCLIENT_DEBUG = "1"
python -m PyInstaller revomc.spec --clean --noconfirm --distpath dist/debug --workpath build/pyinstaller-debug
Remove-Item Env:FLOWWWCLIENT_DEBUG
```

GitHub Actions builds and smoke-tests the executable on a Windows runner on
pushes to `main` and on manual dispatch. To download it, open the repository's
**Actions** tab, select a **Build FlowwwClient for Windows** run, then download
the `FlowwwClient-Windows` ZIP artifact. The executable itself is a single-file application;
downloaded Java runtimes, Minecraft data, and launcher configuration are stored
in the user's writable `~/.revomc` directory (not in the application
installation directory).

The executable contains Windows product metadata but is not code-signed. A
verified publisher identity requires an appropriate signing certificate.

---

## First Time Use

1. **Enter your username** (top-right field) — this is the in-game name shown to other players
2. Click on the default latest releases for fabric or vanilla or click on **+ New** to create a profile — pick a name, type (Vanilla or Fabric+Mods), version, and which mods to include
3. **Adjust RAM** — 2–4 GB is fine for modded play
4. Click **⬇ Install & Play** — this downloads:
   - Java runtime (first time only, ~50 MB)
   - Minecraft client jar + libraries + assets (~300 MB first time)
   - Fabric loader (if Fabric profile)
   - Selected mods from Modrinth (if Fabric profile)
   - After all dowloads are complete, it launches the game.

---

## File Structure
```
RevoMC/
├── main.py               # Entry point (includes pre-release smoke testing)
├── requirements.txt
├── revomc.spec           # PyInstaller build spec with auto-dependency collection
├── core/
│   ├── installer.py      # Dependency-aware downloader for MC, Fabric, and mods
│   ├── launcher.py       # Builds JVM args, dGPU environment, and launches the game
│   ├── config.py         # Saves your settings and tracks profile versions
│   ├── updater.py        # Safe self-updater using GitHub releases
│   ├── auth.py           # Microsoft OAuth2 PKCE login flow
│   └── java_manager.py   # Auto-downloads and manages Java runtime
└── ui/
    └── main_window.py    # CustomTkinter UI
```

RevoMC stores launcher data in `~/.revomc/` and shares game files with the standard `.minecraft` folder:
```
~/.revomc/
├── config.json
├── runtime/              # Bundled Java JRE (auto-downloaded based on MC version)
├── versions/             # Vanilla + Fabric version profiles
├── libraries/            # Shared JARs for Minecraft and Fabric
└── instances/            # Isolated game data for each launcher profile

~/.revomc/instances/<profile-id>/  # Each profile's game directory
├── mods/
├── resourcepacks/
├── shaderpacks/
└── saves/                 # Profile-specific worlds and their datapacks

~/.minecraft/             # Shared Minecraft assets and pre-existing worlds
└── assets/               # Shared game assets
```

Use a profile's **Edit** action to open its content manager. Mod and pack downloads are installed only into that profile's game directory. Datapacks require selecting a world in that profile; worlds found in the standard `.minecraft/saves` directory are copied into each profile the first time it launches. Modpack imports support vanilla and Fabric only; Forge and NeoForge packs are rejected rather than partially installed.

---

## Notes

- **Microsoft login is supported** — switch to "Microsoft" mode in the launcher header and sign in with your Microsoft account to play on online-mode servers. Your session persists between launches via refresh tokens.
- **Offline mode still works** — if you don't have a Microsoft account or prefer LAN/offline play, use "Offline" mode with any username.
- **Skins and capes** — selecting local skins or capes for offline accounts is not supported. Offline accounts are not Microsoft-authenticated, and their appearance may not be available on online-mode servers.
- **Dedicated GPU (dGPU) mode** — enabled by default on systems with hybrid graphics. On Windows, it sets a registry key (`HKCU\Software\Microsoft\DirectX\UserGpuPreferences`) to tell Windows to run the Java runtime on your high-performance GPU. On Linux, it uses the `DRI_PRIME=1` environment variable.
- **Safe Auto-Updates** — RevoMC checks GitHub for launcher updates and safely installs them by downloading to a temporary directory and running a smoke-test on the new binary. If the new binary is missing libraries or corrupt, the update automatically aborts without breaking your currently installed version.
- Mod downloads use the [Modrinth](https://modrinth.com) API. Occasionally their servers may drop a connection mid-download — if this happens just hit **Install / Update** again to retry.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Security warning on launch | See the ⚠️ Security Warning section above |
| Download fails mid-way | Hit Install / Update again — downloads retry automatically |
| Game crashes on launch | Check the console — usually a missing native or wrong Java version |
| Mod not found for version | That mod hasn't released for that MC version yet — try a slightly older version |
| Black screen | Make sure your GPU drivers are up to date (Sodium uses OpenGL) |
| Linux: `ModuleNotFoundError: _tkinter` | Install tkinter: `sudo dnf install python3-tkinter` (Fedora) or `sudo apt install python3-tk` (Ubuntu) |
| macOS: app won't open | Go to System Settings → Privacy & Security → Open Anyway |
