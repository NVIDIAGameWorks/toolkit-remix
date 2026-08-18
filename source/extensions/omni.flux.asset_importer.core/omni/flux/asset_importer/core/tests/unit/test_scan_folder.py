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

import re
from unittest.mock import Mock

import omni.kit.test

from ...scan_folder.scanner import ScannerCore


class TestScannerCore(omni.kit.test.AsyncTestCase):
    """Verify file filtering performed by the folder scanner."""

    def test_add_callback_with_existing_action_appends_callback(self):
        """Adding an existing action preserves its callbacks and appends new callbacks."""
        # Arrange
        first_callback = Mock()
        second_callback = Mock()
        core = ScannerCore(callbacks={"import": [first_callback]})

        # Act
        core.add_callback({"import": [second_callback]})

        # Assert
        core.do("import", ["asset.fbx"])
        first_callback.assert_called_once_with(["asset.fbx"])
        second_callback.assert_called_once_with(["asset.fbx"])

    def test_add_callback_with_new_action_registers_callback(self):
        """Adding a new action makes it dispatchable."""
        # Arrange
        callback = Mock()
        core = ScannerCore(callbacks={})

        # Act
        core.add_callback({"texture": [callback]})

        # Assert
        core.do("texture", ["albedo.png"])
        callback.assert_called_once_with(["albedo.png"])

    def test_do_with_unknown_action_raises_key_error(self):
        """Dispatching an unregistered action reports the missing action."""
        # Arrange
        core = ScannerCore(callbacks={})

        # Act
        with self.assertRaises(KeyError) as error:
            core.do("missing", [])

        # Assert
        self.assertEqual(error.exception.args, ("missing",))

    def test_get_valid_files_with_mixed_entries_returns_matching_supported_files(self):
        """Scanning filters directories, non-matching names, and unsupported types."""
        # Arrange
        directory = Mock(is_file=Mock(return_value=False), suffix="", name="folder")
        texture = Mock(is_file=Mock(return_value=True), suffix=".PNG", name="normal.PNG")
        asset = Mock(is_file=Mock(return_value=True), suffix=".fbx", name="mesh.fbx")
        uppercase_usd = Mock(is_file=Mock(return_value=True), suffix=".USD", name="scene.USD")
        unsupported = Mock(is_file=Mock(return_value=True), suffix=".txt", name="readme.txt")
        folder = Mock()
        folder.iterdir.return_value = (directory, texture, asset, uppercase_usd, unsupported)
        core = ScannerCore(callbacks={})

        # Act
        result = core.get_valid_files(folder, "normal|mesh|scene")

        # Assert
        self.assertEqual([texture, asset, uppercase_usd], result)

    def test_get_valid_files_with_invalid_expression_raises_error(self):
        """Scanning reports malformed regular expressions before enumerating the directory."""
        # Arrange
        folder = Mock()
        core = ScannerCore(callbacks={})

        # Act
        with self.assertRaises(re.error) as error:
            core.get_valid_files(folder, "[")

        # Assert
        self.assertIsInstance(error.exception, re.error)
        folder.iterdir.assert_not_called()

    def test_get_valid_files_with_enumeration_failure_propagates_error(self):
        """Scanning preserves directory enumeration failures for the caller to report."""
        # Arrange
        folder = Mock()
        folder.iterdir.side_effect = OSError("unavailable")
        core = ScannerCore(callbacks={})

        # Act
        with self.assertRaises(OSError) as error:
            core.get_valid_files(folder, "")

        # Assert
        self.assertEqual(str(error.exception), "unavailable")
