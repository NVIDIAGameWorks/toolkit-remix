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

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

import omni.kit.test
from omni.flux.utils.common.symlink import create_folder_symlinks as _create_folder_symlinks
from omni.flux.utils.common.symlink import should_confirm_link_path_replacement as _should_confirm_link_path_replacement
from omni.flux.utils.common.uac import UnsupportedPlatformError as _UnsupportedPlatformError

_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_JUNCTION_ATTRIBUTES = _FILE_ATTRIBUTE_REPARSE_POINT | _FILE_ATTRIBUTE_DIRECTORY


class TestSymlink(omni.kit.test.AsyncTestCase):
    async def test_should_confirm_link_path_replacement_returns_false_for_missing_path(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "missing"

            # Act
            should_confirm = _should_confirm_link_path_replacement(link)

            # Assert
            self.assertFalse(should_confirm)

    async def test_should_confirm_link_path_replacement_returns_false_for_empty_directory(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            link.mkdir()

            # Act
            should_confirm = _should_confirm_link_path_replacement(link)

            # Assert
            self.assertFalse(should_confirm)
            self.assertTrue(link.exists())

    async def test_should_confirm_link_path_replacement_returns_true_for_non_empty_directory(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            link.mkdir()
            (link / "file.txt").write_text("content")

            # Act
            should_confirm = _should_confirm_link_path_replacement(link)

            # Assert
            self.assertTrue(should_confirm)
            self.assertTrue(link.exists())

    async def test_should_confirm_link_path_replacement_returns_true_when_directory_cannot_be_inspected(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            link.mkdir()

            # Act
            with patch.object(Path, "iterdir", side_effect=OSError("denied")):
                should_confirm = _should_confirm_link_path_replacement(link)

            # Assert
            self.assertTrue(should_confirm)
            self.assertTrue(link.exists())

    async def test_create_folder_symlinks_replace_existing_links_deletes_directory(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            target = Path(temp_dir) / "target"
            child = link / "child"
            child.mkdir(parents=True)
            target.mkdir()
            (child / "file.txt").write_text("content")

            # Act
            with patch("sys.platform", "win32"), patch("subprocess.check_call") as mock:
                _create_folder_symlinks([(link, target)], create_junction=True, replace_existing_links=True)

            # Assert
            self.assertFalse(link.exists())
            self.assertEqual(mock.call_args, call(f'mklink /J "{link}" "{target}"', shell=True))

    async def test_create_folder_symlinks_replace_existing_links_deletes_file(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            target = Path(temp_dir) / "target"
            link.write_text("content")
            target.mkdir()

            # Act
            with patch("sys.platform", "win32"), patch("subprocess.check_call") as mock:
                _create_folder_symlinks([(link, target)], create_junction=True, replace_existing_links=True)

            # Assert
            self.assertFalse(link.exists())
            self.assertEqual(mock.call_args, call(f'mklink /J "{link}" "{target}"', shell=True))

    async def test_create_folder_symlinks_replace_existing_links_removes_junction_not_target(self):
        if sys.platform != "win32":
            self.skipTest("Windows junction behavior")

        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            target = Path(temp_dir) / "target"
            target.mkdir()
            target_child = target / "content.txt"
            target_child.write_text("content")
            subprocess.check_call(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Act
            with patch("subprocess.check_call") as mock:
                _create_folder_symlinks([(link, target)], create_junction=True, replace_existing_links=True)

            # Assert
            self.assertFalse(link.exists())
            self.assertTrue(target.exists())
            self.assertTrue(target_child.exists())
            self.assertEqual(mock.call_args, call(f'mklink /J "{link}" "{target}"', shell=True))

    async def test_create_folder_symlinks_replace_existing_links_uses_rmdir_for_detected_junction(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            target = Path(temp_dir) / "target"
            link.mkdir()
            target.mkdir()

            # Act
            with (
                patch("os.lstat", return_value=Mock(st_file_attributes=_JUNCTION_ATTRIBUTES)),
                patch("omni.flux.utils.common.symlink.rmtree") as rmtree_mock,
                patch("subprocess.check_call") as check_call_mock,
                patch("sys.platform", "win32"),
            ):
                _create_folder_symlinks([(link, target)], create_junction=True, replace_existing_links=True)

            # Assert
            self.assertFalse(link.exists())
            rmtree_mock.assert_not_called()
            self.assertEqual(check_call_mock.call_args, call(f'mklink /J "{link}" "{target}"', shell=True))

    async def test_create_folder_symlinks_existing_detected_junction_skips_creation(self):
        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            target = Path(temp_dir) / "target"
            link.mkdir()
            target.mkdir()

            # Act
            with (
                patch("os.lstat", return_value=Mock(st_file_attributes=_JUNCTION_ATTRIBUTES)),
                patch("omni.flux.utils.common.symlink.is_broken_symlink") as is_broken_symlink_mock,
                patch("omni.flux.utils.common.symlink._link_points_to_target", return_value=True),
                patch("subprocess.check_call") as check_call_mock,
                patch("sys.platform", "win32"),
            ):
                _create_folder_symlinks([(link, target)], create_junction=True)

            # Assert
            self.assertTrue(link.exists())
            is_broken_symlink_mock.assert_not_called()
            check_call_mock.assert_not_called()

    async def test_create_folder_symlinks_existing_junction_without_replace_skips_creation(self):
        if sys.platform != "win32":
            self.skipTest("Windows junction behavior")

        with TemporaryDirectory() as temp_dir:
            # Arrange
            link = Path(temp_dir) / "link"
            target = Path(temp_dir) / "target"
            target.mkdir()
            subprocess.check_call(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            try:
                # Act
                with patch("subprocess.check_call") as mock:
                    _create_folder_symlinks([(link, target)], create_junction=True, replace_existing_links=False)

                # Assert
                self.assertTrue(link.exists())
                mock.assert_not_called()
            finally:
                if link.exists():
                    link.rmdir()

    async def test_create_symlink_as_admin(self):
        with (
            patch("sys.platform", "win32"),
            patch("subprocess.check_call") as mock,
            patch("omni.flux.utils.common.symlink._is_admin") as mock_is_admin,
        ):
            # Arrange
            mock_is_admin.return_value = True

            # Act
            _create_folder_symlinks([("link", "target")])

            # Assert
            self.assertEqual(mock.call_args, call('mklink /d "link" "target"', shell=True))

    async def test_create_symlinks_as_admin(self):
        with (
            patch("sys.platform", "win32"),
            patch("subprocess.check_call") as mock,
            patch("omni.flux.utils.common.symlink._is_admin") as mock_is_admin,
        ):
            # Arrange
            mock_is_admin.return_value = True

            # Act
            _create_folder_symlinks([("link1", "target1"), ("link2", "target2")])

            # Assert
            self.assertEqual(
                mock.call_args, call('mklink /d "link1" "target1" && mklink /d "link2" "target2"', shell=True)
            )

    async def test_create_symlinks_as_no_admin(self):
        with (
            patch("sys.platform", "win32"),
            patch("omni.flux.utils.common.symlink._sudo") as mock,
            patch("omni.flux.utils.common.symlink._is_admin") as mock_is_admin,
        ):
            # Arrange
            mock_is_admin.return_value = False

            # Act
            _create_folder_symlinks([("link1", "target1"), ("link2", "target2")])

            # Assert
            self.assertEqual(
                mock.call_args,
                call(
                    "cmd",
                    params=["/c", "mklink", "/d", '"link1"', '"target1"', "&&", "mklink", "/d", '"link2"', '"target2"'],
                ),
            )

    async def test_create_junctions_as_admin(self):
        with (
            patch("sys.platform", "win32"),
            patch("subprocess.check_call") as mock,
            patch("omni.flux.utils.common.symlink._is_admin") as mock_is_admin,
        ):
            # Arrange
            mock_is_admin.return_value = True

            # Act
            _create_folder_symlinks([("link1", "target1"), ("link2", "target2")], create_junction=True)

            # Assert
            self.assertEqual(
                mock.call_args, call('mklink /J "link1" "target1" && mklink /J "link2" "target2"', shell=True)
            )

    async def test_create_symlinks_linux(self):
        with patch("sys.platform", "linux"), patch("subprocess.check_call") as mock:
            # Arrange
            links = [("link1", "target1"), ("link2", "target2")]

            # Act
            _create_folder_symlinks(links)

            # Assert
            self.assertEqual(mock.call_args, call('ln -s "target1" "link1" && ln -s "target2" "link2"', shell=True))

    async def test_wrong_plaform(self):
        # Arrange
        links = [("link1", "target1"), ("link2", "target2")]

        with patch("sys.platform", "blabla"):
            # Act
            with self.assertRaises(_UnsupportedPlatformError) as raised:
                _create_folder_symlinks(links)

            # Assert
            self.assertIsInstance(raised.exception, _UnsupportedPlatformError)
