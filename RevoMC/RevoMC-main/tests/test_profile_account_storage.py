import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import accounts, profiles


class ProfileAccountStorageTests(unittest.TestCase):
    def test_initialize_profile_creates_isolated_content_folders_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = {
                "instance_id": "1" * 32,
                "name": "Test Profile",
                "mc_version": "1.21.1",
                "type": "fabric",
                "memory_gb": 5,
                "java_args": "-XX:+UseG1GC",
                "performance_boost": True,
                "installed_content": {
                    "mods": [{
                        "project_id": "abc123",
                        "version_id": "def456",
                        "filename": "example.jar",
                    }]
                },
            }
            with patch("core.modrinth.Path.home", return_value=root):
                instance = profiles.initialize_profile(profile)
                document = json.loads((instance / "profile.json").read_text())

            self.assertEqual(
                {path.name for path in instance.iterdir() if path.is_dir()},
                set(profiles.PROFILE_DIRECTORIES),
            )
            self.assertEqual(document["loader"], "fabric")
            self.assertEqual(document["installed_content"], profile["installed_content"])
            self.assertTrue((instance / "profile.json").is_file())

    def test_offline_identity_uses_java_name_uuid_v3(self):
        self.assertEqual(
            accounts.offline_uuid("Notch"),
            "b50ad385-829d-3141-a216-7e7d7539ba7f",
        )

    def test_search_projects_requests_loader_scoped_pages_and_caches_results(self):
        from core import modrinth

        with patch.object(modrinth, "_request_json", return_value={"hits": [{"project_id": "one"}]}) as request:
            modrinth._search_cache.clear()
            first = modrinth.search_projects("mods", "sodium", "1.21.1", "fabric", 20)
            second = modrinth.search_projects("mods", "sodium", "1.21.1", "fabric", 20)

        self.assertEqual(first, second)
        request.assert_called_once()
        self.assertIn("offset=20", request.call_args.args[0])
        self.assertIn("%22categories%3Afabric%22", request.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
