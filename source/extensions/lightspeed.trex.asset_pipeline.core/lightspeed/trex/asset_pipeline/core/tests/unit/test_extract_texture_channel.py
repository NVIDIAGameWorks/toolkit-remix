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

__all__ = ["TestExtractTextureChannelStep"]

import pathlib
import tempfile
from unittest.mock import patch

import numpy as np
import omni.kit.test
from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core import utils
from lightspeed.trex.asset_pipeline.core.steps import ExtractTextureChannelStep
from omni.flux.asset_importer.core.data_models import TextureTypes


def _make_context(
    work_dir: pathlib.Path, channel: str | None = None, factor: tuple[float, ...] | None = None
) -> RemixAssetPipelineContext:
    """Build a pipeline context with a prepared EXR texture and optional markers."""
    source = work_dir / "packed.exr"
    source.write_bytes(b"prepared float texture")
    item = RemixAssetItem.from_texture(source, TextureTypes.ROUGHNESS)
    item.textures[0].channel = channel
    item.textures[0].factor = factor
    return RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=work_dir)


class TestExtractTextureChannelStep(omni.kit.test.AsyncTestCase):
    """Test the channel extraction step decisions and record updates."""

    def setUp(self):
        """Create a work directory for step outputs."""
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.work_dir = pathlib.Path(self._temp_dir.name)

    async def test_should_run_returns_false_for_unmarked_texture(self):
        """A texture with no channel and no factor needs no extraction."""
        # Arrange
        context = _make_context(work_dir=self.work_dir)

        # Act
        should_run = ExtractTextureChannelStep().should_run(context)

        # Assert
        self.assertFalse(should_run)

    async def test_should_run_returns_true_for_marked_texture(self):
        """A channel marker or a factor marker alone requests extraction."""
        for title, channel, factor in (("channel", "G", None), ("factor", None, (0.5,))):
            with self.subTest(title=title):
                # Arrange
                context = _make_context(work_dir=self.work_dir, channel=channel, factor=factor)

                # Act
                should_run = ExtractTextureChannelStep().should_run(context)

                # Assert
                self.assertTrue(should_run)

    async def test_run_extracts_channel_and_clears_markers(self):
        """Extraction preserves float precision and clears markers after conversion."""
        # Arrange
        context = _make_context(channel="G", factor=(0.25, 1, 0.5), work_dir=self.work_dir)
        texture = context.items[0].textures[0]
        pixels = np.full((2, 2, 4), (0.125, 0.3333, 0.8, 0.2), "float32")

        def convert(_source, _destination, transform):
            """Apply the step callback to prepared pixels without file conversion."""
            transform(pixels)

        with patch.object(utils, "convert_to_openexr", side_effect=convert):
            # Act
            await ExtractTextureChannelStep().run(context)

        # Assert
        np.testing.assert_allclose(pixels, np.full((2, 2, 4), (0.083325, 0.3333, 0.16665, 1.0), "float32"))
        self.assertEqual(texture.path.name, "packed.g.x0.25_1_0.5.exr")
        self.assertTrue(context.is_in_work_dir(texture.path))
        self.assertEqual(texture.udim_tiles, ())
        self.assertIsNone(texture.channel)
        self.assertIsNone(texture.factor)

    async def test_run_skips_unmarked_texture(self):
        """A texture without markers keeps its path and does not reach the worker."""
        # Arrange
        context = _make_context(work_dir=self.work_dir)
        texture = context.items[0].textures[0]
        source_path = texture.path

        with patch.object(utils, "convert_to_openexr") as extract:
            # Act
            await ExtractTextureChannelStep().run(context)

        # Assert
        extract.assert_not_called()
        self.assertEqual(texture.path, source_path)

    async def test_run_leaves_record_unchanged_when_extraction_fails(self):
        """A failed extraction propagates and does not update the texture record."""
        # Arrange
        context = _make_context(channel="G", factor=(0.5,), work_dir=self.work_dir)
        texture = context.items[0].textures[0]
        source_path = texture.path

        with patch.object(utils, "convert_to_openexr", side_effect=RuntimeError("unreadable")):
            # Act
            with self.assertRaises(RuntimeError):
                await ExtractTextureChannelStep().run(context)

        # Assert
        self.assertEqual(texture.path, source_path)
        self.assertEqual(texture.channel, "G")
        self.assertEqual(texture.factor, (0.5,))

    async def test_should_run_excludes_marked_dds_textures(self):
        """DDS inputs bypass extraction even when factors or channels request changes."""
        for suffix, content, expected in ((".png", b"DDS payload", False), (".dds", b"not a dds", True)):
            with self.subTest(title=suffix):
                # Arrange
                context = _make_context(work_dir=self.work_dir, channel="G", factor=(0.5,))
                source = self.work_dir / f"packed{suffix}"
                source.write_bytes(content)
                context.items[0].textures[0].path = source
                context.force_dds_reencode = True

                # Act
                should_run = ExtractTextureChannelStep().should_run(context)

                # Assert
                self.assertEqual(should_run, expected)

    async def test_run_applies_factors_and_alpha_without_eight_bit_rounding(self):
        """Mono factors discard alpha. Color factors preserve or multiply linear alpha."""
        cases = (
            (None, (0.5,), (0.0625, 0.16665, 0.4, 1.0)),
            (None, (0.5, 0.25, 2.0), (0.0625, 0.083325, 1.6, 0.2)),
            (None, (0.5, 0.25, 2.0, 0.5), (0.0625, 0.083325, 1.6, 0.1)),
            ("A", None, (0.2, 0.2, 0.2, 1.0)),
        )
        for channel, factor, expected in cases:
            with self.subTest(title=f"channel={channel}, factor={factor}"):
                # Arrange
                context = _make_context(channel=channel, factor=factor, work_dir=self.work_dir)
                pixels = np.full((2, 2, 4), (0.125, 0.3333, 0.8, 0.2), "float32")

                def convert(_source, _destination, transform, pixels=pixels):
                    """Apply the step callback to prepared pixels without file conversion."""
                    transform(pixels)

                with patch.object(utils, "convert_to_openexr", side_effect=convert):
                    # Act
                    await ExtractTextureChannelStep().run(context)

                # Assert
                np.testing.assert_allclose(pixels, np.full((2, 2, 4), expected, "float32"))

    async def test_run_converts_only_authoritative_udim_tiles_and_colocates_outputs(self):
        """Extraction retains the ledger order and does not discover extra tiles."""
        # Arrange
        context = _make_context(channel="G", work_dir=self.work_dir)
        texture = context.items[0].textures[0]
        ledger = tuple(self.work_dir / f"packed.{tile}.exr" for tile in (1003, 1001))
        for tile in ledger:
            tile.write_bytes(b"prepared float texture")
        texture.path = ledger[0]
        texture.original_path = self.work_dir / "packed.<UDIM>.png"
        texture.udim_tiles = ledger
        (self.work_dir / "packed.1002.exr").write_bytes(b"not in ledger")

        with patch.object(utils, "convert_to_openexr", return_value=None):
            # Act
            await ExtractTextureChannelStep().run(context)

        # Assert
        self.assertEqual([tile.name for tile in texture.udim_tiles], ["packed.1003.g.exr", "packed.1001.g.exr"])
        self.assertEqual(len({tile.parent for tile in texture.udim_tiles}), 1)
        self.assertEqual(texture.path, texture.udim_tiles[0])
        self.assertIsNone(texture.channel)
