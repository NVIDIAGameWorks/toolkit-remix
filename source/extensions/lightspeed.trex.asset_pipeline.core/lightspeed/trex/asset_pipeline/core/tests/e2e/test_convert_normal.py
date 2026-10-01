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

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.kit.test import AsyncTestCase
from PIL import Image

from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import ConvertNormalStep, StandardizeLinearTexturesStep
from lightspeed.trex.asset_pipeline.core.utils import get_source_hash


async def _convert(
    source: pathlib.Path, texture_type: TextureTypes, work_dir: pathlib.Path
) -> tuple[RemixAssetPipelineContext, pathlib.Path]:
    """Prepare and convert a normal source to a float octahedral work file.

    Returns:
        The pipeline context and the path of the work file.
    """
    item = RemixAssetItem.from_texture(source, texture_type)
    context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)
    await StandardizeLinearTexturesStep().run(context)
    await ConvertNormalStep().run(context)
    return context, pathlib.Path(item.textures[0].path)


class TestConvertNormalE2E(AsyncTestCase):
    """Make sure that normal conversion writes stable float work files, one for each normal convention."""

    async def test_directx_and_opengl_conversions_of_one_source_keep_separate_work_files(self):
        """Keep normal conventions separate when one batch shares a source file or UDIM sequence."""
        for use_udim in (False, True):
            with self.subTest(use_udim=use_udim), tempfile.TemporaryDirectory() as temp_dir:
                root = pathlib.Path(temp_dir)
                source = root / ("normal.<UDIM>.png" if use_udim else "normal.png")
                source_tiles = tuple(root / f"normal.{tile}.png" for tile in (1001, 1002)) if use_udim else (source,)
                for tile in source_tiles:
                    Image.new("RGB", (4, 4), (128, 200, 230)).save(tile)
                items = [
                    RemixAssetItem.from_texture(source, texture_type)
                    for texture_type in (TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OGL)
                ]
                context = RemixAssetPipelineContext(items=items, work_dir=root / "work")
                await StandardizeLinearTexturesStep().run(context)

                await ConvertNormalStep().run(context)

                directx, opengl = (item.textures[0] for item in items)
                directx_tiles = directx.udim_tiles or (directx.path,)
                opengl_tiles = opengl.udim_tiles or (opengl.path,)
                for texture in (directx, opengl):
                    self.assertEqual(texture.texture_type, TextureTypes.NORMAL_OTH)
                    if use_udim:
                        self.assertEqual(len(texture.udim_tiles), 2)
                        self.assertEqual(texture.path, texture.udim_tiles[0])
                        self.assertEqual({tile.parent for tile in texture.udim_tiles}, {texture.path.parent})
                    else:
                        self.assertEqual(texture.udim_tiles, ())
                for directx_tile, opengl_tile in zip(directx_tiles, opengl_tiles):
                    self.assertEqual(directx_tile.suffix, ".exr")
                    self.assertEqual(directx_tile.name, opengl_tile.name)
                    self.assertNotEqual(directx_tile.parent, opengl_tile.parent)
                    self.assertNotEqual(get_source_hash(context, directx_tile), get_source_hash(context, opengl_tile))

    async def test_repeated_conversion_of_one_source_keeps_the_reuse_key(self):
        """The octahedral work file is byte-stable, so a second run reuses the DDS of the first one."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            source = root / "normal.png"
            Image.new("RGB", (4, 4), (128, 200, 230)).save(source)

            first_context, first = await _convert(source, TextureTypes.NORMAL_DX, root / "first")
            second_context, second = await _convert(source, TextureTypes.NORMAL_DX, root / "second")

            self.assertEqual(get_source_hash(first_context, first), get_source_hash(second_context, second))
