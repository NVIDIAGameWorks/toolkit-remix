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

__all__ = ["TestStandardizeLinearTextures"]

import pathlib
import tempfile
from unittest.mock import patch

import numpy as np
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.common.path_utils import hash_file, read_metadata
from omni.kit.test import AsyncTestCase

from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.constants import DDS_SOURCE_HASH_METADATA_KEY
from lightspeed.trex.asset_pipeline.core.steps import StandardizeLinearTexturesStep, standardize_linear_textures


class TestStandardizeLinearTextures(AsyncTestCase):
    """Test texture preparation, pixel ranges, and UDIM discovery."""

    def setUp(self):
        """Create an isolated workspace for texture records."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)

    async def test_linear_textures_become_range_fixed_openexr(self):
        """Float sources retain values within the range of their DDS format."""
        nan, inf = float("nan"), float("inf")
        cases = (
            (TextureTypes.ROUGHNESS, (-0.5, 0.25, 3.0, nan), (0.0, 0.25, 1.0, 0.0)),
            (TextureTypes.NORMAL_DX, (-1.0, 0.0, 1.0, 1.0), (0.0, 0.5, 1.0, 1.0)),
            (TextureTypes.NORMAL_OGL, (0.2, 0.5, 1.0, 1.0), (0.2, 0.5, 1.0, 1.0)),
            (TextureTypes.SKYBOX, (inf, 2.0, -1.0, 1.0), (65504.0, 2.0, 0.0, 1.0)),
        )
        for texture_type, source_value, expected in cases:
            with self.subTest(title=texture_type.name):
                # Arrange
                source = self.root / "source.exr"
                source.write_bytes(b"float texture")
                pixels = np.full((2, 2, 4), source_value, dtype="float32")
                item = RemixAssetItem.from_texture(source, texture_type)
                context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")

                def convert(_source, _destination, transform, pixels=pixels):
                    """Apply the step callback to source pixels without file conversion."""
                    transform(pixels)

                with (
                    patch.object(standardize_linear_textures, "is_linear_image", return_value=True),
                    patch.object(standardize_linear_textures, "convert_to_openexr", side_effect=convert),
                ):
                    # Act
                    await StandardizeLinearTexturesStep().run(context)

                # Assert
                texture = item.textures[0]
                self.assertTrue(context.is_in_work_dir(texture.path))
                self.assertEqual(texture.path.name, "source.exr")
                self.assertEqual(texture.path.parent.name, texture_type.name)
                self.assertEqual(texture.udim_tiles, ())
                np.testing.assert_array_equal(pixels, np.full((2, 2, 4), expected, "float32"))

    async def test_sdr_textures_become_linear_openexr_in_the_color_space_of_their_type(self):
        """Color textures decode sRGB. Data textures retain linear values and alpha."""
        cases = (
            (TextureTypes.DIFFUSE, 0.2158605),
            (TextureTypes.ROUGHNESS, 128 / 255),
            (TextureTypes.NORMAL_DX, 128 / 255),
            (TextureTypes.SKYBOX, 0.2158605),
        )
        for texture_type, green in cases:
            with self.subTest(title=texture_type.name):
                # Arrange
                source = self.root / "source.png"
                source.write_bytes(b"source texture")
                pixels = np.full((2, 2, 4), (0.0, 128 / 255, 1.0, 7 / 255), "float32")
                item = RemixAssetItem.from_texture(source, texture_type)
                context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")

                def convert(_source, _destination, transform, pixels=pixels):
                    """Apply the step callback to source pixels without file conversion."""
                    transform(pixels)

                with (
                    patch.object(standardize_linear_textures, "is_linear_image", return_value=False),
                    patch.object(standardize_linear_textures, "convert_to_openexr", side_effect=convert),
                ):
                    # Act
                    await StandardizeLinearTexturesStep().run(context)

                # Assert
                work_path = item.textures[0].path
                self.assertEqual(work_path.name, "source.exr")
                self.assertEqual(work_path.parent.name, texture_type.name)
                self.assertEqual(read_metadata(str(work_path), DDS_SOURCE_HASH_METADATA_KEY), hash_file(str(source)))
                np.testing.assert_allclose(pixels, np.full((2, 2, 4), (0.0, green, 1.0, 7 / 255), "float32"), atol=1e-6)

    async def test_should_run_requires_non_dds_or_unresolved_udim(self):
        """DDS files need preparation only while their UDIM pattern remains unresolved."""
        cases = (
            ("source.exr", b"float texture", (), True),
            ("source.png", b"DDS payload", (), False),
            ("source.dds", b"DDS payload", (), False),
            ("not-dds.dds", b"not a dds", (), True),
            ("source.DDS", b"DDS payload", (), False),
            ("source.<UDIM>.dds", b"DDS payload", (), True),
            ("source.1001.dds", b"DDS payload", ("source.1001.dds", "source.1002.dds"), False),
        )
        for name, content, tiles, expected in cases:
            with self.subTest(title=name):
                # Arrange
                source = self.root / name
                if "<UDIM>" not in name:
                    source.write_bytes(content)
                for tile in tiles:
                    (self.root / tile).write_bytes(content)
                item = RemixAssetItem.from_texture(source, TextureTypes.NORMAL_DX)
                item.textures[0].udim_tiles = tuple(self.root / tile for tile in tiles)
                context = RemixAssetPipelineContext(items=[item], force_dds_reencode=True)

                # Act
                should_run = StandardizeLinearTexturesStep().should_run(context)

                # Assert
                self.assertEqual(should_run, expected)

    async def test_run_resolves_udim_patterns_and_records_concrete_tiles(self):
        """Preparation records every DDS tile unchanged and converts every non-DDS tile to EXR."""
        for suffix in (".DDS", ".png"):
            with self.subTest(title=suffix):
                # Arrange
                source = self.root / f"tiles.<UDIM>{suffix}"
                tiles = tuple(self.root / f"tiles.{tile}{suffix}" for tile in (1001, 1002, 1003))
                for tile in tiles:
                    tile.write_bytes(b"DDS payload" if suffix == ".DDS" else b"source tile")
                item = RemixAssetItem.from_texture(source, TextureTypes.NORMAL_OGL)
                context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")

                with (
                    patch.object(standardize_linear_textures, "is_linear_image", return_value=False),
                    patch.object(standardize_linear_textures, "convert_to_openexr", return_value=None) as converter,
                ):
                    # Act
                    await StandardizeLinearTexturesStep().run(context)

                # Assert
                texture = item.textures[0]
                self.assertEqual(texture.path, texture.udim_tiles[0])
                self.assertEqual(texture.original_path, source)
                if suffix == ".DDS":
                    self.assertCountEqual(texture.udim_tiles, tiles)
                    converter.assert_not_called()
                else:
                    self.assertCountEqual(
                        [tile.name for tile in texture.udim_tiles],
                        ["tiles.1001.exr", "tiles.1002.exr", "tiles.1003.exr"],
                    )
                    self.assertTrue(all(context.is_in_work_dir(tile) for tile in texture.udim_tiles))
                    self.assertTrue(all(tile.parent.name == "NORMAL_OGL" for tile in texture.udim_tiles))

    async def test_run_raises_when_udim_pattern_has_no_tiles(self):
        """An empty UDIM sequence cannot continue to later steps, including a DDS sequence."""
        for suffix in (".png", ".dds"):
            with self.subTest(title=suffix):
                # Arrange
                source = self.root / f"missing.<UDIM>{suffix}"
                item = RemixAssetItem.from_texture(source, TextureTypes.DIFFUSE)
                context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")

                # Act
                with self.assertRaises(RuntimeError) as raised:
                    await StandardizeLinearTexturesStep().run(context)

                # Assert
                self.assertEqual(
                    str(raised.exception), f"UDIM texture resolves to no tiles: {source}. UDIM files don't exist."
                )
                self.assertEqual(item.textures[0].path, source)
                self.assertEqual(item.textures[0].udim_tiles, ())

    async def test_run_propagates_unknown_or_unreadable_source_errors(self):
        """Failed conversion cannot leave an unreadable source for later steps."""
        for name in ("source.unknown", "unreadable.png"):
            with self.subTest(title=name):
                # Arrange
                source = self.root / name
                source.write_bytes(b"not an image")
                item = RemixAssetItem.from_texture(source, TextureTypes.DIFFUSE)
                context = RemixAssetPipelineContext(items=[item], work_dir=self.root / "work")
                failure = RuntimeError("Cannot read source texture")

                with (
                    patch.object(standardize_linear_textures, "is_linear_image", return_value=False),
                    patch.object(standardize_linear_textures, "convert_to_openexr", side_effect=failure),
                ):
                    # Act
                    with self.assertRaises(RuntimeError) as raised:
                        await StandardizeLinearTexturesStep().run(context)

                # Assert
                self.assertIs(raised.exception, failure)
                self.assertEqual(item.textures[0].path, source)
                self.assertEqual(item.textures[0].udim_tiles, ())
