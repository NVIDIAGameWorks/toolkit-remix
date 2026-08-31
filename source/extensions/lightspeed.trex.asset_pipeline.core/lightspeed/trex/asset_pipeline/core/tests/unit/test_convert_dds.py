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

import json
import pathlib
import tempfile
import threading
from unittest.mock import patch

import omni.kit.test
from lightspeed.common.constants import TEXTURE_INFO
from lightspeed.common.texture_info import CompressionFormat, MipFilter, TextureInfo
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes

import lightspeed.trex.asset_pipeline.core.steps.convert_dds as convert_dds_module
from lightspeed.trex.asset_pipeline.core.constants import (
    DDS_CONVERSION_SETTINGS_METADATA_KEY,
    DDS_SOURCE_HASH_METADATA_KEY,
    DDS_TEXTURE_TYPE_METADATA_KEY,
)
from lightspeed.trex.asset_pipeline.core.steps import ConvertDDSStep
from lightspeed.trex.asset_pipeline.core import (
    MaterialType,
    RemixAssetItem,
    RemixAssetPipelineContext,
)


class TestConvertDDS(omni.kit.test.AsyncTestCase):
    """Test DDS conversion behavior."""

    async def test_run_converts_texture_records_without_replacing_item(self):
        """Non-DDS texture records convert off-thread without replacing their owning item."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            output_dir = pathlib.Path(temp_dir) / "processed"
            output_dir.mkdir()
            item = RemixAssetItem.from_texture(pathlib.Path("/textures/albedo.png"), TextureTypes.DIFFUSE)
            original_item = item
            context = RemixAssetPipelineContext(items=[item], work_dir=output_dir, output_dir=output_dir)
            step = ConvertDDSStep()
            caller_thread = threading.get_ident()
            worker_threads = []

            def convert_texture(*_args) -> None:
                """Record the thread used by the mocked NVTT invocation.

                Args:
                    *_args: Arguments passed to the mocked NVTT invocation.
                """
                worker_threads.append(threading.get_ident())

            with patch.object(convert_dds_module, "_convert_texture", side_effect=convert_texture) as mock_nvtt:
                # Act
                await step.run(context)

            # Assert
            self.assertIs(context.items[0], original_item)
            self.assertEqual(item.value, pathlib.Path("/textures/albedo.png"))
            self.assertEqual(item.textures[0].path.name, "albedo.diffuse.dds")
            self.assertEqual(item.textures[0].path.parent.parent, output_dir)
            mock_nvtt.assert_called_once()
            self.assertTrue(worker_threads)
            self.assertNotIn(caller_thread, worker_threads)

    async def test_convert_texture_calls_encode_dds_with_mapped_settings(self):
        """_convert_texture derives BlockFormat, gamma_encoded, and MipmapFilter from the texture info."""
        texture_info = TextureInfo(CompressionFormat.BC7, True, mip_filter=MipFilter.BOX)
        with patch.object(convert_dds_module, "encode_dds") as mock_encode:
            # Act
            convert_dds_module._convert_texture("input.png", "output.dds", texture_info)

        # Assert
        mock_encode.assert_called_once_with(
            pathlib.Path("input.png"),
            pathlib.Path("output.dds"),
            block_format=convert_dds_module.BlockFormat.BC7,
            gamma_encoded=True,
            mip_filter=convert_dds_module.MipmapFilter.BOX,
        )

    async def test_run_uses_canonical_texture_info_for_conversion(self):
        """DDS conversion derives compression settings from the shared texture-info table."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            output_dir = pathlib.Path(temp_dir) / "processed"
            output_dir.mkdir()
            item = RemixAssetItem.from_texture(pathlib.Path("/textures/roughness.png"), TextureTypes.ROUGHNESS)
            context = RemixAssetPipelineContext(items=[item], work_dir=output_dir, output_dir=output_dir)

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            mock_nvtt.assert_called_once()
            self.assertEqual(mock_nvtt.call_args.args[0], str(pathlib.Path("/textures/roughness.png")))
            self.assertEqual(pathlib.Path(mock_nvtt.call_args.args[1]).name, "roughness.roughness.dds")
            self.assertIs(
                mock_nvtt.call_args.args[2],
                TEXTURE_INFO[TEXTURE_TYPE_INPUT_MAP[TextureTypes.ROUGHNESS]],
            )

    async def test_run_reuses_existing_dds_output(self):
        """Existing DDS outputs are reused instead of recompressed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.png"
            source_path.write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            dds_path = output_dir / "albedo.diffuse.dds"
            dds_path.write_bytes(b"dds")
            dds_path.with_suffix(".dds.meta").write_text(
                json.dumps(
                    {
                        DDS_SOURCE_HASH_METADATA_KEY: convert_dds_module._hash_existing_file(str(source_path)),
                        DDS_TEXTURE_TYPE_METADATA_KEY: TextureTypes.DIFFUSE.name,
                        DDS_CONVERSION_SETTINGS_METADATA_KEY: convert_dds_module._texture_info_metadata(
                            convert_dds_module._get_texture_info(TextureTypes.DIFFUSE)
                        ),
                    }
                )
            )
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)
            expected_work_path = context.get_work_path(source_path, stem_suffix=".diffuse", suffix=".dds")

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual(item.textures[0].path, expected_work_path)
            self.assertEqual(item.textures[0].path.name, "albedo.diffuse.dds")
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"dds")
            mock_nvtt.assert_not_called()

    async def test_run_with_dds_input_reserves_final_output_path(self):
        """Already-DDS textures still reserve their publish path before later model-reference steps."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.dds"
            source_path.write_bytes(b"dds")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            # Act
            await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"dds")
            self.assertEqual(
                context.get_output_path(item.textures[0].path, source_path=source_path),
                output_dir / "albedo.diffuse.dds",
            )

    async def test_run_ignores_existing_dds_output_when_reuse_metadata_does_not_match(self):
        """Stale DDS outputs are recompressed instead of reused by basename only."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.png"
            source_path.write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            dds_path = output_dir / "albedo.diffuse.dds"
            dds_path.write_bytes(b"stale")
            dds_path.with_suffix(".dds.meta").write_text(
                json.dumps(
                    {
                        DDS_SOURCE_HASH_METADATA_KEY: "different-source-hash",
                        DDS_TEXTURE_TYPE_METADATA_KEY: TextureTypes.NORMAL_OTH.name,
                        DDS_CONVERSION_SETTINGS_METADATA_KEY: {"block_format": "STALE"},
                    }
                )
            )
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual(item.textures[0].path.name, "albedo.diffuse.dds")
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertNotEqual(item.textures[0].path, dds_path)
            mock_nvtt.assert_called_once()

    async def test_run_converts_same_stem_textures_to_distinct_work_paths(self):
        """The pipeline context provides collision-safe DDS output paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            first_source = temp_path / "first" / "albedo.png"
            second_source = temp_path / "second" / "albedo.png"
            first_source.parent.mkdir()
            second_source.parent.mkdir()
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            first_item = RemixAssetItem.from_texture(first_source, TextureTypes.DIFFUSE)
            second_item = RemixAssetItem.from_texture(second_source, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(
                items=[first_item, second_item], work_dir=work_dir, output_dir=output_dir
            )

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual(mock_nvtt.call_count, 2)
            self.assertEqual(first_item.textures[0].path.name, "albedo.diffuse.dds")
            self.assertEqual(second_item.textures[0].path.name, "albedo.diffuse.dds")
            self.assertEqual(first_item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(second_item.textures[0].path.parent.parent, work_dir)
            self.assertNotEqual(first_item.textures[0].path, second_item.textures[0].path)

    async def test_should_run_returns_false_when_all_texture_records_are_dds(self):
        """should_run returns False when all texture records already point to DDS files."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/albedo.dds"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = ConvertDDSStep().should_run(context)

        # Assert
        self.assertFalse(should_run)

    async def test_should_run_returns_false_when_no_texture_records_exist(self):
        """Items without texture records leave DDS conversion with no work."""
        # Arrange
        item = RemixAssetItem.from_model(pathlib.Path("/meshes/mesh.usd"), MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = ConvertDDSStep().should_run(context)

        # Assert
        self.assertFalse(should_run)

    async def test_should_run_returns_true_when_non_dds_texture_record_exists(self):
        """should_run returns True when any texture record still needs DDS conversion."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/albedo.png"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = ConvertDDSStep().should_run(context)

        # Assert
        self.assertTrue(should_run)
