import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core import fps_boost, launcher


def _jar(path: Path, mod_id: str, project_id: str | None = None):
    meta = {"schemaVersion": 1, "id": mod_id, "version": "1"}
    if project_id:
        meta["custom"] = {"modrinth": {"project_id": project_id}}
    with zipfile.ZipFile(path, "w") as jar:
        jar.writestr("fabric.mod.json", json.dumps(meta))


class FpsBoostTests(unittest.TestCase):
    def test_removes_only_known_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = Path(tmp)
            mods = instance / "mods"
            mods.mkdir()
            _jar(mods / "hud-plus-1.0.jar", "hudplus")
            _jar(mods / "blur.jar.disabled", "x", "M5szsQT4")
            _jar(mods / "sodium.jar", "sodium", "AANobbMI")
            _jar(mods / "fabric-api.jar", "fabric-api")
            _jar(mods / "customskinloader.jar", "customskinloader", "idMHQ4n2")
            profile = {"installed_content": {"mods": [
                {"filename": "hud-plus-1.0.jar", "project_id": "EqwpK4rm"},
                {"filename": "sodium.jar", "project_id": "AANobbMI"},
            ]}, "client_pack": {"hud-plus": "EqwpK4rm"}}
            removed = fps_boost.remove_extras(profile, instance)
            self.assertEqual(sorted(removed), ["blur.jar.disabled", "hud-plus-1.0.jar"])
            self.assertEqual(sorted(p.name for p in mods.iterdir()),
                             ["customskinloader.jar", "fabric-api.jar", "sodium.jar"])
            self.assertEqual([r["filename"] for r in profile["installed_content"]["mods"]],
                             ["sodium.jar"])
            self.assertNotIn("client_pack", profile)

    def test_vanilla_profiles_are_rejected(self):
        with self.assertRaises(RuntimeError):
            fps_boost.apply({"type": "vanilla", "mc_version": "1.21.1"})

    def test_jvm_flags_stay_simple(self):
        args = launcher.build_jvm_args(21, 4)
        self.assertIn("-XX:+UseG1GC", args)
        self.assertNotIn("-XX:G1NewSizePercent=30", args)
        self.assertNotIn("-XX:InitiatingHeapOccupancyPercent=15", args)


if __name__ == "__main__":
    unittest.main()
