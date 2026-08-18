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

import pathlib
import threading
from unittest.mock import patch

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes

import lightspeed.trex.asset_pipeline.core.steps.write_metadata as write_metadata_module
from lightspeed.trex.asset_pipeline.core.steps import WriteMetadataStep
from lightspeed.trex.asset_pipeline.core import (
    MaterialType,
    RemixAssetItem,
    RemixAssetPipelineContext,
)


class TestWriteMetadata(omni.kit.test.AsyncTestCase):
    """Test pipeline metadata sidecar generation."""

    async def test_run_writes_metadata_for_texture_records(self):
        """Texture metadata is written off-thread with its hash and validation status."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/albedo.dds"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])
        calling_thread_id = threading.get_ident()
        metadata_thread_ids = []

        with (
            patch.object(write_metadata_module, "hash_file", return_value="abc123def456"),
            patch.object(
                write_metadata_module,
                "write_metadata",
                side_effect=lambda *_args: metadata_thread_ids.append(threading.get_ident()),
            ) as mock_write,
        ):
            # Act
            await WriteMetadataStep().run(context)

        # Assert
        file_path = str(pathlib.Path("/textures/albedo.dds"))
        self.assertEqual(mock_write.call_count, 2)
        mock_write.assert_any_call(file_path, "base_hash", "abc123def456")
        mock_write.assert_any_call(file_path, "validation_passed", True)
        self.assertTrue(metadata_thread_ids)
        self.assertNotIn(calling_thread_id, metadata_thread_ids)

    async def test_run_writes_metadata_for_model_output(self):
        """Model items write metadata for the standardized model output path."""
        # Arrange
        item = RemixAssetItem.from_model(pathlib.Path("/models/chair.usd"), MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(items=[item])

        with (
            patch.object(write_metadata_module, "hash_file", return_value="modelhash"),
            patch.object(write_metadata_module, "write_metadata") as mock_write,
        ):
            # Act
            await WriteMetadataStep().run(context)

        # Assert
        file_path = str(pathlib.Path("/models/chair.usd"))
        mock_write.assert_any_call(file_path, "base_hash", "modelhash")
        mock_write.assert_any_call(file_path, "validation_passed", True)

    async def test_run_raises_when_output_cannot_be_hashed(self):
        """Missing pipeline outputs fail before any metadata is written."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/missing.dds"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])

        with (
            patch.object(write_metadata_module, "hash_file", return_value=None),
            patch.object(write_metadata_module, "write_metadata") as mock_write,
        ):
            # Act
            with self.assertRaises(FileNotFoundError) as error:
                await WriteMetadataStep().run(context)

        # Assert
        self.assertIn("Pipeline output cannot be hashed", str(error.exception))
        mock_write.assert_not_called()

    async def test_should_run_returns_false_without_outputs(self):
        """Empty contexts do not write metadata."""
        # Arrange
        context = RemixAssetPipelineContext()

        # Act
        should_run = WriteMetadataStep().should_run(context)

        # Assert
        self.assertFalse(should_run)
