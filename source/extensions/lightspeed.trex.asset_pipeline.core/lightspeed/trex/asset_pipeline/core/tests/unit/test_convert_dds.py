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
from lightspeed.trex.asset_pipeline.core import (
    AssetKind,
    RemixAssetItem,
    RemixAssetPipelineContext,
    TextureAsset,
)
from lightspeed.trex.asset_pipeline.core import utils
from lightspeed.trex.asset_pipeline.core.constants import DDS_SOURCE_HASH_METADATA_KEY
from lightspeed.trex.asset_pipeline.core.steps import ConvertDDSStep
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.common.path_utils import hash_file, read_metadata


class TestConvertDDS(omni.kit.test.AsyncTestCase):
    """Test DDS conversion behavior."""

    async def test_run_converts_texture_records_without_replacing_item(self):
        """Non-DDS texture records convert off-thread without replacing their owning item."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            output_dir = pathlib.Path(temp_dir) / "processed"
            output_dir.mkdir()
            source_path = pathlib.Path(temp_dir) / "albedo.exr"
            source_path.write_bytes(b"prepared float texture")
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
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
            self.assertEqual(item.value, source_path)
            self.assertEqual(item.textures[0].path.name, "albedo.a.rtex.dds")
            self.assertEqual(item.textures[0].path.parent.parent, output_dir)
            self.assertEqual(item.textures[0].udim_tiles, ())
            mock_nvtt.assert_called_once()
            self.assertTrue(worker_threads)
            self.assertNotIn(caller_thread, worker_threads)

    async def test_run_reuses_existing_dds_output(self):
        """A DDS carrying only the legacy ``src_hash`` sidecar is reused when the work file records that hash."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            work_dir = temp_path / "work"
            work_dir.mkdir()
            source_path = work_dir / "albedo.exr"
            source_path.write_bytes(b"prepared float texture")
            original_path = temp_path / "albedo.png"
            original_path.write_bytes(b"source texture")
            source_hash = hash_file(str(original_path))
            source_path.with_suffix(".exr.meta").write_text(json.dumps({DDS_SOURCE_HASH_METADATA_KEY: source_hash}))
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            dds_path = output_dir / "albedo.a.rtex.dds"
            dds_path.write_bytes(b"DDS payload")
            dds_path.with_suffix(".dds.meta").write_text(
                json.dumps(
                    {
                        DDS_SOURCE_HASH_METADATA_KEY: source_hash,
                    }
                )
            )
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            item.textures[0].original_path = original_path
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)
            expected_work_path = context.get_work_path(source_path, stem_suffix=".a", suffix=".rtex.dds")

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual(item.textures[0].path, expected_work_path)
            self.assertEqual(item.textures[0].path.name, "albedo.a.rtex.dds")
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"DDS payload")
            mock_nvtt.assert_not_called()

    async def test_run_reencodes_linear_source_dds_output_with_legacy_hash(self):
        """A DDS from a linear source with the legacy plain-hash sidecar encodes again and gets the new key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.hdr"
            source_path.write_bytes(b"hdr")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            dds_path = output_dir / "albedo.a.rtex.dds"
            dds_path.write_bytes(b"legacy")
            dds_path.with_suffix(".dds.meta").write_text(
                json.dumps({DDS_SOURCE_HASH_METADATA_KEY: hash_file(str(source_path))})
            )
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)
            expected_key = hash_file(str(source_path)) + utils.LINEAR_SOURCE_HASH_SUFFIX

            def convert_texture(_input_path, output_path, _texture_info):
                pathlib.Path(output_path).write_bytes(b"encoded")

            with (
                patch.object(utils, "is_linear_image", return_value=True),
                patch.object(convert_dds_module, "_convert_texture", side_effect=convert_texture) as mock_nvtt,
            ):
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            mock_nvtt.assert_called_once()
            self.assertEqual(item.textures[0].path.read_bytes(), b"encoded")
            self.assertEqual(read_metadata(str(item.textures[0].path), DDS_SOURCE_HASH_METADATA_KEY), expected_key)

    async def test_run_hashes_source_bytes_when_source_outside_work_dir_has_stale_sidecar(self):
        """A source outside the work directory keys DDS reuse on its bytes, not on a stale ``src_hash`` sidecar."""
        cases = (("albedo.png", b"edited texture", False), ("albedo.dds", b"DDS edited payload", True))
        for name, content, force_dds_reencode in cases:
            with self.subTest(title=name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Arrange
                    temp_path = pathlib.Path(temp_dir)
                    source_path = temp_path / name
                    source_path.write_bytes(content)
                    source_path.with_name(f"{name}.meta").write_text(json.dumps({DDS_SOURCE_HASH_METADATA_KEY: "old"}))
                    output_dir = temp_path / "processed"
                    output_dir.mkdir()
                    work_dir = temp_path / "work"
                    work_dir.mkdir()
                    dds_path = output_dir / "albedo.a.rtex.dds"
                    dds_path.write_bytes(b"old encoding")
                    dds_path.with_suffix(".dds.meta").write_text(json.dumps({DDS_SOURCE_HASH_METADATA_KEY: "old"}))
                    item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
                    context = RemixAssetPipelineContext(
                        items=[item],
                        work_dir=work_dir,
                        output_dir=output_dir,
                        force_dds_reencode=force_dds_reencode,
                    )

                    def convert_texture(_input_path, output_path, _texture_info):
                        """Write a new encoding in place of the NVTT invocation."""
                        pathlib.Path(output_path).write_bytes(b"new encoding")

                    with (
                        patch.object(utils, "is_linear_image", return_value=False),
                        patch.object(convert_dds_module, "_convert_texture", side_effect=convert_texture),
                    ):
                        # Act
                        await ConvertDDSStep().run(context)

                    # Assert
                    self.assertEqual(item.textures[0].path.read_bytes(), b"new encoding")
                    self.assertEqual(
                        read_metadata(str(item.textures[0].path), DDS_SOURCE_HASH_METADATA_KEY),
                        hash_file(str(source_path)),
                    )

    async def test_run_passes_through_dds_input_without_semantic_suffix(self):
        """An encoded DDS is copied unchanged, whatever its name, so it is never compressed twice."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "emissive_bc7_abc.dds"
            source_path.write_bytes(b"DDS payload")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            item = RemixAssetItem.from_texture(source_path, TextureTypes.EMISSIVE)
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir)

            with patch.object(convert_dds_module, "_convert_texture") as mock_nvtt:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            mock_nvtt.assert_not_called()
            self.assertEqual(item.textures[0].path.name, "emissive_bc7_abc.dds")
            self.assertEqual(item.textures[0].path.parent.parent, work_dir)
            self.assertEqual(item.textures[0].path.read_bytes(), b"DDS payload")

    async def test_run_reencodes_dds_input_when_forced(self):
        """force_dds_reencode re-encodes a DDS source to the semantic output name."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.dds"
            source_path.write_bytes(b"DDS payload")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(
                items=[item], work_dir=work_dir, output_dir=output_dir, force_dds_reencode=True
            )

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
            source_path.write_bytes(b"DDS payload")
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
            self.assertEqual(item.textures[0].path.read_bytes(), b"DDS payload")
            self.assertEqual(
                context.get_output_path(item.textures[0].path, source_path=source_path),
                output_dir / "albedo.a.rtex.dds",
            )

    async def test_run_ignores_existing_dds_output_when_reuse_metadata_does_not_match(self):
        """Stale DDS outputs are recompressed instead of reused by basename only."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.exr"
            source_path.write_bytes(b"prepared float texture")
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
            first_source = temp_path / "first" / "albedo.exr"
            second_source = temp_path / "second" / "albedo.exr"
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

    async def test_should_run_requires_work_for_dds_only_outside_workspace(self):
        """Workspace DDS records need no copy, including records with a concrete UDIM ledger."""
        cases = ((False, False), (False, True), (True, False), (True, True))
        for in_workspace, udim in cases:
            with self.subTest(title=f"in_workspace={in_workspace}, udim={udim}"):
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Arrange
                    root = pathlib.Path(temp_dir)
                    work_dir = root / "work"
                    source_dir = work_dir if in_workspace else root / "source"
                    source_dir.mkdir(parents=True)
                    source = source_dir / ("albedo.1001.DDS" if udim else "albedo.DDS")
                    source.write_bytes(b"DDS payload")
                    item = RemixAssetItem.from_texture(source, TextureTypes.DIFFUSE)
                    if udim:
                        second_tile = source_dir / "albedo.1002.DDS"
                        second_tile.write_bytes(b"DDS payload")
                        item.textures[0].udim_tiles = (source, second_tile)
                    context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

                    # Act
                    should_run = ConvertDDSStep().should_run(context)

                    # Assert
                    self.assertEqual(should_run, not in_workspace)

    async def test_should_run_returns_true_for_workspace_dds_when_forced(self):
        """Forced encoding overrides the workspace DDS exclusion, including UDIM ledgers."""
        for udim in (False, True):
            with self.subTest(title=f"udim={udim}"):
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Arrange
                    work_dir = pathlib.Path(temp_dir) / "work"
                    work_dir.mkdir()
                    source = work_dir / ("albedo.1001.dds" if udim else "albedo.dds")
                    source.write_bytes(b"DDS payload")
                    item = RemixAssetItem.from_texture(source, TextureTypes.DIFFUSE)
                    if udim:
                        second_tile = work_dir / "albedo.1002.dds"
                        second_tile.write_bytes(b"DDS payload")
                        item.textures[0].udim_tiles = (source, second_tile)
                    context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, force_dds_reencode=True)

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
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            source_path = pathlib.Path(temp_dir) / "albedo.exr"
            source_path.write_bytes(b"prepared float texture")
            item = RemixAssetItem.from_texture(source_path, TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item])

            # Act
            should_run = ConvertDDSStep().should_run(context)

            # Assert
            self.assertTrue(should_run)

    async def test_run_processes_only_the_existing_prepared_ledger(self):
        """Prepared tiles retain their ledger order and produce co-located semantic DDS names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            work_dir = temp_path / "work"
            tile_dir = work_dir / "prepared"
            tile_dir.mkdir(parents=True)
            tiles = tuple(tile_dir / f"normal.{tile}_OTH_Normal.exr" for tile in (1003, 1001))
            for tile in tiles:
                tile.write_bytes(b"prepared float texture")
            (tile_dir / "normal.1002_OTH_Normal.exr").write_bytes(b"not in ledger")
            original = temp_path / "normal.<UDIM>.png"
            item = RemixAssetItem.from_texture(original, TextureTypes.NORMAL_OTH)
            texture = item.textures[0]
            texture.path = tiles[0]
            texture.udim_tiles = tiles
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=temp_path / "output")

            with patch.object(convert_dds_module, "_convert_texture") as converter:
                # Act
                await ConvertDDSStep().run(context)

            # Assert
            self.assertEqual([call.args[0] for call in converter.call_args_list], [str(tile) for tile in tiles])
            self.assertEqual(
                [tile.name for tile in texture.udim_tiles],
                ["normal.1003_OTH_Normal.n.rtex.dds", "normal.1001_OTH_Normal.n.rtex.dds"],
            )
            self.assertEqual(texture.path, texture.udim_tiles[0])
            self.assertEqual(len({tile.parent for tile in texture.udim_tiles}), 1)
            self.assertTrue(all(context.is_in_work_dir(tile) for tile in texture.udim_tiles))

    async def test_should_run_returns_true_for_prepared_udim_ledger(self):
        """A prepared float ledger still needs DDS encoding."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            root = pathlib.Path(temp_dir)
            work_dir = root / "work"
            work_dir.mkdir()
            tiles = tuple(work_dir / f"tile.{tile}.exr" for tile in (1001, 1002))
            for tile in tiles:
                tile.write_bytes(b"prepared float texture")
            texture = TextureAsset(path=tiles[0], texture_type=TextureTypes.NORMAL_OTH, udim_tiles=tiles)
            item = RemixAssetItem(
                value=root / "toto.<UDIM>.png",
                kind=AssetKind.TEXTURE,
                source_path=root / "toto.<UDIM>.png",
                textures=[texture],
            )
            context = RemixAssetPipelineContext(items=[item], work_dir=work_dir)

            # Act
            should_run = ConvertDDSStep().should_run(context)

            # Assert
            self.assertTrue(should_run)
