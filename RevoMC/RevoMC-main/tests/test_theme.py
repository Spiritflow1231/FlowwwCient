import unittest

import customtkinter as ctk

from ui.theme import apply_customtkinter_palette, get_theme


class CrimsonThemeTests(unittest.TestCase):
    def test_legacy_theme_names_resolve_to_the_crimson_brand_palette(self):
        for name in ("crimson", "overworld", "nether", "end"):
            with self.subTest(name=name):
                theme = get_theme(name)
                self.assertEqual(theme["BG_PRIMARY"], "#0B0D10")
                self.assertEqual(theme["BG_SECONDARY"], "#14171C")
                self.assertEqual(theme["ACCENT"], "#E53945")
                self.assertEqual(theme["TEXT_FG"], "#F4F5F7")

    def test_customtkinter_defaults_cover_dialogs_scrollbars_and_controls(self):
        apply_customtkinter_palette()
        theme = ctk.ThemeManager.theme

        self.assertEqual(theme["CTkToplevel"]["fg_color"], ["#0B0D10", "#0B0D10"])
        self.assertEqual(theme["CTkButton"]["fg_color"], ["#E53945", "#E53945"])
        self.assertEqual(theme["CTkLabel"]["text_color"], ["#F4F5F7", "#F4F5F7"])
        self.assertEqual(theme["CTkSwitch"]["progress_color"], ["#E53945", "#E53945"])
        self.assertEqual(theme["CTkScrollbar"]["button_hover_color"], ["#E53945", "#E53945"])
        self.assertEqual(theme["CTkTextbox"]["fg_color"], ["#0B0D10", "#0B0D10"])
        self.assertEqual(
            theme["CTkScrollableFrame"]["label_fg_color"],
            ["#14171C", "#14171C"],
        )


if __name__ == "__main__":
    unittest.main()
