# FlowwwClient Custom UI Pack

A source bundle with two parts:

1. **`launcher-panel/`** — a standalone premium red/black desktop control panel. It lets you select a Minecraft instance, manage `.jar` mods in that instance's `mods` folder (enable/disable by renaming, import, remove), and edit the shared FlowwwClient JSON settings. The panel is a separate utility; it is **not automatically wired into the existing FlowwwClient launcher window** without merging its page into your existing `ui/main_window.py`.
2. **`fabric-mod/`** — a Fabric 1.21.1 client-mod project with a Right Shift settings screen and a real configurable `ঌ` marker appended to player name labels in your own client. Nameplate color and global label scale settings are used by the renderer mixin. Config lives at `<instance>/config/flowwwclient.json`, the same path the desktop panel writes when you select an instance.

## What is and isn't implemented

- The UI panel uses persistent settings, animated page transitions, enable/disable switches, sliders, color choices, custom module cards, file import/removal, and per-instance config output.
- The Fabric mod implements the `ঌ` name-label marker and applies its color and scale settings.
- Motion Blur has a control/config value in the panel and in-game screen, but **a real motion-blur rendering effect is not implemented in this starter**. The UI labels this as settings-only; it does not claim blur is active.
- A client-side mod cannot reliably know whether other players are running FlowwwClient. When enabled, this starter marks player name labels visible to your client; it does not prove those players use FlowwwClient.
- The desktop panel can manage actual `.jar` files in a selected profile's `mods` directory. It cannot safely hot-unload an already loaded Fabric mod; enable/disable changes take effect on the next game start.
- The companion source project is targeted at Minecraft 1.21.1, Java 21, Fabric Loader and Fabric API. It has not been compiled on this offline creation environment. Use the included GitHub Actions workflow template or Gradle on a networked machine to build and validate it.

## Desktop panel: run locally

From `launcher-panel/`:

```bash
python -m pip install -r requirements.txt
python main.py
```

Select your Minecraft instance folder in **Profiles**, then select its `mods` folder in **Game Mods**. The panel writes settings to the selected instance's `config/flowwwclient.json`.

## Build the Fabric mod

You need Java 21 and network access for Gradle to download Minecraft/Fabric dependencies.

From `fabric-mod/`:

```bash
gradle build
```

The JAR should be created under `fabric-mod/build/libs/`. Copy the normal (non-sources) `flowwwclient-1.0.0.jar` into the target instance's `mods/` folder. Launch Fabric 1.21.1 and press **Right Shift** in-game to open the settings screen.

## Optional GitHub Actions build

Copy `workflow-template/build-flowwwclient-mod.yml` to the repository's `.github/workflows/build-flowwwclient-mod.yml`, making sure the `fabric-mod/` directory is at repository root as laid out in this pack. Push the source folder and workflow, then download the `FlowwwClient-Fabric-Mod` artifact from Actions. This is separate from your existing Python launcher's Windows EXE workflow.

## Install into an existing launcher repository

Extract this pack into your repo as a separate folder first. Review `git status --short` and `git diff --check`. The current launcher build workflow will not automatically replace your existing desktop UI just because this folder is added; integration with the current launcher requires wiring the control-panel page into its actual `main_window.py` and packaging rules. Do not overwrite your existing UI files blindly.
