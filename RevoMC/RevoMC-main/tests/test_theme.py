import unittest

import customtkinter as ctk

from core.skin_render import render_player
from ui import main_window
from ui.motion import Motion, lerp_color
from ui.theme import (
    DEFAULT_THEME, apply_customtkinter_palette, color_map, get_theme,
    normalize_theme_name,
)


class ThemeTests(unittest.TestCase):
    def test_default_is_dark_purple(self):
        self.assertEqual(DEFAULT_THEME, "dark")
        self.assertEqual(get_theme()["BG_PRIMARY"], "#0B0A1A")
        self.assertEqual(get_theme()["ACCENT"], "#6C5CE7")

    def test_legacy_names_resolve_to_dark(self):
        for name in ("crimson", "overworld", "nether", "end", None, ""):
            self.assertEqual(normalize_theme_name(name), "dark")

    def test_palette_values_unique_per_theme(self):
        for name in ("light", "dark"):
            theme = get_theme(name)
            values = [v.lower() for k, v in theme.items() if k not in ("ACCENT_TEXT",)]
            # shared brand colours may repeat across themes, but not inside one
            self.assertEqual(len(values), len(set(values)), name)

    def test_no_red_accent(self):
        for name in ("light", "dark"):
            self.assertEqual(get_theme(name)["ACCENT"], "#6C5CE7")

    def test_color_map_skips_identical(self):
        mapping = color_map(get_theme("light"), get_theme("dark"))
        self.assertNotIn("#6c5ce7", mapping)
        self.assertEqual(mapping["#fdfcff"], "#0B0A1A")

    def test_customtkinter_defaults(self):
        apply_customtkinter_palette(get_theme("dark"))
        t = ctk.ThemeManager.theme
        self.assertEqual(t["CTkButton"]["fg_color"], ["#6C5CE7", "#6C5CE7"])
        self.assertEqual(t["CTkLabel"]["text_color"], ["#F4F3FA", "#F4F3FA"])

    def test_lerp_color(self):
        self.assertEqual(lerp_color("#000000", "#ffffff", 0.5), "#808080")


class SkinRenderTests(unittest.TestCase):
    def _skin(self, h):
        from PIL import Image
        return Image.new("RGBA", (64, h), (200, 120, 90, 255))

    def test_classic_slim_legacy(self):
        for h, slim in ((64, False), (64, True), (32, False)):
            res = render_player(self._skin(h), slim=slim, size=(180, 240))
            self.assertEqual(res.image.size, (180, 240))
            self.assertIsNotNone(res.image.getbbox())


if __name__ == "__main__":
    unittest.main()
