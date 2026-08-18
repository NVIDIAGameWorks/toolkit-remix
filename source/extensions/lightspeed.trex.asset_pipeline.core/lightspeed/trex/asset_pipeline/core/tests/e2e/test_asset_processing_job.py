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
import shutil
import tempfile
from unittest import mock

import omni.kit.app
import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.enums import ApplyDisposition, JobState
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import (
    Job,
    JobGraph,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)
from omni.flux.job_queue.core.execute import JobScheduler
from omni.flux.job_queue.core.persistence import PersistenceCodec, get_registry

import lightspeed.trex.asset_pipeline.core.publication as publication_module
from lightspeed.trex.asset_pipeline.core.extension import AssetPipelineCoreExtension
from lightspeed.trex.asset_pipeline.core.job import TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.models import (
    TextureProcessingItem,
    TextureProcessingRequest,
)


class _RequestProducer(Job):
    """Return a bound texture request through a real typed graph connection."""

    REQUEST = JobInputPort("request", TextureProcessingRequest)
    RESULT = JobOutputPort("result", TextureProcessingRequest)
    input_ports = (REQUEST,)
    output_ports = (RESULT,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Forward the bound request through the scheduler.

        Args:
            job_directory: Queue-owned directory unused by this in-memory producer.
            inputs: Typed request input.
            progress_callback: Async callback receiving producer progress.

        Returns:
            The exact request supplied through the input port.
        """
        del job_directory
        await progress_callback(JobProgress(completed=1, total=1, detail="Prepare textures"))
        return JobOutputs({self.RESULT: inputs[self.REQUEST]})


def _encode_request_producer(job: _RequestProducer) -> tuple:
    """Encode the real E2E producer without introspection.

    Args:
        job: Producer job to persist.

    Returns:
        Canonical base-job payload.
    """
    return job.job_id, job.name, job.skip_reason, job.apply_binding


def _decode_request_producer(payload: tuple) -> _RequestProducer:
    """Decode the real E2E producer from its canonical payload.

    Args:
        payload: Canonical base-job payload.

    Returns:
        Reconstructed producer job.
    """
    job_id, name, skip_reason, apply_binding = payload
    return _RequestProducer(
        job_id=job_id,
        name=name,
        skip_reason=skip_reason,
        apply_binding=apply_binding,
    )


_REQUEST_PRODUCER_CODEC = PersistenceCodec(
    "test.asset_pipeline.RequestProducer",
    _RequestProducer,
    _encode_request_producer,
    _decode_request_producer,
)


class TestTextureProcessingJobE2E(omni.kit.test.AsyncTestCase):
    """Exercise the reusable texture job through real queue and client boundaries."""

    async def setUp(self) -> None:
        """Register the test-only producer job."""
        get_registry().register_codecs([_REQUEST_PRODUCER_CODEC])

    async def tearDown(self) -> None:
        """Unregister the test-only producer job."""
        get_registry().unregister_codecs([_REQUEST_PRODUCER_CODEC])

    async def test_literal_request_persists_real_outputs_and_per_asset_progress(self):
        """A literal request reports completed textures and monotonic per-texture progress."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_fixture = _get_normal_fixture_path()
            source_paths = (temp_path / "normal_a.png", temp_path / "normal_b.png")
            for source_path in source_paths:
                shutil.copy2(source_fixture, source_path)
            request = _make_texture_request(source_paths, temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Literal texture optimization")
            job = TextureProcessingJob(name="Process two textures")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]
            progress: list[JobProgress] = []

            def record_progress(changed_job_id, current_progress: JobProgress) -> None:
                """Record committed progress for the submitted job.

                Args:
                    changed_job_id: Identifier whose queue state changed.
                    current_progress: Exact progress value committed for the job.
                """
                if changed_job_id == job.job_id:
                    progress.append(current_progress)

            subscription = interface.subscribe_job_progress_changed(record_progress)

            # Let the real scheduler process both bound textures while queue notifications capture durable progress.
            outputs = await _run_until_outputs(queue_job, interface)

            del subscription

            # The typed result contains both textures and progress advances monotonically to the complete batch.
            self.assertEqual(len(outputs[TextureProcessingJob.PROCESSED_TEXTURES].items), 2)
            completed_counts = [value.completed for value in progress]
            self.assertIn(1, completed_counts)
            self.assertEqual(completed_counts[-1], 2)
            self.assertTrue(all(value.total == 2 for value in progress))
            self.assertEqual(completed_counts, sorted(completed_counts))

    async def test_request_without_destination_publishes_to_durable_job_directory(self):
        """Project-independent processing keeps real outputs with the persisted queue job."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "normal.png"
            shutil.copy2(_get_normal_fixture_path(), source_path)
            request = TextureProcessingRequest(
                items=(
                    TextureProcessingItem(
                        key="normal",
                        path=source_path,
                        texture_type=TextureTypes.NORMAL_DX,
                    ),
                ),
                source_root=temp_path,
                output_url=None,
            )
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Project-independent texture optimization")
            job = TextureProcessingJob(name="Optimize one texture")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Run the real scheduler and pipeline without a project-owned publication URL.
            outputs = await _run_until_outputs(queue_job, interface)

            # The durable result stays below the queue-owned job directory and survives output reconstruction.
            output = pathlib.Path(outputs[TextureProcessingJob.PROCESSED_TEXTURES].items[0].asset_url)
            self.assertTrue(output.is_file())
            self.assertEqual(output.parent, interface.get_job_directory(job.job_id) / "processed")
            self.assertEqual(
                interface.get_job_outputs(job.job_id)[TextureProcessingJob.PROCESSED_TEXTURES],
                outputs[TextureProcessingJob.PROCESSED_TEXTURES],
            )

    async def test_completed_outputs_reconstruct_through_fresh_queue_interface(self):
        """A fresh queue interface reconstructs a completed typed texture result."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request((_get_normal_fixture_path(),), temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Durable texture optimization")
            job = TextureProcessingJob(name="Process durable texture")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Complete the texture job, then reopen its SQLite database through a fresh queue interface.
            outputs = await _run_until_outputs(queue_job, interface)

            restored_outputs = _reopen_outputs(queue_job, interface)

            # Typed outputs survive serialization and reconstruct without relying on the original interface.
            self.assertEqual(restored_outputs, outputs)

    async def test_independent_jobs_preserve_source_hierarchy_in_shared_output_directory(self):
        """Independent jobs keep same-named source textures at distinct stable destinations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_root = temp_path / "project"
            table_source = source_root / "textures" / "table" / "albedo.png"
            chair_source = source_root / "textures" / "chair" / "albedo.png"
            for source_path in (table_source, chair_source):
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_get_normal_fixture_path(), source_path)
            output_dir = temp_path / "ProcessedTextures"
            interface = QueueInterface(str(temp_path / "queue.sqlite"))

            # Submit and complete separate graphs so each job owns an independent pipeline context.
            results = []
            for name, source_path in (("Table", table_source), ("Chair", chair_source)):
                graph = JobGraph(name=name)
                job = TextureProcessingJob(name=f"Process {name}")
                graph.add_job(job)
                graph.bind(
                    job,
                    TextureProcessingJob.SOURCE_TEXTURES,
                    _make_texture_request((source_path,), output_dir, source_root=source_root),
                )
                results.append(
                    (await _run_until_outputs(interface.submit(graph)[0], interface))[job.PROCESSED_TEXTURES]
                )

            # Source-relative folders and processing semantics make both durable results collision-free.
            table_output = pathlib.Path(results[0].items[0].asset_url)
            chair_output = pathlib.Path(results[1].items[0].asset_url)
            expected_name = "albedo.normal_dx.octahedral.normal_oth.dds"
            self.assertEqual(table_output.relative_to(output_dir), pathlib.Path("textures/table") / expected_name)
            self.assertEqual(chair_output.relative_to(output_dir), pathlib.Path("textures/chair") / expected_name)
            self.assertTrue(table_output.exists())
            self.assertTrue(chair_output.exists())

    async def test_extension_shutdown_keeps_codecs_until_active_queue_work_drains(self):
        """Texture jobs serialize successful outputs after their product extension begins shutdown."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request((_get_normal_fixture_path(),), temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Drain texture optimization")
            job = TextureProcessingJob(name="Finish active processing")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Product shutdown runs before the core queue drains work during application shutdown.
            AssetPipelineCoreExtension().on_shutdown()
            outputs = await _run_until_outputs(queue_job, interface)

            # The active job completes and persists its typed output before core-owned registry teardown.
            self.assertIs(queue_job.snapshot().state, JobState.DONE)
            self.assertEqual(len(outputs[TextureProcessingJob.PROCESSED_TEXTURES].items), 1)

    async def test_connected_request_reaches_texture_job_through_real_scheduler(self):
        """A producer output supplies the exact connected texture-processing input."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request((_get_normal_fixture_path(),), temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Connected texture optimization")
            producer = _RequestProducer(name="Prepare request")
            processor = TextureProcessingJob(name="Process request")
            graph.add_job(producer)
            graph.add_job(processor)
            graph.bind(producer, _RequestProducer.REQUEST, request)
            graph.connect(
                producer.output(_RequestProducer.RESULT),
                processor.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            producer_queue_job, processor_queue_job = interface.submit(graph)

            # Run the connected graph so the scheduler forwards the producer's output into texture optimization.
            outputs = await _run_until_outputs(processor_queue_job, interface)

            # Both stages settle and the processor publishes the texture represented by the connected request.
            self.assertIs(producer_queue_job.snapshot().state, JobState.DONE)
            result = outputs[TextureProcessingJob.PROCESSED_TEXTURES]
            self.assertEqual(len(result.items), 1)
            self.assertEqual(result.items[0].key, "texture_1")

    async def test_queue_publication_failure_persists_failed_state_without_apply_ready_output(self):
        """A publication failure crosses the real queue boundary without durable outputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request(
                (_get_normal_fixture_path(),),
                "omniverse://server/project/processed",
            )
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Failed texture publication")
            job = TextureProcessingJob(name="Publish processed texture")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Fail at the real publication boundary after the queue has claimed and executed the job.
            with (
                mock.patch.object(
                    publication_module,
                    "_publish_remote_batch",
                    new=mock.AsyncMock(side_effect=RuntimeError("injected publication failure")),
                ),
                self.assertRaisesRegex(RuntimeError, "injected publication failure"),
            ):
                await _run_until_outputs(queue_job, interface)

            # Queue failure is durable, not Apply-ready, and cannot expose a partial typed result.
            snapshot = queue_job.snapshot()
            self.assertIs(snapshot.state, JobState.FAILED)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
            with self.assertRaises(KeyError):
                interface.get_job_outputs(job.job_id)


async def _run_until_outputs(queue_job, interface: QueueInterface) -> JobOutputs:
    """Run one real scheduler until the selected job returns outputs.

    Args:
        queue_job: Submitted job handle to await.
        interface: Queue containing the job graph.

    Returns:
        Durable typed outputs from the selected job.
    """
    scheduler = JobScheduler(interface)
    scheduler.start()
    try:
        return await queue_job.outputs(timeout=120)
    finally:
        await scheduler.stop()


def _reopen_outputs(queue_job, interface: QueueInterface) -> JobOutputs:
    """Read completed outputs through a fresh queue interface.

    Args:
        queue_job: Completed submitted job handle.
        interface: Queue containing the job graph.

    Returns:
        Freshly reconstructed typed outputs.
    """
    reopened_interface = QueueInterface(interface.db_path)
    return reopened_interface.get_job_outputs(queue_job.job_id)


def _make_texture_request(
    source_paths: tuple[pathlib.Path, ...],
    output_dir: pathlib.Path | str,
    *,
    source_root: pathlib.Path | None = None,
) -> TextureProcessingRequest:
    """Create one real texture-processing request for E2E queue runs.

    Args:
        source_paths: Texture sources in stable order.
        output_dir: Final local or remote publication directory.
        source_root: Stable root used to preserve source-relative output paths.

    Returns:
        Immutable request containing every source texture.
    """
    return TextureProcessingRequest(
        items=tuple(
            TextureProcessingItem(
                key=f"texture_{index}",
                path=source_path,
                texture_type=TextureTypes.NORMAL_DX,
            )
            for index, source_path in enumerate(source_paths, start=1)
        ),
        source_root=source_root or source_paths[0].parent,
        output_url=str(output_dir),
    )


def _get_normal_fixture_path() -> pathlib.Path:
    """Return the repository's real DirectX normal-map fixture.

    Returns:
        Absolute fixture path.
    """
    extension_root = pathlib.Path(
        omni.kit.app.get_app()
        .get_extension_manager()
        .get_extension_path_by_module("omni.flux.utils.octahedral_converter")
    )
    return extension_root / "data" / "tests" / "textures" / "Normal_Map_Test_DirectX.png"
