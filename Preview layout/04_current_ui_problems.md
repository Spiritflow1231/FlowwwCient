# 04 – Problems in the current UI (see `images/00_current_launcher_ui.png`)

1. **Skin render is bad**: flat, straight, low-res, with a thin white band on the head (hat/overlay layer mis-composited) and no pose. Replace with a proper 3/4 isometric 3D render (see `05`, section Skin).
2. **"Manage profiles" button and the big hero artwork card are wasteful.** Remove the button, remove the huge creeper art panel, and use that space for a BIG skin render of the selected account (at least 300x420 px, scaling with the window). Put a large **PLAY** button where "Manage profiles" was.
3. The lower-right panel is titled "Play" and only holds the skin; "Quick access" below it is cut off. Fix: title the page "Play", show Quick access fully (Edit profile, Browse mods, Settings, View logs) with equal button sizes.
4. The background is flat black. Use the gradient background and glass panels from `03`.
5. Every page needs a visible page title at the top (Play, Profiles, Accounts, Settings, Logs).
6. Edit profile: sections (Mods, Resource Packs, Shader Packs, Datapacks, Modpacks) show nothing and no Browse results. The heading and the search placeholder say "Mods" in every section. Installed mods are not listed. Fix per `05` Phase 0 and 1.
7. Navigation and page switches are instant and jumpy. Add the motion rules from `03`.
8. Profile cards are inconsistent. Use fixed-height rounded cards with Edit / Show Folder / Delete always visible on the right.
9. The skin does not appear in the game for offline accounts. Fix per `05` Skin B.
