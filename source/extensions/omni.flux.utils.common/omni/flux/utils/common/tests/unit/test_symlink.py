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

from unittest.mock import call, patch

import omni.kit.test
from omni.flux.utils.common.symlink import create_folder_symlinks as _create_folder_symlinks
from omni.flux.utils.common.uac import UnsupportedPlatformError as _UnsupportedPlatformError


class TestSymlink(omni.kit.test.AsyncTestCase):
    async def test_create_symlink_as_admin(self):
        with (
            patch("sys.platform", "win32"),
            patch("subprocess.check_call") as mock,
            patch("omni.flux.utils.common.symlink._is_admin") as mock_is_admin,
        ):
            mock_is_admin.return_value = True
            _create_folder_symlinks([("link", "target")])

            self.assertEqual(mock.call_args, call('mklink /d "link" "target"', shell=True))

    async def test_create_symlinks_as_admin(self):
        with (
            patch("sys.platform", "win32"),
            patch("subprocess.check_call") as mock,
            patch("omni.flux.utils.common.symlink._is_admin") as mock_is_admin,
        ):
            mock_is_admin.return_value = True
            _create_folder_symlinks([("link1", "target1"), ("link2", "target2")])

            self.assertEqual(
                mock.call_args, call('mklink /d "link1" "target1" && mklink /d "link2" "target2"', shell=True)
            )

    async def test_create_symlinks_as_no_admin(self):
        with (
            patch("sys.platform", "win32"),
            patch("omni.flux.utils.common.symlink._sudo") as mock,
            patch("omni.flux.utils.common.symlink._is_admin") as mock_is_admin,
        ):
            mock_is_admin.return_value = False
            _create_folder_symlinks([("link1", "target1"), ("link2", "target2")])

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
            mock_is_admin.return_value = True
            _create_folder_symlinks([("link1", "target1"), ("link2", "target2")], create_junction=True)

            self.assertEqual(
                mock.call_args, call('mklink /J "link1" "target1" && mklink /J "link2" "target2"', shell=True)
            )

    async def test_create_symlinks_linux(self):
        with patch("sys.platform", "linux"), patch("subprocess.check_call") as mock:
            _create_folder_symlinks([("link1", "target1"), ("link2", "target2")])

            self.assertEqual(mock.call_args, call('ln -s "target1" "link1" && ln -s "target2" "link2"', shell=True))

    async def test_wrong_plaform(self):
        with patch("sys.platform", "blabla"):
            with self.assertRaises(_UnsupportedPlatformError):
                _create_folder_symlinks([("link1", "target1"), ("link2", "target2")])
