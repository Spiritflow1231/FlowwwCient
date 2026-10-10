import re
import unittest
from pathlib import Path


class WindowsVersionResourceTests(unittest.TestCase):
    def setUp(self):
        self.app_root = Path(__file__).parents[1]

    def test_required_executable_metadata(self):
        resource_path = self.app_root / "version_info.txt"
        resource = resource_path.read_text(encoding="utf-8")

        expected = {
            "ProductName": "FlowwwClient",
            "FileDescription": "FlowwwClient Minecraft Launcher",
            "OriginalFilename": "FlowwwClient.exe",
            "CompanyName": "FlowwwClient",
        }
        for field, value in expected.items():
            with self.subTest(field=field):
                entry = rf"StringStruct\('{re.escape(field)}', '([^']*)'\)"
                match = re.search(entry, resource)
                self.assertIsNotNone(match, f"Missing {field} in version resource")
                self.assertEqual(match.group(1), value)

    def test_windows_spec_passes_version_resource_to_executable(self):
        spec = (self.app_root / "revomc.spec").read_text(encoding="utf-8")
        self.assertIn('VERSION_FILE = PROJECT_ROOT / "version_info.txt"', spec)
        self.assertIn("version=str(VERSION_FILE)", spec)
        self.assertIn("if not VERSION_FILE.is_file():", spec)


if __name__ == "__main__":
    unittest.main()
