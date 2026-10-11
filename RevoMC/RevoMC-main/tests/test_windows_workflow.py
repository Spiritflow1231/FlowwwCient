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
            "      - name: Package Windows ZIP\n        if: always() && steps.sign-windows-executable.outcome != 'failure'",
            workflow,
        )
        self.assertIn(
            "      - name: Upload Windows ZIP package\n        if: always()",
            workflow,
        )
        self.assertIn("name: FlowwwClient-Windows", workflow)
        self.assertIn("dist/FlowwwClient-Windows.zip", workflow)

    def test_authenticode_signing_is_configurable_and_verified_before_packaging(self):
        workflow_path = Path(__file__).parents[3] / ".github" / "workflows" / "build-windows.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        signing = workflow.index("- name: Sign Windows executable")
        verification = workflow.index("- name: Verify Authenticode signature")
        smoke_test = workflow.index("- name: Smoke-test executable")
        packaging = workflow.index("- name: Package Windows ZIP")
        self.assertLess(signing, verification)
        self.assertLess(verification, smoke_test)
        self.assertLess(smoke_test, packaging)
        self.assertIn("secrets.WINDOWS_SIGNING_CERTIFICATE_BASE64", workflow)
        self.assertIn("secrets.WINDOWS_SIGNING_CERTIFICATE_PASSWORD", workflow)
        self.assertIn("vars.WINDOWS_TIMESTAMP_SERVER_URL", workflow)
        self.assertIn("Write-Warning \"UNSIGNED:", workflow)
        self.assertIn("Both WINDOWS_SIGNING_CERTIFICATE_BASE64 and WINDOWS_SIGNING_CERTIFICATE_PASSWORD must be configured.", workflow)
        self.assertIn("Join-Path $env:RUNNER_TEMP", workflow)
        self.assertIn("/fd SHA256 /tr $timestampServer /td SHA256", workflow)
        self.assertIn("& $signTool verify /pa /v $executable", workflow)
        self.assertIn("finally {", workflow)
        self.assertIn("Remove-Item -LiteralPath $certificatePath", workflow)


if __name__ == "__main__":
    unittest.main()
