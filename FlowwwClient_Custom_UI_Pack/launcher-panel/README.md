# FlowwwClient control panel

This is a standalone CustomTkinter desktop utility. It is not automatically integrated into the original launcher window.

## Start

```bash
python -m pip install -r requirements.txt
python main.py
```

Select your Minecraft instance folder first. `Game Mods` then lets you import `.jar` files, rename `.jar` to `.jar.disabled` to disable for the next restart, re-enable them, and remove files after confirmation. Use with care and do not disable required Fabric/API dependencies unless you understand the consequences.

`Client Mods` config is written to `<selected-instance>/config/flowwwclient.json`. The companion Fabric mod reads its nametag settings. Motion blur values are saved but no blur renderer is implemented yet.
