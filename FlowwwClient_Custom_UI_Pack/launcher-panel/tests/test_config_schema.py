import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ConfigSchemaTests(unittest.TestCase):
    def test_source_has_expected_shared_config_keys(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        for key in ("nametagEnabled", "nametagSymbol", "nametagColor", "nametagScale", "motionBlurEnabled", "motionBlurStrength"):
            with self.subTest(key=key):
                self.assertIn(key, source)

    def test_companion_mod_and_panel_use_same_config_filename(self):
        java = (ROOT.parent / "fabric-mod" / "src/main/java/com/flowwwclient/FlowwwClientConfig.java").read_text(encoding="utf-8")
        self.assertIn('resolve("flowwwclient.json")', java)
        self.assertIn('"flowwwclient.json"', (ROOT / "main.py").read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
