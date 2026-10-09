import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import launcher


class MinecraftLaunchTests(unittest.TestCase):
    def test_fabric_launch_uses_selected_loader_and_profile_game_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "launcher"
            game_dir = root / "instances" / "profile-id"
            minecraft_version = "1.21.1"
            loader_id = "fabric-loader-0.16.10-1.21.1"
            vanilla_dir = base / "versions" / minecraft_version
            fabric_dir = base / "versions" / loader_id
            vanilla_dir.mkdir(parents=True)
            fabric_dir.mkdir(parents=True)
            (vanilla_dir / f"{minecraft_version}.json").write_text(json.dumps({
                "mainClass": "net.minecraft.client.main.Main",
                "assetIndex": {"id": "1.21"},
                "arguments": {
                    "game": [
                        "--username", "${auth_player_name}",
                        "--version", "${version_name}",
                        "--gameDir", "${game_directory}",
                    ],
                },
                "libraries": [],
            }))
            (fabric_dir / f"{loader_id}.json").write_text(json.dumps({
                "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
                "libraries": [],
            }))
            process = object()

            with (
                patch("core.launcher.get_launcher_dir", return_value=base),
                patch("core.launcher.get_shared_assets_dir", return_value=root / "assets"),
                patch("core.launcher._find_java", return_value="java.exe"),
                patch("core.launcher.platform.system", return_value="Windows"),
                patch("core.launcher.subprocess.Popen", return_value=process) as popen,
            ):
                result = launcher.launch(
                    mc_version=minecraft_version,
                    profile_type="fabric",
                    fabric_profile_id=loader_id,
                    username="Player",
                    ram_gb=4,
                    log=lambda _message: None,
                    game_dir=game_dir,
                )

            self.assertIs(result, process)
            command = popen.call_args.args[0]
            self.assertEqual(command[0], "java.exe")
            self.assertIn("net.fabricmc.loader.impl.launch.knot.KnotClient", command)
            self.assertIn(loader_id, command)
            self.assertIn(str(game_dir), command)
            self.assertEqual(popen.call_args.kwargs["cwd"], str(game_dir))

    def test_fabric_launch_requires_loader_profile(self):
        with self.assertRaisesRegex(ValueError, "Fabric profile ID missing"):
            launcher.launch(
                mc_version="1.21.1",
                profile_type="fabric",
                fabric_profile_id=None,
                username="Player",
                ram_gb=4,
                log=lambda _message: None,
            )


if __name__ == "__main__":
    unittest.main()
