# Preview layout – FlowwwClient redesign pack

This folder is the design reference for the FlowwwClient launcher (Python / CustomTkinter, `RevoMC/RevoMC-main`).
Read the files in this order:

| File | What it is |
|---|---|
| `images/00_current_launcher_ui.png` | How the launcher looks today (problems listed in `04_current_ui_problems.md`) |
| `images/01_reference_mods_list_view.png` | Reference for the profile **Mods / content list** page |
| `images/02_reference_client_mods_grid.png` | Reference for the **Client Mods grid** page |
| `images/03_reference_background.jpg` | Reference for the background mood |
| `images/bg_1920x1080.jpg` | The background to ship. Copy it to `RevoMC/RevoMC-main/assets/bg.jpg` |
| `01_mods_list_view.md` | Region-by-region breakdown of the list view |
| `02_client_mods_grid_view.md` | Region-by-region breakdown of the grid view |
| `03_theme_and_background.md` | Colors, glass-panel recipe, typography, spacing, motion |
| `04_current_ui_problems.md` | What is wrong in the current UI and must be fixed |
| `05_functional_requirements.md` | Every behaviour that must work (Modrinth, installed lists, skin, crash safety) |
| `theme_tokens.json` | Machine-readable color/spacing tokens |

## Rules
- The reference screenshots come from third-party software and are for LAYOUT AND STYLE ONLY.
  Do not copy their names, logos, icons, mod lists or artwork. Build everything from our own widgets and the FlowwwClient name.
- Keep what already works (profiles, accounts, install & play, Modrinth browse, Microsoft login). Keep the existing red accent for primary actions.
- The theme is dark translucent glass over the purple-blue gradient, with light text.
