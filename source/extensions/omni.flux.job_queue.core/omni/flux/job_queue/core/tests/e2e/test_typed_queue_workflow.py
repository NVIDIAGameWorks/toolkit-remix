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
import pathlib
import tempfile
import uuid
from typing import ClassVar

import omni.kit.test
import omni.flux.job_queue.core.persistence as persistence
from omni.flux.job_queue.core.enums import ApplyDisposition, JobState
from omni.flux.job_queue.core.execute import JobExecutor, JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import (
    Job,
    JobGraph,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgressCallback,
)
from omni.flux.job_queue.core.persistence import PersistenceCodec

__all__ = ("TestTypedQueueWorkflow",)

NUMBER = JobOutputPort("number", int)
NUMBER_INPUT = JobInputPort("number", int)
TEXT = JobOutputPort("text", str)


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


_PERSISTENCE_CODECS = (
    PersistenceCodec("tests.e2e.GatedJobTypeA", _GatedJobTypeA, _encode_job, _decode_gated_a),
    PersistenceCodec("tests.e2e.GatedJobTypeB", _GatedJobTypeB, _encode_job, _decode_gated_b),
    PersistenceCodec("tests.e2e.ProducerJob", _ProducerJob, _encode_job, _decode_producer),
    PersistenceCodec("tests.e2e.ConsumerJob", _ConsumerJob, _encode_plain_job, _decode_consumer),
    PersistenceCodec("tests.e2e.FailingJob", _FailingJob, _encode_plain_job, _decode_failing),
    PersistenceCodec("tests.e2e.DependentJob", _DependentJob, _encode_plain_job, _decode_dependent),
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
