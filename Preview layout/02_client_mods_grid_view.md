# 02 – Client Mods GRID view (breakdown of `images/02_reference_client_mods_grid.png`)

The reference is an in-game style menu: a translucent dark panel over a blurred scene. In FlowwwClient this becomes a launcher page called **Client Mods** (the built-in PvP / performance pack). It is NOT an in-game overlay.

## Overall structure
```
+------------------------------------------------------------------+
|              MODS      SETTINGS      PROFILES   (centered tabs)   |
+------------+-----------------------------------------------------+
| preset     |  [ALL] [NEW] [HUD] [PERFORMANCE] [MECHANIC]  [search]|
| dropdown   |                                                     |
|            |  +---------+  +---------+  +---------+              |
|            |  | card    |  | card    |  | card    |   3 columns  |
|            |  +---------+  +---------+  +---------+              |
|            |  +---------+  +---------+  +---------+              |
| [save new] |                                                     |
| [reset]    |                                       scrollbar -> |
+------------+-----------------------------------------------------+
```

## Region A – Tab header
Small-caps tabs centered at the top: MODS (active, lighter text and underline or filled), SETTINGS, PROFILES. 12 px, letter-spaced, muted when inactive.
FlowwwClient: tabs inside the Client Mods page = **MODS | SETTINGS | PRESETS**. SETTINGS holds global options (install location, auto-update toggle). PRESETS lists saved presets.

## Region B – Left column (about 190 px wide)
- A dropdown with the current preset name ("Default") and a small X button to delete it.
- Bottom: two full-width buttons: "SAVE AS NEW PRESET" (neutral gray fill) and a second action (blue in the reference, "EDIT HUD LAYOUT"). We have no HUD editor, so the second button is **"RESET TO DEFAULT"**.
- A preset stores which client mods are enabled for the profile. Switching preset renames jars accordingly.

## Region C – Filter row
- Chips: ALL (active, filled blue #4890F0 in the reference), NEW (green accent chip), HUD, SERVER, MECHANIC. Chip height 30 px, 8 px radius, bold 11 px caps.
- FlowwwClient chips: **ALL, NEW, HUD, PERFORMANCE, MECHANIC**. Active chip uses our accent; others are translucent with a 1 px border.
- Search box at the far right (about 220 px) with a magnifier icon, placeholder "Search client mods…", filters while typing (debounce 200 ms).

## Region D – Mod cards (3-column grid, 12-16 px gap)
Each card (about 190x140 at 1360 width, grows with the window, minimum 2 columns below 1100 px):
```
+--------------------------------+
|        Mod name (15 bold)       |
|     short subtitle (11 muted)   |
|                                 |
| [   OPTIONS   ] [gear]          |
| [ ENABLED  (green)  ]           |
+--------------------------------+
```
- Card fill: dark, semi-transparent (about 55-65 percent black) with a 1 px border rgba(255,255,255,0.08), 10 px radius. Hover: border brightens and the card lifts 2 px (animated).
- OPTIONS button: dark gray fill, caps 11 px. The square gear button next to it opens the mod's config file/folder.
- Status button, full width, 34 px high, caps bold:
  - ENABLED: solid green (reference #289868, use our token `enabled`).
  - DISABLED: reference uses solid red (#C04050). Because our brand accent is also red, use an OUTLINED red button (transparent fill, red border and text) for DISABLED so it never looks like the primary PLAY button.
  - UNAVAILABLE for this Minecraft version: gray, locked, tooltip "No compatible release for <version>".
  - INSTALLING: animated progress inside the button.
- Clicking the status button installs the mod if it is missing (resolving dependencies), otherwise toggles enable/disable.

## Region E – Scrolling
Vertical scrollbar on the right, thin (6 px), thumb rgba(255,255,255,0.25). Use CTkScrollableFrame; build cards lazily (first 12, rest after idle) so the page opens instantly.

## Content of the grid
Cards come from `assets/client_mods.json` (name, category, description, Modrinth query/slug, config path). Categories: PERFORMANCE, HUD, MECHANIC. Show only legal, fair-play mods (no x-ray, auto-clicker, reach or hitbox mods). Versions are resolved from Modrinth at install time for the profile's Minecraft version and Fabric.

## Header button
At the top right of the page: **Install PvP pack** (primary button) installs every available card in one go with progress and reports which ones were unavailable.
