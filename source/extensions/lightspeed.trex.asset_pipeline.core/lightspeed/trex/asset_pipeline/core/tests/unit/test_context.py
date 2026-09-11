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

import lightspeed.trex.asset_pipeline.core.pipeline.context as pipeline_context_module
from lightspeed.trex.asset_pipeline.core import RemixAssetPipelineContext


class TestRemixAssetPipelineContext(omni.kit.test.AsyncTestCase):
    """Verify the pipeline context owns collision-safe workspace and output paths."""

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

    async def test_copy_to_work_dir_returns_a_path_already_inside_the_workspace(self):
        """A file that already belongs to this run's workspace is not copied again."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            work_dir = temp_path / "work"
            context = RemixAssetPipelineContext(work_dir=work_dir)
            work_path = context.get_work_path(pathlib.Path("/assets/chair/albedo.png"))
            work_path.write_bytes(b"already-in-workspace")

            # Act
            returned_path = context.copy_to_work_dir(work_path)

            # Assert
            self.assertEqual(returned_path, work_path)

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

    async def test_is_in_work_dir_reports_workspace_membership(self):
        """Steps can ask whether a path already belongs to this pipeline run."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            work_dir = temp_path / "work"
            cases = [
                (work_dir / "hash" / "albedo.dds", True),
                (temp_path / "outside" / "albedo.dds", False),
            ]
            for candidate_path, expected in cases:
                with self.subTest(title=f"path={candidate_path}"):
                    # Arrange
                    context = RemixAssetPipelineContext(work_dir=work_dir)

                    # Act
                    result = context.is_in_work_dir(candidate_path)

                    # Assert
                    self.assertEqual(result, expected)

    async def test_validate_work_dir_reports_missing_and_wrong_typed_work_dir(self):
        """Steps that need the workspace get an explicit error before they run."""
        cases = [
            (None, "context.work_dir must be set by the pipeline runner"),
            ("/work", "context.work_dir must be a pathlib.Path"),
            (pathlib.Path("/work"), None),
        ]
        for work_dir, expected_error in cases:
            with self.subTest(title=f"work_dir={work_dir!r}"):
                # Arrange
                context = RemixAssetPipelineContext(work_dir=work_dir)

                # Act
                errors = context.validate_work_dir("my_step")

                # Assert
                self.assertEqual(errors, [] if expected_error is None else [f"my_step: {expected_error}"])

    async def test_validate_output_dir_reports_missing_and_wrong_typed_output_dir(self):
        """Steps that publish get an explicit error before they run."""
        cases = [
            (None, "context.output_dir must be set by the pipeline runner"),
            ("/processed", "context.output_dir must be a pathlib.Path"),
            (pathlib.Path("/processed"), None),
        ]
        for output_dir, expected_error in cases:
            with self.subTest(title=f"output_dir={output_dir!r}"):
                # Arrange
                context = RemixAssetPipelineContext(output_dir=output_dir)

                # Act
                errors = context.validate_output_dir("my_step")

                # Assert
                self.assertEqual(errors, [] if expected_error is None else [f"my_step: {expected_error}"])

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

    async def test_get_output_path_places_sources_outside_the_root_under_external(self):
        """A source outside the project root still gets a stable collision-safe destination."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext(source_root=temp_path / "project", output_dir=output_dir)
            outside_source = temp_path / "elsewhere" / "albedo.png"

            # Act
            output_path = context.get_output_path(temp_path / "work" / "albedo.dds", source_path=outside_source)

            # Assert
            self.assertEqual(output_path.name, "albedo.dds")
            self.assertEqual(output_path.parent.parent, output_dir / "_external")

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

    async def test_clear_output_paths_releases_final_name_reservations(self):
        """A fresh pipeline run reuses the preferred final name instead of a collision suffix."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext(output_dir=output_dir)
            context.get_output_path(temp_path / "work" / "albedo.dds", source_path=pathlib.Path("/a/albedo.png"))
            context.clear_output_paths()

            # Act
            output_path = context.get_output_path(
                temp_path / "other-work" / "albedo.dds", source_path=pathlib.Path("/b/albedo.png")
            )

            # Assert
            self.assertEqual(output_path, output_dir / "albedo.dds")

    async def test_a_lease_returns_to_the_pool_when_the_close_fails(self):
        """A failed close reaches the caller, and the context still returns for the next scope to reuse."""
        context = RemixAssetPipelineContext()
        stage_context = MagicMock()
        context._stage_context = stage_context
        context.stage_context_name = "failed_close"

        # Act
        with (
            patch.object(context, "close_stage", side_effect=RuntimeError("close failed")),
            self.assertRaises(RuntimeError) as caught,
        ):
            await context._close_ingestion_context()

        # Assert
        self.assertEqual(str(caught.exception), "close failed")
        self.assertIs(pipeline_context_module._lease_ingestion_context().context, stage_context)
