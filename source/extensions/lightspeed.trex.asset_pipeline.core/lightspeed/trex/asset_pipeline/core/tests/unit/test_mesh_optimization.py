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
from unittest import mock

import lightspeed.trex.asset_pipeline.core.jobs.mesh_optimization as mesh_optimization_module
import omni.kit.test
from lightspeed.trex.asset_pipeline.core.constants import PROCESSED_OUTPUT_DIR_NAME
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob
from lightspeed.trex.asset_pipeline.core.jobs.models import PrepareOptimizationResult, TextureProcessingResult
from omni.flux.job_queue.core.job import JobInputs, JobProgress
from pxr import Usd


class TestMeshOptimizationJob(omni.kit.test.AsyncTestCase):
    """Test mesh optimization job output publication."""

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
                            MeshOptimizationJob.TEXTURE_INPUT: TextureProcessingResult(items=()),
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
