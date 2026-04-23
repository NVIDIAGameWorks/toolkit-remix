"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import tempfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import omni.kit.test
from omni.flux.utils.common import version as _version


class TestVersion(omni.kit.test.AsyncTestCase):
    async def test_get_app_version_returns_version_file_contents_when_version_file_exists(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            kit_dir = Path(temp_dir) / "kit"
            kit_dir.mkdir()
            version_file = Path(temp_dir) / "VERSION"
            version_file.write_text("1.2.3+dev.456\n", encoding="utf-8")
            tokens = Mock()
            tokens.resolve.return_value = str(kit_dir)

            with patch.object(_version.carb.tokens, "get_tokens_interface", return_value=tokens):
                # Act
                result = _version.get_app_version()

        # Assert
        self.assertEqual("1.2.3+dev.456", result)

    async def test_get_app_version_returns_kit_app_version_when_version_file_is_missing(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            kit_dir = Path(temp_dir) / "kit"
            kit_dir.mkdir()
            tokens = Mock()
            tokens.resolve.return_value = str(kit_dir)
            app = Mock()
            app.get_app_version.return_value = "9.9.9"

            with (
                patch.object(_version.carb.tokens, "get_tokens_interface", return_value=tokens),
                patch.object(_version.omni.kit.app, "get_app", return_value=app),
            ):
                # Act
                result = _version.get_app_version()

        # Assert
        self.assertEqual("9.9.9", result)

    async def test_get_app_version_logs_and_falls_back_when_version_file_read_fails(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            kit_dir = Path(temp_dir) / "kit"
            kit_dir.mkdir()
            version_file = Path(temp_dir) / "VERSION"
            version_file.write_text("unused", encoding="utf-8")
            tokens = Mock()
            tokens.resolve.return_value = str(kit_dir)
            app = Mock()
            app.get_app_version.return_value = "fallback-version"

            with (
                patch.object(_version.carb.tokens, "get_tokens_interface", return_value=tokens),
                patch.object(_version.omni.kit.app, "get_app", return_value=app),
                patch("builtins.open", mock_open()) as open_mock,
                patch.object(_version.carb, "log_error") as log_error_mock,
            ):
                open_mock.side_effect = OSError("boom")

                # Act
                result = _version.get_app_version()

        # Assert
        self.assertEqual("fallback-version", result)
        log_error_mock.assert_called_once()
        self.assertIn("Error reading version file", log_error_mock.call_args.args[0])

    async def test_get_app_distribution_returns_suffix_when_version_contains_distribution(self):
        # Arrange
        with patch.object(_version, "get_app_version", return_value="1.0.0+dev.123456"):
            # Act
            result = _version.get_app_distribution()

        # Assert
        self.assertEqual("dev.123456", result)

    async def test_get_app_distribution_returns_none_when_version_has_no_distribution(self):
        # Arrange
        with patch.object(_version, "get_app_version", return_value="1.0.0"):
            # Act
            result = _version.get_app_distribution()

        # Assert
        self.assertIsNone(result)
