import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ui.main_window import _resource_path


class BrandImageTests(unittest.TestCase):
    def test_main_brand_image_is_a_valid_jpeg_asset(self):
        image_path = _resource_path("assets/Minecraft.jpg")

        self.assertTrue(image_path.is_file())
        with Image.open(image_path) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertGreater(image.width, 0)
            self.assertGreater(image.height, 0)
            image.verify()

    def test_resource_path_uses_the_frozen_application_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            with patch.object(sys, "_MEIPASS", str(bundle_root), create=True):
                self.assertEqual(
                    _resource_path("assets/Minecraft.jpg"),
                    bundle_root / "assets" / "Minecraft.jpg",
                )


if __name__ == "__main__":
    unittest.main()
