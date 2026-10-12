# 05 – Functional requirements (what must work)

Project: FlowwwClient launcher, Python / CustomTkinter, folder `RevoMC/RevoMC-main`. Work through the phases in order. Visual details live in `01`-`04`; this file says what must behave correctly. Keep all existing working features. Never type shell commands into source files.

## Phase 0 – Debug first: Edit profile shows nothing, Browse is empty
Symptom: Manage profiles -> Edit -> Mods / Resource Packs / Shader Packs / Datapacks / Modpacks show no projects and no installed items. Before a recent change, mods could be added from Browse.
1. Reproduce headless: call `core.modrinth.search_projects` for every category with the current profile's Minecraft version (1.21.11) and Fabric. Print the request URL, facets, HTTP status, result count and any exception.
2. Check and fix the usual causes: wrong facets per project type (for resourcepack, shader, datapack do NOT filter by `categories:fabric`; mods and modpacks filter by loader; shaders optionally by iris/optifine), facet format (`versions:1.21.11`), missing User-Agent, URL encoding of the facets JSON, wrong index/limit/offset, exceptions swallowed in the worker thread, the `_request_serial` stale check discarding every result, results frame hidden or not re-gridded after `grid_remove()` of other widgets, the editor window/page not being created when Edit is clicked.
3. If Modrinth returns 0 results for the newest Minecraft version, show a clear message and a "Show results for the latest 3 supported versions" toggle. If a request fails, show the real error text and a Retry button inside the results area. Never show a blank panel.
4. Add tests (mock the HTTP layer) for the facet builder per category and for rendering cards from a fake response.
5. The same fix must apply to ALL five sections, not only Mods.

## Phase 1 – Profile editor is an in-app page with its own sidebar
- Replace the separate `ProfileEditorWindow` (Toplevel) with a page inside the main window. Clicking Edit on a profile switches the left navigation to a profile context: "Back to Profiles", profile name + "Minecraft <version> · <loader> <loader version>", then Overview, Mods, Resource Packs, Shader Packs, Datapacks, Modpacks, Client Mods.
- Each content section has two tabs, **Installed** and **Browse**, laid out as in `01_mods_list_view.md`. Heading and search placeholder match the section ("Search mods…", "Filter installed mods…"). Never show "Mods" inside another section.
- Browse shows only items compatible with the profile's Minecraft version (and loader where relevant); anything already installed shows "Installed" (disabled) and cannot be installed twice.

## Phase 2 – Redesign
Implement the look from `01`, `02`, `03`, using `theme_tokens.json` and `assets/bg.jpg`. Profiles page: fixed-height (about 80 px) rounded cards, name + "version · loader · loader version · N mods" on the left, Edit / Show Folder / Delete always visible on the right, ACTIVE badge and accent border on the active profile, big "+ New profile" button on top. Settings, Accounts and Logs use the same glass panels and page titles.

## Phase 3 – Play (home) page
- REMOVE the "Manage profiles" button and the oversized hero artwork card.
- Hero, left to right: (a) tall panel with the player's 3D skin render, BIG (at least 300x420, scales with the window); (b) center column: small label, "Ready to play?", active profile name + details, a profile dropdown to switch profile, and a large PLAY / Install & Play button where "Manage profiles" used to be; (c) right card: Memory allocation, progress bar and status text (no second play button).
- Delete the bottom-right panel titled "Play" that only holds the skin. Fix the cut-off "Quick access" (Edit profile, Browse mods, Settings, View logs) with equal button sizes.
- Every page has a title at the top.

## Phase 4 – Skin
A) Launcher preview (`core/skins.py` + UI). Build a proper 3/4 isometric 3D render in PIL/NumPy:
- From the 64x64 skin (legacy 64x32: mirror the left limbs): head, hat layer (slightly larger), body, jacket, both arms (classic 4 px or slim 3 px by the account's `skin_model`), both legs, sleeve and pants overlays. Alpha-composite the overlay layers correctly (the current render shows a white band on the head).
- About 20 degrees yaw and 10 degrees pitch, per-face shading (top lighter, sides darker), arms slightly away from the body, one leg slightly forward. Render at 4x and downscale with LANCZOS. Transparent background.
- Cache by (uuid, skin mtime, model); re-render only when the skin or the selected account changes. If no skin is set use the default Steve texture (generate one or bundle it in assets/).
- Use the same render (head only) in the Accounts list.
B) Skin visible INSIDE the game for offline accounts:
- Use the CustomSkinLoader Fabric mod from Modrinth. For Fabric profiles with an offline account install it automatically, matching the profile's Minecraft version; if no compatible version exists log a clear warning and skip.
- Before launch copy the selected account's `skin.png` and `cape.png` (if any) into `<instance>/CustomSkinLoader/LocalSkin/skins/<username>.png` and `.../capes/<username>.png`, and write or update the CustomSkinLoader config so LocalSkin is the first loader. Read the mod's own documentation for exact folder names and config format; do not guess. Handle classic/slim as the mod requires. Log what was written.
- Accounts page note: "Offline skins and capes are visible on your own client (singleplayer, LAN, offline servers). Other players on online-mode servers will not see them."

## Phase 5 – Installed lists, dependencies, loader
- Installed tab lists EVERY `.jar` and `.jar.disabled` in `<instance>/mods`, every pack in `resourcepacks`, `shaderpacks` and each world's `datapacks`, even without an `installed_content` record. Name/version from `fabric.mod.json` (mods) or `pack.mcmeta` (packs); fallback to the filename. Row layout and behaviours as in `01_mods_list_view.md`.
- Whenever the launcher installs mods itself (default profile mods, performance mods, PvP pack, CustomSkinLoader, dependencies) write an `installed_content` record (project_id, version_id, filename, title), so Browse shows "Installed".
- Installing a mod from Browse resolves Modrinth dependencies: install every `required` dependency recursively (skip installed; pick the version matching the profile's Minecraft version and loader), warn about `incompatible` ones, always ensure Fabric API on Fabric profiles. The status bar names what was added ("Installed Sodium + Fabric API").
- Fabric loader: fetch the latest STABLE loader from `https://meta.fabricmc.net/v2/versions/loader` (first entry with `stable == true`) at install time, upgrade older pinned loaders (the old one was 0.18.2), and show the loader version on profile cards and in Overview. `_is_installed_for_profile` returns False when the installed loader is older than the latest stable.

## Phase 6 – Client Mods (built-in PvP / performance pack)
- Page layout as in `02_client_mods_grid_view.md`.
- Data from a bundled, editable `assets/client_mods.json`: category, short description, and a Modrinth search query or slug per entry. Do NOT hardcode versions or file URLs. At install time resolve the project through the Modrinth API, choose the newest version compatible with the profile's Minecraft version and Fabric, download, verify sha512, record it. If there is no compatible version, show the card as "Unavailable for <version>" instead of failing.
- Cover with well-known Fabric mods found by searching Modrinth: performance (Sodium, Lithium, FerriteCore, ImmediatelyFast, Entity Culling, Krypton, Dynamic FPS), HUD / PvP utilities (keystrokes display, CPS counter, armor and potion status, coordinates, FPS counter), mechanics (zoom, freelook, toggle sprint/sneak). Only fair-play mods: no x-ray, auto-clickers, reach or hitbox changes. Verify each candidate exists and supports the profile version before enabling it by default.
- "Install PvP pack" installs all available entries with dependencies and progress. Toggling a card enables/disables the jar by renaming `.jar` <-> `.jar.disabled`. Presets store the enabled set.
- Be honest about latency: Krypton reduces in-game networking overhead; nothing here fixes bad Wi-Fi. Keep that note in Settings.

## Phase 7 – Motion
Implement the motion rules from `03_theme_and_background.md` (page/section slide+fade 160-200 ms, hover transitions, staggered rows, smooth progress, "Animations" setting).

## Phase 8 – Crash safety
- Always write the game's output to `<instance>/logs/launcher-game.log`. On a non-zero exit show the last 40 lines in the Logs page and an error banner.
- Pre-launch validation: read `fabric.mod.json` of each jar in `<instance>/mods`; if its declared Minecraft dependency does not match the profile version, rename it to `.jar.disabled` and log which one and why. Ensure Fabric API is present on Fabric profiles. Validate the JVM argument builder for Java 17 and Java 21 (no removed flags, Xms <= Xmx).

## Verify (after every phase)
1. `cd RevoMC/RevoMC-main && python -m compileall -q main.py core ui tests`
2. `python -m pytest tests -x -q`
3. `xvfb-run -a timeout 20 python main.py` (no Traceback; exit code 124 from the timeout is fine)
4. Take screenshots under xvfb of Play, Profiles, Edit/Mods (Installed and Browse), Client Mods and Accounts at 1360x820 and 1040x660; fix any clipped or overlapping widgets.
Commit after each phase (`git add -A`, make sure `assets/bg.jpg` and any new asset are included). Push to `main` only when all four checks pass for the last phase. If something cannot be verified, say so instead of claiming it works.
Final report per phase: done / not verified, the root cause found in Phase 0, and anything that must be tested on Windows.
