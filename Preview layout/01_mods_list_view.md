# 01 – Mods / content LIST view (breakdown of `images/01_reference_mods_list_view.png`)

Reference aspect ratio is about 1.65:1, the same as our 1360x820 launcher window, so proportions below can be applied directly.
Reference sizes are given for a 1360x820 window. Everything must still work at 1040x660 and when maximized (use grid weights, not fixed pixel widths, for the big areas).

## Overall structure
```
+------+------------------------------------------------------------+
| rail | TOP BAR: quick-switch row ........ account pill  icons      |
|      +--------------------------------------+---------------------+
|      | LIST PANEL (about 66 percent)        | DETAILS PANEL       |
|      |  header + tabs                       |  (about 34 percent) |
|      |  sub-row (folder link, count)        |  breadcrumb         |
|      |  scrolling mod rows                  |  title, description |
|      |                                      |  link button        |
|      |                                      |  --- bottom block   |
|      |                                      |  version + PLAY     |
+------+--------------------------------------+---------------------+
```

## Region A – Left rail (about 70 px wide, full height)
- Logo mark at the top, then 5 stacked icon buttons (play, mods, servers, news, store), settings at the bottom, small version text under it.
- Active item: lighter rounded background plus accent-colored icon. Inactive: muted gray icon. Hover: lighter background.
- FlowwwClient: keep our existing labeled sidebar (Play, Profiles, Accounts, Settings, Logs). In the profile-edit context the same sidebar switches to: Back to Profiles, Overview, Mods, Resource Packs, Shader Packs, Datapacks, Modpacks, Client Mods (see `05`).

## Region B – Top bar (about 64 px high)
- Left: small caps label "QUICK PLAY" and a row of 8 square tiles (36 px, 10 px radius, dark fill, 1 px border) with a colored icon each.
- Right: account pill (32 px avatar, username, small subtitle), a mail icon button, and a close X.
- FlowwwClient: top bar shows the app name, the Offline / Microsoft switch and the username entry (already exists). Optional: a quick-switch row where each profile is a tile (initial letter or icon, active one has an accent border). Do not add social/mail buttons.

## Region C – List panel header
- Left: pack icon (about 40 px) and the pack title in bold, in an amber/orange accent (#F09000 in the reference). Right: three pill tabs "Mods" (active, lighter fill), "Information", "Gallery", each with a small icon.
- FlowwwClient: icon = profile icon, title = profile name, tabs per content section: **Installed | Browse**. Tab switch must animate (see `03`).
- Under the header, one thin row: left side a blue link-style "Open mods folder" (#1098C0), right side muted text "Showing N mods". In our app the link text follows the section ("Open resource packs folder", ...). Browse tab shows "Showing N results · page X".

## Region D – Mod rows (the scrolling list)
Row, about 72-84 px high, separated by 1 px lines or an 8 px gap, no zebra stripes:
```
[ icon 48 ]  Name (bold 14-15 px, white)                    Enabled [x]
             By author  (11 px muted, tiny verified dot)    [ version dropdown v ]
```
- Icon: 48 px, 10 px radius, dark tile, image from the project icon (fallback: first letter on accent tint).
- Right side: tiny "Enabled" label with a green check box above, and under it a version dropdown (about 170 px wide, fill #1C1E24, 1 px border #2B2E32, chevron at the right, text like `v1.1.2`).
- Hover: row fill lighter (#1A1B1F -> #20232A). Selected row: 1 px accent border and the details panel shows that mod.
- FlowwwClient behaviour:
  - Switch (CTkSwitch) enables/disables by renaming `.jar` <-> `.jar.disabled`.
  - Version dropdown lists the installed version first, then other versions compatible with the profile's Minecraft version and loader. Choosing another version downloads it and replaces the old file (confirm dialog, keep the old file until the new one is verified).
  - A kebab (three dots) or small trash button for Remove and Open folder. Dependencies that other mods need show a small "Required by X" label and cannot be removed without a warning.
  - Rows for items without a record in `installed_content` (manually dropped jars) still appear, with name/version read from `fabric.mod.json`.
- Empty state: centered muted text and a primary button ("Browse mods").

## Region E – Details panel (right, about 34 percent)
- Top: breadcrumb "< Back / Section / Name" in muted text, then the title (bold 20 px).
- Description paragraph (12 px, muted, wrapped, max about 6 lines, "Show more").
- A green outlined button "View on Modrinth" (opens the project page in the browser).
- FlowwwClient: when no mod is selected, this panel shows the profile summary (Minecraft version, loader + loader version, number of mods, memory, Java). When a row is selected it shows that mod's description, author, downloads, categories, dependencies and the Modrinth link.

## Region F – Bottom action block (inside the details panel, pinned to the bottom)
- Label "Selected Version", a pill with the version text (about 80 px wide, edit icon with a small status dot), a square back-arrow button (44 px), and a large LAUNCH GAME button (about 250x48, 10 px radius, bold uppercase, game icon, solid green #18E068 in the reference).
- FlowwwClient: pill = profile's Minecraft version, back arrow = Back to Profiles, big button = **PLAY** (our red accent, not green) with the same states as the Play page (Install & Play, progress, disabled when no account).

## Colors seen in the reference (sampled)
| Use | Hex |
|---|---|
| Outer background | #0C0E12 / #0A0C10 |
| Panel | #111418 / #15161B |
| Row | #1A1B1F / #1C1E24 |
| Border / divider | #2B2E32 |
| Primary text | #FFFFFF |
| Muted text | #9C9FA5 |
| Green (enabled, launch) | #18E068 / #20C070 |
| Link blue | #1098C0 |
| Title amber | #F09000 |
In FlowwwClient use the tokens from `03_theme_and_background.md`, not these raw values.

## States to implement
Row: normal, hover, selected, disabled-mod (dimmed text + "Disabled" label), updating (small spinner), incompatible (amber "Not compatible with <version>" label and the switch locked).
