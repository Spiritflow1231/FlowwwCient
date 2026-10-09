import hashlib
import io
import json
import tempfile
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest.mock import patch

from core import modrinth


class _FakeResponse:
    def __init__(self, data: bytes):
        self._stream = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1):
        return self._stream.read(size)

    def geturl(self):
        return "https://cdn.modrinth.com/sample.jar"


class ModrinthContentTests(unittest.TestCase):
    def test_rejects_unsafe_archive_paths(self):
        for value in ("../escape", "/absolute", "folder\\file", "C:/escape"):
            with self.subTest(path=value), self.assertRaises(ValueError):
                modrinth._safe_relative_path(value)

    def test_search_uses_modrinth_project_type_and_fabric_facets(self):
        response = {"hits": [{"project_id": "test"}]}
        with patch("core.modrinth._request_json", return_value=response) as request:
            projects = modrinth.search_projects("mods", "sodium", "1.21.1", "fabric")
        self.assertEqual(projects, response["hits"])
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args.args[0]).query)
        facets = json.loads(params["facets"][0])
        self.assertEqual(
            facets,
            [["project_type:mod"], ["versions:1.21.1"], ["categories:fabric"]],
        )

    def test_version_query_filters_game_version_and_loader(self):
        with patch(
            "core.modrinth._request_json",
            return_value=[
                {"game_versions": ["1.21.1"], "loaders": ["fabric"]},
                {"game_versions": ["1.21.1"], "loaders": ["forge"]},
                {"game_versions": ["1.20.1"], "loaders": ["fabric"]},
            ],
        ):
            versions = modrinth.compatible_versions("project", "mods", "1.21.1", "fabric")
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["loaders"], ["fabric"])

    def test_imports_fabric_modpack_overrides_into_fresh_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = root / "pack.mrpack"
            destination = root / "instances" / "profile"
            manifest = {
                "formatVersion": 1,
                "name": "Test Pack",
                "dependencies": {
                    "minecraft": "1.21.1",
                    "fabric-loader": "0.16.10",
                },
                "files": [],
            }
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("modrinth.index.json", json.dumps(manifest))
                archive.writestr("overrides/config/example.txt", "profile config")

            imported = modrinth.install_modpack(archive_path, destination)

            self.assertEqual(imported["type"], "fabric")
            self.assertEqual(imported["fabric_loader_version"], "0.16.10")
            self.assertEqual(
                (destination / "config" / "example.txt").read_text(),
                "profile config",
            )

    def test_rejects_unsupported_modpack_loader_without_creating_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = root / "pack.mrpack"
            destination = root / "instances" / "profile"
            manifest = {
                "formatVersion": 1,
                "dependencies": {
                    "minecraft": "1.20.1",
                    "forge": "47.2.0",
                },
                "files": [],
            }
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("modrinth.index.json", json.dumps(manifest))

            with self.assertRaisesRegex(RuntimeError, "vanilla and Fabric"):
                modrinth.install_modpack(archive_path, destination)
            self.assertFalse(destination.exists())

    def test_download_verifies_hash_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("fabric.mod.json", "{}")
            data = payload.getvalue()
            version = {
                "files": [{
                    "filename": "sample.jar",
                    "url": "https://cdn.modrinth.com/sample.jar",
                    "primary": True,
                    "hashes": {"sha1": hashlib.sha1(data).hexdigest()},
                }],
            }
            with patch("core.modrinth.urllib.request.urlopen", return_value=_FakeResponse(data)):
                installed = modrinth.download_project_file(version, "mods", root)
            self.assertEqual(installed.read_bytes(), data)

            with patch("core.modrinth.urllib.request.urlopen") as open_url:
                with self.assertRaises(FileExistsError):
                    modrinth.download_project_file(version, "mods", root)
                open_url.assert_not_called()

    def test_rejects_download_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("fabric.mod.json", "{}")
            data = payload.getvalue()
            version = {
                "files": [{
                    "filename": "sample.jar",
                    "url": "https://cdn.modrinth.com/sample.jar",
                    "hashes": {"sha1": "0" * 40},
                }],
            }
            with patch("core.modrinth.urllib.request.urlopen", return_value=_FakeResponse(data)):
                with self.assertRaisesRegex(RuntimeError, "integrity check"):
                    modrinth.download_project_file(version, "mods", root)
            self.assertFalse((root / "sample.jar").exists())


if __name__ == "__main__":
    unittest.main()
