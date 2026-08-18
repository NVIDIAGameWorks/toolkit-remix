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
from unittest.mock import MagicMock, patch

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from pxr import Sdf

import lightspeed.trex.asset_pipeline.core.pipeline_context as pipeline_context_module
from lightspeed.trex.asset_pipeline.core import (
    AssetKind,
    MaterialType,
    RemixAssetItem,
    RemixAssetPipelineContext,
    TextureAsset,
    TextureBinding,
)


class TestRemixAssetPipelineContext(omni.kit.test.AsyncTestCase):
    """Verify Remix pipeline foundation types have the expected explicit fields."""

    async def test_context_defaults_create_empty_runtime_state(self):
        """All base fields have sensible defaults."""
        # Arrange
        expected_items = []
        expected_execution_state = {}

        # Act
        ctx = RemixAssetPipelineContext()

        # Assert
        self.assertEqual(ctx.items, expected_items)
        self.assertEqual(ctx.execution_state, expected_execution_state)

    async def test_from_texture_creates_one_texture_asset(self):
        """Texture callers get one stable item with one typed texture record."""
        # Arrange
        texture_path = pathlib.Path("/textures/albedo.png")

        # Act
        item = RemixAssetItem.from_texture(texture_path, TextureTypes.DIFFUSE)

        # Assert
        self.assertEqual(item.kind, AssetKind.TEXTURE)
        self.assertEqual(item.value, texture_path)
        self.assertEqual(item.source_path, texture_path)
        self.assertEqual(len(item.textures), 1)
        self.assertEqual(item.textures[0].path, texture_path)
        self.assertEqual(item.textures[0].original_path, texture_path)
        self.assertEqual(item.textures[0].texture_type, TextureTypes.DIFFUSE)

    async def test_from_model_creates_model_without_texture_records(self):
        """Model callers start with only the model path; later steps populate textures and bindings."""
        # Arrange
        model_path = pathlib.Path("/models/chair.fbx")

        # Act
        item = RemixAssetItem.from_model(model_path, MaterialType.TRANSLUCENT)

        # Assert
        self.assertEqual(item.kind, AssetKind.MODEL)
        self.assertEqual(item.value, model_path)
        self.assertEqual(item.source_path, model_path)
        self.assertEqual(item.material_type, MaterialType.TRANSLUCENT)
        self.assertEqual(item.textures, [])
        self.assertEqual(item.texture_bindings, [])

    async def test_texture_binding_uses_typed_usd_fields(self):
        """Texture bindings keep USD paths explicit instead of using loose metadata."""
        # Arrange
        texture = TextureAsset(path=pathlib.Path("/textures/normal.png"), texture_type=TextureTypes.NORMAL_DX)

        # Act
        binding = TextureBinding(
            shader_path=Sdf.Path("/World/Looks/Shader"),
            input_name="inputs:normalmap_texture",
            original_asset_path=Sdf.AssetPath("normal.png"),
            texture=texture,
        )

        # Assert
        self.assertIsInstance(binding.shader_path, Sdf.Path)
        self.assertIsInstance(binding.original_asset_path, Sdf.AssetPath)
        self.assertIs(binding.texture, texture)

    async def test_stage_context_names_do_not_collide_between_pipeline_runs(self):
        """Parallel pipeline runs get separate ingestion context names."""
        # Arrange
        expected_prefix = "remix_asset_pipeline_ingestion_"

        # Act
        context_a = RemixAssetPipelineContext()
        context_b = RemixAssetPipelineContext()

        # Assert
        self.assertTrue(context_a.stage_context_name.startswith(expected_prefix))
        self.assertTrue(context_b.stage_context_name.startswith(expected_prefix))
        self.assertNotEqual(context_a.stage_context_name, context_b.stage_context_name)

    async def test_get_work_path_isolates_same_filename_sources(self):
        """The context owns collision-safe workspace naming for pipeline steps."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            work_dir = pathlib.Path(temp_dir) / "work"
            context = RemixAssetPipelineContext(work_dir=work_dir)
            first_source = pathlib.Path("/assets/chair/albedo.png")
            second_source = pathlib.Path("/assets/table/albedo.png")

            # Act
            first_path = context.get_work_path(first_source)
            second_path = context.get_work_path(second_source)

            # Assert
            self.assertEqual(first_path.name, "albedo.png")
            self.assertEqual(second_path.name, "albedo.png")
            self.assertEqual(first_path.parent.parent, work_dir)
            self.assertEqual(second_path.parent.parent, work_dir)
            self.assertNotEqual(first_path, second_path)

    async def test_get_work_path_preserves_case_sensitive_source_identity(self):
        """Platform path normalization does not collapse distinct case-sensitive source paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            work_dir = pathlib.Path(temp_dir) / "work"
            context = RemixAssetPipelineContext(work_dir=work_dir)
            first_source = pathlib.Path("/assets/Albedo.png")
            second_source = pathlib.Path("/assets/albedo.png")

            with patch.object(pipeline_context_module.os.path, "normcase", side_effect=lambda value: value):
                # Act
                first_path = context.get_work_path(first_source)
                second_path = context.get_work_path(second_source)

            # Assert
            self.assertNotEqual(first_path, second_path)

    async def test_get_work_path_builds_derived_output_names(self):
        """Steps request suffix changes without constructing full output filenames."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            work_dir = pathlib.Path(temp_dir) / "work"
            context = RemixAssetPipelineContext(work_dir=work_dir)
            source_path = pathlib.Path("/assets/chair/normal.png")

            # Act
            work_path = context.get_work_path(source_path, stem_suffix=".octahedral", suffix=".dds")

            # Assert
            self.assertEqual(work_path.name, "normal.octahedral.dds")
            self.assertEqual(work_path.parent.parent, work_dir)

    async def test_copy_to_work_dir_isolates_same_filename_sources(self):
        """Copying through the context never reuses another source file with the same basename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            first_source = temp_path / "first" / "diffuse.dds"
            second_source = temp_path / "second" / "diffuse.dds"
            first_source.parent.mkdir()
            second_source.parent.mkdir()
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")
            context = RemixAssetPipelineContext(work_dir=temp_path / "work")

            # Act
            first_work_path = context.copy_to_work_dir(first_source)
            second_work_path = context.copy_to_work_dir(second_source)

            # Assert
            self.assertNotEqual(first_work_path, second_work_path)
            self.assertEqual(first_work_path.read_bytes(), b"first")
            self.assertEqual(second_work_path.read_bytes(), b"second")

    async def test_copy_to_work_dir_overwrites_stale_workspace_copy(self):
        """Copying through the context refreshes an existing workspace file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "source.dds"
            source_path.write_bytes(b"old")
            context = RemixAssetPipelineContext(work_dir=temp_path / "work")
            context.copy_to_work_dir(source_path)
            source_path.write_bytes(b"new")

            # Act
            work_path = context.copy_to_work_dir(source_path)

            # Assert
            self.assertEqual(work_path.read_bytes(), b"new")

    async def test_copy_to_work_path_uses_requested_workspace_path(self):
        """Reusable files can be copied into an already-reserved workspace path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "processed" / "albedo.dds"
            source_path.parent.mkdir()
            source_path.write_bytes(b"dds")
            context = RemixAssetPipelineContext(work_dir=temp_path / "work")
            work_path = context.get_work_path(pathlib.Path("/source/albedo.png"), suffix=".dds")

            # Act
            copied_path = context.copy_to_work_path(source_path, work_path)

            # Assert
            self.assertEqual(copied_path, work_path)
            self.assertEqual(work_path.read_bytes(), b"dds")

    async def test_copy_to_work_path_rejects_non_workspace_output(self):
        """Explicit copy destinations must still belong to the pipeline workspace."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.dds"
            source_path.write_bytes(b"dds")
            context = RemixAssetPipelineContext(work_dir=temp_path / "work")

            # Act
            with self.assertRaises(RuntimeError) as error:
                context.copy_to_work_path(source_path, temp_path / "outside" / "albedo.dds")

            # Assert
            self.assertIn("must belong to this pipeline run", str(error.exception))

    async def test_get_output_path_deduplicates_same_filename_outputs(self):
        """The context owns collision-safe final output naming for pipeline steps."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext(output_dir=output_dir)
            first_work_path = temp_path / "work" / "first" / "albedo.dds"
            second_work_path = temp_path / "work" / "second" / "albedo.dds"
            first_source_path = pathlib.Path("/assets/chair/albedo.png")
            second_source_path = pathlib.Path("/assets/table/albedo.png")

            # Act
            first_output_path = context.get_output_path(first_work_path, source_path=first_source_path)
            second_output_path = context.get_output_path(second_work_path, source_path=second_source_path)

            # Assert
            self.assertEqual(first_output_path, output_dir / "albedo.dds")
            self.assertEqual(second_output_path.parent, output_dir)
            self.assertEqual(second_output_path.suffix, ".dds")
            self.assertTrue(second_output_path.name.startswith("albedo."))
            self.assertNotEqual(first_output_path, second_output_path)

    async def test_get_output_path_reuses_reserved_path(self):
        """Repeated requests for one workspace output return the same final path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            context = RemixAssetPipelineContext(output_dir=temp_path / "processed")
            work_path = temp_path / "work" / "albedo.dds"
            source_path = pathlib.Path("/assets/chair/albedo.png")

            # Act
            first_output_path = context.get_output_path(work_path, source_path=source_path)
            second_output_path = context.get_output_path(work_path, source_path=pathlib.Path("/other/albedo.png"))

            # Assert
            self.assertEqual(first_output_path, second_output_path)

    async def test_get_output_path_preserves_source_hierarchy_across_contexts(self):
        """Independent pipeline runs map same-named sources to stable distinct destinations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_root = temp_path / "project"
            output_dir = temp_path / "processed"
            table_source = source_root / "textures" / "table" / "albedo.png"
            chair_source = source_root / "textures" / "chair" / "albedo.png"
            table_context = RemixAssetPipelineContext(source_root=source_root, output_dir=output_dir)
            chair_context = RemixAssetPipelineContext(source_root=source_root, output_dir=output_dir)

            # Act
            table_output = table_context.get_output_path(
                temp_path / "table-work" / "albedo.diffuse.dds", source_path=table_source
            )
            chair_output = chair_context.get_output_path(
                temp_path / "chair-work" / "albedo.diffuse.dds", source_path=chair_source
            )

            # Assert
            self.assertEqual(table_output, output_dir / "textures" / "table" / "albedo.diffuse.dds")
            self.assertEqual(chair_output, output_dir / "textures" / "chair" / "albedo.diffuse.dds")

    async def test_get_output_path_reuses_source_semantic_across_contexts(self):
        """The same source and processing semantic resolve to one stable destination."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_root = temp_path / "project"
            source_path = source_root / "textures" / "chair" / "albedo.png"
            output_dir = temp_path / "processed"
            first_context = RemixAssetPipelineContext(source_root=source_root, output_dir=output_dir)
            second_context = RemixAssetPipelineContext(source_root=source_root, output_dir=output_dir)

            # Act
            first_output = first_context.get_output_path(
                temp_path / "first-work" / "albedo.diffuse.dds", source_path=source_path
            )
            second_output = second_context.get_output_path(
                temp_path / "second-work" / "albedo.diffuse.dds", source_path=source_path
            )

            # Assert
            self.assertEqual(first_output, second_output)

    async def test_get_output_path_requires_output_dir(self):
        """Final output naming fails clearly when the runner has not set an output directory."""
        # Arrange
        context = RemixAssetPipelineContext()

        # Act
        with self.assertRaises(RuntimeError) as error:
            context.get_output_path(pathlib.Path("/work/albedo.dds"))

        # Assert
        self.assertIn("context.output_dir must be set by the pipeline runner", str(error.exception))

    async def test_reserve_output_path_returns_workspace_and_final_paths(self):
        """Steps reserve one output and receive both paths owned by the pipeline."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            context = RemixAssetPipelineContext(work_dir=temp_path / "work", output_dir=temp_path / "processed")
            source_path = pathlib.Path("/assets/chair/normal.png")

            # Act
            reservation = context.reserve_output_path(source_path, stem_suffix=".octahedral", suffix=".dds")
            repeated_reservation = context.reserve_output_path(source_path, stem_suffix=".octahedral", suffix=".dds")

            # Assert
            self.assertEqual(reservation.work_path.name, "normal.octahedral.dds")
            self.assertEqual(reservation.work_path.parent.parent, temp_path / "work")
            self.assertEqual(reservation.output_path, temp_path / "processed" / "normal.octahedral.dds")
            self.assertEqual(repeated_reservation, reservation)

    async def test_reserve_output_path_deduplicates_colliding_final_names(self):
        """Output reservations keep same-named source files from sharing a final path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            context = RemixAssetPipelineContext(work_dir=temp_path / "work", output_dir=temp_path / "processed")
            first_source = pathlib.Path("/assets/chair/albedo.png")
            second_source = pathlib.Path("/assets/table/albedo.png")

            # Act
            first_reservation = context.reserve_output_path(first_source, suffix=".dds")
            second_reservation = context.reserve_output_path(second_source, suffix=".dds")

            # Assert
            self.assertNotEqual(first_reservation.work_path, second_reservation.work_path)
            self.assertEqual(first_reservation.output_path, temp_path / "processed" / "albedo.dds")
            self.assertEqual(second_reservation.output_path.parent, temp_path / "processed")
            self.assertTrue(second_reservation.output_path.name.startswith("albedo."))
            self.assertNotEqual(first_reservation.output_path, second_reservation.output_path)

    async def test_get_relative_output_asset_path_uses_final_reserved_names(self):
        """Steps can ask the pipeline for safe published asset references."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            context = RemixAssetPipelineContext(work_dir=temp_path / "work", output_dir=temp_path / "processed")
            model_work_path = context.reserve_output_path(pathlib.Path("/models/chair.fbx"), suffix=".usd").work_path
            texture_work_path = context.reserve_output_path(
                pathlib.Path("/textures/chair/albedo.png"), suffix=".dds"
            ).work_path

            # Act
            relative_path = context.get_relative_output_asset_path(
                model_work_path,
                texture_work_path,
                asset_source_path=pathlib.Path("/textures/chair/albedo.png"),
            )

            # Assert
            self.assertEqual(relative_path, "albedo.dds")

    async def test_open_stage_creates_isolated_ingestion_context(self):
        """Stage access opens USD files through the pipeline's isolated context."""
        # Arrange
        context_mock = MagicMock()
        context_mock.open_stage.return_value = True
        stage_mock = MagicMock()
        context_mock.get_stage.return_value = stage_mock
        context = RemixAssetPipelineContext()
        stage_path = pathlib.Path("/model.usda")

        with patch.object(
            pipeline_context_module.omni.usd,
            "create_context",
            return_value=context_mock,
        ) as create_context_mock:
            # Act
            stage = context.open_stage(stage_path)
            context_name = create_context_mock.call_args.args[0]

        # Assert
        self.assertIs(stage, stage_mock)
        self.assertTrue(context_name.startswith("remix_asset_pipeline_ingestion_"))
        create_context_mock.assert_called_once_with(context_name)
        context_mock.open_stage.assert_called_once_with(str(stage_path))

    async def test_open_stage_reuses_cached_ingestion_context(self):
        """Repeated access to the same stage avoids extra USD context creation and open calls."""
        # Arrange
        context_mock = MagicMock()
        stage_mock = MagicMock()
        context_mock.get_stage.return_value = stage_mock
        context = RemixAssetPipelineContext()
        stage_path = pathlib.Path("/model.usda")
        context._stage_context = context_mock
        context._stage_path = stage_path

        with patch.object(pipeline_context_module.omni.usd, "create_context") as create_context_mock:
            # Act
            stage = context.open_stage(stage_path)

        # Assert
        self.assertIs(stage, stage_mock)
        create_context_mock.assert_not_called()
        context_mock.open_stage.assert_not_called()

    async def test_close_stage_cache_destroys_ingestion_context_and_resets_name(self):
        """Stage-cache cleanup releases the isolated USD context and prepares a fresh name."""
        # Arrange
        context_mock = MagicMock()
        context_mock.can_close_stage.return_value = True
        context_mock.get_stage.return_value = MagicMock()
        context = RemixAssetPipelineContext()
        context._stage_context = context_mock
        context._stage_path = pathlib.Path("/model.usda")
        context_name = context.stage_context_name

        with patch.object(pipeline_context_module.omni.usd, "destroy_context") as destroy_context_mock:
            # Act
            context.close_stage_cache()

        # Assert
        context_mock.close_stage.assert_called_once()
        destroy_context_mock.assert_called_once_with(context_name)
        self.assertNotEqual(context.stage_context_name, context_name)

    async def test_close_stage_cache_without_open_stage_is_noop(self):
        """Closing an unused context does not rotate ingestion state."""
        # Arrange
        context = RemixAssetPipelineContext()
        context_name = context.stage_context_name

        with patch.object(pipeline_context_module.omni.usd, "destroy_context") as destroy_context_mock:
            # Act
            context.close_stage_cache()

        # Assert
        destroy_context_mock.assert_not_called()
        self.assertEqual(context.stage_context_name, context_name)

    async def test_del_closes_open_ingestion_context(self):
        """The context destructor is a fallback for abandoned ingestion contexts."""
        # Arrange
        context_mock = MagicMock()
        context_mock.can_close_stage.return_value = True
        context = RemixAssetPipelineContext()
        context._stage_context = context_mock
        context_name = context.stage_context_name

        with patch.object(pipeline_context_module.omni.usd, "destroy_context") as destroy_context_mock:
            # Act
            context.__del__()

        # Assert
        context_mock.close_stage.assert_called_once()
        destroy_context_mock.assert_called_once_with(context_name)

    async def test_del_ignores_partially_initialized_context(self):
        """The destructor tolerates objects that failed before dataclass fields were assigned."""
        # Arrange
        context = object.__new__(RemixAssetPipelineContext)

        with patch.object(pipeline_context_module.omni.usd, "destroy_context") as destroy_context_mock:
            # Act
            context.__del__()

        # Assert
        destroy_context_mock.assert_not_called()
