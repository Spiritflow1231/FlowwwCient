import tempfile
import unittest
from pathlib import Path

from core import skin_loader


class SkinLoaderTests(unittest.TestCase):
    def test_copies_and_removes_skin_and_cape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skin, cape = tmp / "s.png", tmp / "c.png"
            skin.write_bytes(b"skin")
            cape.write_bytes(b"cape")
            game = tmp / "game"
            self.assertEqual(skin_loader.sync_local_skin(game, "Flowww", skin, cape),
                             ["skins", "capes"])
            base = game / "CustomSkinLoader" / "LocalSkin"
            self.assertEqual((base / "skins" / "Flowww.png").read_bytes(), b"skin")
            skin_loader.sync_local_skin(game, "Flowww", skin, None)
            self.assertFalse((base / "capes" / "Flowww.png").exists())

    def test_rejects_path_like_usernames(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(skin_loader.sync_local_skin(Path(tmp), "../x", None, None), [])

    def test_vanilla_profile_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(skin_loader.ensure_installed({"type": "vanilla"}, Path(tmp)))


if __name__ == "__main__":
    unittest.main()
