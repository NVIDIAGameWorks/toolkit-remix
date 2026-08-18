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

from unittest.mock import Mock, patch

import omni.kit.test

from ...selection_validation import classify_asset_selection, classify_texture_selection


class TestSelectionValidation(omni.kit.test.AsyncTestCase):
    """Verify one-pass classification for asset-ingestion selections."""

    def test_classify_asset_selection_with_mixed_paths_partitions_each_path(self):
        """Asset classification separates valid files, invalid files, and directories."""
        # Arrange
        directory = Mock(is_directory=True, suffix=".USD")
        valid_asset = Mock(is_directory=False, suffix=".fbx")
        unsupported_asset = Mock(is_directory=False, suffix="")

        # Act
        with patch(
            "omni.flux.asset_importer.core.selection_validation.OmniUrl",
            side_effect=(directory, valid_asset, unsupported_asset),
        ):
            result = classify_asset_selection(("folder.USD", "mesh.fbx", "extensionless"))

        # Assert
        self.assertEqual(("mesh.fbx",), result.valid_paths)
        self.assertEqual((unsupported_asset,), result.unsupported_paths)
        self.assertEqual((directory,), result.directory_paths)
        self.assertFalse(result.is_valid)

    def test_classify_asset_selection_with_uppercase_usd_accepts_file(self):
        """Asset extensions are accepted independently of case."""
        # Arrange
        uppercase_usd = Mock(is_directory=False, suffix=".USD")

        # Act
        with patch(
            "omni.flux.asset_importer.core.selection_validation.OmniUrl",
            return_value=uppercase_usd,
        ):
            result = classify_asset_selection(("scene.USD",))

        # Assert
        self.assertEqual(("scene.USD",), result.valid_paths)
        self.assertTrue(result.is_valid)

    def test_classify_texture_selection_with_uppercase_extension_accepts_file(self):
        """Texture extensions are accepted independently of case."""
        # Arrange
        uppercase_texture = Mock(is_directory=False, suffix=".PNG")

        # Act
        with patch(
            "omni.flux.asset_importer.core.selection_validation.OmniUrl",
            return_value=uppercase_texture,
        ):
            result = classify_texture_selection(("albedo.PNG",))

        # Assert
        self.assertEqual(("albedo.PNG",), result.valid_paths)
        self.assertTrue(result.is_valid)
