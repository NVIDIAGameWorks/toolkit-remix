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

from __future__ import annotations

import asyncio
import dataclasses
import os
import pathlib
import tempfile
import uuid
from typing import ClassVar
from unittest import mock

import carb.settings
import omni.flux.job_queue.core.persistence as persistence
import omni.kit.test
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.apply_handler_registry import ApplyHandlerRegistry
from omni.flux.job_queue.core.enums import ApplyDisposition, JobState
from omni.flux.job_queue.core.errors import JobExecutionError
from omni.flux.job_queue.core.execute import JobExecutor, JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import (
    ApplyBinding,
    Job,
    JobGraph,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)
from omni.flux.job_queue.core.models import FileReference, QueueJob, UsageSnapshot
from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.settings import SCHEDULER_ENABLED_SETTING_PATH, JobQueueSettings

if os.name == "nt":
    import _winapi

__all__ = ("TestTypedQueueWorkflow",)

NUMBER = JobOutputPort("number", int)
NUMBER_INPUT = JobInputPort("number", int)
TEXT = JobOutputPort("text", str)
PUBLISHED_TEXT = "Published text from the producer."


@dataclasses.dataclass(frozen=True)
class _FileRequest:
    """Persist the file that a consumer must read."""

    path: str


FILE_REQUEST_OUTPUT = JobOutputPort("file", _FileRequest)
FILE_REQUEST_INPUT = JobInputPort("file", _FileRequest)


@dataclasses.dataclass
class _GatedJob(Job):
    """Hold real scheduler work on a per-job event for concurrency assertions."""

    value: int = 0
    output_ports = (NUMBER,)
    started: ClassVar[dict[uuid.UUID, asyncio.Event]] = {}
    releases: ClassVar[dict[uuid.UUID, asyncio.Event]] = {}
    active: ClassVar[dict[type[Job], int]] = {}
    peak: ClassVar[dict[type[Job], int]] = {}

    async def execute(
        self,
        _job_directory: pathlib.Path,
        _inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Wait until this exact job is released and return its configured value."""
        job_type = type(self)
        self.active[job_type] = self.active.get(job_type, 0) + 1
        self.peak[job_type] = max(self.peak.get(job_type, 0), self.active[job_type])
        self.started[self.job_id].set()
        try:
            await self.releases[self.job_id].wait()
            return JobOutputs({NUMBER: self.value})
        finally:
            self.active[job_type] -= 1


@dataclasses.dataclass
class _GatedJobTypeA(_GatedJob):
    """Identify one exact scheduler lane."""


@dataclasses.dataclass
class _GatedJobTypeB(_GatedJob):
    """Identify another exact scheduler lane."""


@dataclasses.dataclass
class _CancellationWaitJob(_GatedJob):
    """Retain execution capacity until cancellation confirmation arrives."""

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Wait on a representative cancellation awaitable before reporting a timeout."""
        await progress_callback(JobProgress(completed=0, total=1, detail="Waiting for cancellation confirmation."))
        await super().execute(job_directory, inputs, progress_callback)
        raise JobExecutionError("The job timed out. Try again.", TimeoutError("Cancellation confirmed after timeout"))


@dataclasses.dataclass
class _ProducerJob(Job):
    """Produce one typed integer for a connected consumer."""

    value: int = 0
    output_ports = (NUMBER,)

    async def execute(
        self,
        _job_directory: pathlib.Path,
        _inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return the configured typed value."""
        return JobOutputs({NUMBER: self.value})


@dataclasses.dataclass
class _ConsumerJob(Job):
    """Consume a producer's persisted integer and return visible text."""

    input_ports = (NUMBER_INPUT,)
    output_ports = (TEXT,)

    async def execute(
        self,
        _job_directory: pathlib.Path,
        inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Format the exact connected input."""
        return JobOutputs({TEXT: f"processed {inputs[NUMBER_INPUT]}"})


@dataclasses.dataclass
class _PublishedFileJob(Job):
    """Publish text and metadata in one exclusively owned folder."""

    output_directory: str = ""
    output_ports = (FILE_REQUEST_OUTPUT,)

    def get_owned_output_urls(self) -> tuple[str, ...]:
        """Return the published folder, including its metadata."""
        return (self.output_directory,)

    async def execute(self, _directory, _inputs, _progress) -> JobOutputs:
        """Publish a file and its metadata."""
        directory = pathlib.Path(self.output_directory)
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "result.txt"
        source.write_text(PUBLISHED_TEXT, encoding="utf-8")
        (directory / "result.txt.meta").write_text(source.name, encoding="utf-8")
        return JobOutputs({FILE_REQUEST_OUTPUT: _FileRequest(str(source))})


class _ApplyFileHandler(ApplyHandler[_FileRequest, str, str]):
    """Apply a persisted file to a real target file."""

    name = "tests.e2e.ApplyFileHandler"
    input_type = _FileRequest
    target_type = str
    receipt_type = str

    async def capture_receipt(self, value: _FileRequest, target: str) -> str:
        """Read the target before Apply changes it."""
        return pathlib.Path(target).read_text(encoding="utf-8")

    async def apply(self, value: _FileRequest, target: str, receipt: str) -> None:
        """Copy the source text to the target."""
        pathlib.Path(target).write_text(pathlib.Path(value.path).read_text(encoding="utf-8"), encoding="utf-8")

    async def revert(self, value: _FileRequest, target: str, receipt: str) -> None:
        """Restore the target text from its receipt."""
        pathlib.Path(target).write_text(receipt, encoding="utf-8")


@dataclasses.dataclass
class _ReadFileJob(Job):
    """Read the source from a persisted typed request."""

    input_ports = (FILE_REQUEST_INPUT,)
    output_ports = (TEXT, FILE_REQUEST_OUTPUT)

    def get_input_urls(self, inputs: JobInputs) -> tuple[str, ...]:
        """Report the source only when its typed request is available."""
        return (inputs[FILE_REQUEST_INPUT].path,) if FILE_REQUEST_INPUT in inputs else ()

    async def execute(self, _directory, inputs, _progress) -> JobOutputs:
        """Read the persisted file request."""
        source = pathlib.Path(inputs[FILE_REQUEST_INPUT].path)
        return JobOutputs({TEXT: source.read_text(encoding="utf-8"), FILE_REQUEST_OUTPUT: inputs[FILE_REQUEST_INPUT]})


@dataclasses.dataclass
class _FailingJob(Job):
    """Fail deterministically inside the real executor."""

    async def execute(
        self,
        _job_directory: pathlib.Path,
        _inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Raise the durable failure used by the descendant workflow."""
        raise RuntimeError("Generation failed")


@dataclasses.dataclass
class _DependentJob(Job):
    """Represent work that must be skipped after an upstream failure."""

    async def execute(
        self,
        _job_directory: pathlib.Path,
        _inputs: JobInputs,
        _progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return empty outputs when the prerequisite succeeds."""
        return JobOutputs()


def _encode_job(job: Job) -> tuple[uuid.UUID, str, str | None, int]:
    """Encode one configured integer job with explicit stable fields."""
    return job.job_id, job.name, job.skip_reason, job.value


def _decode_gated_a(value: tuple[uuid.UUID, str, str | None, int]) -> _GatedJobTypeA:
    """Decode one type-A gated job."""
    job_id, name, skip_reason, number = value
    return _GatedJobTypeA(job_id=job_id, name=name, skip_reason=skip_reason, value=number)


def _decode_gated_b(value: tuple[uuid.UUID, str, str | None, int]) -> _GatedJobTypeB:
    """Decode one type-B gated job."""
    job_id, name, skip_reason, number = value
    return _GatedJobTypeB(job_id=job_id, name=name, skip_reason=skip_reason, value=number)


def _decode_producer(value: tuple[uuid.UUID, str, str | None, int]) -> _ProducerJob:
    """Decode one producer job."""
    job_id, name, skip_reason, number = value
    return _ProducerJob(job_id=job_id, name=name, skip_reason=skip_reason, value=number)


def _decode_cancellation_wait(value: tuple[uuid.UUID, str, str | None, int]) -> _CancellationWaitJob:
    """Decode one job that waits for cancellation confirmation."""
    job_id, name, skip_reason, number = value
    return _CancellationWaitJob(job_id=job_id, name=name, skip_reason=skip_reason, value=number)


def _encode_plain_job(job: Job) -> tuple[uuid.UUID, str, str | None]:
    """Encode one job with only the shared persisted fields."""
    return job.job_id, job.name, job.skip_reason


def _decode_consumer(value: tuple[uuid.UUID, str, str | None]) -> _ConsumerJob:
    """Decode one connected consumer job."""
    return _ConsumerJob(job_id=value[0], name=value[1], skip_reason=value[2])


def _decode_failing(value: tuple[uuid.UUID, str, str | None]) -> _FailingJob:
    """Decode one failing job."""
    return _FailingJob(job_id=value[0], name=value[1], skip_reason=value[2])


def _decode_dependent(value: tuple[uuid.UUID, str, str | None]) -> _DependentJob:
    """Decode one dependent job."""
    return _DependentJob(job_id=value[0], name=value[1], skip_reason=value[2])


_FILE_REQUEST_CODEC = PersistenceCodec("tests.e2e.FileRequest", _FileRequest, lambda value: value.path, _FileRequest)
_PUBLISHED_FILE_JOB_CODEC = PersistenceCodec(
    "tests.e2e.PublishedFileJob",
    _PublishedFileJob,
    lambda job: (job.job_id, job.name, job.skip_reason, job.apply_binding, job.output_directory),
    lambda value: _PublishedFileJob(*value),
)

_PERSISTENCE_CODECS = (
    PersistenceCodec("tests.e2e.GatedJobTypeA", _GatedJobTypeA, _encode_job, _decode_gated_a),
    PersistenceCodec("tests.e2e.GatedJobTypeB", _GatedJobTypeB, _encode_job, _decode_gated_b),
    PersistenceCodec("tests.e2e.CancellationWaitJob", _CancellationWaitJob, _encode_job, _decode_cancellation_wait),
    PersistenceCodec("tests.e2e.ProducerJob", _ProducerJob, _encode_job, _decode_producer),
    PersistenceCodec("tests.e2e.ConsumerJob", _ConsumerJob, _encode_plain_job, _decode_consumer),
    PersistenceCodec("tests.e2e.FailingJob", _FailingJob, _encode_plain_job, _decode_failing),
    PersistenceCodec("tests.e2e.DependentJob", _DependentJob, _encode_plain_job, _decode_dependent),
    _FILE_REQUEST_CODEC,
    _PUBLISHED_FILE_JOB_CODEC,
    PersistenceCodec(
        "tests.e2e.ReadFileJob",
        _ReadFileJob,
        lambda job: (*_encode_plain_job(job), job.apply_binding),
        lambda value: _ReadFileJob(*value),
    ),
    PersistenceCodec("tests.e2e.ApplyFileHandler", _ApplyFileHandler),
)


class TestTypedQueueWorkflow(omni.kit.test.AsyncTestCase):
    """Exercise typed graphs through real SQLite, scheduling, and execution."""

    async def setUp(self):
        """Register exact test codecs and create an isolated queue database."""
        persistence.get_registry().register_codecs(_PERSISTENCE_CODECS)
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="typed-queue-e2e-")
        self._database_path = str(pathlib.Path(self._temporary_directory.name) / "queue.sqlite")
        self._interface = QueueInterface(self._database_path)
        self._scheduler: JobScheduler | None = None
        _GatedJob.started = {}
        _GatedJob.releases = {}
        _GatedJob.active = {}
        _GatedJob.peak = {}

    async def tearDown(self):
        """Settle owned work and remove codecs and queue files."""
        for release in _GatedJob.releases.values():
            release.set()
        if self._scheduler is not None:
            await self._scheduler.stop()
        persistence.get_registry().unregister_codecs(_PERSISTENCE_CODECS)
        self._temporary_directory.cleanup()

    @staticmethod
    def _prepare_gated_job(job: _GatedJob) -> None:
        """Create deterministic start and release signals for one submitted job."""
        _GatedJob.started[job.job_id] = asyncio.Event()
        _GatedJob.releases[job.job_id] = asyncio.Event()

    @staticmethod
    async def _wait_for_scheduler_setting(scheduler: JobScheduler, enabled: bool) -> None:
        """Wait for the settings callback to reconcile one dispatch state."""
        while True:
            reconcile_task = handlers._scheduler_reconcile_task
            if reconcile_task is not None and reconcile_task.done():
                reconcile_task.result()
            if scheduler.is_running() is enabled and (reconcile_task is None or reconcile_task.done()):
                return
            await asyncio.sleep(0)

    async def _publish_text(self, directory: pathlib.Path) -> tuple[QueueJob, _FileRequest]:
        """Publish a typed file through real queue claims and execution."""
        job = _PublishedFileJob(name="Publish text", output_directory=str(directory))
        handle = self._interface.submit(job)[0]
        self.assertEqual(self._interface.claim_runnable_jobs(), [job.job_id])
        await JobExecutor(self._interface).execute(job.job_id)
        request = (await handle.outputs(2))[FILE_REQUEST_OUTPUT]
        return handle, request

    async def test_scheduler_serializes_same_type_while_different_types_overlap(self):
        """Exact job classes own independent one-worker execution lanes."""
        first_a = _GatedJobTypeA(name="First A", value=1)
        second_a = _GatedJobTypeA(name="Second A", value=2)
        first_b = _GatedJobTypeB(name="First B", value=3)
        handles = []
        for job in (first_a, second_a, first_b):
            self._prepare_gated_job(job)
            handles.extend(self._interface.submit(job))

        self._scheduler = JobScheduler(self._interface)
        self._scheduler.start()

        # Different concrete job types start together while the second type-A job remains behind the first.
        await asyncio.wait_for(_GatedJob.started[first_a.job_id].wait(), 2)
        await asyncio.wait_for(_GatedJob.started[first_b.job_id].wait(), 2)

        self.assertFalse(_GatedJob.started[second_a.job_id].is_set())
        self.assertEqual(_GatedJob.active, {_GatedJobTypeA: 1, _GatedJobTypeB: 1})
        self.assertEqual(_GatedJob.peak, {_GatedJobTypeA: 1, _GatedJobTypeB: 1})

        # Releasing the first type-A slot allows its queued peer to start without waiting for type B.
        _GatedJob.releases[first_a.job_id].set()
        await asyncio.wait_for(_GatedJob.started[second_a.job_id].wait(), 2)
        _GatedJob.releases[second_a.job_id].set()
        _GatedJob.releases[first_b.job_id].set()
        await asyncio.gather(*(handle.outputs(2) for handle in handles))
        await self._scheduler.stop()
        self._scheduler = None

        # Both lanes finish, and neither concrete type exceeds its one-worker limit.
        self.assertEqual(_GatedJob.peak, {_GatedJobTypeA: 1, _GatedJobTypeB: 1})
        self.assertEqual(
            [self._interface.get_job_snapshot(job.job_id).state for job in (first_a, second_a, first_b)],
            [JobState.DONE, JobState.DONE, JobState.DONE],
        )

    async def test_connected_output_survives_reopen_and_reaches_consumer(self):
        """A typed graph reconstructs after reopening the same SQLite database."""
        producer = _ProducerJob(name="Generate", value=17)
        consumer = _ConsumerJob(name="Process")
        graph = JobGraph(name="Material graph", jobs=[producer, consumer])
        graph.connect(producer.output(NUMBER), consumer.input(NUMBER_INPUT))
        handles = self._interface.submit(graph)
        self._scheduler = JobScheduler(self._interface)

        # Execute the connected graph once and then reopen the same persisted queue.
        self._scheduler.start()
        outputs = await handles[1].outputs(2)
        await self._scheduler.stop()
        self._scheduler = None
        reopened = QueueInterface(self._database_path)

        # Reopening preserves graph topology plus typed producer and consumer outputs.
        graph_snapshot = reopened.get_graph_snapshots()[0]
        persisted_producer_outputs = reopened.get_job_outputs(producer.job_id)
        persisted_consumer_outputs = reopened.get_job_outputs(consumer.job_id)
        self.assertEqual(outputs[TEXT], "processed 17")
        self.assertEqual([job.job_id for job in graph_snapshot.jobs], [producer.job_id, consumer.job_id])
        self.assertEqual(persisted_producer_outputs[NUMBER], 17)
        self.assertEqual(persisted_consumer_outputs[TEXT], "processed 17")

    async def test_stop_start_settings_during_cancellation_wait_preserve_capacity_and_run_other_type(self):
        """The real settings callback resumes another type before cancellation confirmation arrives."""
        # Arrange
        settings = JobQueueSettings()
        settings_backend = carb.settings.get_settings()
        original_setting = settings_backend.get(SCHEDULER_ENABLED_SETTING_PATH)
        original_scheduler = handlers._scheduler
        original_reconcile_task = handlers._scheduler_reconcile_task
        if original_reconcile_task is not None:
            await asyncio.wait_for(asyncio.shield(original_reconcile_task), 2)
        self.assertIsNotNone(handlers._scheduler_subscription)
        active = _CancellationWaitJob(name="Pending cancellation", value=1)
        queued = _CancellationWaitJob(name="Next same-type job", value=2)
        unrelated = _GatedJobTypeB(name="Unrelated job", value=17)
        handles = {}
        for job in (active, queued):
            self._prepare_gated_job(job)
            handles[job.job_id] = self._interface.submit(job)[0]
        self._prepare_gated_job(unrelated)
        scheduler = JobScheduler(self._interface)
        self._scheduler = scheduler
        runtime_tasks = set()
        try:
            with (
                mock.patch.object(handlers, "_scheduler", scheduler),
                mock.patch.object(handlers, "_settings", settings),
                mock.patch.object(handlers, "_main_loop", asyncio.get_running_loop()),
                mock.patch.object(handlers, "_scheduler_reconcile_task", None),
                mock.patch.object(handlers, "_background_tasks", runtime_tasks),
            ):
                scheduler.start()
                try:
                    settings.set_scheduler_enabled(True)
                    await asyncio.wait_for(self._wait_for_scheduler_setting(scheduler, True), 2)
                    await asyncio.wait_for(_GatedJob.started[active.job_id].wait(), 2)
                    owner = scheduler._task
                    active_execution = scheduler._active[active.job_id]

                    # Act
                    settings.set_scheduler_enabled(False)
                    await asyncio.wait_for(self._wait_for_scheduler_setting(scheduler, False), 2)
                    paused = not scheduler.is_running()
                    unrelated_handle = self._interface.submit(unrelated)[0]
                    unrelated_before_resume = self._interface.get_job_snapshot(unrelated.job_id).state
                    settings.set_scheduler_enabled(True)
                    await asyncio.wait_for(self._wait_for_scheduler_setting(scheduler, True), 2)
                    await asyncio.wait_for(_GatedJob.started[unrelated.job_id].wait(), 2)
                    _GatedJob.releases[unrelated.job_id].set()
                    unrelated_outputs = await unrelated_handle.outputs(2)
                    retained_owner = scheduler._task
                    retained_active_execution = (
                        scheduler._active.get(active.job_id) is active_execution and not active_execution.done()
                    )
                    waiting_snapshot = self._interface.get_job_snapshot(active.job_id)
                    queued_before_release = self._interface.get_job_snapshot(queued.job_id).state
                    queued_started_before_release = _GatedJob.started[queued.job_id].is_set()
                    confirmation_before_release = _GatedJob.releases[active.job_id].is_set()
                    _GatedJob.releases[active.job_id].set()
                    with self.assertRaisesRegex(RuntimeError, "Cancellation confirmed after timeout"):
                        await handles[active.job_id].outputs(2)
                    await asyncio.wait_for(_GatedJob.started[queued.job_id].wait(), 2)
                    _GatedJob.releases[queued.job_id].set()
                    with self.assertRaisesRegex(RuntimeError, "Cancellation confirmed after timeout"):
                        await handles[queued.job_id].outputs(2)
                finally:
                    scheduler.pause()
                    for job in (active, queued, unrelated):
                        _GatedJob.releases[job.job_id].set()
                    reconcile_task = handlers._scheduler_reconcile_task
                    if reconcile_task is not None:
                        if not reconcile_task.done():
                            reconcile_task.cancel()
                        await asyncio.wait_for(asyncio.gather(reconcile_task, return_exceptions=True), 2)
                    await asyncio.wait_for(scheduler.stop(), 2)
                    self._scheduler = None
                    if runtime_tasks:
                        await asyncio.wait_for(asyncio.gather(*tuple(runtime_tasks)), 2)
        finally:
            if original_setting is None:
                settings_backend.destroy_item(SCHEDULER_ENABLED_SETTING_PATH)
            else:
                settings_backend.set(SCHEDULER_ENABLED_SETTING_PATH, original_setting)
            if original_scheduler is not None:
                await asyncio.wait_for(
                    self._wait_for_scheduler_setting(original_scheduler, settings.scheduler_enabled), 2
                )

        # Assert
        self.assertTrue(paused)
        self.assertIs(unrelated_before_resume, JobState.QUEUED)
        self.assertEqual(unrelated_outputs[NUMBER], 17)
        self.assertIs(retained_owner, owner)
        self.assertTrue(retained_active_execution)
        self.assertIs(waiting_snapshot.state, JobState.IN_PROGRESS)
        self.assertIsNone(waiting_snapshot.error)
        self.assertEqual(waiting_snapshot.progress.detail, "Waiting for cancellation confirmation.")
        self.assertIs(queued_before_release, JobState.QUEUED)
        self.assertFalse(queued_started_before_release)
        self.assertFalse(confirmation_before_release)
        self.assertEqual(_GatedJob.peak[_CancellationWaitJob], 1)
        self.assertEqual(_GatedJob.peak[_GatedJobTypeB], 1)
        for job in (active, queued):
            snapshot = self._interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.state, JobState.FAILED)
            self.assertTrue(snapshot.error.timed_out)
            self.assertEqual(snapshot.error.message, "Cancellation confirmed after timeout")
        self.assertIs(self._interface.get_job_snapshot(unrelated.job_id).state, JobState.DONE)

    async def test_stop_waits_for_active_job_without_dispatching_next_same_type(self):
        """Stopping pauses claims while the already active job finishes."""
        active = _GatedJobTypeA(name="Active", value=1)
        queued = _GatedJobTypeA(name="Queued", value=2)
        for job in (active, queued):
            self._prepare_gated_job(job)
            self._interface.submit(job)
        self._scheduler = JobScheduler(self._interface)
        self._scheduler.start()
        await asyncio.wait_for(_GatedJob.started[active.job_id].wait(), 2)

        # Stop while the first job owns the type lane; shutdown must wait for it but claim nothing else.
        stop_task = asyncio.create_task(self._scheduler.stop())
        observation = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(
            observation.set_result,
            (stop_task.done(), _GatedJob.started[queued.job_id].is_set()),
        )
        stopped_early, queued_started_early = await observation
        _GatedJob.releases[active.job_id].set()
        await asyncio.wait_for(stop_task, 2)
        self._scheduler = None

        # The active job settles Done while its same-type successor remains queued for a later restart.
        self.assertFalse(stopped_early)
        self.assertFalse(queued_started_early)
        self.assertFalse(_GatedJob.started[queued.job_id].is_set())
        self.assertIs(self._interface.get_job_snapshot(active.job_id).state, JobState.DONE)
        self.assertIs(self._interface.get_job_snapshot(queued.job_id).state, JobState.QUEUED)

    async def test_runtime_failure_recursively_skips_descendants(self):
        """A real executor failure prevents every downstream job from running."""
        failing = _FailingJob(name="Generate")
        child = _DependentJob(name="Process")
        grandchild = _DependentJob(name="Publish")
        graph = JobGraph(name="Failure graph", jobs=[failing, child, grandchild])
        graph.depends_on(child, failing)
        graph.depends_on(grandchild, child)
        handles = self._interface.submit(graph)
        self._scheduler = JobScheduler(self._interface)

        # Execute the root failure through the real scheduler and wait for its public handle to report it.
        self._scheduler.start()
        with self.assertRaisesRegex(RuntimeError, "Generation failed"):
            await handles[0].outputs(2)
        await self._scheduler.stop()
        self._scheduler = None

        # Dependency propagation skips each descendant with the immediate prerequisite named in its reason.
        child_snapshot = self._interface.get_job_snapshot(child.job_id)
        grandchild_snapshot = self._interface.get_job_snapshot(grandchild.job_id)
        self.assertIs(child_snapshot.state, JobState.SKIPPED)
        self.assertIs(grandchild_snapshot.state, JobState.SKIPPED)
        self.assertIn('Prerequisite "Generate"', child_snapshot.state_reason)
        self.assertIn('Prerequisite "Process"', grandchild_snapshot.state_reason)
        self.assertIs(child_snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
        self.assertIs(grandchild_snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)

    async def test_job_directory_creation_failure_settles_job(self):
        """Artifact setup failures settle claimed work instead of leaving it in progress."""
        # Replace the artifact directory with a file to reproduce the setup failure through the real executor.
        job = _ProducerJob(name="Blocked artifacts", value=17)
        self._interface.submit(job)
        self.assertIn(job.job_id, self._interface.claim_runnable_jobs())
        self._interface.get_job_directory(job.job_id).parent.write_text("not a directory", encoding="utf-8")

        # Execute the already claimed job through the production artifact-directory setup path.
        await JobExecutor(self._interface).execute(job.job_id)

        # Setup failure settles the row as Failed instead of stranding it In Progress.
        snapshot = self._interface.get_job_snapshot(job.job_id)
        self.assertIs(snapshot.state, JobState.FAILED)
        self.assertIsNotNone(snapshot.error)
        self.assertEqual(snapshot.error.exception_type, "FileExistsError")

    async def test_delete_published_files_respects_consumers_codecs_and_file_references(self):
        """Keep protected outputs and queue files while deleting selected records."""
        registry = persistence.get_registry()
        for case, codecs in (
            ("consumer", ()),
            ("unavailable_job", (_PUBLISHED_FILE_JOB_CODEC,)),
            ("unavailable_input", (_FILE_REQUEST_CODEC,)),
            ("internal_reference", ()),
            ("external_reference", ()),
        ):
            with self.subTest(case=case):
                # Publish a real file and retain its queue-file list for the deletion checks.
                project = pathlib.Path(self._temporary_directory.name) / case
                self._interface = QueueInterface(str(project.with_suffix(".sqlite")))
                producer, request = await self._publish_text(project / "published")
                source = pathlib.Path(request.path)
                metadata = source.with_suffix(".txt.meta")
                queue_directory = self._interface.get_job_directory(producer.job_id)
                queue_files = tuple(queue_directory.rglob("*"))
                queue_count = sum(path.is_file() for path in queue_files)
                survivors, references = [], ()
                # Bind a queued consumer or record an internal or external file reference to test each protection rule.
                if case in ("consumer", "unavailable_input"):
                    consumer = _ReadFileJob(name="Read published text")
                    graph = JobGraph(jobs=[consumer])
                    graph.bind(consumer, FILE_REQUEST_INPUT, request)
                    consumer_handle = self._interface.submit(graph)[0]
                    survivors.append(graph.graph_id)
                elif case.endswith("reference"):
                    referrer = project / "keep.txt" if case == "external_reference" else metadata
                    referrer.write_text(source.name, encoding="utf-8")
                    references = (FileReference(path=request.path, referrer=str(referrer)),)
                snapshot = UsageSnapshot.from_urls(verified_roots=(str(project),), references=references)
                if case == "unavailable_job":
                    self.assertEqual(
                        self._interface.get_graphs_artifact_file_count((producer.graph_id,), snapshot), queue_count + 2
                    )
                # Remove the selected codecs and reopen the queue to exercise persisted unavailable types.
                registry.unregister_codecs(codecs)
                try:
                    self._interface = QueueInterface(str(project.with_suffix(".sqlite")))
                    self.assertEqual(
                        self._interface.get_graphs_artifact_file_count((producer.graph_id,), snapshot),
                        0 if case == "unavailable_input" else queue_count + (2 if case == "internal_reference" else 0),
                    )
                    # Delete the producer records and expect the consumer and codec rules to control folder removal.
                    self.assertEqual(self._interface.delete_graphs((producer.graph_id,), snapshot), ())
                    self.assertEqual([item.graph_id for item in self._interface.get_graph_snapshots()], survivors)
                    self.assertEqual(queue_directory.exists(), case == "unavailable_input")
                    if case == "unavailable_input":
                        self.assertTrue(all(path.exists() for path in queue_files))
                    # Internal references permit folder removal, but external references and unavailable types preserve it.
                    if case == "internal_reference":
                        self.assertFalse(source.parent.exists())
                    else:
                        self.assertEqual(source.read_text(encoding="utf-8"), PUBLISHED_TEXT)
                        self.assertEqual(metadata.read_text(encoding="utf-8"), source.name)
                    if case == "external_reference":
                        self.assertEqual(referrer.read_text(encoding="utf-8"), source.name)
                finally:
                    registry.register_codecs(codecs)
                if survivors:
                    # Restore codec access and expect each surviving queued consumer to read the preserved source.
                    self.assertEqual(self._interface.resolve_job_inputs(consumer.job_id)[FILE_REQUEST_INPUT], request)
                    self.assertIs(self._interface.get_job_snapshot(consumer.job_id).state, JobState.QUEUED)
                    self.assertEqual(self._interface.claim_runnable_jobs(), [consumer.job_id])
                    await JobExecutor(self._interface).execute(consumer.job_id)
                    self.assertEqual((await consumer_handle.outputs(2))[TEXT], PUBLISHED_TEXT)

    async def test_delete_producer_preserves_declined_consumer_result_for_apply(self):
        """A declined consumer can Apply its shared file after producer deletion."""
        # Publish a source and execute a consumer whose Apply target still contains its original text.
        project = pathlib.Path(self._temporary_directory.name) / "project"
        producer, request = await self._publish_text(project / "published")
        target = project / "target.txt"
        target.write_text("Original target.", encoding="utf-8")
        consumer = _ReadFileJob(
            name="Reuse published text",
            apply_binding=ApplyBinding(FILE_REQUEST_OUTPUT, _ApplyFileHandler, str(target)),
        )
        graph = JobGraph(jobs=[consumer])
        graph.bind(consumer, FILE_REQUEST_INPUT, request)
        consumer_handle = self._interface.submit(graph)[0]
        self.assertEqual(self._interface.claim_runnable_jobs(), [consumer.job_id])
        await JobExecutor(self._interface).execute(consumer.job_id)
        self.assertEqual((await consumer_handle.outputs(2))[FILE_REQUEST_OUTPUT], request)
        registry = ApplyHandlerRegistry()
        registry.register_plugins([_ApplyFileHandler])
        executor = ApplyExecutor(self._interface, registry)
        try:
            # Decline the result and expect its completed output to remain available for a later Apply.
            await executor.decline(consumer.job_id)
            declined = self._interface.get_job_snapshot(consumer.job_id)
            self.assertIs(declined.state, JobState.DONE)
            self.assertIs(declined.apply_disposition, ApplyDisposition.DECLINED)

            # Delete the producer and expect its file to remain because the declined consumer still uses it.
            snapshot = UsageSnapshot.from_urls(verified_roots=(str(project),))
            self.assertEqual(self._interface.delete_graphs((producer.graph_id,), snapshot), ())
            self.assertEqual([item.graph_id for item in self._interface.get_graph_snapshots()], [graph.graph_id])
            self.assertEqual(pathlib.Path(request.path).read_text(encoding="utf-8"), PUBLISHED_TEXT)
            # Apply the declined consumer and expect the preserved file to replace the target text.
            await executor.apply(consumer.job_id)

            self.assertEqual(target.read_text(encoding="utf-8"), PUBLISHED_TEXT)
            self.assertIs(self._interface.get_job_snapshot(consumer.job_id).apply_disposition, ApplyDisposition.APPLIED)
        finally:
            await executor.shutdown()
            registry.destroy()

    async def test_delete_graph_with_linked_queue_directory_rejects_link_and_preserves_target(self):
        """A real queue link must not redirect artifact deletion to its target."""
        # Prepare a queued graph and an external folder whose contents must survive deletion.
        handle = self._interface.submit(_ProducerJob(name="Linked queue directory", value=17))[0]
        queue_directory = self._interface.get_job_directory(handle.job_id)
        queue_directory.parent.mkdir(parents=True)
        project = pathlib.Path(self._temporary_directory.name) / "project"
        target = project / "external-target"
        target_file = target / "nested" / "keep.txt"
        target_file.parent.mkdir(parents=True)
        target_file.write_text("Keep the target unchanged.", encoding="utf-8")
        graphs_before = self._interface.get_graph_snapshots()
        snapshot = UsageSnapshot.from_urls(verified_roots=(str(project),))
        # Link the queue folder to the external target so both cleanup entry points must reject it.
        try:
            try:
                queue_directory.symlink_to(target, target_is_directory=True)
            except OSError:
                if os.name != "nt":
                    raise
                # Windows can create a junction without the privilege required for a symbolic link.
                _winapi.CreateJunction(str(target), str(queue_directory))
            # Count and delete must reject the link without changing graph records or the external file.
            for operation in (self._interface.get_graphs_artifact_file_count, self._interface.delete_graphs):
                with self.assertRaises(OSError):
                    operation((handle.graph_id,), snapshot)
            self.assertEqual(self._interface.get_graph_snapshots(), graphs_before)
            self.assertTrue(queue_directory.samefile(target))
            self.assertEqual(target_file.read_text(encoding="utf-8"), "Keep the target unchanged.")
        finally:
            # Remove only the link so fixture cleanup cannot traverse its target.
            if queue_directory.is_symlink():
                queue_directory.unlink()
            elif os.path.lexists(queue_directory):
                queue_directory.rmdir()
