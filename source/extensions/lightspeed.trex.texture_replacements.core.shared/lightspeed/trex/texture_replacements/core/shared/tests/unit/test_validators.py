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

import tempfile
from unittest.mock import patch

from lightspeed.trex.texture_replacements.core.shared.data_models import validators
from lightspeed.trex.texture_replacements.core.shared.data_models import TextureReplacementsValidators
from omni.kit.test import AsyncTestCase


class TestTextureReplacementAssetValidation(AsyncTestCase):
    """Test filesystem-only texture replacement validation."""

    async def test_is_valid_texture_asset_accepts_existing_source_when_forced(self):
        """Forced validation accepts an existing texture without requiring ingestion."""
        # Arrange
        with tempfile.NamedTemporaryFile(suffix=".png") as texture_file:
            input_value = (None, texture_file.name)

            # Act
            with patch.object(validators, "is_asset_ingested") as is_asset_ingested:
                result = TextureReplacementsValidators.is_valid_texture_asset(input_value, force=True)

        # Assert
        self.assertEqual(result, input_value)
        is_asset_ingested.assert_not_called()

    async def test_is_valid_texture_asset_rejects_uningested_source_by_default(self):
        """Default validation requires existing textures to have completed ingestion."""
        # Arrange
        with tempfile.NamedTemporaryFile(suffix=".png") as texture_file:
            input_value = (None, texture_file.name)

            # Act
            with (
                patch.object(validators, "is_asset_ingested", return_value=False),
                self.assertRaises(ValueError) as error_context,
            ):
                TextureReplacementsValidators.is_valid_texture_asset(input_value, force=False)

        # Assert
        self.assertEqual(
            str(error_context.exception),
            f"The asset was not ingested. Ingest the asset before replacing the texture: {texture_file.name}",
        )

    async def test_is_valid_texture_asset_accepts_ingested_source_by_default(self):
        """Default validation returns an existing ingested source unchanged."""
        # Arrange
        with tempfile.NamedTemporaryFile(suffix=".png") as texture_file:
            input_value = (None, texture_file.name)

            # Act
            with patch.object(validators, "is_asset_ingested", return_value=True) as is_asset_ingested:
                result = TextureReplacementsValidators.is_valid_texture_asset(input_value, force=False)

        # Assert
        self.assertEqual(result, input_value)
        is_asset_ingested.assert_called_once()

    async def test_is_valid_texture_asset_rejects_unsupported_type_even_when_forced(self):
        """Force never bypasses supported texture-type validation."""
        # Arrange
        asset_path = "Z:/Test/invalid_type.docx"

        # Act
        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_asset((None, asset_path), force=True)

        # Assert
        self.assertEqual(
            str(error_context.exception),
            f"The asset path points to an unsupported texture file type: {asset_path}",
        )

    async def test_is_valid_texture_asset_accepts_missing_authored_path_when_forced(self):
        """Force permits restoration of a supported path whose source is no longer available."""
        # Arrange
        input_value = (None, "Z:/Test/non_existent.png")

        # Act
        result = TextureReplacementsValidators.is_valid_texture_asset(input_value, force=True)

        # Assert
        self.assertEqual(result, input_value)

    async def test_is_valid_texture_asset_rejects_missing_source_by_default(self):
        """Default validation rejects unavailable source textures."""
        # Arrange
        asset_path = "Z:/Test/non_existent.png"

        # Act
        with self.assertRaises(ValueError) as error_context:
            TextureReplacementsValidators.is_valid_texture_asset((None, asset_path), force=False)

        # Assert
        self.assertEqual(
            str(error_context.exception),
            f"The asset path does not point to an existing file: {asset_path}",
        )
