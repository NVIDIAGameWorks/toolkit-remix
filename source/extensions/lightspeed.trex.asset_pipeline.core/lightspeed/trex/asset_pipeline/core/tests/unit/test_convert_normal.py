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

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes

import lightspeed.trex.asset_pipeline.core.steps.convert_normal as convert_normal_module
from lightspeed.trex.asset_pipeline.core.steps import ConvertNormalStep
from lightspeed.trex.asset_pipeline.core import (
    RemixAssetItem,
    RemixAssetPipelineContext,
)


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
            self.assertEqual(item.textures[0].path.name, "normal.normal_dx.octahedral.png")
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
            self.assertEqual(item.textures[0].path.name, "normal.normal_ogl.octahedral.png")
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
