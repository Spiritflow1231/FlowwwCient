import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import client_mods, modrinth

IID = "a" * 32


def _profile():
    return {"instance_id": IID, "mc_version": "1.21.1", "type": "fabric"}


class CatalogTests(unittest.TestCase):
    def test_catalog_is_fair_play_and_well_formed(self):
        catalog = client_mods.load_catalog()
        slugs = [m["slug"] for m in catalog["mods"]]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertIn("sodium", slugs)
        banned = {"freecam", "xray", "autoclicker", "reach", "killaura", "baritone"}
        self.assertFalse(banned & {s.replace("-", "") for s in slugs})
        for mod in catalog["mods"]:
            self.assertTrue(mod["title"] and mod["description"] and mod["category"])
        self.assertTrue(client_mods.preset_entries(catalog, "pvp"))
        self.assertTrue(client_mods.preset_entries(catalog, "performance"))

    def test_only_fabric_profiles_supported(self):
        self.assertTrue(client_mods.supports_profile(_profile()))
        self.assertFalse(client_mods.supports_profile({"type": "vanilla"}))


class InstallTests(unittest.TestCase):
    def test_installs_skips_installed_and_reports_failures(self):
        profile = _profile()
        entries = [
            {"slug": "sodium", "title": "Sodium"},
            {"slug": "lithium", "title": "Lithium"},
            {"slug": "ghost", "title": "Ghost"},
        ]

        def versions(slug, category, game_version, loader):
            if slug == "ghost":
                return []
            return [{"project_id": f"id_{slug}", "version_number": "1"}]

        installed_calls = []

        def fake_install(project_id, title, version, category, destination, prof, **_kw):
            installed_calls.append(project_id)
            return [{"project_id": project_id, "title": title, "filename": f"{title}.jar",
                     "enabled": True}], []

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(modrinth, "compatible_versions", versions), \
                mock.patch.object(modrinth, "install_mod_project_with_dependencies", fake_install), \
                mock.patch.object(modrinth, "installed_mod_project_ids",
                                  lambda p: {"id_lithium"}
                                  | {r["project_id"] for r in p["installed_content"]["mods"]}):
            records, failures, _warn = client_mods.install_entries(
                profile, entries, Path(tmp) / "mods"
            )
        self.assertEqual(installed_calls, ["id_sodium"])
        self.assertEqual(records[0]["slug"], "sodium")
        self.assertEqual(len(failures), 1)
        self.assertIn("Ghost", failures[0])
        self.assertEqual(profile["client_pack"], {"sodium": "id_sodium", "lithium": "id_lithium"})
        self.assertEqual(len(profile["installed_content"]["mods"]), 1)


class LocalSkinTests(unittest.TestCase):
    def test_copies_and_removes_skin_and_cape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skin, cape = tmp / "s.png", tmp / "c.png"
            skin.write_bytes(b"skin")
            cape.write_bytes(b"cape")
            game = tmp / "game"
            done = client_mods.sync_local_skin(game, "Flowww", skin, cape)
            self.assertEqual(done, ["skins", "capes"])
            base = game / "CustomSkinLoader" / "LocalSkin"
            self.assertEqual((base / "skins" / "Flowww.png").read_bytes(), b"skin")
            self.assertEqual((base / "capes" / "Flowww.png").read_bytes(), b"cape")
            client_mods.sync_local_skin(game, "Flowww", skin, None)
            self.assertFalse((base / "capes" / "Flowww.png").exists())

    def test_rejects_path_like_usernames(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(client_mods.sync_local_skin(Path(tmp), "../x", None, None), [])


if __name__ == "__main__":
    unittest.main()
