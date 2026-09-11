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
import threading
from unittest.mock import MagicMock, patch

import lightspeed.trex.asset_pipeline.core.steps.convert_normal as convert_normal_module
import omni.kit.test
from lightspeed.trex.asset_pipeline.core import (
    RemixAssetItem,
    RemixAssetPipelineContext,
)
from lightspeed.trex.asset_pipeline.core.steps import ConvertNormalStep
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.common.path_utils import is_udim_texture


class TestConvertNormal(omni.kit.test.AsyncTestCase):
    """Test normal-map conversion behavior."""

    async def test_run_converts_normal_dx_texture_record_to_oth(self):
        """NORMAL_DX records convert off-thread to octahedral normals without replacing their item."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            caller_thread = threading.get_ident()
            worker_threads = []
            mock_converter = MagicMock(side_effect=lambda *_args: worker_threads.append(threading.get_ident()))
            output_dir = pathlib.Path(temp_dir) / "processed"
            output_dir.mkdir()
            item = RemixAssetItem.from_texture(pathlib.Path("/textures/normal.png"), TextureTypes.NORMAL_DX)
            original_item = item
            context = RemixAssetPipelineContext(items=[item], work_dir=output_dir)

            with patch.object(
                convert_normal_module.OctahedralConverter,
                "convert_dx_file_to_octahedral",
                mock_converter,
            ):
                # Act
                await ConvertNormalStep().run(context)

            # Assert
            self.assertIs(context.items[0], original_item)
            self.assertEqual(item.value, pathlib.Path("/textures/normal.png"))
            self.assertEqual(item.textures[0].path.name, "normal_OTH_Normal.png")
            self.assertEqual(item.textures[0].path.parent.parent, output_dir)
            self.assertEqual(item.textures[0].texture_type, TextureTypes.NORMAL_OTH)
            mock_converter.assert_called_once()
            self.assertTrue(worker_threads)
            self.assertNotIn(caller_thread, worker_threads)

    async def test_run_converts_normal_ogl_texture_record_to_oth(self):
        """NORMAL_OGL records are converted to octahedral normals."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            mock_converter = MagicMock()
            output_dir = pathlib.Path(temp_dir) / "processed"
            output_dir.mkdir()
            item = RemixAssetItem.from_texture(pathlib.Path("/textures/normal.png"), TextureTypes.NORMAL_OGL)
            context = RemixAssetPipelineContext(items=[item], work_dir=output_dir)

            with patch.object(
                convert_normal_module.OctahedralConverter,
                "convert_ogl_file_to_octahedral",
                mock_converter,
            ):
                # Act
                await ConvertNormalStep().run(context)

            # Assert
            self.assertEqual(item.textures[0].path.name, "normal_OTH_Normal.png")
            self.assertEqual(item.textures[0].path.parent.parent, output_dir)
            self.assertEqual(item.textures[0].texture_type, TextureTypes.NORMAL_OTH)
            mock_converter.assert_called_once()

    async def test_run_skips_non_normal_texture_records(self):
        """Diffuse texture records are left unchanged."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/diffuse.png"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item], work_dir=pathlib.Path("/processed"))

        # Act
        await ConvertNormalStep().run(context)

        # Assert
        self.assertEqual(item.textures[0].path, pathlib.Path("/textures/diffuse.png"))
        self.assertEqual(item.textures[0].texture_type, TextureTypes.DIFFUSE)

    async def test_should_run_returns_false_when_no_normals(self):
        """should_run returns False when no texture records have normal types."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/diffuse.png"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = ConvertNormalStep().should_run(context)

        # Assert
        self.assertFalse(should_run)

    async def test_should_run_returns_true_when_normal_present(self):
        """should_run returns True when a normal texture record is present."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/normal.png"), TextureTypes.NORMAL_DX)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = ConvertNormalStep().should_run(context)

        # Assert
        self.assertTrue(should_run)

    # ------------------------------------------------------------------
    # UDIM expansion and conversion — ledger pattern
    # ------------------------------------------------------------------

    async def test_run_expands_udim_normal_and_populates_ledger(self):
        """A three-tile UDIM normal source expands: three tiles convert, ledger has three entries, path is concrete."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            for name in ("toto.1001.png", "toto.1002.png", "toto.1003.png"):
                (temp_path / name).write_bytes(b"png")
            work_dir = temp_path / "work"
            work_dir.mkdir()

            udim_source = temp_path / "toto.<UDIM>.png"
            item = RemixAssetItem.from_texture(udim_source, TextureTypes.NORMAL_DX)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

            converted_tiles = []

            def record_conversion(in_path, out_path):
                converted_tiles.append((in_path, out_path))

            with patch.object(
                convert_normal_module.OctahedralConverter,
                "convert_dx_file_to_octahedral",
                side_effect=record_conversion,
            ):
                await ConvertNormalStep().run(context)

            texture = item.textures[0]
            self.assertEqual(len(converted_tiles), 3)
            self.assertEqual(len(texture.udim_tiles), 3)
            # path is the first concrete tile, not a token.
            self.assertEqual(texture.path, texture.udim_tiles[0])
            self.assertFalse(is_udim_texture(str(texture.path)))
            self.assertIs(texture.texture_type, TextureTypes.NORMAL_OTH)
            # All tiles co-located.
            tile_parents = {t.parent for t in texture.udim_tiles}
            self.assertEqual(len(tile_parents), 1)

    async def test_run_udim_normal_raises_on_empty_sequence(self):
        """A UDIM pattern that resolves to zero tiles raises RuntimeError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            work_dir = temp_path / "work"
            work_dir.mkdir()

            udim_source = temp_path / "missing.<UDIM>.png"
            item = RemixAssetItem.from_texture(udim_source, TextureTypes.NORMAL_DX)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

            with self.assertRaises(RuntimeError) as error_context:
                await ConvertNormalStep().run(context)
            self.assertIn("UDIM files don't exist", str(error_context.exception))

    async def test_non_udim_normal_keeps_empty_ledger(self):
        """A non-UDIM normal texture has empty udim_tiles after conversion (no regression)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "normal.png"
            source_path.write_bytes(b"png")
            work_dir = temp_path / "work"
            work_dir.mkdir()

            item = RemixAssetItem.from_texture(source_path, TextureTypes.NORMAL_DX)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

            with patch.object(
                convert_normal_module.OctahedralConverter,
                "convert_dx_file_to_octahedral",
            ):
                await ConvertNormalStep().run(context)

            texture = item.textures[0]
            self.assertEqual(texture.udim_tiles, ())
            self.assertIn("_OTH_Normal", texture.path.name)
            self.assertIs(texture.texture_type, TextureTypes.NORMAL_OTH)

    async def test_should_run_returns_true_for_udim_normal_texture(self):
        """A UDIM normal texture triggers should_run via its path pattern."""
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/toto.<UDIM>.png"), TextureTypes.NORMAL_DX)
        context = RemixAssetPipelineContext(items=[item])
        should_run = ConvertNormalStep().should_run(context)
        self.assertTrue(should_run)
