import ast
from pathlib import Path
import unittest

from ui.main_window import _default_steve_skin, _render_skin_preview


MAIN_WINDOW_PATH = Path(__file__).resolve().parents[1] / "ui" / "main_window.py"


class MainWindowSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN_WINDOW_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(MAIN_WINDOW_PATH))

    def test_main_window_source_compiles(self):
        compile(self.source, str(MAIN_WINDOW_PATH), "exec")

    def test_main_window_methods_do_not_reference_category(self):
        main_window = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
        )
        category_references = [
            node
            for node in ast.walk(main_window)
            if isinstance(node, ast.Attribute)
            and node.attr == "category"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ]
        self.assertEqual(category_references, [])

    def test_source_has_no_pasted_terminal_text(self):
        for line_number, line in enumerate(self.source.splitlines(), start=1):
            with self.subTest(line_number=line_number):
                self.assertNotIn("grep -n", line)
                self.assertNotIn("git push", line)

    def test_default_skin_renders_to_a_pixel_art_preview(self):
        preview = _render_skin_preview(_default_steve_skin())
        self.assertEqual(preview.size, (116, 174))
        self.assertGreater(preview.getbbox()[2], 0)

    def test_preview_supports_classic_64_by_32_skin(self):
        skin = _default_steve_skin().crop((0, 0, 64, 32))
        self.assertEqual(_render_skin_preview(skin).size, (116, 174))


if __name__ == "__main__":
    unittest.main()
