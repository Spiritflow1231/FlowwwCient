import json
import os
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image

from core import config, modrinth
from ui.main_window import (
    ProfileEditorWindow,
    _project_card_content,
    validate_cosmetic_image,
)


class _Widget:
    def __init__(self):
        self.values = {}

    def configure(self, **values):
        self.values.update(values)


def _bare_editor(tab="Browse"):
    editor = object.__new__(ProfileEditorWindow)
    editor._working = True
    editor._cancel_event = object()
    editor._active_install_project_id = None
    editor.cancel_btn = _Widget()
    editor.status = _Widget()
    editor.tab = tab
    editor.theme = modrinth
    editor._set_manager_busy = Mock()
    editor._refresh_content = Mock()
    editor._project_installed = Mock(return_value=False)
    editor._project_buttons = {}
    editor._browse_projects = []
    return editor


class InstalledContentDiscoveryTests(unittest.TestCase):
    def test_editor_category_keys_resolve_to_visible_headings(self):
        self.assertEqual(
            ProfileEditorWindow.CATEGORY_LABELS,
            {
                "overview": "Overview",
                "mods": "Mods",
                "resourcepacks": "Resource Packs",
                "shaderpacks": "Shader Packs",
                "datapacks": "Datapacks",
                "modpacks": "Modpacks",
            },
        )

    def test_browse_card_content_uses_fake_response_and_active_category(self):
        title, description, details = _project_card_content(
            {
                "title": "Sample Pack",
                "description": "A useful resource pack.",
                "author": "Flowww",
                "display_categories": ["16x"],
                "versions": ["1.21.11", "1.21.10"],
                "downloads": 1234,
            },
            "resourcepacks",
            "1.21.11",
        )

        self.assertEqual(title, "Sample Pack")
        self.assertEqual(description, "A useful resource pack.")
        self.assertIn("Resource Packs", details)
        self.assertIn("MC 1.21.11", details)
        self.assertIn("1,234 downloads", details)

    def test_missing_category_directory_is_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            instance = Path(temp) / "instance"
            instance.mkdir()
            with patch.object(modrinth, "profile_instance_dir", return_value=instance):
                self.assertEqual(modrinth.list_installed_files({}, "mods"), [])

    def test_discovers_enabled_and_disabled_mods_only_in_selected_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first"
            second = Path(temp) / "second"
            (first / "mods").mkdir(parents=True)
            (second / "mods").mkdir(parents=True)
            (first / "mods" / "sodium.jar").write_bytes(b"jar")
            (first / "mods" / "iris.jar.disabled").write_bytes(b"jar")
            (second / "mods" / "other.jar").write_bytes(b"jar")

            with patch.object(modrinth, "profile_instance_dir", return_value=first):
                found = modrinth.list_installed_files({}, "mods")

            self.assertEqual(
                [path.name for path in found],
                ["iris.jar.disabled", "sodium.jar"],
            )
            self.assertNotIn(second / "mods" / "other.jar", found)

    def test_discovers_resource_and_shader_pack_files_and_directories_per_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles = {
                "first": root / "first",
                "second": root / "second",
            }
            (profiles["first"] / "resourcepacks").mkdir(parents=True)
            (profiles["first"] / "shaderpacks").mkdir()
            (profiles["second"] / "resourcepacks").mkdir(parents=True)
            (profiles["second"] / "shaderpacks").mkdir()
            (profiles["first"] / "resourcepacks" / "pack.zip").write_bytes(b"pack")
            (profiles["first"] / "resourcepacks" / "Directory Pack").mkdir()
            (profiles["first"] / "shaderpacks" / "shader.zip").write_bytes(b"shader")
            (profiles["first"] / "shaderpacks" / "Directory Shader").mkdir()
            (profiles["second"] / "resourcepacks" / "other.zip").write_bytes(b"other")
            (profiles["second"] / "shaderpacks" / "other.zip").write_bytes(b"other")

            def instance_for(profile):
                return profiles[profile["instance_id"]]

            with patch.object(modrinth, "profile_instance_dir", side_effect=instance_for):
                first_resources = modrinth.list_installed_files(
                    {"instance_id": "first"}, "resourcepacks"
                )
                first_shaders = modrinth.list_installed_files(
                    {"instance_id": "first"}, "shaderpacks"
                )

            self.assertEqual(
                [path.name for path in first_resources],
                ["Directory Pack", "pack.zip"],
            )
            self.assertEqual(
                [path.name for path in first_shaders],
                ["shader.zip"],
            )
            self.assertNotIn(profiles["second"] / "resourcepacks" / "other.zip", first_resources)
            self.assertNotIn(profiles["second"] / "shaderpacks" / "other.zip", first_shaders)

    def test_discovers_datapacks_only_for_selected_world(self):
        with tempfile.TemporaryDirectory() as temp:
            instance = Path(temp) / "instance"
            for world in ("World One", "World Two"):
                datapacks = instance / "saves" / world / "datapacks"
                datapacks.mkdir(parents=True)
                (datapacks / f"{world}.zip").write_bytes(b"pack")

            with patch.object(modrinth, "profile_instance_dir", return_value=instance):
                selected = modrinth.list_installed_files(
                    {}, "datapacks", "World Two"
                )
                no_selection = modrinth.list_installed_files({}, "datapacks")

            self.assertEqual([path.name for path in selected], ["World Two.zip"])
            self.assertEqual(no_selection, [])

    def test_installed_mod_record_and_disabled_file_are_not_rendered_twice(self):
        with tempfile.TemporaryDirectory() as temp:
            mods_dir = Path(temp) / "mods"
            mods_dir.mkdir()
            disabled_mod = mods_dir / "iris.jar.disabled"
            disabled_mod.write_bytes(b"jar")
            editor = object.__new__(ProfileEditorWindow)
            editor.category = "mods"
            editor.profile = {
                "installed_content": {
                    "mods": [{"filename": "iris.jar", "title": "Iris", "world": None}]
                }
            }
            editor.parent = SimpleNamespace(cfg={"profiles": []})
            editor.search = _Widget()
            editor.search.get = Mock(return_value="")
            editor._category_directory = Mock(return_value=mods_dir)
            editor._render_installed_record = Mock()
            editor._render_installed_file = Mock()
            editor._show_state = Mock()

            with patch.object(modrinth, "list_installed_files", return_value=[disabled_mod]):
                editor._show_installed()

            editor._render_installed_record.assert_called_once()
            editor._render_installed_file.assert_not_called()

    def test_installed_tab_lists_both_unrecorded_mod_jars_in_instance_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            mods_dir = Path(temp) / "instance" / "mods"
            mods_dir.mkdir(parents=True)
            for filename in ("fabric-api.jar", "sodium.jar"):
                with zipfile.ZipFile(mods_dir / filename, "w") as jar:
                    jar.writestr(
                        "fabric.mod.json",
                        json.dumps({
                            "id": filename.removesuffix(".jar"),
                            "name": filename.removesuffix(".jar").title(),
                            "version": "1.0.0",
                        }),
                    )
            editor = object.__new__(ProfileEditorWindow)
            editor.category = "mods"
            editor.profile = {"instance_id": "profile"}
            editor.parent = SimpleNamespace(cfg={"profiles": []})
            editor.search = _Widget()
            editor.search.get = Mock(return_value="")
            editor._category_directory = Mock(return_value=mods_dir)
            editor._render_installed_record = Mock()
            editor._render_installed_file = Mock()
            editor._show_state = Mock()

            with patch.object(
                modrinth,
                "list_installed_files",
                return_value=sorted(mods_dir.glob("*.jar")),
            ):
                editor._show_installed()

            self.assertEqual(editor._render_installed_file.call_count, 2)
            self.assertEqual(
                {
                    call.args[0].name
                    for call in editor._render_installed_file.call_args_list
                },
                {"fabric-api.jar", "sodium.jar"},
            )

    def test_browse_state_recognizes_unrecorded_modrinth_project_jar(self):
        with tempfile.TemporaryDirectory() as temp:
            instance = Path(temp) / "instance"
            mods = instance / "mods"
            mods.mkdir(parents=True)
            with zipfile.ZipFile(mods / "example.jar", "w") as jar:
                jar.writestr(
                    "fabric.mod.json",
                    json.dumps({
                        "id": "example",
                        "custom": {"modrinth": {"project_id": "project-id"}},
                    }),
                )
            editor = object.__new__(ProfileEditorWindow)
            editor.category = "mods"
            editor.profile = {"instance_id": "profile"}

            with patch.object(modrinth, "profile_instance_dir", return_value=instance):
                self.assertTrue(editor._project_installed("project-id"))

    def test_installer_records_bootstrap_modrinth_metadata(self):
        from core import installer

        profile = {}

        def fake_install(name, project_id, _mc, _folder, _log, pinned_version_id=None, records=None):
            filename = f"{name}.jar"
            records.append({
                "project_id": project_id,
                "version_id": f"{name}-version",
                "filename": filename,
                "title": name,
                "version": "1.2.3",
            })
            return [filename], {}

        with tempfile.TemporaryDirectory() as temp:
            with patch.object(installer, "_install_single_mod", side_effect=fake_install):
                installer.install_mods(
                    "1.21.1",
                    ["sodium"],
                    lambda _message: None,
                    lambda *_args: None,
                    mods_dir=Path(temp) / "mods",
                    profile=profile,
                )

        records = profile["installed_content"]["mods"]
        self.assertEqual(
            {record["project_id"] for record in records},
            {installer.FABRIC_API_ID, installer.AVAILABLE_MODS["sodium"]["id"]},
        )
        self.assertTrue(all(
            record.get("version_id") and record.get("filename") and record.get("title")
            for record in records
        ))

    @unittest.skipIf(os.name == "nt", "Creating symlinks may require Windows privileges")
    def test_discovers_pack_directories_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            instance = Path(temp) / "instance"
            packs = instance / "resourcepacks"
            packs.mkdir(parents=True)
            directory_pack = packs / "Directory Pack"
            directory_pack.mkdir()
            (packs / "pack.zip").write_bytes(b"not validated here")
            outside = Path(temp) / "outside"
            outside.mkdir()
            (outside / "secret.zip").write_bytes(b"secret")
            (packs / "linked").symlink_to(outside, target_is_directory=True)

            with patch.object(modrinth, "profile_instance_dir", return_value=instance):
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    modrinth.list_installed_files({}, "resourcepacks")



class ContentArchiveValidationTests(unittest.TestCase):
    def test_accepts_valid_datapack_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "example.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("pack.mcmeta", json.dumps({"pack": {"pack_format": 48}}))
                archive.writestr("data/example/functions/load.mcfunction", "say ready")

            modrinth.validate_content_archive(archive_path, "datapacks")

    def test_rejects_invalid_and_unsafe_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / "invalid.zip"
            invalid.write_text("not a zip", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "valid ZIP/JAR"):
                modrinth.validate_content_archive(invalid, "resourcepacks")

            unsafe = Path(temp) / "unsafe.jar"
            with zipfile.ZipFile(unsafe, "w") as archive:
                archive.writestr("../escape", "bad")
            with self.assertRaisesRegex(ValueError, "unsafe file path"):
                modrinth.validate_content_archive(unsafe, "mods")

    def test_resourcepack_requires_minecraft_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "resource.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("assets/example/texture.png", b"placeholder")
            with self.assertRaisesRegex(ValueError, "pack.mcmeta"):
                modrinth.validate_content_archive(archive_path, "resourcepacks")


class CosmeticImageValidationTests(unittest.TestCase):
    def test_accepts_skin_and_cape_canvas_sizes(self):
        with tempfile.TemporaryDirectory() as temp:
            skin = Path(temp) / "skin.png"
            cape = Path(temp) / "cape.png"
            Image.new("RGBA", (64, 64)).save(skin)
            Image.new("RGBA", (64, 32)).save(cape)

            self.assertEqual(validate_cosmetic_image(skin, "skin"), (64, 64))
            self.assertEqual(validate_cosmetic_image(cape, "cape"), (64, 32))

    def test_rejects_invalid_skin_dimensions_and_non_png(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid_skin = Path(temp) / "wide.png"
            Image.new("RGBA", (64, 48)).save(invalid_skin)
            with self.assertRaisesRegex(ValueError, "skin canvas"):
                validate_cosmetic_image(invalid_skin, "skin")

            wrong_extension = Path(temp) / "skin.jpg"
            Image.new("RGB", (64, 64)).save(wrong_extension)
            with self.assertRaisesRegex(ValueError, "PNG"):
                validate_cosmetic_image(wrong_extension, "skin")

    def test_offline_profiles_and_cosmetic_paths_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "CONFIG_PATH", Path(temp) / "config.json"):
                cfg = dict(config.DEFAULTS)
                cfg["offline_profiles"] = ["Builder"]
                cfg["active_offline_profile"] = "Builder"
                cfg["username"] = "Builder"
                cfg["local_cosmetics"] = {
                    "skin_path": "/local/skin.png",
                    "cape_path": "/local/cape.png",
                }
                config.save(cfg)
                saved = config.load()

            self.assertEqual(saved["offline_profiles"], ["Builder"])
            self.assertEqual(saved["active_offline_profile"], "Builder")
            self.assertEqual(saved["local_cosmetics"]["skin_path"], "/local/skin.png")


class BrowseInstallStateTests(unittest.TestCase):
    def test_successful_sequential_installs_keep_browse_results_and_query(self):
        editor = _bare_editor()
        editor.theme = {
            "BORDER_COL": "#292E36",
            "TEXT_MUTED": "#A2A8B2",
        }
        first_button = _Widget()
        second_button = _Widget()
        editor._project_buttons = {"first": first_button, "second": second_button}
        results = [{"project_id": "first"}, {"project_id": "second"}]
        editor._browse_projects = results
        editor.search = _Widget()
        editor.search.get = Mock(return_value="sodium")

        for project_id, button in (("first", first_button), ("second", second_button)):
            editor._working = True
            editor._active_install_project_id = project_id
            editor._finish_install(f"Installed {project_id}")
            self.assertEqual(button.values["text"], "Installed")
            self.assertEqual(button.values["state"], "disabled")

        self.assertIs(editor._browse_projects, results)
        self.assertEqual(editor.search.get(), "sodium")
        editor._refresh_content.assert_not_called()

    def test_failed_install_restores_only_its_browse_button(self):
        editor = _bare_editor()
        editor._project_buttons = {"failed": _Widget()}
        editor._browse_projects = [{"project_id": "failed"}]
        editor._active_install_project_id = "failed"

        editor._finish_install_error("network unavailable")

        self.assertEqual(editor._project_buttons["failed"].values["text"], "Install")
        self.assertEqual(editor._project_buttons["failed"].values["state"], "normal")
        self.assertEqual(editor._browse_projects, [{"project_id": "failed"}])
        self.assertEqual(editor.status.values["text"], "network unavailable")
        editor._refresh_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
