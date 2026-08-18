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
import tempfile
from unittest.mock import AsyncMock, patch

import omni.kit.test
from omni.flux.asset_importer.core.data_models import (
    SUPPORTED_ASSET_EXTENSIONS,
    SUPPORTED_TEXTURE_EXTENSIONS,
    TextureTypes,
)

import lightspeed.trex.asset_pipeline.core.steps.standardize_input as standardize_input_module
from lightspeed.trex.asset_pipeline.core import (
    AssetKind,
    MaterialType,
    RemixAssetItem,
    RemixAssetPipelineConfig,
    RemixAssetPipelineContext,
)
from lightspeed.trex.asset_pipeline.core.steps import StandardizeInputStep


class TestStandardizeInput(omni.kit.test.AsyncTestCase):
    async def test_validate_with_supported_uppercase_texture_suffix_returns_no_errors(self):
        """Input validation accepts supported texture extensions case-insensitively."""
        # Arrange
        suffix = SUPPORTED_TEXTURE_EXTENSIONS[0].upper()
        texture_path = pathlib.Path("/textures") / f"roughness{suffix}"
        item = RemixAssetItem.from_texture(texture_path, TextureTypes.ROUGHNESS)
        context = RemixAssetPipelineContext(items=[item], work_dir=pathlib.Path("/work"))

        # Act
        errors = StandardizeInputStep(_make_config()).validate(context)

        # Assert
        self.assertEqual(errors, [])

    async def test_validate_with_supported_uppercase_model_suffix_returns_no_errors(self):
        """Input validation accepts supported model extensions case-insensitively."""
        # Arrange
        suffix = SUPPORTED_ASSET_EXTENSIONS[0].upper()
        model_path = pathlib.Path("/models") / f"chair{suffix}"
        item = RemixAssetItem.from_model(model_path, MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(
            items=[item],
            work_dir=pathlib.Path("/work"),
            output_dir=pathlib.Path("/processed"),
        )

        # Act
        errors = StandardizeInputStep(_make_config()).validate(context)

        # Assert
        self.assertEqual(errors, [])

    async def test_validate_with_model_item_requires_output_dir(self):
        """Model standardization needs final-path reservations before mutation."""
        # Arrange
        item = RemixAssetItem.from_model(pathlib.Path("/models/chair.fbx"), MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(items=[item], work_dir=pathlib.Path("/work"))

        # Act
        errors = StandardizeInputStep(_make_config()).validate(context)

        # Assert
        self.assertIn("context.output_dir must be set by the pipeline runner", "\n".join(errors))

    async def test_validate_with_unsupported_texture_suffix_returns_error(self):
        """Input validation rejects texture files unsupported by the shared importer constants."""
        # Arrange
        texture_path = pathlib.Path("/textures/albedo.txt")
        item = RemixAssetItem.from_texture(texture_path, TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item], work_dir=pathlib.Path("/work"))

        # Act
        errors = StandardizeInputStep(_make_config()).validate(context)

        # Assert
        self.assertIn("unsupported texture extension '.txt'", "\n".join(errors))

    async def test_validate_with_unsupported_model_suffix_returns_error(self):
        """Input validation rejects model files unsupported by the shared importer constants."""
        # Arrange
        model_path = pathlib.Path("/models/chair.ma")
        item = RemixAssetItem.from_model(model_path, MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(items=[item], work_dir=pathlib.Path("/work"))

        # Act
        errors = StandardizeInputStep(_make_config()).validate(context)

        # Assert
        self.assertIn("unsupported model extension '.ma'", "\n".join(errors))

    async def test_validate_with_untyped_raw_texture_returns_error(self):
        """A missing texture record requires an explicit semantic before mutation."""
        # Arrange
        texture_path = pathlib.Path("/textures/albedo.png")
        item = RemixAssetItem(value=texture_path, kind=AssetKind.TEXTURE, source_path=texture_path)
        context = RemixAssetPipelineContext(items=[item], work_dir=pathlib.Path("/work"))
        config = RemixAssetPipelineConfig(output_dir=pathlib.Path("/processed"), texture_type=None)

        # Act
        errors = StandardizeInputStep(config).validate(context)

        # Assert
        self.assertIn("requires an explicit texture type", "\n".join(errors))

    async def test_run_with_raw_texture_item_creates_texture_record(self):
        """A raw texture RemixAssetItem can be standardized into one texture record."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            texture_path = pathlib.Path(temp_dir) / "roughness.png"
            texture_path.write_bytes(b"png")
            work_dir = pathlib.Path(temp_dir) / "work"
            work_dir.mkdir()
            item = RemixAssetItem(value=texture_path, kind=AssetKind.TEXTURE, source_path=texture_path)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

            # Act
            await StandardizeInputStep(_make_config(texture_type=TextureTypes.ROUGHNESS)).run(context)

            # Assert
            self.assertEqual(len(item.textures), 1)
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"png")
            self.assertEqual(item.textures[0].texture_type, TextureTypes.ROUGHNESS)
            self.assertEqual(item.textures[0].original_path, texture_path)

    async def test_run_with_texture_record_snapshots_source_into_workspace(self):
        """Existing texture records are copied into the runner workspace before later steps read them."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            texture_path = pathlib.Path(temp_dir) / "albedo.png"
            texture_path.write_bytes(b"png")
            work_dir = pathlib.Path(temp_dir) / "work"
            work_dir.mkdir()
            item = RemixAssetItem.from_texture(texture_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

            # Act
            await StandardizeInputStep(_make_config()).run(context)

            # Assert
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"png")
            self.assertEqual(item.textures[0].original_path, texture_path)

    async def test_run_with_missing_texture_input_raises_clear_error(self):
        """Missing texture inputs fail at the snapshot operation with the source path visible."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            texture_path = temp_path / "missing.png"
            work_dir = temp_path / "work"
            work_dir.mkdir()
            item = RemixAssetItem.from_texture(texture_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

            # Act
            with self.assertRaises(FileNotFoundError) as raised:
                await StandardizeInputStep(_make_config()).run(context)

            # Assert
            self.assertIn(str(texture_path), str(raised.exception))

    async def test_run_with_model_item_imports_model_with_importer_core(self):
        """Model standardization uses ImporterCore to produce the canonical USD path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "chair.fbx"
            source_path.write_text("")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            item = RemixAssetItem.from_model(source_path, MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item], work_dir=output_dir, output_dir=output_dir)

            with patch.object(standardize_input_module, "ImporterCore") as importer_core_mock:
                importer_core_mock.return_value.import_batch_async = AsyncMock(return_value=True)

                # Act
                await StandardizeInputStep(_make_config(output_dir=output_dir)).run(context)

            # Assert
            self.assertEqual(item.value.name, "chair.opaque.usd")
            self.assertEqual(item.value.parent.parent, output_dir)
            importer_core_mock.return_value.import_batch_async.assert_awaited_once()

    async def test_run_with_usd_model_collects_model_into_output_dir(self):
        """USD model sources still go through ImporterCore so dependencies are collected."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "chair.usda"
            source_path.write_text("#usda 1.0\n")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            item = RemixAssetItem.from_model(source_path, MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item], work_dir=output_dir, output_dir=output_dir)

            with patch.object(standardize_input_module, "ImporterCore") as importer_core_mock:
                importer_core_mock.return_value.import_batch_async = AsyncMock(return_value=True)

                # Act
                await StandardizeInputStep(_make_config(output_dir=output_dir)).run(context)

            # Assert
            self.assertEqual(item.value.name, "chair.opaque.usd")
            self.assertEqual(item.value.parent.parent, output_dir)
            importer_core_mock.return_value.import_batch_async.assert_awaited_once()

    async def test_run_with_multiple_model_items_reuses_importer_core(self):
        """One pipeline run does not recreate ImporterCore for every model item."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            first_source_path = temp_path / "chair.fbx"
            second_source_path = temp_path / "table.fbx"
            first_source_path.write_text("")
            second_source_path.write_text("")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            items = [
                RemixAssetItem.from_model(first_source_path, MaterialType.OPAQUE),
                RemixAssetItem.from_model(second_source_path, MaterialType.OPAQUE),
            ]
            context = RemixAssetPipelineContext(items=items, work_dir=output_dir, output_dir=output_dir)

            with patch.object(standardize_input_module, "ImporterCore") as importer_core_mock:
                importer_core_mock.return_value.import_batch_async = AsyncMock(return_value=True)

                # Act
                await StandardizeInputStep(_make_config(output_dir=output_dir)).run(context)

            # Assert
            importer_core_mock.assert_called_once()
            self.assertEqual(importer_core_mock.return_value.import_batch_async.await_count, 2)


def _make_config(
    output_dir: pathlib.Path = pathlib.Path("/processed"),
    texture_type: TextureTypes = TextureTypes.DIFFUSE,
) -> RemixAssetPipelineConfig:
    return RemixAssetPipelineConfig(output_dir=output_dir, texture_type=texture_type)
