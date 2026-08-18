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

import dataclasses
import pathlib

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.kit.test import AsyncTestCase

from lightspeed.trex.asset_pipeline.core.models import (
    ProcessedTexture,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)


class TestTextureProcessingModels(AsyncTestCase):
    """Test immutable texture-processing persistence boundaries."""

    def test_source_record_with_invalid_texture_semantic_raises(self):
        """A source texture record requires an exact texture semantic."""
        # Arrange
        source_path = pathlib.Path("texture.png")

        # Act
        with self.assertRaises(TypeError) as error:
            TextureProcessingItem(key="albedo", path=source_path, texture_type="albedo")

        # Assert
        self.assertIn("texture_type must be a TextureTypes value", str(error.exception))

    def test_processed_record_with_invalid_texture_semantic_raises(self):
        """A processed texture record requires an exact texture semantic."""
        # Arrange
        source_path = pathlib.Path("texture.png")

        # Act
        with self.assertRaises(TypeError) as error:
            ProcessedTexture(
                key="albedo",
                source_path=source_path,
                asset_url="texture.dds",
                texture_type="albedo",
            )

        # Assert
        self.assertIn("texture_type must be a TextureTypes value", str(error.exception))

    def test_source_record_is_immutable(self):
        """A valid source record cannot be mutated after construction."""
        # Arrange
        valid_item = TextureProcessingItem(
            key="albedo",
            path=pathlib.Path("texture.png"),
            texture_type=TextureTypes.DIFFUSE,
        )

        # Act
        with self.assertRaises(dataclasses.FrozenInstanceError) as error:
            valid_item.path = pathlib.Path("other.png")

        # Assert
        self.assertIsInstance(error.exception, dataclasses.FrozenInstanceError)

    def test_request_with_duplicate_keys_raises(self):
        """One request rejects duplicate stable item correlation keys."""
        # Arrange
        item = TextureProcessingItem(
            key="albedo",
            path=pathlib.Path("texture.png"),
            texture_type=TextureTypes.DIFFUSE,
        )

        # Act
        with self.assertRaises(ValueError) as error:
            TextureProcessingRequest(items=(item, item), source_root=pathlib.Path("."), output_url="processed")

        # Assert
        self.assertIn("unique", str(error.exception))

    def test_request_without_output_url_uses_job_owned_destination(self):
        """A request may keep processed textures in its durable queue job directory."""
        # Arrange
        item = TextureProcessingItem(
            key="albedo",
            path=pathlib.Path("texture.png"),
            texture_type=TextureTypes.DIFFUSE,
        )

        # Act
        request = TextureProcessingRequest(items=(item,), source_root=pathlib.Path("."), output_url=None)

        # Assert
        self.assertIsNone(request.output_url)

    def test_result_with_duplicate_keys_raises(self):
        """A persisted result independently rejects duplicate correlation keys."""
        # Arrange
        item = ProcessedTexture(
            key="albedo",
            source_path=pathlib.Path("texture.png"),
            asset_url="texture.dds",
            texture_type=TextureTypes.DIFFUSE,
        )

        # Act
        with self.assertRaises(ValueError) as error:
            TextureProcessingResult(items=(item, item))

        # Assert
        self.assertIn("unique", str(error.exception))
