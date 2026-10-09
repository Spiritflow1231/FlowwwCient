import unittest

from core.java_manager import get_required_java_version


class JavaVersionSelectionTests(unittest.TestCase):
    def test_selects_java_version_required_by_minecraft_release(self):
        cases = {
            "1.16.5": 8,
            "1.17": 17,
            "1.20.4": 17,
            "1.20.5": 21,
            "1.21.1": 21,
            "1.21.4": 21,
            "26.1": 25,
        }
        for minecraft_version, java_version in cases.items():
            with self.subTest(minecraft_version=minecraft_version):
                self.assertEqual(
                    get_required_java_version(minecraft_version), java_version
                )

    def test_rejects_unrecognized_major_version(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Minecraft version"):
            get_required_java_version("2.0")


if __name__ == "__main__":
    unittest.main()
