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
from unittest.mock import patch

import numpy as np
import omni.kit.test
from lightspeed.trex.asset_pipeline.core import (
    RemixAssetItem,
    RemixAssetPipelineContext,
)
from lightspeed.trex.asset_pipeline.core import utils
from lightspeed.trex.asset_pipeline.core.steps import ConvertNormalStep
from omni.flux.asset_importer.core.data_models import TextureTypes


class TestConvertNormal(omni.kit.test.AsyncTestCase):
    """Test normal-map conversion from prepared float textures."""

    def setUp(self):
        """Create an isolated workspace for normal outputs."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)

    async def test_run_converts_prepared_normals_to_octahedral_off_thread(self):
        """DirectX and OpenGL normals produce different octahedral values without source metadata."""
        cases = (
            (TextureTypes.NORMAL_DX, (2 / 3, 1 / 3, 0.0, 1.0)),
            (TextureTypes.NORMAL_OGL, (1 / 3, 2 / 3, 0.0, 1.0)),
        )
        for texture_type, expected in cases:
            with self.subTest(title=texture_type.name):
                # Arrange
                source = self.root / "normal.exr"
                source.write_bytes(b"prepared float normal")
                source.with_suffix(".exr.meta").write_text('{"src_hash": "original-source"}')
                item = RemixAssetItem.from_texture(source, texture_type)
                context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")
                pixels = np.full((2, 2, 4), (0.5, 0.75, 1.0, 0.25), "float32")
                caller_thread = threading.get_ident()
                worker_threads = []

                def convert(_source, _destination, transform, pixels=pixels, worker_threads=worker_threads):
                    """Apply the normal callback and record its execution thread."""
                    worker_threads.append(threading.get_ident())
                    transform(pixels)

                with patch.object(utils, "convert_to_openexr", side_effect=convert):
                    # Act
                    await ConvertNormalStep().run(context)

                # Assert
                texture = item.textures[0]
                self.assertIs(context.items[0], item)
                self.assertEqual(item.value, source)
                self.assertEqual(texture.path.name, "normal_OTH_Normal.exr")
                self.assertTrue(context.is_in_work_dir(texture.path))
                self.assertEqual(texture.udim_tiles, ())
                self.assertIs(texture.texture_type, TextureTypes.NORMAL_OTH)
                self.assertFalse(texture.path.with_suffix(".exr.meta").exists())
                self.assertEqual(len(worker_threads), 1)
                self.assertNotIn(caller_thread, worker_threads)
                np.testing.assert_allclose(pixels, np.full((2, 2, 4), expected, "float32"))

    async def test_should_run_accepts_only_non_dds_directx_or_opengl_normals(self):
        """DDS sources bypass normal conversion even when the final encoder forces a re-encode."""
        cases = (
            (TextureTypes.NORMAL_DX, ".dds", b"not a dds", True),
            (TextureTypes.NORMAL_OGL, ".exr", b"prepared float normal", True),
            (TextureTypes.NORMAL_OTH, ".exr", b"prepared float normal", False),
            (TextureTypes.DIFFUSE, ".exr", b"prepared float texture", False),
            (TextureTypes.NORMAL_DX, ".png", b"DDS payload", False),
            (TextureTypes.NORMAL_OGL, ".DDS", b"DDS payload", False),
        )
        for texture_type, suffix, content, expected in cases:
            with self.subTest(title=f"{texture_type.name} {suffix}"):
                # Arrange
                source = self.root / f"normal{suffix}"
                source.write_bytes(content)
                item = RemixAssetItem.from_texture(source, texture_type)
                context = RemixAssetPipelineContext(items=[item], force_dds_reencode=True)

                # Act
                should_run = ConvertNormalStep().should_run(context)

                # Assert
                self.assertEqual(should_run, expected)

    async def test_run_leaves_octahedral_and_non_normal_records_unchanged(self):
        """Prepared octahedral and diffuse textures require no normal conversion."""
        for texture_type in (TextureTypes.NORMAL_OTH, TextureTypes.DIFFUSE):
            with self.subTest(title=texture_type.name):
                # Arrange
                source = self.root / "texture.exr"
                item = RemixAssetItem.from_texture(source, texture_type)
                context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")

                with patch.object(utils, "convert_to_openexr") as converter:
                    # Act
                    await ConvertNormalStep().run(context)

                # Assert
                converter.assert_not_called()
                self.assertEqual(item.textures[0].path, source)
                self.assertEqual(item.textures[0].texture_type, texture_type)

    async def test_run_converts_every_tile_of_a_standardized_udim_ledger(self):
        """The ledger determines tile order and membership, and all outputs share one directory."""
        # Arrange
        ledger = tuple(self.root / f"normal.{tile}.exr" for tile in (1003, 1001))
        for tile in ledger:
            tile.write_bytes(b"prepared float normal")
        (self.root / "normal.1002.exr").write_bytes(b"not in ledger")
        item = RemixAssetItem.from_texture(self.root / "normal.<UDIM>.png", TextureTypes.NORMAL_OGL)
        texture = item.textures[0]
        texture.path = ledger[0]
        texture.udim_tiles = ledger
        context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")

        with patch.object(utils, "convert_to_openexr", return_value=None) as converter:
            # Act
            await ConvertNormalStep().run(context)

        # Assert
        self.assertEqual([call.args[0] for call in converter.call_args_list], list(ledger))
        self.assertEqual(
            [tile.name for tile in texture.udim_tiles], ["normal.1003_OTH_Normal.exr", "normal.1001_OTH_Normal.exr"]
        )
        self.assertEqual(len({tile.parent for tile in texture.udim_tiles}), 1)
        self.assertEqual(texture.path, texture.udim_tiles[0])
        self.assertIs(texture.texture_type, TextureTypes.NORMAL_OTH)

    async def test_run_isolates_directx_and_opengl_outputs_from_one_source(self):
        """Prepared paths keep two normal conventions from overwriting the same output."""
        for udim in (False, True):
            with self.subTest(title=f"udim={udim}"):
                # Arrange
                original = self.root / ("normal.<UDIM>.png" if udim else "normal.png")
                items = []
                for texture_type in (TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OGL):
                    item = RemixAssetItem.from_texture(original, texture_type)
                    prepared = self.root / texture_type.name
                    tiles = tuple(prepared / f"normal.{tile}.exr" for tile in (1001, 1002))
                    prepared.mkdir(exist_ok=True)
                    item.textures[0].path = tiles[0] if udim else prepared / "normal.exr"
                    item.textures[0].udim_tiles = tiles if udim else ()
                    for source in item.textures[0].udim_tiles or (item.textures[0].path,):
                        source.write_bytes(b"prepared float normal")
                    items.append(item)
                context = RemixAssetPipelineContext(items=items, work_dir=self.root / "work")

                with patch.object(utils, "convert_to_openexr", return_value=None):
                    # Act
                    await ConvertNormalStep().run(context)

                # Assert
                directx, opengl = (item.textures[0] for item in items)
                self.assertNotEqual(directx.path.parent, opengl.path.parent)
                self.assertEqual(directx.path.name, opengl.path.name)
                self.assertEqual(directx.original_path, opengl.original_path)
                self.assertTrue(set(directx.udim_tiles).isdisjoint(opengl.udim_tiles))
