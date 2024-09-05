"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import omni.client
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.capture.core.shared import Setup as CaptureCore
from lightspeed.trex.contexts import get_instance as _get_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.project_wizard.core import ProjectWizardKeys, ProjectWizardSchema
from lightspeed.trex.replacement.core.shared import Setup as ReplacementCore
from omni.flux.utils.widget.resources import get_test_data as _get_test_data


class MockListEntry:
    def __init__(self, path: str, size: int = 0, access: int = 0, flags=omni.client.ItemFlags.READABLE_FILE):
        self.relative_path = path
        self.size = size
        self.access = access
        self.flags = flags
        self.modified_time = datetime.now()


class TestItems(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def copy_from_example_project(self, source: str, target: str):
        example_dir = _get_test_data("usd/project_example")
        shutil.copyfile(f"{example_dir}/{source}", f"{self.temp_dir.name}/{target}")
        project_file = Path(self.temp_dir.name) / target
        return project_file

    async def test_keys_have_expected_values(self):
        # This test only serves to make sure we preserve compatibility with existing schemas.
        # Changing the Keys enum values will result in "legacy" schemas breaking.

        # Arrange
        existing_project = ProjectWizardKeys.EXISTING_PROJECT.value
        project_file = ProjectWizardKeys.PROJECT_FILE.value
        remix_directory = ProjectWizardKeys.REMIX_DIRECTORY.value
        capture_file = ProjectWizardKeys.CAPTURE_FILE.value
        existing_mods = ProjectWizardKeys.EXISTING_MODS.value
        mod_file = ProjectWizardKeys.MOD_FILE.value

        # Act
        pass

        # Assert
        self.assertEqual(6, len(ProjectWizardKeys))
        self.assertEqual("existing_project", existing_project)
        self.assertEqual("project_file", project_file)
        self.assertEqual("remix_directory", remix_directory)
        self.assertEqual("capture_file", capture_file)
        self.assertEqual("existing_mods", existing_mods)
        self.assertEqual("mod_file", mod_file)

    async def test_schema_are_project_symlinks_valid_no_deps_returns_false(self):
        # Arrange
        project_file = Path(self.temp_dir.name) / "projects" / "MyProject" / "project.usda"
        project_dir = project_file.parent

        os.makedirs(project_dir, exist_ok=True)
        with open(project_file, "xb"):
            pass

        # Act
        value = ProjectWizardSchema.are_project_symlinks_valid(project_file)

        # Assert
        self.assertEqual(False, value)

    async def test_schema_are_project_symlinks_valid_no_remix_mod_returns_false(self):
        # Arrange
        project_dir = Path(self.temp_dir.name) / "projects" / "MyProject"
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER

        project_file = project_dir / "project.usda"
        deps_dir = project_dir / constants.REMIX_DEPENDENCIES_FOLDER

        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(remix_dir, exist_ok=True)

        subprocess.check_call(f'mklink /J "{deps_dir}" "{remix_dir}"', shell=True)

        # Act
        value = ProjectWizardSchema.are_project_symlinks_valid(project_file)

        # Assert
        self.assertEqual(False, value)

    async def test_schema_are_project_symlinks_valid_accepted_returns_true(self):
        # Arrange
        project_dir = Path(self.temp_dir.name) / "projects" / "MyProject"
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER

        deps_dir = project_dir / constants.REMIX_DEPENDENCIES_FOLDER
        mods_dir = remix_dir / constants.REMIX_MODS_FOLDER
        project_link_dir = mods_dir / "MyProject"
        project_file = project_dir / "project.usda"

        try:
            os.makedirs(mods_dir, exist_ok=True)
            os.makedirs(project_dir, exist_ok=True)

            subprocess.check_call(f'mklink /J "{deps_dir}" "{remix_dir}"', shell=True)
            subprocess.check_call(f'mklink /J "{project_link_dir}" "{project_dir}"', shell=True)

            # Act
            value = ProjectWizardSchema.are_project_symlinks_valid(project_file)

            # Assert
            self.assertEqual(True, value)

        finally:
            # Break the recursive loop or the temp_dir cleanup breaks
            project_link_dir.unlink()
            deps_dir.unlink()

    async def test_schema_is_project_file_valid_empty_name_throws(self):
        # Arrange
        file_name = "  "

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_project_file_valid(file_name, {})

        # Assert
        self.assertEqual(f"'{file_name}' is not valid", str(cm.exception))

    async def test_schema_is_project_file_valid_invalid_characters(self):
        file_names = [
            "test<.usd",
            "test(.usd",
            "test|.usd",
            "test?.usd",
            "test*.usd",
            "test>.usd",
            "test).usd",
            "test:.usd",
            'test".usd',
        ]

        for name in file_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as cm:
                    ProjectWizardSchema.is_project_file_valid(Path(self.temp_dir.name) / name, {})
                self.assertEqual(str(cm.exception), f"'{name}' has an invalid character in filename.")

    async def test_schema_is_project_file_valid_invalid_windows_reserved_words(self):
        file_names = [
            "NUL.usd",
            "AUX.usd",
            "CON.usd",
            "PRN.usd",
            "COM1.usd",
            "LPT1.usd",
        ]

        for name in file_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as cm:
                    ProjectWizardSchema.is_project_file_valid(Path(self.temp_dir.name) / name, {})
                self.assertEqual(str(cm.exception), f"'{name}' has a Windows reserved word in filename.")

    async def test_schema_is_project_file_valid_invalid_whitespace(self):
        file_names = [
            Path(self.temp_dir.name) / "test whitespace.usd",
            "path/to/invalid proj/test.usd",
        ]

        for path in file_names:
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as cm:
                    ProjectWizardSchema.is_project_file_valid(path, {})
                self.assertEqual(str(cm.exception), f"'{path}' has a whitespace in file path.")

    async def test_schema_is_capture_file_valid_accepted_filename(self):
        file_names = [
            "test.usd",
            "testmod.usd",
            "test_capture.usd",
            "test_baker.usd",
            "testsublayer.usd",
            "gibberishmod.usd",
            "gibberishcapture.usd",
        ]

        for name in file_names:
            with self.subTest(name=name):
                value = ProjectWizardSchema.is_project_file_valid(Path(self.temp_dir.name) / name, {})
                self.assertEqual(Path(self.temp_dir.name) / name, value)

    async def test_schema_is_project_file_valid_reserved_words(self):
        file_names = ["mod.usda", "mod_capture_baker.usda", "sublayer.usda"]

        for name in file_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as cm:
                    ProjectWizardSchema.is_project_file_valid(Path(self.temp_dir.name) / name, {})
                self.assertEqual(str(cm.exception), f"'{name}' has a reserved name in filename.")

    async def test_schema_is_project_file_valid_not_usd_throws(self):
        # Arrange
        project_file = Path(self.temp_dir.name) / "project.txt"

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_project_file_valid(project_file, {})

        # Assert
        self.assertEqual(f"The path '{project_file}' is not a USD file", str(cm.exception))

    async def test_schema_is_project_file_valid_not_writable_file_throws(self):
        # Arrange
        project_file = await self.copy_from_example_project("combined.usda", "project.usda")

        # Act
        with patch.object(omni.client, "stat") as mock:
            mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(project_file), flags=omni.client.ItemFlags.READABLE_FILE),
            )

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_project_file_valid(
                    project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: True}
                )

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(project_file), args[0])
        self.assertEqual(f"The path '{project_file}' is not a writable file", str(cm.exception))

    async def test_schema_is_project_file_valid_is_mod_file_throws(self):
        # Arrange
        project_file = await self.copy_from_example_project("combined.usda", "project.usda")

        # Act
        with (
            patch.object(omni.client, "stat") as stat_mock,
            patch.object(ReplacementCore, "is_mod_file") as mod_file_mock,
        ):
            stat_mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(project_file), flags=omni.client.ItemFlags.WRITEABLE_FILE),
            )
            mod_file_mock.return_value = True

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_project_file_valid(
                    project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: True}
                )

        # Assert
        stat_args, _ = stat_mock.call_args
        mod_file_args, _ = mod_file_mock.call_args
        self.assertEqual(str(project_file), stat_args[0])
        self.assertEqual(str(project_file), mod_file_args[0])
        self.assertEqual(f"The path '{project_file}' is a mod file", str(cm.exception))

    async def test_schema_is_project_file_valid_is_capture_file_throws(self):
        # Arrange
        project_file = await self.copy_from_example_project("combined.usda", "project.usda")

        # Act
        with (
            patch.object(omni.client, "stat") as stat_mock,
            patch.object(ReplacementCore, "is_mod_file") as mod_file_mock,
            patch.object(CaptureCore, "is_capture_file") as capture_file_mock,
        ):
            stat_mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(project_file), flags=omni.client.ItemFlags.WRITEABLE_FILE),
            )
            mod_file_mock.return_value = False
            capture_file_mock.return_value = True

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_project_file_valid(
                    project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: True}
                )

        # Assert
        stat_args, _ = stat_mock.call_args
        mod_file_args, _ = mod_file_mock.call_args
        capture_file_args, _ = capture_file_mock.call_args
        self.assertEqual(str(project_file), stat_args[0])
        self.assertEqual(str(project_file), mod_file_args[0])
        self.assertEqual(str(project_file), capture_file_args[0])
        self.assertEqual(f"The path '{project_file}' is a capture file", str(cm.exception))

    async def test_schema_is_project_file_valid_not_writable_directory_throws(self):
        # Arrange
        project_file = Path(self.temp_dir.name) / "project.usda"

        # Act
        with patch.object(omni.client, "stat") as mock:
            mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(project_file.parent), flags=omni.client.ItemFlags.READABLE_FILE),
            )

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_project_file_valid(
                    project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: False}
                )

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(project_file.parent), args[0])
        self.assertEqual(f"The path's parent directory '{str(project_file.parent)}' is not writable", str(cm.exception))

    async def test_schema_is_project_file_valid_is_in_rtx_remix_dir_throws(self):
        # Arrange
        project_file = Path(self.temp_dir.name) / constants.REMIX_FOLDER / "project.usda"

        project_file.parent.mkdir(parents=True)

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_project_file_valid(project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: False})

        # Assert
        self.assertEqual(
            f"The project should not be created in the '{constants.REMIX_FOLDER}' root directory", str(cm.exception)
        )

    async def test_schema_is_project_file_valid_is_in_rtx_remix_mods_dir_throws(self):
        # Arrange
        project_file = Path(self.temp_dir.name) / constants.REMIX_FOLDER / constants.REMIX_MODS_FOLDER / "project.usda"

        project_file.parent.mkdir(parents=True)

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_project_file_valid(project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: False})

        # Assert
        self.assertEqual(
            f"The project should not be created directly in the '{constants.REMIX_MODS_FOLDER}' directory. "
            f"It should be created in a unique subdirectory.",
            str(cm.exception),
        )

    async def test_schema_is_project_file_valid_is_in_rtx_remix_captures_dir_throws(self):
        # Arrange
        project_file = (
            Path(self.temp_dir.name)
            / constants.REMIX_FOLDER
            / constants.REMIX_CAPTURE_FOLDER
            / "TestProject"
            / "project.usda"
        )

        project_file.parent.mkdir(parents=True)

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_project_file_valid(project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: False})

        # Assert
        self.assertEqual(
            f"The project should not be created in the '{constants.REMIX_CAPTURE_FOLDER}' directory", str(cm.exception)
        )

    async def test_schema_is_project_file_valid_non_empty_directory_throws(self):
        # Arrange
        project_file = Path(self.temp_dir.name) / "project.usda"

        # Act
        with patch.object(omni.client, "list") as mock:
            mock.return_value = (
                omni.client.Result.OK,
                [MockListEntry(str(project_file.parent / "existing.usda"), flags=omni.client.ItemFlags.WRITEABLE_FILE)],
            )

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_project_file_valid(
                    project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: False}
                )

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(project_file.parent), args[0])
        self.assertEqual("The project should be created in a valid empty directory", str(cm.exception))

    async def test_schema_is_project_file_valid_project_exists_throws(self):
        # Arrange
        project_dir = "MyProject"
        project_file = Path(self.temp_dir.name) / "projects" / project_dir / "project.usda"
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER
        remix_project_dir = remix_dir / constants.REMIX_MODS_FOLDER / project_dir

        # Act
        with patch.object(omni.client, "stat") as stat_mock, patch.object(omni.client, "list") as list_mock:
            stat_mock.side_effect = [
                (
                    omni.client.Result.OK,
                    MockListEntry(str(project_file.parent), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                ),
                (
                    omni.client.Result.OK,
                    MockListEntry(str(remix_project_dir), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
                ),
            ]
            list_mock.return_value = (
                omni.client.Result.OK,
                [],
            )

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_project_file_valid(
                    project_file,
                    {
                        ProjectWizardKeys.EXISTING_PROJECT.value: False,
                        ProjectWizardKeys.REMIX_DIRECTORY.value: remix_dir,
                    },
                )

        # Assert
        self.assertEqual(
            f"A project with the same name already exists: '{remix_project_dir}'",
            str(cm.exception),
        )

    async def test_schema_is_project_file_valid_accepted_new_returns_val(self):
        # Arrange
        project_file = Path(self.temp_dir.name) / "project.usda"

        # Act
        with patch.object(omni.client, "stat") as mock:
            mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(project_file), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
            )

            value = ProjectWizardSchema.is_project_file_valid(
                project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: False}
            )

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(project_file.parent), args[0])
        self.assertEqual(project_file, value)

    async def test_schema_is_project_file_valid_accepted_existing_returns_val(self):
        # Arrange
        project_file = await self.copy_from_example_project("combined.usda", "project.usda")

        # Act
        with (
            patch.object(omni.client, "stat") as stat_mock,
            patch.object(ReplacementCore, "is_mod_file") as mod_file_mock,
            patch.object(CaptureCore, "is_capture_file") as capture_file_mock,
        ):
            stat_mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(project_file), flags=omni.client.ItemFlags.WRITEABLE_FILE),
            )
            mod_file_mock.return_value = False
            capture_file_mock.return_value = False

            value = ProjectWizardSchema.is_project_file_valid(
                project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: True}
            )

        # Assert
        stat_args, _ = stat_mock.call_args
        mod_file_args, _ = mod_file_mock.call_args
        self.assertEqual(str(project_file), stat_args[0])
        self.assertEqual(str(project_file), mod_file_args[0])
        self.assertEqual(project_file, value)

    async def test_schema_is_remix_directory_valid_none_new_project_throws(self):
        # Arrange
        pass

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_remix_directory_valid(None, {ProjectWizardKeys.EXISTING_PROJECT.value: False})

        # Assert
        self.assertEqual("The is mandatory for new projects", str(cm.exception))

    async def test_schema_is_remix_directory_valid_none_invalid_symlinks_throws(self):
        # Arrange
        pass

        # Act
        with patch.object(ProjectWizardSchema, "are_project_symlinks_valid") as mock:
            mock.return_value = False
            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_remix_directory_valid(None, {ProjectWizardKeys.EXISTING_PROJECT.value: True})

        # Assert
        self.assertEqual(
            "The project path symlinks are invalid. A Remix directory is required to fix them.", str(cm.exception)
        )

    async def test_schema_is_remix_directory_valid_not_remix_folder_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / "invalid"

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_remix_directory_valid(remix_dir, {})

        # Assert
        self.assertEqual(
            f"The path must point to a directory with the name: '{constants.REMIX_FOLDER}'", str(cm.exception)
        )

    async def test_schema_is_remix_directory_valid_stat_not_ok_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER

        # Act
        with patch.object(omni.client, "stat") as mock:
            mock.return_value = (omni.client.Result.ERROR, None)
            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_remix_directory_valid(remix_dir, {})

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(remix_dir), args[0])
        self.assertEqual("The remix directory invalid", str(cm.exception))

    async def test_schema_is_remix_directory_valid_not_writable_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER

        # Act
        with patch.object(omni.client, "stat") as mock:
            mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(remix_dir), flags=omni.client.ItemFlags.READABLE_FILE),
            )
            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_remix_directory_valid(remix_dir, {})

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(remix_dir), args[0])
        self.assertEqual("The remix directory is not writable", str(cm.exception))

    async def test_schema_is_remix_directory_valid_no_capture_subdir_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER

        # Act
        with patch.object(omni.client, "stat") as stat_mock, patch.object(omni.client, "list") as list_mock:
            stat_mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(remix_dir), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
            )
            list_mock.return_value = (omni.client.Result.OK, [MockListEntry(str(constants.REMIX_MODS_FOLDER))])
            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_remix_directory_valid(remix_dir, {})

        # Assert
        stat_args, _ = stat_mock.call_args
        list_args, _ = list_mock.call_args
        self.assertEqual(str(remix_dir), stat_args[0])
        self.assertEqual(str(remix_dir), list_args[0])
        self.assertEqual(
            f"The remix directory is missing a {constants.REMIX_CAPTURE_FOLDER} subdirectory", str(cm.exception)
        )

    async def test_schema_is_remix_directory_valid_accepted_returns_val(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER

        # Act
        with patch.object(omni.client, "stat") as stat_mock, patch.object(omni.client, "list") as list_mock:
            stat_mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(remix_dir), flags=omni.client.ItemFlags.CAN_HAVE_CHILDREN),
            )
            list_mock.return_value = (
                omni.client.Result.OK,
                [MockListEntry(str(constants.REMIX_CAPTURE_FOLDER)), MockListEntry(str(constants.REMIX_MODS_FOLDER))],
            )
            value = ProjectWizardSchema.is_remix_directory_valid(remix_dir, {})

        # Assert
        stat_args, _ = stat_mock.call_args
        list_args, _ = list_mock.call_args
        self.assertEqual(str(remix_dir), stat_args[0])
        self.assertEqual(str(remix_dir), list_args[0])
        self.assertEqual(remix_dir, value)

    async def test_schema_are_all_mod_files_valid_parent_not_mod_folder_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER
        mod_dir = Path(self.temp_dir.name) / "ExistingMod" / "mod.usda"

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.are_all_mod_files_valid(mod_dir, {ProjectWizardKeys.REMIX_DIRECTORY.value: remix_dir})

        # Assert
        self.assertEqual(
            f"The mod should be in the '{constants.REMIX_MODS_FOLDER}' subdirectory of the Remix Directory",
            str(cm.exception),
        )

    async def test_schema_are_all_mod_files_valid_is_not_mod_file_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER
        mod_dir = remix_dir / constants.REMIX_MODS_FOLDER / "ExistingMod" / "mod.usda"

        # Act
        with patch.object(ReplacementCore, "is_mod_file") as mock:
            mock.return_value = False
            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.are_all_mod_files_valid(
                    mod_dir, {ProjectWizardKeys.REMIX_DIRECTORY.value: remix_dir}
                )

            # Assert
            args, _ = mock.call_args
            self.assertEqual(str(mod_dir), args[0])
            self.assertEqual("The path is not a valid mod file", str(cm.exception))

    async def test_schema_are_all_mod_files_valid_accepted_returns_val(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER
        mod_dir = remix_dir / constants.REMIX_MODS_FOLDER / "ExistingMod" / "mod.usda"

        # Act
        with patch.object(ReplacementCore, "is_mod_file") as mock:
            mock.return_value = True
            value = ProjectWizardSchema.are_all_mod_files_valid(
                mod_dir, {ProjectWizardKeys.REMIX_DIRECTORY.value: remix_dir}
            )

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(mod_dir), args[0])
        self.assertEqual(mod_dir, value)

    async def test_schema_is_mod_file_valid_not_in_existing_mods_throws(self):
        # Arrange
        mod_file = Path(self.temp_dir.name) / "mod.usda"

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_mod_file_valid(mod_file, {ProjectWizardKeys.EXISTING_MODS.value: []})

        # Assert
        self.assertEqual("The path must also be present in the `existing_mods` list", str(cm.exception))

    async def test_schema_is_mod_file_valid_is_not_mod_file_throws(self):
        # Arrange
        mod_file = Path(self.temp_dir.name) / "mod.usda"

        # Act
        with patch.object(ReplacementCore, "is_mod_file") as mock:
            mock.return_value = False

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_mod_file_valid(mod_file, {ProjectWizardKeys.EXISTING_MODS.value: [mod_file]})

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(mod_file), args[0])
        self.assertEqual("The path is not a valid mod file", str(cm.exception))

    async def test_schema_is_mod_file_valid_no_value_returns_val(self):
        # Arrange
        pass

        # Act
        value = ProjectWizardSchema.is_mod_file_valid(None, {})

        # Assert
        self.assertEqual(None, value)

    async def test_schema_is_mod_file_valid_accepted_returns_val(self):
        # Arrange
        mod_file = Path(self.temp_dir.name) / "mod.usda"

        # Act
        with patch.object(ReplacementCore, "is_mod_file") as mock:
            mock.return_value = True
            value = ProjectWizardSchema.is_mod_file_valid(mod_file, {ProjectWizardKeys.EXISTING_MODS.value: [mod_file]})

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(mod_file), args[0])
        self.assertEqual(mod_file, value)

    async def test_schema_is_capture_file_valid_not_in_capture_folder_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER
        capture_file = Path(self.temp_dir.name) / "capture.usda"

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_capture_file_valid(
                capture_file, {ProjectWizardKeys.REMIX_DIRECTORY.value: remix_dir}
            )

        # Assert
        self.assertEqual(
            f"The capture should be in the '{constants.REMIX_CAPTURE_FOLDER}' subdirectory "
            f"of the {constants.REMIX_FOLDER} Directory",
            str(cm.exception),
        )

    async def test_schema_is_capture_file_valid_is_not_capture_file_throws(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER
        capture_file = remix_dir / constants.REMIX_CAPTURE_FOLDER / "capture.usda"

        # Act
        with patch.object(CaptureCore, "is_capture_file") as mock:
            mock.return_value = False

            with self.assertRaises(ValueError) as cm:
                ProjectWizardSchema.is_capture_file_valid(
                    capture_file, {ProjectWizardKeys.REMIX_DIRECTORY.value: remix_dir}
                )

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(capture_file), args[0])
        self.assertEqual("The path is not a valid capture file", str(cm.exception))

    async def test_schema_is_capture_file_valid_no_value_opening_returns_val(self):
        # Arrange
        pass

        # Act
        value = ProjectWizardSchema.is_capture_file_valid(None, {ProjectWizardKeys.EXISTING_PROJECT.value: True})

        # Assert
        self.assertEqual(None, value)

    async def test_schema_is_capture_file_valid_no_value_creating_throws(self):
        # Arrange
        pass

        # Act
        with self.assertRaises(ValueError) as cm:
            ProjectWizardSchema.is_capture_file_valid(None, {ProjectWizardKeys.EXISTING_PROJECT.value: False})

        # Assert
        self.assertEqual("A capture must be selected when creating a project", str(cm.exception))

    async def test_schema_is_capture_file_valid_accepted_returns_val(self):
        # Arrange
        remix_dir = Path(self.temp_dir.name) / constants.REMIX_FOLDER
        capture_file = remix_dir / constants.REMIX_CAPTURE_FOLDER / "capture.usda"

        # Act
        with patch.object(CaptureCore, "is_capture_file") as mock:
            mock.return_value = True
            value = ProjectWizardSchema.is_capture_file_valid(
                capture_file, {ProjectWizardKeys.REMIX_DIRECTORY.value: remix_dir}
            )

        # Assert
        args, _ = mock.call_args
        self.assertEqual(str(capture_file), args[0])
        self.assertEqual(capture_file, value)

    async def test_schema_is_existing_project_file_valid_layer_type_invalid(self):
        # Arrange
        project_file = await self.copy_from_example_project("replacements.usda", "project.usda")

        # Act
        with patch.object(omni.client, "stat") as mock:
            mock.return_value = (
                omni.client.Result.OK,
                MockListEntry(str(project_file.parent), flags=omni.client.ItemFlags.READABLE_FILE),
            )

            with self.assertRaises(ValueError) as cm:
                context = _get_contexts_instance()
                context.set_current_context(_TrexContexts.STAGE_CRAFT)
                ProjectWizardSchema.is_project_file_valid(
                    project_file, {ProjectWizardKeys.EXISTING_PROJECT.value: True}
                )

        # Assert
        self.assertEqual(
            "Unable to load layer as project file. Invalid layer type. Needs to be of type workfile.",
            str(cm.exception),
        )
