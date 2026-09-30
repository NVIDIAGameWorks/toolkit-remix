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

import lightspeed.trex.asset_pipeline.core.steps.extract_texture_channel as extract_module
import omni.kit.test
from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import ExtractTextureChannelStep
from omni.flux.asset_importer.core.data_models import TextureTypes
from PIL import Image


def _make_context(
    channel: str | None = None, factor: tuple[float, ...] | None = None, work_dir: pathlib.Path | None = None
) -> RemixAssetPipelineContext:
    """Build a pipeline context with one PNG texture that carries the given markers."""
    item = RemixAssetItem.from_texture(pathlib.Path("/textures/packed.png"), TextureTypes.ROUGHNESS)
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
        context = _make_context()

        # Act
        should_run = ExtractTextureChannelStep().should_run(context)

        # Assert
        self.assertFalse(should_run)

    async def test_should_run_returns_true_for_marked_texture(self):
        """A channel marker or a factor marker alone requests extraction."""
        for title, context in (("channel", _make_context(channel="G")), ("factor", _make_context(factor=(0.5,)))):
            with self.subTest(title=title):
                # Act
                should_run = ExtractTextureChannelStep().should_run(context)

                # Assert
                self.assertTrue(should_run)

    async def test_run_extracts_channel_and_clears_markers(self):
        """Extraction writes a suffixed PNG to the work path and clears both markers."""
        # Arrange
        context = _make_context(channel="G", factor=(0.25, 1, 0.5), work_dir=self.work_dir)
        texture = context.items[0].textures[0]
        source_path = texture.path
        expected_path = context.get_work_path(source_path, stem_suffix=".g.x0.25_1_0.5", suffix=".png")

        with patch.object(extract_module, "_extract_channel") as extract:
            # Act
            await ExtractTextureChannelStep().run(context)

        # Assert
        extract.assert_called_once_with(source_path, expected_path, "G", (0.25, 1, 0.5))
        self.assertEqual(texture.path, expected_path)
        self.assertIsNone(texture.channel)
        self.assertIsNone(texture.factor)

    async def test_run_skips_unmarked_texture(self):
        """A texture without markers keeps its path and does not reach the worker."""
        # Arrange
        context = _make_context(work_dir=self.work_dir)
        texture = context.items[0].textures[0]
        source_path = texture.path

        with patch.object(extract_module, "_extract_channel") as extract:
            # Act
            await ExtractTextureChannelStep().run(context)

        # Assert
        extract.assert_not_called()
        self.assertEqual(texture.path, source_path)

    async def test_run_leaves_record_unchanged_when_extraction_fails(self):
        """A failed extraction propagates and does not update the texture record."""
        # Arrange
        context = _make_context(channel="G", work_dir=self.work_dir)
        texture = context.items[0].textures[0]
        source_path = texture.path

        with patch.object(extract_module, "_extract_channel", side_effect=OSError("unreadable")):
            # Act
            with self.assertRaises(OSError):
                await ExtractTextureChannelStep().run(context)

        # Assert
        self.assertEqual(texture.path, source_path)
        self.assertEqual(texture.channel, "G")

    async def test_extract_channel_converts_palette_and_grayscale_sources(self):
        """Palette and grayscale images have no RGB bands but still yield the selected channel."""
        cases = (
            ("palette", Image.new("RGB", (2, 2), (17, 64, 192)).convert("P", palette=Image.Palette.ADAPTIVE), 64),
            ("grayscale", Image.new("L", (2, 2), 99), 99),
        )
        for title, source_image, expected in cases:
            with self.subTest(title=title):
                # Arrange
                source = self.work_dir / f"{title}.png"
                destination = self.work_dir / f"{title}.g.png"
                source_image.save(source)

                # Act
                extract_module._extract_channel(source, destination, "G", None)

                # Assert
                with Image.open(destination) as result:
                    self.assertEqual(result.mode, "RGB")
                    self.assertEqual(result.getpixel((0, 0)), (expected, expected, expected))
