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

import dataclasses
import pathlib
import tempfile
from unittest import mock

import lightspeed.trex.asset_pipeline.core.jobs.mesh_optimization as mesh_optimization_module
import omni.kit.test
from lightspeed.trex.asset_pipeline.core import TextureAsset
from lightspeed.trex.asset_pipeline.core.constants import PROCESSED_OUTPUT_DIR_NAME
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    ALREADY_OPTIMIZED_REASON,
    PrepareOptimizationResult,
    ProcessedTexture,
    TextureOptimizationResult,
)
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.job import JobInputs, JobProgress
from pxr import Usd


class TestMeshOptimizationJob(omni.kit.test.AsyncTestCase):
    """Test mesh optimization job output publication."""

    async def test_execute_publishes_an_already_optimized_source_in_place(self):
        """An already-optimized source runs no step and the result points at the source itself."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "mesh.usd"
            source_path.write_text("#usda 1.0\n", encoding="utf-8")
            prepared = PrepareOptimizationResult(
                model_work_path=source_path,
                texture_items=(),
                referenced_layers=(),
                texture_ledger=(),
                source_path=source_path,
                source_root=temp_path,
                output_url="omniverse://server/project/assets/ingested/comfyui/job",
                already_optimized=True,
            )
            textures = TextureOptimizationResult(items=(), lineage=(), validation_passed=True)

            async def report_progress(value: JobProgress) -> None:
                """Discard progress updates."""

            # Act
            with (
                mock.patch.object(mesh_optimization_module, "run_remix_asset_pipeline") as run_pipeline,
                mock.patch.object(mesh_optimization_module, "publish_remote_outputs") as publish,
            ):
                outputs = await MeshOptimizationJob().execute(
                    temp_path / "job",
                    JobInputs(
                        {MeshOptimizationJob.SOURCE_MODEL: prepared, MeshOptimizationJob.TEXTURE_INPUT: textures}
                    ),
                    report_progress,
                )

            # Assert
            run_pipeline.assert_not_called()
            publish.assert_not_called()
            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertEqual(outputs.skip_reason, ALREADY_OPTIMIZED_REASON)
            self.assertEqual(result.asset_url, str(source_path))
            self.assertEqual(result.source_path, source_path)
            self.assertEqual([(entry[0], entry[1]) for entry in result.lineage], [(str(source_path), str(source_path))])
            self.assertTrue(result.validation_passed)

    async def test_execute_with_remote_output_publishes_to_remote_url(self):
        """The mesh job publishes to a remote URL when the request provides one."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "mesh.fbx"
            output_url = "omniverse://server/project/assets/ingested/comfyui/job"
            prepared = PrepareOptimizationResult(
                model_work_path=temp_path / "prepare_job" / "processed" / "mesh.usd",
                texture_items=(),
                referenced_layers=(),
                texture_ledger=(),
                source_path=source_path,
                source_root=temp_path,
                output_url=output_url,
            )
            prepared.model_work_path.parent.mkdir(parents=True)
            stage = Usd.Stage.CreateNew(str(prepared.model_work_path))
            stage.DefinePrim("/World", "Xform")
            stage.GetRootLayer().Save()
            stage = None
            captured = {}

            async def report_progress(value: JobProgress) -> None:
                """Discard progress updates.

                Args:
                    value: Progress value emitted by the job.
                """

            async def run_pipeline(config, context, steps=None, *, on_step_started, on_item_completed):
                """Produce one model in the queue-owned staging directory.

                Args:
                    config: Pipeline configuration under test.
                    context: Mutable pipeline context under test.
                    steps: Step list supplied by the job.
                    on_step_started: Callback used to report structured progress.
                    on_item_completed: Callback used to report the completed source model.
                """
                del steps, on_step_started
                final_model = config.output_dir / "mesh.usd"
                final_model.parent.mkdir(parents=True)
                final_model.write_bytes(b"usd")
                context.items[0].value = final_model
                await on_item_completed(context.items[0], 1, 1)

            async def publish_remote(local_dir, local_files, destination_url, count, _progress_callback):
                """Record remote publication and return the published URL.

                Args:
                    local_dir: Directory containing the local outputs.
                    local_files: Outputs produced locally.
                    destination_url: Remote destination URL.
                    count: Number of source assets.
                    _progress_callback: Callback for publication progress.

                Returns:
                    The stable remote model URL.
                """
                captured["local_dir"] = local_dir
                captured["local_files"] = local_files
                captured["output_url"] = destination_url
                captured["count"] = count
                return [f"{destination_url}/mesh.usd"]

            # Act
            with (
                mock.patch.object(mesh_optimization_module, "run_remix_asset_pipeline", side_effect=run_pipeline),
                mock.patch.object(
                    mesh_optimization_module,
                    "publish_remote_outputs",
                    side_effect=publish_remote,
                ),
                mock.patch.object(mesh_optimization_module, "hash_file", return_value="model_hash_abc"),
            ):
                outputs = await MeshOptimizationJob().execute(
                    temp_path / "job",
                    JobInputs(
                        {
                            MeshOptimizationJob.SOURCE_MODEL: prepared,
                            MeshOptimizationJob.TEXTURE_INPUT: TextureOptimizationResult(items=()),
                        }
                    ),
                    report_progress,
                )

            # Assert
            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertEqual(result.asset_url, f"{output_url}/mesh.usd")
            self.assertEqual(result.lineage, ((str(source_path), f"{output_url}/mesh.usd", "model_hash_abc"),))
            local_output_dir = temp_path / "job" / PROCESSED_OUTPUT_DIR_NAME
            self.assertEqual(captured["local_dir"], local_output_dir)
            self.assertEqual(captured["local_files"], [local_output_dir / "mesh.usd"])
            self.assertEqual(captured["output_url"], output_url)
            self.assertEqual(captured["count"], 1)

    async def test_execute_attaches_unbound_textures_once_and_maps_tile_lineage_to_published_copies(self):
        """Unbound textures join the model once with their source data. Tile lineage names the published tiles."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            texture_dir = temp_path / "texture_job"
            prepared = PrepareOptimizationResult(
                model_work_path=temp_path / "prepare_job" / "processed" / "mesh.usd",
                texture_items=(),
                referenced_layers=(),
                texture_ledger=(),
                source_path=temp_path / "mesh.fbx",
                source_root=temp_path,
                output_url=None,
            )
            bound = ProcessedTexture(
                key="bound",
                source_path=temp_path / "bound.<UDIM>.png",
                asset_url=str(texture_dir / "bound.a.rtex.dds"),
                texture_type=TextureTypes.DIFFUSE,
                udim_tiles=(str(texture_dir / "bound.1001.a.rtex.dds"),),
            )
            extra = ProcessedTexture(
                key="extra",
                source_path=temp_path / "extra.<UDIM>.png",
                asset_url=str(texture_dir / "extra.a.rtex.dds"),
                texture_type=TextureTypes.DIFFUSE,
                udim_tiles=(str(texture_dir / "extra.1001.a.rtex.dds"),),
            )
            texture_result = TextureOptimizationResult(
                items=(bound, extra),
                lineage=(
                    (str(temp_path / "bound.1001.png"), bound.udim_tiles[0], "bound_hash"),
                    (str(temp_path / "extra.1001.png"), extra.udim_tiles[0], "extra_hash"),
                ),
            )
            attached: list[TextureAsset] = []

            async def report_progress(value: JobProgress) -> None:
                """Discard progress updates.

                Args:
                    value: Progress value emitted by the job.
                """

            async def run_pipeline(config, context, steps=None, *, on_step_started, on_item_completed):
                """Bind one texture, complete the item, then publish every texture beside the model.

                Args:
                    config: Pipeline configuration under test.
                    context: Mutable pipeline context under test.
                    steps: Step list supplied by the job.
                    on_step_started: Callback used to report structured progress.
                    on_item_completed: Callback that attaches unbound textures.
                """
                del steps, on_step_started
                item = context.items[0]
                item.value = config.output_dir / "mesh.usd"
                item.textures.append(
                    TextureAsset(
                        path=pathlib.Path(bound.asset_url),
                        texture_type=TextureTypes.DIFFUSE,
                        key="bound",
                        udim_tiles=(pathlib.Path(bound.udim_tiles[0]),),
                    )
                )
                await on_item_completed(item, 1, 1)
                attached.extend(dataclasses.replace(texture) for texture in item.textures)
                for texture in item.textures:
                    texture.path = config.output_dir / "textures" / texture.path.name
                    texture.udim_tiles = tuple(
                        config.output_dir / "textures" / tile.name for tile in texture.udim_tiles
                    )

            with (
                mock.patch.object(mesh_optimization_module, "run_remix_asset_pipeline", side_effect=run_pipeline),
                mock.patch.object(mesh_optimization_module, "hash_file", return_value="model_hash_abc"),
                mock.patch.object(
                    mesh_optimization_module.UsdUtils, "ComputeAllDependencies", return_value=([], [], [])
                ),
            ):
                # Act
                outputs = await MeshOptimizationJob().execute(
                    temp_path / "job",
                    JobInputs(
                        {
                            MeshOptimizationJob.SOURCE_MODEL: prepared,
                            MeshOptimizationJob.TEXTURE_INPUT: texture_result,
                        }
                    ),
                    report_progress,
                )

            # Assert
            self.assertEqual([texture.key for texture in attached], ["bound", "extra"])
            self.assertEqual(attached[1].path, pathlib.Path(extra.asset_url))
            self.assertEqual(attached[1].original_path, extra.source_path)
            self.assertEqual(attached[1].udim_tiles, (pathlib.Path(extra.udim_tiles[0]),))
            published_dir = temp_path / "job" / PROCESSED_OUTPUT_DIR_NAME / "textures"
            self.assertEqual(
                outputs[MeshOptimizationJob.OPTIMIZED_MESH].texture_result.lineage,
                (
                    (str(temp_path / "bound.1001.png"), str(published_dir / "bound.1001.a.rtex.dds"), "bound_hash"),
                    (str(temp_path / "extra.1001.png"), str(published_dir / "extra.1001.a.rtex.dds"), "extra_hash"),
                ),
            )
