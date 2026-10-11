import ast
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
