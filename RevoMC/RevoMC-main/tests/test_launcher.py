import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core import installer, launcher


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

            def start_game(_command, **kwargs):
                self.assertEqual(
                    Path(kwargs["stdout"].name),
                    game_dir / "logs" / "launcher-game.log",
                )
                kwargs["stdout"].write("Minecraft startup output\n")
                return process

            with (
                patch("core.launcher.get_launcher_dir", return_value=base),
                patch("core.launcher.get_shared_assets_dir", return_value=root / "assets"),
                patch("core.launcher._find_java", return_value="java.exe"),
                patch("core.launcher.platform.system", return_value="Windows"),
                patch("core.launcher.subprocess.Popen", side_effect=start_game) as popen,
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
            self.assertEqual(
                (game_dir / "logs" / "launcher-game.log").read_text(),
                "Minecraft startup output\n",
            )

    def test_jvm_argument_builder_supports_java_17_and_21(self):
        for java_version in (17, 21):
            with self.subTest(java_version=java_version):
                args = launcher.build_jvm_args(
                    java_version,
                    4,
                    user_args=["-Dexample=true", "-XX:+UseConcMarkSweepGC"],
                )
                xmx = int(next(arg[4:-1] for arg in args if arg.startswith("-Xmx")))
                xms = int(next(arg[4:-1] for arg in args if arg.startswith("-Xms")))
                self.assertLessEqual(xms, xmx)
                self.assertIn("-XX:+UseG1GC", args)
                self.assertIn("-XX:+ParallelRefProcEnabled", args)
                self.assertIn("-XX:MaxGCPauseMillis=200", args)
                self.assertIn("-Dexample=true", args)
                self.assertNotIn("-XX:+UseConcMarkSweepGC", args)

    def test_jvm_argument_builder_caps_initial_memory_at_maximum(self):
        args = launcher.build_jvm_args(21, 0)
        self.assertIn("-Xmx1G", args)
        self.assertIn("-Xms1G", args)

    def test_jvm_argument_builder_normalizes_conflicting_memory_overrides(self):
        args = launcher.build_jvm_args(
            17,
            8,
            user_args=["-Xms6G", "-Xmx2G", "-XX:+UseConcMarkSweepGC"],
        )
        xmx = next(arg for arg in args if arg.startswith("-Xmx"))
        xms = next(arg for arg in args if arg.startswith("-Xms"))
        self.assertEqual((xmx, xms), ("-Xmx2G", "-Xms2G"))
        self.assertNotIn("-XX:+UseConcMarkSweepGC", args)

    def test_disables_a_mod_that_rejects_the_selected_minecraft_version(self):
        with tempfile.TemporaryDirectory() as temp:
            mods_dir = Path(temp) / "mods"
            mods_dir.mkdir()
            incompatible = mods_dir / "old-mod.jar"
            with zipfile.ZipFile(incompatible, "w") as archive:
                archive.writestr(
                    "fabric.mod.json",
                    json.dumps({"id": "old-mod", "depends": {"minecraft": "1.20.1"}}),
                )
            logs = []

            disabled = launcher.disable_incompatible_mods(
                mods_dir, "1.21.1", logs.append
            )

            self.assertEqual(disabled, ["old-mod.jar"])
            self.assertFalse(incompatible.exists())
            self.assertTrue((mods_dir / "old-mod.jar.disabled").is_file())
            self.assertIn("old-mod.jar", logs[0])
            self.assertIn("1.21.1", logs[0])

    def test_keeps_mods_matching_fabric_version_ranges(self):
        with tempfile.TemporaryDirectory() as temp:
            mods_dir = Path(temp) / "mods"
            mods_dir.mkdir()
            compatible = mods_dir / "compatible.jar"
            with zipfile.ZipFile(compatible, "w") as archive:
                archive.writestr(
                    "fabric.mod.json",
                    json.dumps({
                        "id": "compatible",
                        "depends": {"minecraft": ">=1.20 <1.22"},
                    }),
                )

            disabled = launcher.disable_incompatible_mods(
                mods_dir, "1.21.1", lambda _message: None
            )

            self.assertEqual(disabled, [])
            self.assertTrue(compatible.is_file())

    def test_detects_only_enabled_fabric_api_jars(self):
        with tempfile.TemporaryDirectory() as temp:
            mods_dir = Path(temp) / "mods"
            mods_dir.mkdir()
            api = mods_dir / "fabric-api.jar"
            with zipfile.ZipFile(api, "w") as archive:
                archive.writestr("fabric.mod.json", json.dumps({"id": "fabric-api"}))
            self.assertTrue(installer.has_fabric_api(mods_dir))
            api.rename(mods_dir / "fabric-api.jar.disabled")
            self.assertFalse(installer.has_fabric_api(mods_dir))

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
