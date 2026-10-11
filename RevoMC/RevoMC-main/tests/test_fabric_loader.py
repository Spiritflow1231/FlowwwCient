import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

from core import installer
from ui.main_window import MainWindow


class FabricLoaderSelectionTests(unittest.TestCase):
    def test_selects_first_stable_global_loader(self):
        with patch.object(
            installer,
            "_get",
            return_value=[
                {"version": "0.20.0", "stable": False},
                {"version": "0.19.5", "stable": True},
                {"version": "0.19.4", "stable": True},
            ],
        ):
            self.assertEqual(installer.fetch_latest_stable_fabric_loader(), "0.19.5")

    def test_uses_latest_stable_loader_supported_by_minecraft(self):
        responses = [
            [
                {"version": "0.20.0", "stable": False},
                {"version": "0.19.5", "stable": True},
            ],
            [
                {"loader": {"version": "0.18.2", "stable": True}},
                {"loader": {"version": "0.18.1", "stable": True}},
            ],
        ]
        with patch.object(installer, "_get", side_effect=responses):
            self.assertEqual(
                installer.fetch_latest_stable_fabric_loader("1.20.1"),
                "0.18.2",
            )

    def test_install_refreshes_cached_profile_json_using_latest_stable_loader(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mc_version = "1.21.1"
            loader_id = f"fabric-loader-0.19.5-{mc_version}"
            profile_json_path = root / "versions" / loader_id / f"{loader_id}.json"
            profile_json_path.parent.mkdir(parents=True)
            profile_json_path.write_text('{"old": true}', encoding="utf-8")
            mc_loaders = [
                {"loader": {"version": "0.19.5", "stable": True}},
                {"loader": {"version": "0.18.2", "stable": True}},
            ]
            profile = {"id": loader_id, "libraries": [], "mainClass": "Main"}
            responses = [
                mc_loaders,
                [
                    {"version": "0.20.0", "stable": False},
                    {"version": "0.19.5", "stable": True},
                ],
                mc_loaders,
                profile,
            ]
            with (
                patch.object(installer, "get_launcher_dir", return_value=root),
                patch.object(installer, "_get", side_effect=responses) as get,
            ):
                installed = installer.install_fabric(
                    mc_version, lambda _message: None, lambda *_args: None
                )

            self.assertEqual(installed, loader_id)
            self.assertEqual(
                json.loads(profile_json_path.read_text(encoding="utf-8")),
                profile,
            )
            self.assertEqual(
                get.call_args_list[-1].args[0],
                f"{installer.FABRIC_META}/versions/loader/{mc_version}/0.19.5/profile/json",
            )

    def test_upgrade_migrates_old_unpinned_profile_and_installed_version_key(self):
        profile = {
            "name": "Old Fabric",
            "mc_version": "1.21.1",
            "type": "fabric",
            "fabric_loader_version": "0.18.2",
        }
        pinned = {
            "name": "Pinned Pack",
            "mc_version": "1.21.1",
            "type": "fabric",
            "fabric_loader_version": "0.18.2",
            "fabric_loader_pinned": True,
        }
        cfg = {
            "profiles": [profile, pinned],
            "installed_versions": {
                "1.21.1": {
                    "type": "fabric",
                    "fabric_profile_id": "fabric-loader-0.18.2-1.21.1",
                },
            },
        }
        window = SimpleNamespace(
            cfg=cfg,
            latest_fabric_loader_versions={"1.21.1": "0.19.5"},
            _log=Mock(),
            _refresh_profile_list=Mock(),
        )
        with patch("core.config.save") as save:
            MainWindow._upgrade_fabric_profiles(window)

        self.assertEqual(profile["fabric_loader_version"], "0.19.5")
        self.assertEqual(
            cfg["installed_versions"]["1.21.1"]["fabric_profile_id"],
            "fabric-loader-0.19.5-1.21.1",
        )
        self.assertEqual(pinned["fabric_loader_version"], "0.18.2")
        save.assert_called_once_with(cfg)
        window._refresh_profile_list.assert_called_once_with()

    def test_old_installed_loader_is_not_considered_ready_for_play(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version = "1.21.1"
            loader_id = f"fabric-loader-0.18.2-{version}"
            versions = root / ".revomc" / "versions"
            vanilla = versions / version
            fabric = versions / loader_id
            vanilla.mkdir(parents=True)
            fabric.mkdir(parents=True)
            (vanilla / f"{version}.json").write_text("{}")
            (vanilla / f"{version}.jar").write_bytes(b"client")
            (fabric / f"{loader_id}.json").write_text("{}")
            window = SimpleNamespace(
                cfg={
                    "installed_versions": {
                        version: {
                            "type": "fabric",
                            "fabric_profile_id": loader_id,
                        },
                    },
                },
                latest_fabric_loader_versions={version: "0.19.5"},
            )
            with patch("pathlib.Path.home", return_value=root):
                self.assertFalse(
                    MainWindow._is_installed_for_profile(
                        window,
                        {"mc_version": version, "type": "fabric"},
                    )
                )


if __name__ == "__main__":
    unittest.main()
