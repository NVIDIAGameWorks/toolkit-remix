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

__all__ = ["TestPrepareOptimizationJob"]

import pathlib
import tempfile
from unittest import mock

import lightspeed.trex.asset_pipeline.core.jobs.prepare_optimization as prepare_optimization_module
import omni.kit.test
from lightspeed.trex.asset_pipeline.core import TextureAsset
from lightspeed.trex.asset_pipeline.core.jobs import PrepareOptimizationJob
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    ALREADY_OPTIMIZED_REASON,
    MeshOptimizationRequest,
    TextureOptimizationItem,
)
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.job import JobInputs, JobProgress
from omni.flux.utils.common.path_utils import hash_file, write_metadata

_DISCOVERED = TextureAsset(
    path=pathlib.Path("/source/albedo.png"), texture_type=TextureTypes.DIFFUSE, key="discovered", channel="G"
)


async def _report_progress(value: JobProgress) -> None:
    """Discard progress updates.

    Args:
        value: Progress value emitted by the job.
    """


async def _discover_one_texture(config, context, steps=None, *, on_step_started, on_item_completed):
    """Attach one discovered texture to the model item in place of the real pipeline.

    Args:
        config: Pipeline configuration under test.
        context: Mutable pipeline context under test.
        steps: Step list supplied by the job.
        on_step_started: Callback used to report structured progress.
        on_item_completed: Callback used to report the completed source model.
    """
    del config, steps, on_step_started
    context.items[0].textures.append(_DISCOVERED)
    await on_item_completed(context.items[0], 1, 1)


class TestPrepareOptimizationJob(omni.kit.test.AsyncTestCase):
    """Test how the prepare job merges request extra textures with discovered textures."""

    async def _execute(self, extra_textures: tuple[TextureOptimizationItem, ...]):
        """Run the job with a mocked pipeline and the given extra textures.

        Args:
            extra_textures: Extra textures placed on the request.

        Returns:
            The job outputs.
        """
        request = MeshOptimizationRequest(
            pathlib.Path("/source/mesh.fbx"), pathlib.Path("/source"), extra_textures=extra_textures
        )
        with mock.patch.object(
            prepare_optimization_module, "run_remix_asset_pipeline", side_effect=_discover_one_texture
        ):
            return await PrepareOptimizationJob().execute(
                pathlib.Path("/job"), JobInputs({PrepareOptimizationJob.SOURCE_MODEL: request}), _report_progress
            )

    async def test_execute_appends_extra_textures_after_discovered_textures(self):
        """Extra textures follow the discovered textures in both outputs and keep their markers."""
        # Arrange
        extra = TextureOptimizationItem("extra", pathlib.Path("/source/extra.png"), TextureTypes.ROUGHNESS, channel="B")

        # Act
        outputs = await self._execute((extra,))

        # Assert
        expected = (
            TextureOptimizationItem("discovered", _DISCOVERED.path, TextureTypes.DIFFUSE, channel="G"),
            extra,
        )
        self.assertEqual(outputs[PrepareOptimizationJob.TEXTURE_REQUEST].items, expected)
        self.assertEqual(outputs[PrepareOptimizationJob.PREPARED_MESH].texture_items, expected)

    async def test_execute_rejects_extra_texture_key_that_collides_with_discovered_key(self):
        """An extra texture that reuses a discovered key is rejected."""
        # Arrange
        colliding = TextureOptimizationItem("discovered", pathlib.Path("/source/other.png"), TextureTypes.ROUGHNESS)

        # Act
        with self.assertRaisesRegex(ValueError, "collide"):
            await self._execute((colliding,))

    async def test_capture_source_requires_matching_successful_validation(self):
        """Capture paths skip preparation only when their metadata proves successful optimization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            source = root / "captures" / "meshes" / "mesh.usda"
            source.parent.mkdir(parents=True)
            source.write_text("#usda 1.0\n", encoding="utf-8")
            request = MeshOptimizationRequest(source, root)
            for validation, file_hash, expected_skip in (
                (None, None, False),
                (False, hash_file(str(source)), False),
                (True, "stale", False),
                (True, hash_file(str(source)), True),
            ):
                with self.subTest(validation=validation, file_hash=file_hash):
                    if validation is not None:
                        write_metadata(str(source), prepare_optimization_module.BASE_HASH_KEY, file_hash)
                        write_metadata(str(source), prepare_optimization_module.VALIDATION_PASSED_KEY, validation)
                    with mock.patch.object(
                        prepare_optimization_module, "run_remix_asset_pipeline", side_effect=_discover_one_texture
                    ):
                        outputs = await PrepareOptimizationJob().execute(
                            root / "job", JobInputs({PrepareOptimizationJob.SOURCE_MODEL: request}), _report_progress
                        )
                    prepared = outputs[PrepareOptimizationJob.PREPARED_MESH]
                    self.assertEqual(prepared.already_optimized, expected_skip)
                    self.assertEqual(
                        outputs[PrepareOptimizationJob.TEXTURE_REQUEST].items,
                        ()
                        if expected_skip
                        else (
                            TextureOptimizationItem("discovered", _DISCOVERED.path, TextureTypes.DIFFUSE, channel="G"),
                        ),
                    )

    async def test_execute_skips_preparation_for_an_ingested_source(self):
        """A source with a valid .meta sidecar settles skipped with outputs: empty batch, source as prepared model."""
        # Arrange
        request = MeshOptimizationRequest(pathlib.Path("/source/mesh.usd"), pathlib.Path("/source"))

        # Act
        with (
            mock.patch.object(prepare_optimization_module, "hash_match_metadata", return_value=True),
            mock.patch.object(prepare_optimization_module, "read_metadata", return_value=True),
            mock.patch.object(prepare_optimization_module, "run_remix_asset_pipeline") as run_pipeline,
        ):
            outputs = await PrepareOptimizationJob().execute(
                pathlib.Path("/job"), JobInputs({PrepareOptimizationJob.SOURCE_MODEL: request}), _report_progress
            )

        # Assert
        run_pipeline.assert_not_called()
        self.assertEqual(outputs.skip_reason, ALREADY_OPTIMIZED_REASON)
        self.assertEqual(outputs[PrepareOptimizationJob.TEXTURE_REQUEST].items, ())
        prepared = outputs[PrepareOptimizationJob.PREPARED_MESH]
        self.assertTrue(prepared.already_optimized)
        self.assertEqual(prepared.model_work_path, request.source_path)

    async def test_execute_prepares_an_ingested_source_that_has_extra_textures(self):
        """Extra textures need wiring into the model, so an ingested source is still prepared."""
        extra = TextureOptimizationItem(
            key="extra", path=pathlib.Path("/gen/albedo.png"), texture_type=TextureTypes.DIFFUSE
        )
        with (
            mock.patch.object(prepare_optimization_module, "hash_match_metadata", return_value=True),
            mock.patch.object(prepare_optimization_module, "read_metadata", return_value=True),
        ):
            outputs = await self._execute((extra,))
        self.assertFalse(outputs[PrepareOptimizationJob.PREPARED_MESH].already_optimized)
        self.assertIsNone(outputs.skip_reason)
