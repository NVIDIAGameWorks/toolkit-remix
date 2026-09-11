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

import lightspeed.trex.asset_pipeline.core.steps.convert_dds as convert_dds_module
import omni.kit.test
from lightspeed.common.constants import TEXTURE_INFO
from lightspeed.common.texture_info import CompressionFormat, MipFilter, TextureInfo
from lightspeed.trex.asset_pipeline.core import (
    AssetKind,
    RemixAssetItem,
    RemixAssetPipelineContext,
    TextureAsset,
)
from lightspeed.trex.asset_pipeline.core.constants import DDS_SOURCE_HASH_METADATA_KEY
from lightspeed.trex.asset_pipeline.core.steps import ConvertDDSStep
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.utils.common.path_utils import is_udim_texture


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
            self.assertEqual(item.textures[0].path.name, "albedo.a.rtex.dds")
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
            self.assertEqual(pathlib.Path(mock_nvtt.call_args.args[1]).name, "roughness.r.rtex.dds")
            self.assertIs(
                mock_nvtt.call_args.args[2],
                TEXTURE_INFO[TEXTURE_TYPE_INPUT_MAP[TextureTypes.ROUGHNESS]],
            )

    async def test_run_reuses_existing_dds_output(self):
        """A DDS carrying only the legacy ``src_hash`` sidecar is reused, not recompressed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.png"
            source_path.write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            dds_path = output_dir / "albedo.a.rtex.dds"
            dds_path.write_bytes(b"dds")
            dds_path.with_suffix(".dds.meta").write_text(
                json.dumps(
                    {
                        DDS_SOURCE_HASH_METADATA_KEY: convert_dds_module._hash_existing_file(str(source_path)),
                    }
                )
            )
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)
            expected_work_path = context.get_work_path(source_path, stem_suffix=".a", suffix=".rtex.dds")

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual(item.textures[0].path, expected_work_path)
            self.assertEqual(item.textures[0].path.name, "albedo.a.rtex.dds")
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"dds")
            mock_nvtt.assert_not_called()

    async def test_run_reencodes_noncanonical_dds_input(self):
        """A DDS without its semantic suffix is re-encoded, matching the legacy plugin."""
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

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            mock_nvtt.assert_called_once()
            self.assertEqual(item.textures[0].path.name, "albedo.a.rtex.dds")
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)

    async def test_run_passes_through_canonical_dds_input(self):
        """A DDS that already carries its semantic suffix is staged without a re-encode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.a.rtex.dds"
            source_path.write_bytes(b"dds")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            mock_nvtt.assert_not_called()
            self.assertEqual(item.textures[0].path.name, "albedo.a.rtex.dds")
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"dds")
            self.assertEqual(
                context.get_output_path(item.textures[0].path, source_path=source_path),
                output_dir / "albedo.a.rtex.dds",
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
            dds_path = output_dir / "albedo.a.rtex.dds"
            dds_path.write_bytes(b"stale")
            dds_path.with_suffix(".dds.meta").write_text(
                json.dumps(
                    {
                        DDS_SOURCE_HASH_METADATA_KEY: "different-source-hash",
                    }
                )
            )
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual(item.textures[0].path.name, "albedo.a.rtex.dds")
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
            self.assertEqual(first_item.textures[0].path.name, "albedo.a.rtex.dds")
            self.assertEqual(second_item.textures[0].path.name, "albedo.a.rtex.dds")
            self.assertEqual(first_item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(second_item.textures[0].path.parent.parent, work_dir)
            self.assertNotEqual(first_item.textures[0].path, second_item.textures[0].path)

    async def test_should_run_returns_false_when_all_texture_records_are_canonical_dds(self):
        """should_run returns False only when every record already carries its semantic suffix."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/albedo.a.rtex.dds"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = ConvertDDSStep().should_run(context)

        # Assert
        self.assertFalse(should_run)

    async def test_should_run_returns_true_for_noncanonical_dds_record(self):
        """A DDS without its semantic suffix still needs a re-encode."""
        # Arrange
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/albedo.dds"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = ConvertDDSStep().should_run(context)

        # Assert
        self.assertTrue(should_run)

    async def test_should_run_returns_false_when_no_texture_records_exist(self):
        """Items without texture records leave DDS conversion with no work."""
        # Arrange
        item = RemixAssetItem.from_model(pathlib.Path("/meshes/mesh.usd"))
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

    # ------------------------------------------------------------------
    # UDIM expansion and conversion — ledger pattern
    # ------------------------------------------------------------------

    async def test_run_expands_udim_and_populates_ledger(self):
        """A three-tile UDIM source expands: three tiles convert, ledger has three entries, path is concrete."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            for name in ("toto.1001.png", "toto.1002.png", "toto.1003.png"):
                (temp_path / name).write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            udim_source = temp_path / "toto.<UDIM>.png"
            item = RemixAssetItem.from_texture(udim_source, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            tile_paths_converted = []

            def record_nvtt(in_path, out_path, _texture_info, **_kw):
                tile_paths_converted.append((in_path, out_path))

            with patch.object(convert_dds_module, "_convert_texture", side_effect=record_nvtt):
                await ConvertDDSStep().run(context)

            texture = item.textures[0]
            # Three tiles were each converted.
            self.assertEqual(len(tile_paths_converted), 3)
            self.assertEqual(len(texture.udim_tiles), 3)
            # path is the first concrete tile, not a token.
            self.assertEqual(texture.path, texture.udim_tiles[0])
            self.assertFalse(is_udim_texture(str(texture.path)))
            # Every tile is in the same work directory (co-located).
            tile_parents = {t.parent for t in texture.udim_tiles}
            self.assertEqual(len(tile_parents), 1)
            self.assertTrue(all(t.parent.parent == work_dir for t in texture.udim_tiles))

    async def test_run_processes_existing_ledger_from_prior_step(self):
        """Tiles arriving via the ledger from a prior step are converted to DDS in place."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            # Simulate tiles left by ConvertNormalStep: three work-dir paths.
            tile_dir = work_dir / "abc123"
            tile_dir.mkdir(parents=True)
            tile_paths = [
                tile_dir / "toto.1001_OTH_Normal.png",
                tile_dir / "toto.1002_OTH_Normal.png",
                tile_dir / "toto.1003_OTH_Normal.png",
            ]
            for tp in tile_paths:
                tp.write_bytes(b"png")

            udim_source = temp_path / "toto.<UDIM>.png"
            texture_asset = TextureAsset(
                path=tile_paths[0],
                texture_type=TextureTypes.NORMAL_OTH,
                original_path=udim_source,
                udim_tiles=tuple(tile_paths),
            )
            item = RemixAssetItem(
                value=udim_source,
                kind=AssetKind.TEXTURE,
                source_path=udim_source,
                textures=[texture_asset],
            )
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            tile_dds_converted = []

            def record_nvtt(in_path, out_path, _texture_info, **_kw):
                tile_dds_converted.append((in_path, out_path))

            with patch.object(convert_dds_module, "_convert_texture", side_effect=record_nvtt):
                await ConvertDDSStep().run(context)

            texture = item.textures[0]
            self.assertEqual(len(tile_dds_converted), 3)
            self.assertEqual(len(texture.udim_tiles), 3)
            # All DDS tiles co-located in the same work directory.
            tile_parents = {t.parent for t in texture.udim_tiles}
            self.assertEqual(len(tile_parents), 1)
            self.assertTrue(all(".rtex.dds" in t.name for t in texture.udim_tiles))

    async def test_run_raises_on_empty_udim_sequence(self):
        """A UDIM pattern that resolves to no concrete tiles raises a clear RuntimeError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            udim_source = temp_path / "missing.<UDIM>.png"
            item = RemixAssetItem.from_texture(udim_source, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            with self.assertRaises(RuntimeError) as error_context:
                await ConvertDDSStep().run(context)
            self.assertIn("UDIM files don't exist", str(error_context.exception))

    async def test_non_udim_texture_keeps_empty_ledger(self):
        """A non-UDIM texture record has an empty udim_tiles after conversion (no regression)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.png"
            source_path.write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            with patch.object(convert_dds_module, "_convert_texture"):
                await ConvertDDSStep().run(context)

            texture = item.textures[0]
            self.assertEqual(texture.udim_tiles, ())
            self.assertTrue(texture.path.name.endswith(".a.rtex.dds"))

    async def test_should_run_returns_true_for_udim_texture(self):
        """A UDIM texture triggers should_run via its path pattern."""
        item = RemixAssetItem.from_texture(pathlib.Path("/textures/toto.<UDIM>.png"), TextureTypes.DIFFUSE)
        context = RemixAssetPipelineContext(items=[item])
        should_run = ConvertDDSStep().should_run(context)
        self.assertTrue(should_run)

    async def test_should_run_returns_true_for_ledger_populated_texture(self):
        """A texture with a non-empty udim_tiles ledger triggers should_run."""
        texture_asset = TextureAsset(
            path=pathlib.Path("/work/tile.1001.png"),
            texture_type=TextureTypes.NORMAL_OTH,
            udim_tiles=(
                pathlib.Path("/work/tile.1001.png"),
                pathlib.Path("/work/tile.1002.png"),
            ),
        )
        item = RemixAssetItem(
            value=pathlib.Path("/source/toto.<UDIM>.png"),
            kind=AssetKind.TEXTURE,
            source_path=pathlib.Path("/source/toto.<UDIM>.png"),
            textures=[texture_asset],
        )
        context = RemixAssetPipelineContext(items=[item])
        should_run = ConvertDDSStep().should_run(context)
        self.assertTrue(should_run)
