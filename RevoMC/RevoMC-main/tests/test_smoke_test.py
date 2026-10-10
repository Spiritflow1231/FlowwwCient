import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SmokeTestDiagnosticsTests(unittest.TestCase):
    def test_smoke_test_writes_result_for_windowed_builds(self):
        app_root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as temp:
            diagnostics = Path(temp) / "smoke.log"
            environment = os.environ.copy()
            environment["FLOWWWCLIENT_SMOKE_LOG"] = str(diagnostics)

            result = subprocess.run(
                [sys.executable, str(app_root / "main.py"), "--smoke-test"],
                cwd=app_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"{result.stdout}\n{result.stderr}\n"
                f"{diagnostics.read_text(encoding='utf-8') if diagnostics.exists() else ''}",
            )
            self.assertEqual(
                diagnostics.read_text(encoding="utf-8"),
                "SMOKE TEST PASSED\n",
            )


if __name__ == "__main__":
    unittest.main()
