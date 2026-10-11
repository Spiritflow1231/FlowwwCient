import unittest

import customtkinter as ctk

from ui.theme import apply_customtkinter_palette, get_theme
from ui import main_window


class CrimsonThemeTests(unittest.TestCase):
    def test_main_window_module_level_color_tokens_match_theme(self):
        theme = get_theme()
        tokens = {
            "BG_PRIMARY": "BG_PRIMARY",
            "BG_SECONDARY": "BG_SECONDARY",
            "BG_CONSOLE": "BG_CONSOLE",
            "BG_CARD": "BG_CARD",
            "BORDER_COL": "BORDER_COL",
            "GREEN": "ACCENT",
            "GREEN_DARK": "ACCENT_DARK",
            "BLUE": "ACCENT_ALT",
            "RED": "RED",
            "MS_BLUE": "MS_BLUE",
            "MS_BLUE_DARK": "MS_BLUE_DARK",
            "TEXT_FG": "TEXT_FG",
            "TEXT_MUTED": "TEXT_MUTED",
            "TEXT_LABEL": "TEXT_LABEL",
        }
        for name, theme_key in tokens.items():
            with self.subTest(name=name):
                self.assertEqual(getattr(main_window, name), theme[theme_key])

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
