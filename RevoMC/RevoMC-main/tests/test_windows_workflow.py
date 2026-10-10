import unittest
from pathlib import Path


class WindowsWorkflowPackagingTests(unittest.TestCase):
    def test_workflow_builds_using_spec_and_verifies_metadata(self):
        workflow_path = Path(__file__).parents[3] / ".github" / "workflows" / "build-windows.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn(
            "python -m PyInstaller revomc.spec --clean --noconfirm",
            workflow,
        )
        self.assertIn('ProductName = "FlowwwClient"', workflow)
        self.assertIn('FileDescription = "FlowwwClient Minecraft Launcher"', workflow)
        self.assertIn('OriginalFilename = "FlowwwClient.exe"', workflow)
        self.assertIn('CompanyName = "FlowwwClient"', workflow)
        self.assertIn("Expected EXE $field", workflow)
        self.assertIn("dist/FlowwwClient.exe", workflow)
        self.assertLess(
            workflow.index("- name: Verify Windows executable metadata"),
            workflow.index("- name: Smoke-test executable"),
        )
        self.assertLess(
            workflow.index("$versionInfo = (Get-Item $executable).VersionInfo"),
            workflow.index("- name: Smoke-test executable"),
        )

    def test_zip_packaging_and_upload_run_after_prior_failures(self):
        workflow_path = Path(__file__).parents[3] / ".github" / "workflows" / "build-windows.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn(
            "      - name: Package Windows ZIP\n        if: always()",
            workflow,
        )
        self.assertIn(
            "      - name: Upload Windows ZIP package\n        if: always()",
            workflow,
        )
        self.assertIn("name: FlowwwClient-Windows", workflow)
        self.assertIn("dist/FlowwwClient-Windows.zip", workflow)


if __name__ == "__main__":
    unittest.main()
