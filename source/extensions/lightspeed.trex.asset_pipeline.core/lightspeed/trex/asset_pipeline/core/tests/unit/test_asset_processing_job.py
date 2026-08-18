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
import threading
from types import SimpleNamespace
from unittest import mock

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.job import JobInputs, JobOutputs, JobProgress
from omni.flux.job_queue.core.serializer import deserialize, serialize

import lightspeed.trex.asset_pipeline.core.job as job_module
import lightspeed.trex.asset_pipeline.core.publication as publication_module
from lightspeed.trex.asset_pipeline.core.job import TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.models import (
    ProcessedTexture,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)


class TestTextureProcessingJob(omni.kit.test.AsyncTestCase):
    """Test the typed job boundary around the Remix asset pipeline."""

    def test_job_exposes_exact_typed_ports(self):
        """The reusable job exposes one exact typed input and output."""
        # Arrange
        job_type = TextureProcessingJob

        # Act
        job = job_type()

        # Assert
        self.assertEqual(job.input_ports, (TextureProcessingJob.SOURCE_TEXTURES,))
        self.assertEqual(job.output_ports, (TextureProcessingJob.PROCESSED_TEXTURES,))
        self.assertEqual(TextureProcessingJob.SOURCE_TEXTURES.name, "source_textures")
        self.assertIs(TextureProcessingJob.SOURCE_TEXTURES.value_type, TextureProcessingRequest)
        self.assertEqual(TextureProcessingJob.PROCESSED_TEXTURES.name, "processed_textures")
        self.assertIs(TextureProcessingJob.PROCESSED_TEXTURES.value_type, TextureProcessingResult)

    def test_persisted_values_with_explicit_codecs_round_trip(self):
        """Every texture-processing value uses its registered custom codec."""
        # Arrange
        item = TextureProcessingItem(
            key="normal",
            path=pathlib.Path("normal.png"),
            texture_type=TextureTypes.NORMAL_DX,
        )
        request = TextureProcessingRequest(
            items=(item,),
            source_root=pathlib.Path("."),
            output_url="omniverse://server/project/processed",
        )
        processed = ProcessedTexture(
            key="normal",
            source_path=pathlib.Path("normal.png"),
            asset_url="omniverse://server/project/processed/normal.dds",
            texture_type=TextureTypes.NORMAL_OTH,
        )
        result = TextureProcessingResult(items=(processed,))
        job = TextureProcessingJob(name="Process normal")

        for value in (item, request, processed, result, job):
            with self.subTest(value_type=type(value).__name__):
                # Act
                restored = deserialize(serialize(value))

                # Assert
                self.assertEqual(restored, value)

    async def test_execute_literal_input_runs_pipeline_and_returns_immutable_result(self):
        """A literal request runs one pipeline batch and returns ordered processed textures."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.png"
            source_path.write_bytes(b"source")
            output_path = temp_path / "processed" / "albedo.dds"
            request = TextureProcessingRequest(
                items=(
                    TextureProcessingItem(
                        key="albedo",
                        path=source_path,
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                ),
                source_root=temp_path,
                output_url=str(output_path.parent),
            )
            progress: list[JobProgress] = []
            pipeline_configs = []

            async def report_progress(value: JobProgress) -> None:
                """Record one structured progress update.

                Args:
                    value: Progress value emitted by the job.
                """
                progress.append(value)

            async def run_pipeline(config, context, *, on_step_started, on_item_completed):
                """Produce one deterministic pipeline output for the job boundary test.

                Args:
                    config: Pipeline configuration under test.
                    context: Mutable pipeline context under test.
                    on_step_started: Callback used to report structured progress.
                    on_item_completed: Callback used to report completed source textures.
                """
                pipeline_configs.append(config)
                await on_step_started(SimpleNamespace(description="Convert texture"), 2, 4)
                output_path.parent.mkdir(parents=True)
                output_path.write_bytes(b"DDS ")
                context.items[0].textures[0].path = output_path
                await on_item_completed(context.items[0], 1, 1)

            # Act
            with mock.patch.object(job_module, "run_remix_asset_pipeline", side_effect=run_pipeline):
                outputs = await TextureProcessingJob().execute(
                    temp_path / "job",
                    JobInputs({TextureProcessingJob.SOURCE_TEXTURES: request}),
                    report_progress,
                )

            # Assert
            self.assertEqual(
                outputs,
                JobOutputs(
                    {
                        TextureProcessingJob.PROCESSED_TEXTURES: TextureProcessingResult(
                            items=(
                                ProcessedTexture(
                                    key="albedo",
                                    source_path=source_path,
                                    asset_url=str(output_path),
                                    texture_type=TextureTypes.DIFFUSE,
                                ),
                            )
                        )
                    }
                ),
            )
            self.assertEqual(pipeline_configs[0].output_dir, output_path.parent)
            self.assertEqual(progress[0], JobProgress(completed=0, total=1, detail="Convert texture"))
            self.assertEqual(progress[-2], JobProgress(completed=1, total=1, detail="Optimize textures"))
            self.assertEqual(progress[-1], JobProgress(completed=1, total=1, detail="Texture optimization complete"))

    async def test_execute_remote_request_keeps_progress_monotonic(self):
        """Remote publication extends pipeline progress without resetting completed work."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "albedo.png"
            output_path = temp_path / "job" / "processed" / "albedo.dds"
            request = TextureProcessingRequest(
                items=(
                    TextureProcessingItem(
                        key="albedo",
                        path=source_path,
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                ),
                source_root=temp_path,
                output_url="omniverse://server/project/processed",
            )
            progress: list[JobProgress] = []
            event_loop_thread = threading.get_ident()
            listing_threads: list[int] = []
            list_output_files = publication_module._list_output_files

            def record_listing_thread(directory: pathlib.Path) -> list[pathlib.Path]:
                """Record the output-enumeration thread before forwarding the call.

                Args:
                    directory: Local output directory to enumerate.

                Returns:
                    Sorted output files returned by the production helper.
                """
                listing_threads.append(threading.get_ident())
                return list_output_files(directory)

            async def report_progress(value: JobProgress) -> None:
                """Record one structured progress update.

                Args:
                    value: Progress value emitted by the job.
                """
                progress.append(value)

            async def run_pipeline(_config, context, *, on_step_started, on_item_completed):
                """Produce one output and sidecar for remote publication.

                Args:
                    _config: Unused pipeline configuration.
                    context: Mutable pipeline context under test.
                    on_step_started: Callback used to report structured progress.
                    on_item_completed: Callback used to report completed source textures.
                """
                await on_step_started(SimpleNamespace(description="Convert texture"), 2, 4)
                output_path.parent.mkdir(parents=True)
                output_path.write_bytes(b"DDS ")
                output_path.with_suffix(".dds.meta").write_text("metadata")
                context.items[0].textures[0].path = output_path
                await on_item_completed(context.items[0], 1, 1)

            # Act
            with (
                mock.patch.object(job_module, "run_remix_asset_pipeline", side_effect=run_pipeline),
                mock.patch.object(publication_module, "is_local_url", return_value=False),
                mock.patch.object(publication_module, "_list_output_files", side_effect=record_listing_thread),
                mock.patch.object(
                    publication_module,
                    "_publish_remote_batch",
                    new=mock.AsyncMock(),
                ),
            ):
                outputs = await TextureProcessingJob().execute(
                    temp_path / "job",
                    JobInputs({TextureProcessingJob.SOURCE_TEXTURES: request}),
                    report_progress,
                )

            # Assert
            self.assertEqual(
                outputs[TextureProcessingJob.PROCESSED_TEXTURES].items[0].asset_url,
                "omniverse://server/project/processed/albedo.dds",
            )
            completed = [value.completed for value in progress if value.completed is not None]
            self.assertEqual(completed, sorted(completed))
            self.assertEqual(len(listing_threads), 1)
            self.assertNotEqual(listing_threads[0], event_loop_thread)
            self.assertTrue(all(value.total == len(request.items) for value in progress))
            self.assertEqual(progress[-1], JobProgress(completed=1, total=1, detail="Texture optimization complete"))
            self.assertTrue(all("albedo" not in (value.detail or "") for value in progress))

    async def test_execute_pipeline_failure_returns_no_apply_ready_output(self):
        """A pipeline failure propagates before the job can return a processed-textures output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            request = TextureProcessingRequest(
                items=(
                    TextureProcessingItem(
                        key="normal",
                        path=temp_path / "normal.png",
                        texture_type=TextureTypes.NORMAL_DX,
                    ),
                ),
                source_root=temp_path,
                output_url=str(temp_path / "processed"),
            )
            progress: list[JobProgress] = []

            async def report_progress(value: JobProgress) -> None:
                """Record one structured progress update.

                Args:
                    value: Progress value emitted by the job.
                """
                progress.append(value)

            # Act
            with mock.patch.object(
                job_module,
                "run_remix_asset_pipeline",
                side_effect=RuntimeError("conversion failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "conversion failed"):
                    await TextureProcessingJob().execute(
                        temp_path / "job",
                        JobInputs({TextureProcessingJob.SOURCE_TEXTURES: request}),
                        report_progress,
                    )

            # Assert
            self.assertNotIn(JobProgress(detail="Texture optimization complete"), progress)
