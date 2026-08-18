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

import asyncio
import dataclasses
import pathlib
import sqlite3
import threading
import uuid
from collections.abc import Callable
from typing import ClassVar
from unittest import mock

import omni.kit.test
import omni.flux.job_queue.core.persistence as persistence
import omni.flux.job_queue.core.interface as queue_interface
from omni.flux.job_queue.core.constants import QUEUE_SCHEMA_VERSION
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, JobState
from omni.flux.job_queue.core.errors import JobError, JobExecutionError, QueueSubmissionError
from omni.flux.job_queue.core.execute import JobExecutor, JobScheduler
from omni.flux.job_queue.core.extension import get_job_queue
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
from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.models import QueueJob
from omni.flux.job_queue.core.serializer import serialize
from omni.flux.utils.common import EventSubscription

from .helpers import temp_db_path

RESULT = JobOutputPort("result", int)
INPUT = JobInputPort("input", int)


@dataclasses.dataclass(frozen=True, slots=True)
class _UnregisteredValue:
    """Represent a port value deliberately absent from persistence."""

    value: int


UNREGISTERED_RESULT = JobOutputPort("unregistered_result", _UnregisteredValue)


@dataclasses.dataclass
class _LaneJob(Job):
    """Block execution on a shared gate while recording active jobs."""

    value: int = 0
    output_ports = (RESULT,)
    release: ClassVar[asyncio.Event | None] = None
    started: ClassVar[dict[uuid.UUID, asyncio.Event]] = {}
    active: ClassVar[dict[type, int]] = {}
    peak: ClassVar[dict[type, int]] = {}

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Wait for release and return the configured value.

        Args:
            job_directory: Queue-owned job directory.
            inputs: Empty typed input mapping.
            progress_callback: Callback that persists structured progress.

        Returns:
            Configured exact typed output.
        """
        del job_directory, inputs
        job_type = type(self)
        self.active[job_type] = self.active.get(job_type, 0) + 1
        self.peak[job_type] = max(self.peak.get(job_type, 0), self.active[job_type])
        self.started[self.job_id].set()
        try:
            await progress_callback(JobProgress(completed=0, total=1, detail="Waiting"))
            await self.release.wait()
            await progress_callback(JobProgress(completed=1, total=1, detail="Done"))
            return JobOutputs({RESULT: self.value})
        finally:
            self.active[job_type] -= 1


@dataclasses.dataclass
class _LaneA(_LaneJob):
    """Represent one exact scheduler concurrency class."""


@dataclasses.dataclass
class _LaneB(_LaneJob):
    """Represent a different exact scheduler concurrency class."""


@dataclasses.dataclass
class _BlockingReadinessJob(_LaneJob):
    """Block the synchronous product readiness callback for lock-scope tests."""

    readiness_entered: ClassVar[threading.Event | None] = None
    release_readiness: ClassVar[threading.Event | None] = None

    def get_schedule_block_reason(self) -> str | None:
        """Wait for the test while remaining logically ready."""
        self.readiness_entered.set()
        self.release_readiness.wait()
        return None


@dataclasses.dataclass
class _FailingReadinessJob(_LaneJob):
    """Raise one private diagnostic while the scheduler evaluates readiness."""

    def get_schedule_block_reason(self) -> str | None:
        """Raise a product-owned readiness failure."""
        raise RuntimeError("private readiness service failure")


@dataclasses.dataclass
class _InvalidPortJob(Job):
    """Declare a port value type that is intentionally not registered."""

    output_ports = (UNREGISTERED_RESULT,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return one value if invalid submission were ever allowed."""
        del job_directory, inputs, progress_callback
        return JobOutputs({UNREGISTERED_RESULT: _UnregisteredValue(1)})


@dataclasses.dataclass
class _FailureJob(Job):
    """Raise either an explicit domain failure or one unexpected diagnostic."""

    friendly: bool = False

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Raise the configured failure without producing output."""
        del job_directory, inputs, progress_callback
        diagnostic = ValueError("HTTP 500 from http://internal/service")
        if self.friendly:
            raise JobExecutionError("The generation service could not complete this job.", diagnostic)
        raise diagnostic


@dataclasses.dataclass
class _DetailJob(Job):
    """Expose typed input and output metadata for targeted detail queries."""

    input_ports = (INPUT,)
    output_ports = (RESULT,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return the exact persisted input value."""
        del job_directory, progress_callback
        return JobOutputs({RESULT: inputs[INPUT]})


_BLOCKING_READINESS_CODEC = PersistenceCodec(
    "test.BlockingReadinessJob",
    _BlockingReadinessJob,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding, value.value),
    lambda value: _BlockingReadinessJob(*value),
)
_DETAIL_CODEC = PersistenceCodec(
    "test.DetailJob",
    _DetailJob,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding),
    lambda value: _DetailJob(*value),
)
_FAILING_READINESS_CODEC = PersistenceCodec(
    "test.FailingReadinessJob",
    _FailingReadinessJob,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding, value.value),
    lambda value: _FailingReadinessJob(*value),
)
_FAILURE_CODEC = PersistenceCodec(
    "test.FailureJob",
    _FailureJob,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding, value.friendly),
    lambda value: _FailureJob(*value),
)
_INVALID_PORT_CODEC = PersistenceCodec(
    "test.InvalidPortJob",
    _InvalidPortJob,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding),
    lambda value: _InvalidPortJob(*value),
)
_LANE_A_CODEC = PersistenceCodec(
    "test.LaneA",
    _LaneA,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding, value.value),
    lambda value: _LaneA(*value),
)
_LANE_B_CODEC = PersistenceCodec(
    "test.LaneB",
    _LaneB,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding, value.value),
    lambda value: _LaneB(*value),
)
_LANE_CODECS = (
    _BLOCKING_READINESS_CODEC,
    _DETAIL_CODEC,
    _FAILING_READINESS_CODEC,
    _FAILURE_CODEC,
    _INVALID_PORT_CODEC,
    _LANE_A_CODEC,
    _LANE_B_CODEC,
)


class _TracingQueueInterface(QueueInterface):
    """Capture executed SQLite statements for snapshot-query assertions."""

    def __init__(self, db_path: str):
        """Create a queue and statement probe."""
        self.statements: list[str] = []
        super().__init__(db_path)

    def connection(self):
        """Attach the statement probe to each owned SQLite connection."""
        context = super().connection()
        statements = self.statements

        class _TracedConnection:
            """Proxy one connection while installing its statement trace."""

            def __enter__(self):
                """Enter the connection and install statement tracing."""
                connection = context.__enter__()
                connection.set_trace_callback(statements.append)
                return connection

            def __exit__(self, *args):
                """Delegate context exit to the owned connection context."""
                return context.__exit__(*args)

        return _TracedConnection()


class _SubscriptionProbeQueue(QueueInterface):
    """Expose deterministic notification subscription for output waiting."""

    def __init__(self, db_path: str):
        """Create a queue and subscription signal."""
        self.subscribed = asyncio.Event()
        super().__init__(db_path)

    def subscribe_job_changed(self, callback: Callable[[uuid.UUID], None]) -> EventSubscription:
        """Signal before retaining the targeted callback."""
        self.subscribed.set()
        return super().subscribe_job_changed(callback)


class TestQueueModuleBoundaries(omni.kit.test.AsyncTestCase):
    """Validate the queue interface module exposes only the interface."""

    def test_interface_module_exports_only_queue_interface(self):
        """Keep errors and immutable records in their dedicated modules."""
        # Arrange
        expected_names = ("QueueInterface",)

        # Act
        exported_names = queue_interface.__all__

        # Assert
        self.assertEqual(expected_names, exported_names)


class TestQueuePersistence(omni.kit.test.AsyncTestCase):
    """Validate fresh typed graph persistence and atomic transitions."""

    async def setUp(self):
        """Register exact test job codecs."""
        persistence.get_registry().register_codecs(_LANE_CODECS)

    async def tearDown(self):
        """Unregister exact test job codecs."""
        persistence.get_registry().unregister_codecs(_LANE_CODECS)

    @staticmethod
    def _attempt_competing_starts(interface: QueueInterface, job_id: uuid.UUID) -> tuple[bool, bool]:
        """Run two scheduler-owned starts as one atomic-race scenario."""
        interface.claim_runnable_jobs()
        first = interface.start_job(job_id)
        stale = interface.start_job(job_id)
        return first, stale

    @staticmethod
    def _claim_and_start(interface: QueueInterface, job_id: uuid.UUID) -> None:
        """Claim and start one runnable test job through the runtime-owned APIs."""
        if job_id not in interface.claim_runnable_jobs() or not interface.start_job(job_id):
            raise RuntimeError(f"Could not start test job {job_id}")

    @staticmethod
    async def _complete_from_worker_after_subscription(
        queue_job: QueueJob,
        interface: _SubscriptionProbeQueue,
        job: _LaneA,
    ) -> JobOutputs:
        """Complete one job from a worker thread after its output waiter subscribes."""
        waiter = asyncio.create_task(queue_job.outputs())
        await asyncio.wait_for(interface.subscribed.wait(), 2)
        await asyncio.to_thread(interface.claim_runnable_jobs)
        await asyncio.to_thread(interface.start_job, job.job_id)
        await asyncio.to_thread(interface.complete_job, job.job_id, JobOutputs({RESULT: job.value}))
        return await asyncio.wait_for(waiter, 2)

    async def test_submit_persists_fresh_graph_schema_without_history(self):
        """Submission writes current graph state without event or migration tables."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            first = _LaneA(value=1)
            second = _LaneA(value=2)
            graph = JobGraph(name="Graph", jobs=[first, second])
            graph.depends_on(second, first)

            # Act
            queue_jobs = interface.submit(graph)

            # Assert
            snapshots = list(interface.iter_snapshot())
            self.assertEqual([queue_job.graph_id for queue_job in queue_jobs], [graph.graph_id, graph.graph_id])
            self.assertEqual([snapshot.position for snapshot in snapshots], [0, 1])
            self.assertEqual([snapshot.job_type for snapshot in snapshots], ["test.LaneA", "test.LaneA"])
            self.assertTrue(
                all(snapshot.apply_disposition is ApplyDisposition.NOT_APPLICABLE for snapshot in snapshots)
            )
            self.assertTrue(all(snapshot.apply_operation is ApplyOperation.IDLE for snapshot in snapshots))
            with interface.connection() as connection:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
            self.assertEqual(
                tables,
                {
                    "job_connections",
                    "job_control_edges",
                    "job_graphs",
                    "job_input_values",
                    "jobs",
                },
            )
            self.assertEqual(
                job_columns,
                {
                    "apply_disposition",
                    "apply_error_message",
                    "apply_error_traceback",
                    "apply_error_type",
                    "apply_handler_id",
                    "apply_operation",
                    "apply_reason",
                    "apply_receipt",
                    "completed_at",
                    "error_message",
                    "error_traceback",
                    "error_type",
                    "graph_id",
                    "job_data",
                    "job_id",
                    "job_type",
                    "name",
                    "outputs",
                    "position",
                    "progress_completed",
                    "progress_detail",
                    "progress_total",
                    "started_at",
                    "state",
                    "state_reason",
                },
            )

    async def test_submit_graphs_adds_batch_in_one_transaction_with_one_notification(self):
        """A batch submit adds every graph in a single transaction and notifies subscribers once."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = _TracingQueueInterface(db_path)
            first = JobGraph(name="First", jobs=[_LaneA(value=1)])
            second = JobGraph(name="Second", jobs=[_LaneA(value=2)])
            third = JobGraph(name="Third", jobs=[_LaneA(value=3)])
            mutation_count = 0

            def on_mutation() -> None:
                nonlocal mutation_count
                mutation_count += 1

            subscription = interface.subscribe_mutation(on_mutation)
            interface.statements.clear()

            # Act
            handles = interface.submit_graphs([first, second, third])
            begin_immediate_count = interface.statements.count("BEGIN IMMEDIATE")

            # Assert
            self.assertEqual(begin_immediate_count, 1)
            self.assertEqual(mutation_count, 1)
            self.assertEqual([handle.graph_id for handle in handles], [first.graph_id, second.graph_id, third.graph_id])
            self.assertEqual(len(list(interface.iter_snapshot())), 3)
            del subscription

    async def test_submit_graphs_rolls_back_the_whole_batch_when_one_graph_is_invalid(self):
        """A batch submit is all-or-nothing: one invalid graph leaves the queue empty and unnotified."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            valid = JobGraph(name="Valid", jobs=[_LaneA(value=1)])
            invalid = JobGraph(name="Invalid", jobs=[_InvalidPortJob()])
            mutation_count = 0

            def on_mutation() -> None:
                nonlocal mutation_count
                mutation_count += 1

            subscription = interface.subscribe_mutation(on_mutation)

            # Act
            with self.assertRaises(QueueSubmissionError):
                interface.submit_graphs([valid, invalid])

            # Assert
            self.assertEqual(interface.get_graph_snapshots(), [])
            self.assertEqual(mutation_count, 0)
            del subscription

    async def test_unregistered_port_value_type_rejects_submission_atomically(self):
        """Port type validation completes before any graph row is inserted."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)

            # Act
            with self.assertRaisesRegex(RuntimeError, "UnregisteredValue"):
                interface.submit(_InvalidPortJob())

            # Assert
            self.assertEqual(interface.get_graph_snapshots(), [])
            self.assertEqual(list(interface.iter_snapshot()), [])

    async def test_incompatible_database_file_is_recreated_from_scratch(self):
        """A previous schema is replaced before its removed required columns can reject submissions."""
        # Arrange
        async with temp_db_path() as db_path:
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE jobs(job_id TEXT, input_ports TEXT NOT NULL)")
                connection.execute(f"PRAGMA user_version = {QUEUE_SCHEMA_VERSION - 1}")
                connection.commit()
            finally:
                connection.close()

            # Act
            interface = QueueInterface(db_path, clear_incompatible_database=True)
            submitted = interface.submit(_LaneA())

            # Assert
            with interface.connection() as connection:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
                version = connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertIn("jobs", tables)
            self.assertNotIn("input_ports", job_columns)
            self.assertEqual(version, QUEUE_SCHEMA_VERSION)
            self.assertEqual(len(submitted), 1)

    async def test_incompatible_database_requires_explicit_clear_permission(self):
        """A caller-selected SQLite file is never deleted without destructive opt-in."""
        # Arrange
        async with temp_db_path() as db_path:
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE caller_records(value TEXT)")
                connection.execute(f"PRAGMA user_version = {QUEUE_SCHEMA_VERSION + 1}")
                connection.commit()
            finally:
                connection.close()

            # Act
            with self.assertRaisesRegex(RuntimeError, "incompatible"):
                QueueInterface(db_path)

            # Assert
            connection = sqlite3.connect(db_path)
            try:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            finally:
                connection.close()
            self.assertIn("caller_records", tables)

    async def test_zero_version_legacy_database_is_recreated_from_scratch(self):
        """A populated unversioned database is incompatible rather than mistaken for a fresh file."""
        # Arrange
        async with temp_db_path() as db_path:
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE stale_records(value TEXT)")
                connection.commit()
            finally:
                connection.close()

            # Act
            interface = QueueInterface(db_path, clear_incompatible_database=True)

            # Assert
            with interface.connection() as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                version = connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertNotIn("stale_records", tables)
            self.assertEqual(version, QUEUE_SCHEMA_VERSION)

    async def test_snapshot_query_does_not_read_payload_or_output_blobs(self):
        """Snapshot reads select only immutable display and lifecycle columns."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = _TracingQueueInterface(db_path)
            interface.submit(_LaneA())
            interface.statements.clear()

            # Act
            list(interface.iter_snapshot())

            # Assert
            select = next(statement.lower() for statement in interface.statements if "from jobs" in statement.lower())
            self.assertNotIn("job_data", select)
            self.assertNotIn("outputs", select)
            self.assertNotIn("apply_receipt", select)

    async def test_snapshot_iterator_is_lazy_until_consumed(self):
        """Creating the full-queue iterator does not open SQLite or materialize rows."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = _TracingQueueInterface(db_path)
            interface.submit(_LaneA())
            interface.statements.clear()

            # Act
            snapshots = interface.iter_snapshot()

            # Assert
            self.assertEqual(interface.statements, [])
            snapshots.close()

    async def test_snapshot_resolves_all_dependency_states_with_one_select(self):
        """Snapshot traversal stays one set-based SQL statement as queue size grows."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = _TracingQueueInterface(db_path)
            source = _LaneA()
            dependent = _LaneB()
            graph = JobGraph(jobs=[source, dependent])
            graph.depends_on(dependent, source)
            interface.submit(graph)
            interface.statements.clear()

            # Act
            snapshots = list(interface.iter_snapshot())

            # Assert
            select_statements = [
                statement for statement in interface.statements if statement.lstrip().upper().startswith("WITH")
            ]
            self.assertEqual(len(select_statements), 1)
            self.assertEqual(
                [snapshot.state for snapshot in snapshots],
                [JobState.QUEUED, JobState.WAITING_FOR_DEPENDENCIES],
            )

    async def test_job_details_returns_typed_related_topology_without_payload_values(self):
        """Targeted details expose declared ports and related edges without reading serialized job values."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = _TracingQueueInterface(db_path)
            source = _LaneA()
            prerequisite = _LaneB()
            target = _DetailJob()
            graph = JobGraph(jobs=[source, prerequisite, target])
            graph.connect(source.output(RESULT), target.input(INPUT))
            graph.depends_on(target, prerequisite)
            interface.submit(graph)
            interface.statements.clear()

            # Act
            details = interface.get_job_details(target.job_id)

            # Assert
            statements = "\n".join(interface.statements).lower()
            self.assertNotIn("job_data", statements)
            self.assertNotIn("select input_ports, output_ports, outputs", statements)
            self.assertEqual(details.input_ports, (INPUT,))
            self.assertEqual(details.output_ports, (RESULT,))
            self.assertEqual(details.connections[0].source_job_id, source.job_id)
            self.assertEqual(details.connections[0].source_port, RESULT)
            self.assertEqual(details.connections[0].target_job_id, target.job_id)
            self.assertEqual(details.connections[0].target_port, INPUT)
            self.assertEqual(details.control_edges[0].prerequisite_job_id, prerequisite.job_id)
            self.assertIsNone(details.inputs)
            self.assertIsNone(details.outputs)

    async def test_job_details_with_values_decodes_literal_inputs_and_exact_outputs(self):
        """Value opt-in returns available typed inputs and validated completed outputs."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _DetailJob()
            graph = JobGraph(jobs=[job])
            graph.bind(job, INPUT, 7)
            interface.submit(graph)
            interface.claim_runnable_jobs()
            interface.start_job(job.job_id)
            interface.complete_job(job.job_id, JobOutputs({RESULT: 7}))

            # Act
            details = interface.get_job_details(job.job_id, include_values=True)

            # Assert
            self.assertEqual(details.literal_inputs[0].value, 7)
            self.assertEqual(details.inputs, JobInputs({INPUT: 7}))
            self.assertEqual(details.outputs, JobOutputs({RESULT: 7}))

    async def test_queued_job_payload_can_be_replaced_before_claim(self):
        """A conditional queued update preserves identity while replacing exact payload data."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA(value=1)
            interface.submit(job)
            updated = dataclasses.replace(job, name="Updated", value=2)

            # Act
            accepted = interface.try_update_queued_job(updated)

            # Assert
            persisted = interface.get_job(job.job_id)
            self.assertTrue(accepted)
            self.assertEqual(persisted.name, "Updated")
            self.assertEqual(persisted.value, 2)

    async def test_queued_job_update_loses_after_scheduler_claim(self):
        """A stale editor cannot replace a payload after execution claims the job."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA(value=1)
            interface.submit(job)
            interface.claim_runnable_jobs()

            # Act
            accepted = interface.try_update_queued_job(dataclasses.replace(job, value=2))

            # Assert
            self.assertFalse(accepted)
            self.assertEqual(interface.get_job(job.job_id).value, 1)

    async def test_malformed_job_payload_fails_and_skips_descendants(self):
        """A registered job with corrupt persisted data settles instead of retrying forever."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            parent = _LaneA(name="parent")
            child = _LaneB(name="child")
            graph = JobGraph(jobs=[parent, child])
            graph.depends_on(child, parent)
            interface.submit(graph)
            with interface.connection() as connection:
                connection.execute("UPDATE jobs SET job_data = ? WHERE job_id = ?", ("not JSON", str(parent.job_id)))
                connection.commit()

            # Act
            claimed = interface.claim_runnable_jobs()

            # Assert
            parent_snapshot = interface.get_job_snapshot(parent.job_id)
            child_snapshot = interface.get_job_snapshot(child.job_id)
            self.assertEqual(claimed, [])
            self.assertIs(parent_snapshot.state, JobState.FAILED)
            self.assertEqual(parent_snapshot.state_reason, "The saved job data is invalid and could not be loaded.")
            self.assertEqual(parent_snapshot.error.exception_type, "ValueError")
            self.assertIs(child_snapshot.state, JobState.SKIPPED)

    async def test_registered_decoder_exception_fails_job_durably(self):
        """An ordinary exception from a registered decoder cannot stop runnable scanning."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            broken = _LaneA()
            later = _LaneB()
            interface.submit(broken)
            interface.submit(later)
            invalid_codec = PersistenceCodec(
                _LANE_A_CODEC.name,
                _LaneA,
                _LANE_A_CODEC.encoder,
                mock.Mock(side_effect=IndexError("invalid codec payload")),
            )
            registry = persistence.get_registry()
            registry.unregister_codecs([_LANE_A_CODEC])
            registry.register_codecs([invalid_codec])

            try:
                # Act
                claimed = interface.claim_runnable_jobs()
            finally:
                registry.unregister_codecs([invalid_codec])
                registry.register_codecs([_LANE_A_CODEC])

            # Assert
            snapshot = interface.get_job_snapshot(broken.job_id)
            self.assertEqual(claimed, [later.job_id])
            self.assertIs(snapshot.state, JobState.FAILED)
            self.assertEqual(snapshot.state_reason, "The saved job data is invalid and could not be loaded.")
            self.assertEqual(snapshot.error.exception_type, "IndexError")

    async def test_graph_snapshots_hold_one_database_read_transaction(self):
        """Graph metadata and child rows come from the same committed SQLite snapshot."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            graph = JobGraph(name="Before", jobs=[job])
            interface.submit(graph)
            original_iter = interface._iter_snapshots

            def mutate_after_job_read(*args, **kwargs):
                """Commit a competing graph rename after the child query is consumed."""
                snapshots = list(original_iter(*args, **kwargs))
                with interface.connection() as writer:
                    writer.execute("UPDATE job_graphs SET name = ? WHERE graph_id = ?", ("After", str(graph.graph_id)))
                    writer.commit()
                yield from snapshots

            # Act
            with mock.patch.object(interface, "_iter_snapshots", side_effect=mutate_after_job_read):
                snapshots = interface.get_graph_snapshots()

            # Assert
            self.assertEqual(snapshots[0].name, "Before")
            self.assertEqual(snapshots[0].jobs[0].graph_name, "Before")
            with interface.connection() as connection:
                persisted_name = connection.execute(
                    "SELECT name FROM job_graphs WHERE graph_id = ?", (str(graph.graph_id),)
                ).fetchone()[0]
            self.assertEqual(persisted_name, "After")

    async def test_cancellation_during_start_settles_terminal_failure(self):
        """Cancellation waits for an in-flight start transition before failing the job."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            interface.claim_runnable_jobs()
            start_entered = threading.Event()
            release_start = threading.Event()
            original_start = interface.start_job

            def blocked_start(job_id: uuid.UUID) -> bool:
                """Pause the worker-owned start transition until cancellation is requested."""
                start_entered.set()
                release_start.wait()
                return original_start(job_id)

            # Act
            with mock.patch.object(interface, "start_job", side_effect=blocked_start):
                execution = asyncio.create_task(JobExecutor(interface).execute(job.job_id))
                try:
                    await asyncio.wait_for(asyncio.to_thread(start_entered.wait), 2)
                    execution.cancel()
                finally:
                    if not execution.done():
                        execution.cancel()
                    release_start.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(execution, 2)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.state, JobState.FAILED)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertEqual(snapshot.state_reason, "The job was cancelled before completion.")
            self.assertEqual(snapshot.error.exception_type, "CancelledError")

    async def test_cancellation_settles_when_start_worker_raises(self):
        """A failing in-flight start cannot bypass cancellation's conditional terminal transition."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            interface.claim_runnable_jobs()
            start_entered = threading.Event()
            release_start = threading.Event()

            def failing_start(_job_id: uuid.UUID) -> bool:
                """Raise after cancellation has raced the worker-owned start call."""
                start_entered.set()
                release_start.wait()
                raise RuntimeError("start failed")

            # Act
            with (
                mock.patch.object(interface, "start_job", side_effect=failing_start),
                mock.patch("omni.flux.job_queue.core.execute.carb.log_error") as log_error,
            ):
                execution = asyncio.create_task(JobExecutor(interface).execute(job.job_id))
                try:
                    await asyncio.wait_for(asyncio.to_thread(start_entered.wait), 2)
                    execution.cancel()
                finally:
                    if not execution.done():
                        execution.cancel()
                    release_start.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(execution, 2)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.state, JobState.FAILED)
            self.assertEqual(snapshot.state_reason, "The job was cancelled before completion.")
            self.assertEqual(snapshot.error.exception_type, "CancelledError")
            log_error.assert_called_once_with(f"Could not finish starting cancelled job {job.job_id}: start failed")

    async def test_cancellation_does_not_settle_after_start_returns_false(self):
        """A losing start cannot fail work already claimed by another executor."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            interface.claim_runnable_jobs()
            start_entered = threading.Event()
            release_start = threading.Event()
            original_start = interface.start_job

            def losing_start(_job_id: uuid.UUID) -> bool:
                """Return a clean ownership loss after the competing executor starts."""
                start_entered.set()
                release_start.wait()
                return False

            # Act
            with mock.patch.object(interface, "start_job", side_effect=losing_start):
                execution = asyncio.create_task(JobExecutor(interface).execute(job.job_id))
                try:
                    await asyncio.wait_for(asyncio.to_thread(start_entered.wait), 2)
                    execution.cancel()
                    competing_started = original_start(job.job_id)
                finally:
                    if not execution.done():
                        execution.cancel()
                    release_start.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(execution, 2)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertTrue(competing_started)
            self.assertIs(snapshot.state, JobState.IN_PROGRESS)
            self.assertIsNone(snapshot.error)

    async def test_cancellation_during_completion_preserves_committed_success(self):
        """Cancellation cannot race a durable completion into terminal failure."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            _LaneJob.release = asyncio.Event()
            _LaneJob.started = {job.job_id: asyncio.Event()}
            interface.submit(job)
            interface.claim_runnable_jobs()
            completion_entered = threading.Event()
            release_completion = threading.Event()
            original_complete = interface.complete_job

            def blocked_complete(job_id: uuid.UUID, outputs: JobOutputs) -> bool:
                """Pause the durable completion transition while cancellation arrives."""
                completion_entered.set()
                release_completion.wait()
                return original_complete(job_id, outputs)

            # Act
            with mock.patch.object(interface, "complete_job", side_effect=blocked_complete):
                execution = asyncio.create_task(JobExecutor(interface).execute(job.job_id))
                await asyncio.wait_for(_LaneJob.started[job.job_id].wait(), 2)
                _LaneJob.release.set()
                await asyncio.wait_for(asyncio.to_thread(completion_entered.wait), 2)
                execution.cancel()
                release_completion.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(execution, 2)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.state, JobState.DONE)
            self.assertIsNone(snapshot.error)

    async def test_queue_job_outputs_wakes_safely_from_worker_thread(self):
        """A stable child handle returns exact outputs without polling or cross-thread Event access."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = _SubscriptionProbeQueue(db_path)
            job = _LaneA(value=8)
            queue_job = interface.submit(job)[0]

            # Act
            outputs = await self._complete_from_worker_after_subscription(queue_job, interface, job)

            # Assert
            self.assertEqual(outputs, JobOutputs({RESULT: 8}))

    async def test_queue_job_outputs_subscription_failure_rolls_back_first_listener(self):
        """A failed mutation subscription cannot leak the earlier job listener."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            queue_job = interface.submit(_LaneA())[0]
            subscriber_count = len(interface._job_changed_event)

            # Act
            with (
                mock.patch.object(interface, "subscribe_mutation", side_effect=RuntimeError("subscription failed")),
                self.assertRaisesRegex(RuntimeError, "subscription failed"),
            ):
                await queue_job.outputs()

            # Assert
            self.assertEqual(len(interface._job_changed_event), subscriber_count)

    async def test_start_requires_expected_state_atomically(self):
        """A stale writer cannot overwrite a state changed by another owner."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)

            # Act
            first, stale = self._attempt_competing_starts(interface, job.job_id)

            # Assert
            self.assertTrue(first)
            self.assertFalse(stale)
            self.assertIs(interface.get_job_snapshot(job.job_id).state, JobState.IN_PROGRESS)

    async def test_submission_snapshot_uses_graph_timestamp_without_execution_times(self):
        """A new child derives its graph submission time without execution lifecycle times."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()

            # Act
            interface.submit(job)

            # Assert
            submitted = interface.get_job_snapshot(job.job_id)
            graph_snapshot = interface.get_graph_snapshots()[0]
            self.assertIsNotNone(submitted.submitted_at)
            self.assertEqual(submitted.submitted_at, graph_snapshot.submitted_at)
            self.assertIsNone(submitted.started_at)
            self.assertIsNone(submitted.completed_at)

    async def test_claim_snapshot_does_not_set_started_timestamp(self):
        """A scheduler claim alone does not imply that job execution started."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)

            # Act
            interface.claim_runnable_jobs()

            # Assert
            claimed = interface.get_job_snapshot(job.job_id)
            self.assertIsNone(claimed.started_at)
            self.assertIsNone(claimed.completed_at)

    async def test_start_snapshot_sets_started_timestamp_only(self):
        """Beginning execution persists start time without a completion time."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            interface.claim_runnable_jobs()

            # Act
            started_result = interface.start_job(job.job_id)

            # Assert
            started = interface.get_job_snapshot(job.job_id)
            self.assertTrue(started_result)
            self.assertIsNotNone(started.started_at)
            self.assertIsNone(started.completed_at)

    async def test_completion_snapshot_sets_ordered_lifecycle_timestamps(self):
        """Terminal success persists completion after submission and execution start."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            interface.claim_runnable_jobs()
            interface.start_job(job.job_id)

            # Act
            completion_result = interface.complete_job(job.job_id, JobOutputs({RESULT: job.value}))

            # Assert
            completed = interface.get_job_snapshot(job.job_id)
            self.assertTrue(completion_result)
            self.assertIsNotNone(completed.completed_at)
            self.assertLessEqual(completed.submitted_at, completed.started_at)
            self.assertLessEqual(completed.started_at, completed.completed_at)

    async def test_readiness_exception_fails_job_safely_and_claims_later_type(self):
        """One broken product readiness hook cannot abort later exact-type scheduling."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            broken = _FailingReadinessJob(name="broken")
            data_child = _DetailJob(name="data child")
            control_grandchild = _LaneA(name="control grandchild")
            later = _LaneB(name="later")
            graph = JobGraph(jobs=[broken, data_child, control_grandchild])
            graph.connect(broken.output(RESULT), data_child.input(INPUT))
            graph.depends_on(control_grandchild, data_child)
            interface.submit(graph)
            interface.submit(later)

            # Act
            claimed = interface.claim_runnable_jobs()

            # Assert
            broken_snapshot = interface.get_job_snapshot(broken.job_id)
            self.assertEqual(claimed, [later.job_id])
            self.assertIs(broken_snapshot.state, JobState.FAILED)
            self.assertEqual(broken_snapshot.state_reason, "The job could not be scheduled.")
            self.assertEqual(broken_snapshot.error.message, "private readiness service failure")
            self.assertNotIn("private", broken_snapshot.state_reason)
            self.assertIs(interface.get_job_snapshot(data_child.job_id).state, JobState.SKIPPED)
            self.assertIs(interface.get_job_snapshot(control_grandchild.job_id).state, JobState.SKIPPED)

    async def test_incomplete_prerequisite_prevents_product_readiness_evaluation(self):
        """A waiting descendant never invokes product readiness before its prerequisites complete."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            prerequisite = _LaneA(name="prerequisite")
            waiting = _FailingReadinessJob(name="waiting")
            graph = JobGraph(jobs=[prerequisite, waiting])
            graph.depends_on(waiting, prerequisite)
            interface.submit(graph)

            # Act
            claimed = interface.claim_runnable_jobs()

            # Assert
            self.assertEqual(claimed, [prerequisite.job_id])
            snapshot = interface.get_job_snapshot(waiting.job_id)
            self.assertIs(snapshot.state, JobState.WAITING_FOR_DEPENDENCIES)
            self.assertIsNone(snapshot.error)

    async def test_progress_notification_does_not_wake_scheduler(self):
        """A progress-only child transition avoids a full runnable scan."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            self._claim_and_start(interface, job.job_id)
            progress_changes = []
            job_changes = []
            schedule_wakes = []
            job_subscription = interface.subscribe_job_changed(job_changes.append)
            progress_subscription = interface.subscribe_job_progress_changed(
                lambda job_id, progress: progress_changes.append((job_id, progress))
            )
            schedule_subscription = interface.subscribe_schedule_conditions_changed(
                lambda: schedule_wakes.append("wake")
            )
            progress = JobProgress(completed=1, total=2)

            # Act
            changed = interface.update_progress(job.job_id, progress)

            # Assert
            self.assertTrue(changed)
            self.assertEqual(progress_changes, [(job.job_id, progress)])
            self.assertEqual(job_changes, [])
            self.assertEqual(schedule_wakes, [])
            del job_subscription, progress_subscription, schedule_subscription

    async def test_execution_notification_wakes_scheduler(self):
        """An execution-state transition wakes the scheduler and child observers."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            self._claim_and_start(interface, job.job_id)
            child_changes = []
            schedule_wakes = []
            external_changes = []
            child_subscription = interface.subscribe_job_changed(child_changes.append)
            schedule_subscription = interface.subscribe_schedule_conditions_changed(
                lambda: schedule_wakes.append("wake")
            )
            external_subscription = interface.subscribe_external_conditions_changed(
                lambda: external_changes.append("external")
            )

            # Act
            changed = interface.complete_job(job.job_id, JobOutputs({RESULT: job.value}))

            # Assert
            self.assertTrue(changed)
            self.assertEqual(child_changes, [job.job_id])
            self.assertEqual(schedule_wakes, ["wake"])
            self.assertEqual(external_changes, [])
            del child_subscription, schedule_subscription, external_subscription

    async def test_apply_notification_does_not_wake_scheduler(self):
        """An Apply-only child transition avoids a full runnable scan."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            self._claim_and_start(interface, job.job_id)
            interface.complete_job(job.job_id, JobOutputs({RESULT: job.value}))
            child_changes = []
            schedule_wakes = []
            child_subscription = interface.subscribe_job_changed(child_changes.append)
            schedule_subscription = interface.subscribe_schedule_conditions_changed(
                lambda: schedule_wakes.append("wake")
            )

            # Act
            changed = interface.start_apply_operation(
                job.job_id,
                (ApplyDisposition.NOT_APPLICABLE,),
                (ApplyOperation.IDLE,),
                ApplyOperation.APPLYING,
            )

            # Assert
            self.assertTrue(changed)
            self.assertEqual(child_changes, [job.job_id])
            self.assertEqual(schedule_wakes, [])
            del child_subscription, schedule_subscription

    async def test_submit_isolates_raising_mutation_subscriber_and_continues_dispatch(self):
        """A committed submission succeeds and reaches later listeners after one listener raises."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            calls = []

            def raise_from_listener() -> None:
                """Raise one product callback failure for dispatch isolation."""
                raise ValueError("subscriber failed")

            raising = interface.subscribe_mutation(raise_from_listener)
            observing = interface.subscribe_mutation(lambda: calls.append("observed"))

            # Act
            with mock.patch("omni.flux.job_queue.core.interface.carb.log_error") as log_error:
                queue_jobs = interface.submit(_LaneA())

            # Assert
            self.assertEqual(len(queue_jobs), 1)
            self.assertEqual(calls, ["observed"])
            log_error.assert_called_once_with("Queue mutation subscriber failed: subscriber failed")
            del raising, observing

    async def test_recovery_makes_interrupted_execution_apply_state_not_applicable(self):
        """A recovered execution failure cannot retain a pending-looking Apply lifecycle."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            interface.claim_runnable_jobs()
            interface.start_job(job.job_id)

            # Act
            interface.recover_interrupted_jobs()

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.state, JobState.FAILED)

    async def test_recovery_requeues_unstarted_claim(self):
        """Restart recovery returns an undispatched claim to the queue."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            interface.claim_runnable_jobs()

            # Act
            interface.recover_interrupted_jobs()

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.state, JobState.QUEUED)

    async def test_sqlite_rejects_derived_state_directly(self):
        """The fresh schema enforces persisted states below the Python API."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)

            # Act
            with self.assertRaises(sqlite3.IntegrityError):
                with interface.connection() as connection:
                    connection.execute(
                        "UPDATE jobs SET state = ? WHERE job_id = ?",
                        (JobState.UNKNOWN.value, str(job.job_id)),
                    )

            # Assert
            self.assertIs(interface.get_job_snapshot(job.job_id).state, JobState.QUEUED)

    async def test_failure_recursively_skips_queued_descendants(self):
        """Failure skips every queued descendant across mixed graph edges."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            first = _LaneA(name="first")
            second = _LaneA(name="second")
            third = _LaneA(name="third")
            graph = JobGraph(jobs=[first, second, third])
            graph.depends_on(second, first)
            graph.depends_on(third, second)
            interface.submit(graph)
            self._claim_and_start(interface, first.job_id)

            # Act
            interface.fail_job(
                first.job_id,
                JobError("ValueError", "SQL syntax near secret_table", "trace"),
                "The source asset could not be prepared.",
            )

            # Assert
            first_snapshot = interface.get_job_snapshot(first.job_id)
            second_snapshot = interface.get_job_snapshot(second.job_id)
            third_snapshot = interface.get_job_snapshot(third.job_id)
            self.assertIs(first_snapshot.state, JobState.FAILED)
            self.assertEqual(first_snapshot.error.message, "SQL syntax near secret_table")
            self.assertEqual(first_snapshot.state_reason, "The source asset could not be prepared.")
            self.assertIs(second_snapshot.state, JobState.SKIPPED)
            self.assertIs(third_snapshot.state, JobState.SKIPPED)
            self.assertEqual(
                second_snapshot.state_reason,
                'Prerequisite "first" failed: The source asset could not be prepared.',
            )
            self.assertEqual(
                third_snapshot.state_reason,
                f'Prerequisite "second" was skipped: {second_snapshot.state_reason}',
            )
            self.assertNotIn(str(first.job_id), second_snapshot.state_reason)
            self.assertNotIn(str(second.job_id), third_snapshot.state_reason)
            self.assertIsNotNone(first_snapshot.completed_at)
            self.assertIsNotNone(second_snapshot.completed_at)
            self.assertIsNotNone(third_snapshot.completed_at)
            self.assertIs(second_snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
            self.assertIs(third_snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)

    async def test_domain_execution_failure_retains_diagnostic_and_surfaces_friendly_reason(self):
        """Explicit product failure text is separate from the retained underlying diagnostic."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _FailureJob(friendly=True)
            interface.submit(job)
            interface.claim_runnable_jobs()
            executor = JobExecutor(interface)

            # Act
            await executor.execute(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(snapshot.error.message, "HTTP 500 from http://internal/service")
            self.assertEqual(snapshot.state_reason, "The generation service could not complete this job.")
            self.assertNotIn("HTTP", snapshot.state_reason)

    async def test_unexpected_execution_failure_uses_safe_generic_reason(self):
        """Unexpected diagnostics never become user-facing failure text."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _FailureJob(friendly=False)
            interface.submit(job)
            interface.claim_runnable_jobs()
            executor = JobExecutor(interface)

            # Act
            await executor.execute(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(snapshot.error.message, "HTTP 500 from http://internal/service")
            self.assertEqual(snapshot.state_reason, "The job could not be completed.")

    async def test_executor_writes_per_job_lifecycle_log(self):
        """Successful execution creates the stdout log consumed by Job Details."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _DetailJob()
            graph = JobGraph(jobs=[job])
            graph.bind(job, INPUT, 7)
            interface.submit(graph)
            interface.claim_runnable_jobs()
            executor = JobExecutor(interface)
            stdout_path = interface.get_job_directory(job.job_id) / "logs" / "stdout.log"

            # Act
            await executor.execute(job.job_id)

            # Assert
            log = stdout_path.read_text(encoding="utf-8")
            self.assertIn(f"Starting {job.name}", log)
            self.assertIn("Completed successfully", log)

    async def test_executor_writes_per_job_failure_log(self):
        """Failed execution creates the stderr log consumed by Job Details."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _FailureJob(friendly=True)
            interface.submit(job)
            interface.claim_runnable_jobs()
            executor = JobExecutor(interface)
            stderr_path = interface.get_job_directory(job.job_id) / "logs" / "stderr.log"

            # Act
            await executor.execute(job.job_id)

            # Assert
            log = stderr_path.read_text(encoding="utf-8")
            self.assertIn("The generation service could not complete this job.", log)
            self.assertIn("HTTP 500 from http://internal/service", log)

    async def test_shutdown_rejects_new_manual_submission(self):
        """A retained interface cannot enqueue new work after extension shutdown begins."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            interface.shutdown()

            # Act
            with self.assertRaisesRegex(RuntimeError, "no longer accepts submissions"):
                interface.submit(_LaneA())

            # Assert
            self.assertEqual(list(interface.iter_snapshot()), [])

    async def test_job_change_event_allows_self_unsubscribe_during_dispatch(self):
        """Committed notifications iterate a copy so a callback may unsubscribe itself safely."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            calls = []
            subscription = None

            def on_changed(job_id: uuid.UUID) -> None:
                """Record one change and release this callback subscription."""
                nonlocal subscription
                calls.append(job_id)
                subscription = None

            subscription = interface.subscribe_job_changed(on_changed)

            # Act
            self._claim_and_start(interface, job.job_id)

            # Assert
            self.assertEqual(calls, [job.job_id])

    async def test_submitted_skipped_root_recursively_skips_descendants(self):
        """An explicit terminal root propagates through committed graph edges at submission."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            root = _LaneA(name="root", skip_reason="Input was intentionally omitted")
            child = _LaneA(name="child")
            graph = JobGraph(jobs=[root, child])
            graph.depends_on(child, root)

            # Act
            interface.submit(graph)

            # Assert
            child_snapshot = interface.get_job_snapshot(child.job_id)
            root_snapshot = interface.get_job_snapshot(root.job_id)
            self.assertIs(child_snapshot.state, JobState.SKIPPED)
            self.assertEqual(
                child_snapshot.state_reason,
                'Prerequisite "root" was skipped: Input was intentionally omitted',
            )
            self.assertNotIn(str(root.job_id), child_snapshot.state_reason)
            self.assertIsNotNone(root_snapshot.completed_at)
            self.assertIsNotNone(child_snapshot.completed_at)
            self.assertIs(child_snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)

    async def test_sqlite_restricts_direct_deletion_of_connected_child(self):
        """Graph edge foreign keys prevent bypassing child ownership with direct SQL."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            source = _LaneA()
            target = _LaneA()
            graph = JobGraph(jobs=[source, target])
            graph.depends_on(target, source)
            interface.submit(graph)

            # Act
            with self.assertRaises(sqlite3.IntegrityError):
                with interface.connection() as connection:
                    connection.execute("DELETE FROM jobs WHERE job_id = ?", (str(source.job_id),))

            # Assert
            self.assertEqual(len(list(interface.iter_snapshot())), 2)

    async def test_sqlite_restricts_direct_deletion_of_isolated_child(self):
        """A database trigger protects graph ownership even when the child has no edges."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)

            # Act
            with self.assertRaises(sqlite3.IntegrityError):
                with interface.connection() as connection:
                    connection.execute("DELETE FROM jobs WHERE job_id = ?", (str(job.job_id),))

            # Assert
            self.assertEqual(len(list(interface.iter_snapshot())), 1)

    async def test_job_output_load_rejects_wrong_exact_port_name_set(self):
        """Persisted output names must exactly match declared output metadata at every read."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA(value=2)
            interface.submit(job)
            self._claim_and_start(interface, job.job_id)
            interface.complete_job(job.job_id, JobOutputs({RESULT: 2}))
            with interface.connection() as connection:
                connection.execute(
                    "UPDATE jobs SET outputs = ? WHERE job_id = ?",
                    (serialize({"unexpected": 2}), str(job.job_id)),
                )
                connection.commit()

            # Act
            with self.assertRaisesRegex(ValueError, "names do not exactly match"):
                interface.get_job_outputs(job.job_id)

            # Assert
            self.assertIs(interface.get_job_snapshot(job.job_id).state, JobState.DONE)

    async def test_delete_idle_graph_removes_all_children(self):
        """Whole graph deletion removes all idle children atomically."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            queue_job = interface.submit(_LaneA())[0]

            # Act
            interface.delete_graphs((queue_job.graph_id,))

            # Assert
            self.assertEqual(list(interface.iter_snapshot()), [])

    async def test_delete_multiple_idle_graphs_removes_every_graph_and_directory_atomically(self):
        """One batch deletion removes every selected graph and its queue-owned directories."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            first = interface.submit(_LaneA())[0]
            second = interface.submit(_LaneB())[0]
            directories = tuple(interface.get_job_directory(job.job_id) for job in (first, second))
            for directory in directories:
                directory.mkdir(parents=True)
                (directory / "result.txt").write_text("result", encoding="utf-8")

            # Act
            retained_cleanup_paths = interface.delete_graphs((first.graph_id, second.graph_id))

            # Assert
            self.assertEqual(retained_cleanup_paths, ())
            self.assertEqual(list(interface.iter_snapshot()), [])
            self.assertTrue(all(not directory.exists() for directory in directories))

    async def test_delete_middle_graphs_compacts_positions_and_preserves_unselected_directories(self):
        """Deleting adjacent middle graphs safely compacts the remaining durable positions."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            jobs = tuple(interface.submit(_LaneA())[0] for _index in range(4))
            directories = tuple(interface.get_job_directory(job.job_id) for job in jobs)
            for index, directory in enumerate(directories):
                directory.mkdir(parents=True)
                (directory / f"result-{index}.txt").write_text(str(index), encoding="utf-8")

            # Act
            retained_cleanup_paths = interface.delete_graphs((jobs[1].graph_id, jobs[2].graph_id))

            # Assert
            snapshots = interface.get_graph_snapshots()
            self.assertEqual(retained_cleanup_paths, ())
            self.assertEqual([snapshot.graph_id for snapshot in snapshots], [jobs[0].graph_id, jobs[3].graph_id])
            self.assertEqual([snapshot.position for snapshot in snapshots], [0, 1])
            self.assertTrue(directories[0].exists())
            self.assertFalse(directories[1].exists())
            self.assertFalse(directories[2].exists())
            self.assertTrue(directories[3].exists())

    async def test_delete_multiple_graphs_keeps_every_graph_when_one_has_active_work(self):
        """Batch validation prevents partial deletion when any selected graph is active."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            first = interface.submit(_LaneA())[0]
            second = interface.submit(_LaneB())[0]
            directories = tuple(interface.get_job_directory(job.job_id) for job in (first, second))
            for directory in directories:
                directory.mkdir(parents=True)
            self.assertEqual(set(interface.claim_runnable_jobs()), {first.job_id, second.job_id})

            # Act
            with self.assertRaisesRegex(RuntimeError, "active work"):
                interface.delete_graphs((first.graph_id, second.graph_id))

            # Assert
            self.assertEqual(len(list(interface.iter_snapshot())), 2)
            self.assertTrue(all(directory.exists() for directory in directories))

    async def test_delete_graph_removes_all_queue_owned_directories(self):
        """Core graph deletion owns recursive artifact cleanup for every child."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            first = _LaneA()
            second = _LaneB()
            graph = JobGraph(jobs=[first, second])
            interface.submit(graph)
            first_directory = interface.get_job_directory(first.job_id)
            second_directory = interface.get_job_directory(second.job_id)
            first_directory.mkdir(parents=True)
            second_directory.mkdir(parents=True)
            (first_directory / "result.txt").write_text("first", encoding="utf-8")
            nested_directory = second_directory / "nested"
            nested_directory.mkdir()
            (nested_directory / "result.txt").write_text("second", encoding="utf-8")

            # Act
            retained_cleanup_paths = interface.delete_graphs((graph.graph_id,))

            # Assert
            self.assertEqual(retained_cleanup_paths, ())
            self.assertFalse(first_directory.exists())
            self.assertFalse(second_directory.exists())
            self.assertEqual(list(interface.iter_snapshot()), [])

    async def test_graph_artifact_file_count_includes_nested_child_files(self):
        """Core inventory counts every regular file owned by graph children."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            queue_job = interface.submit(job)[0]
            nested_directory = interface.get_job_directory(job.job_id) / "nested"
            nested_directory.mkdir(parents=True)
            (nested_directory / "first.txt").write_text("first", encoding="utf-8")
            (nested_directory / "second.txt").write_text("second", encoding="utf-8")

            # Act
            file_count = interface.get_graphs_artifact_file_count((queue_job.graph_id,))

            # Assert
            self.assertEqual(file_count, 2)

    async def test_delete_graph_database_failure_restores_staged_directories(self):
        """A failed database commit restores every directory before returning."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            queue_job = interface.submit(job)[0]
            job_directory = interface.get_job_directory(job.job_id)
            job_directory.mkdir(parents=True)
            artifact = job_directory / "result.txt"
            artifact.write_text("result", encoding="utf-8")
            with interface.connection() as connection:
                connection.execute(
                    """
                    CREATE TRIGGER reject_test_graph_delete BEFORE DELETE ON job_graphs
                    BEGIN SELECT RAISE(ABORT, 'test rejection'); END
                    """
                )
                connection.commit()

            # Act
            with self.assertRaises(sqlite3.IntegrityError):
                interface.delete_graphs((queue_job.graph_id,))

            # Assert
            self.assertTrue(artifact.exists())
            self.assertEqual(len(list(interface.iter_snapshot())), 1)
            staging_directory = pathlib.Path(db_path).parent / "jobs" / ".trash" / str(queue_job.graph_id)
            self.assertFalse(staging_directory.exists())

    async def test_startup_restores_staged_directories_for_existing_graph(self):
        """Startup restores precommit staging when the graph still exists."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            queue_job = interface.submit(job)[0]
            job_directory = interface.get_job_directory(job.job_id)
            job_directory.mkdir(parents=True)
            artifact = job_directory / "result.txt"
            artifact.write_text("result", encoding="utf-8")
            staging_directory = pathlib.Path(db_path).parent / "jobs" / ".trash" / str(queue_job.graph_id)
            staging_directory.mkdir(parents=True)
            job_directory.replace(staging_directory / job_directory.name)

            # Act
            QueueInterface(db_path)

            # Assert
            self.assertTrue(artifact.exists())
            self.assertFalse(staging_directory.exists())

    async def test_startup_deletes_staged_directories_for_deleted_graph(self):
        """Startup completes cleanup when the graph commit already succeeded."""
        # Arrange
        async with temp_db_path() as db_path:
            QueueInterface(db_path)
            missing_graph_id = uuid.uuid4()
            staging_directory = pathlib.Path(db_path).parent / "jobs" / ".trash" / str(missing_graph_id)
            staged_job_directory = staging_directory / str(uuid.uuid4())
            staged_job_directory.mkdir(parents=True)
            (staged_job_directory / "result.txt").write_text("result", encoding="utf-8")

            # Act
            QueueInterface(db_path)

            # Assert
            self.assertFalse(staging_directory.exists())

    async def test_delete_graph_wakes_active_output_waiter(self):
        """Deleting a graph wakes its output waiter with the missing-job error."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = _SubscriptionProbeQueue(db_path)
            queue_job = interface.submit(_LaneA())[0]
            waiter = asyncio.create_task(queue_job.outputs())
            await asyncio.wait_for(interface.subscribed.wait(), 2)

            # Act
            interface.delete_graphs((queue_job.graph_id,))

            # Assert
            with self.assertRaisesRegex(KeyError, "Unknown job"):
                await asyncio.wait_for(waiter, 2)


class TestScheduler(omni.kit.test.AsyncTestCase):
    """Validate event-driven exact concrete job-type scheduling."""

    async def setUp(self):
        """Reset shared lane probes before each scheduler test."""
        persistence.get_registry().register_codecs(_LANE_CODECS)
        _LaneJob.release = asyncio.Event()
        _LaneJob.started = {}
        _LaneJob.active = {}
        _LaneJob.peak = {}
        _BlockingReadinessJob.readiness_entered = threading.Event()
        _BlockingReadinessJob.release_readiness = threading.Event()
        self.scheduler: JobScheduler | None = None

    async def tearDown(self):
        """Stop owned scheduler work and unregister exact test codecs."""
        _LaneJob.release.set()
        _BlockingReadinessJob.release_readiness.set()
        if self.scheduler is not None:
            await self.scheduler.stop()
        persistence.get_registry().unregister_codecs(_LANE_CODECS)

    @staticmethod
    async def _run_concurrency_scenario(
        scheduler: JobScheduler,
        first_a: _LaneA,
        second_a: _LaneA,
        first_b: _LaneB,
    ) -> tuple[bool, int, int]:
        """Run exact-type lanes to completion and capture overlap evidence."""
        scheduler.start()
        await asyncio.wait_for(_LaneJob.started[first_a.job_id].wait(), 2)
        await asyncio.wait_for(_LaneJob.started[first_b.job_id].wait(), 2)
        second_started_early = _LaneJob.started[second_a.job_id].is_set()
        peak_a = _LaneJob.peak[_LaneA]
        peak_b = _LaneJob.peak[_LaneB]
        _LaneJob.release.set()
        await asyncio.wait_for(_LaneJob.started[second_a.job_id].wait(), 2)
        await scheduler.stop()
        return second_started_early, peak_a, peak_b

    @staticmethod
    async def _stop_and_release(scheduler: JobScheduler, queued: _LaneA) -> tuple[bool, bool]:
        """Observe one stop turn before releasing the active job."""
        stop_task = asyncio.create_task(scheduler.stop())
        observation = asyncio.get_running_loop().create_future()

        def observe_and_release() -> None:
            """Capture stop state before releasing the active job."""
            observation.set_result((stop_task.done(), _LaneJob.started[queued.job_id].is_set()))
            _LaneJob.release.set()

        asyncio.get_running_loop().call_soon(observe_and_release)
        stopped_early, queued_started_early = await observation
        await asyncio.wait_for(stop_task, 2)
        return stopped_early, queued_started_early

    @staticmethod
    async def _run_registration_wake_scenario(
        scheduler: JobScheduler,
        unavailable: _LaneA,
        available: _LaneB,
        interface: QueueInterface,
    ) -> bool:
        """Prove an unavailable type does not block later work and registration wakes it."""
        registry = persistence.get_registry()
        registry.unregister_codecs([_LANE_A_CODEC])
        registry.set_changed_callback(interface.notify_schedule_conditions_changed)
        try:
            scheduler.start()
            await asyncio.wait_for(_LaneJob.started[available.job_id].wait(), 2)
            unavailable_started_early = _LaneJob.started[unavailable.job_id].is_set()
            registry.register_codecs([_LANE_A_CODEC])
            await asyncio.wait_for(_LaneJob.started[unavailable.job_id].wait(), 2)
            _LaneJob.release.set()
            await scheduler.stop()
            return unavailable_started_early
        finally:
            if registry.get_name(_LaneA) is None:
                registry.register_codecs([_LANE_A_CODEC])
            registry.set_changed_callback(get_job_queue().notify_schedule_conditions_changed)

    @staticmethod
    async def _write_while_readiness_is_blocked(
        interface: QueueInterface,
        other_job: _LaneA,
    ) -> tuple[bool, list[uuid.UUID], list[uuid.UUID]]:
        """Hold product readiness and prove an unrelated writer remains available."""
        claim_task = asyncio.create_task(asyncio.to_thread(interface.claim_runnable_jobs))
        await asyncio.wait_for(asyncio.to_thread(_BlockingReadinessJob.readiness_entered.wait), 2)
        try:
            skipped = await asyncio.wait_for(
                asyncio.to_thread(interface.skip_job, other_job.job_id, "Skipped by the independent writer"),
                1,
            )
        finally:
            _BlockingReadinessJob.release_readiness.set()
        stale_claim = await asyncio.wait_for(claim_task, 2)
        current_claim = await asyncio.to_thread(interface.claim_runnable_jobs)
        return skipped, stale_claim, current_claim

    async def test_same_type_serializes_while_different_type_overlaps(self):
        """Default concurrency one applies independently to each exact job type."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            first_a = _LaneA(value=1)
            second_a = _LaneA(value=2)
            first_b = _LaneB(value=3)
            for job in (first_a, second_a, first_b):
                _LaneJob.started[job.job_id] = asyncio.Event()
                interface.submit(job)
            scheduler = JobScheduler(interface)
            self.scheduler = scheduler

            # Act
            second_started_early, peak_a, peak_b = await self._run_concurrency_scenario(
                scheduler, first_a, second_a, first_b
            )
            self.scheduler = None

            # Assert
            self.assertFalse(second_started_early)
            self.assertEqual(peak_a, 1)
            self.assertEqual(peak_b, 1)

    async def test_stop_waits_for_active_job_and_pauses_new_dispatch(self):
        """Stopping lets active work finish without claiming another queued job."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            active = _LaneA(value=1)
            queued = _LaneA(value=2)
            for job in (active, queued):
                _LaneJob.started[job.job_id] = asyncio.Event()
                interface.submit(job)
            scheduler = JobScheduler(interface)
            self.scheduler = scheduler
            scheduler.start()
            await asyncio.wait_for(_LaneJob.started[active.job_id].wait(), 2)

            # Act
            stopped_early, queued_started_early = await self._stop_and_release(scheduler, queued)
            self.scheduler = None

            # Assert
            self.assertFalse(stopped_early)
            self.assertFalse(queued_started_early)
            self.assertFalse(_LaneJob.started[queued.job_id].is_set())
            self.assertIs(interface.get_job_snapshot(queued.job_id).state, JobState.QUEUED)

    async def test_cancelled_stop_waiter_does_not_cancel_scheduler_owner(self):
        """Cancelling one stop caller cannot strand active or queued scheduler work."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            active = _LaneA(value=1)
            queued = _LaneA(value=2)
            for job in (active, queued):
                _LaneJob.started[job.job_id] = asyncio.Event()
                interface.submit(job)
            scheduler = JobScheduler(interface)
            self.scheduler = scheduler
            scheduler.start()
            await asyncio.wait_for(_LaneJob.started[active.job_id].wait(), 2)
            stop_task = asyncio.create_task(scheduler.stop())
            await asyncio.sleep(0)

            # Act
            stop_task.cancel()
            _LaneJob.release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(stop_task, 2)
            self.scheduler = None

            # Assert
            self.assertFalse(scheduler.is_running())
            self.assertIs(interface.get_job_snapshot(active.job_id).state, JobState.DONE)
            self.assertIs(interface.get_job_snapshot(queued.job_id).state, JobState.QUEUED)

    async def test_dispatch_failure_releases_every_unassigned_claim(self):
        """A task-creation failure returns all undispatched claims to queued state."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _LaneA()
            interface.submit(job)
            scheduler = JobScheduler(interface)
            self.scheduler = scheduler
            original_create_task = asyncio.create_task
            execution_task_attempted = asyncio.Event()

            def fail_execution_task(coroutine):
                """Reject only the executor coroutine after the queue claim succeeds."""
                if coroutine.cr_code.co_name == "execute":
                    execution_task_attempted.set()
                    raise RuntimeError("task creation failed")
                return original_create_task(coroutine)

            # Act
            with (
                mock.patch("omni.flux.job_queue.core.execute.asyncio.create_task", side_effect=fail_execution_task),
                mock.patch("omni.flux.job_queue.core.execute.carb.log_error"),
            ):
                scheduler.start()
                await asyncio.wait_for(execution_task_attempted.wait(), 2)
                with self.assertRaisesRegex(RuntimeError, "task creation failed"):
                    await scheduler.stop()
            self.scheduler = None

            # Assert
            self.assertIs(interface.get_job_snapshot(job.job_id).state, JobState.QUEUED)

    async def test_start_subscription_failure_rolls_back_partial_ownership(self):
        """A failed second subscription leaves no callback or scheduler owner behind."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            scheduler = JobScheduler(interface)
            mutation_subscriber_count = len(interface._mutation_event)

            # Act
            with (
                mock.patch.object(
                    interface,
                    "subscribe_schedule_conditions_changed",
                    side_effect=RuntimeError("subscription failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "subscription failed"),
            ):
                scheduler.start()

            # Assert
            self.assertEqual(len(interface._mutation_event), mutation_subscriber_count)
            self.assertFalse(scheduler.is_running())
            self.assertIsNone(scheduler._task)
            self.assertIsNone(scheduler._loop)

    async def test_unavailable_type_does_not_block_and_registration_wakes_scheduler(self):
        """One unknown row is skipped until exact registration emits a scheduler event."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            unavailable = _LaneA(value=1)
            available = _LaneB(value=2)
            for job in (unavailable, available):
                _LaneJob.started[job.job_id] = asyncio.Event()
                interface.submit(job)
            scheduler = JobScheduler(interface)
            self.scheduler = scheduler

            # Act
            unavailable_started_early = await self._run_registration_wake_scenario(
                scheduler, unavailable, available, interface
            )
            self.scheduler = None

            # Assert
            self.assertFalse(unavailable_started_early)
            self.assertIs(interface.get_job_snapshot(unavailable.job_id).state, JobState.DONE)
            self.assertIs(interface.get_job_snapshot(available.job_id).state, JobState.DONE)

    async def test_consumer_waits_for_connected_producer_type_registration(self):
        """A completed producer remains a prerequisite while its exact codec is unavailable."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            producer = _LaneA(value=7)
            consumer = _DetailJob()
            graph = JobGraph()
            graph.add_job(producer)
            graph.add_job(consumer)
            graph.connect(producer.output(RESULT), consumer.input(INPUT))
            interface.submit(graph)
            self.assertEqual(interface.claim_runnable_jobs(), [producer.job_id])
            self.assertTrue(interface.start_job(producer.job_id))
            self.assertTrue(interface.complete_job(producer.job_id, JobOutputs({RESULT: 7})))
            registry = persistence.get_registry()
            registry.unregister_codecs([_LANE_A_CODEC])

            try:
                # Act
                claimed_without_producer_type = interface.claim_runnable_jobs()

                # Assert
                self.assertEqual(claimed_without_producer_type, [])
                self.assertIs(interface.get_job_snapshot(consumer.job_id).state, JobState.QUEUED)
            finally:
                if registry.get_name(_LaneA) is None:
                    registry.register_codecs([_LANE_A_CODEC])

    async def test_product_readiness_callback_does_not_hold_sqlite_write_lock(self):
        """A slow product callback cannot block independent queue mutations."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            blocking = _BlockingReadinessJob()
            other = _LaneA()
            interface.submit(blocking)
            interface.submit(other)

            # Act
            skipped, stale_claim, current_claim = await self._write_while_readiness_is_blocked(interface, other)

            # Assert
            self.assertTrue(skipped)
            self.assertEqual(stale_claim, [])
            self.assertEqual(current_claim, [blocking.job_id])

    async def test_payload_edit_during_readiness_invalidates_claim(self):
        """A claim cannot use readiness computed from a replaced queued payload."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _BlockingReadinessJob(value=1)
            interface.submit(job)
            claim_task = asyncio.create_task(asyncio.to_thread(interface.claim_runnable_jobs))
            await asyncio.wait_for(asyncio.to_thread(_BlockingReadinessJob.readiness_entered.wait), 2)

            # Act
            try:
                accepted = await asyncio.to_thread(interface.try_update_queued_job, dataclasses.replace(job, value=2))
            finally:
                _BlockingReadinessJob.release_readiness.set()
            stale_claim = await asyncio.wait_for(claim_task, 2)
            current_claim = await asyncio.to_thread(interface.claim_runnable_jobs)

            # Assert
            self.assertTrue(accepted)
            self.assertEqual(stale_claim, [])
            self.assertEqual(current_claim, [job.job_id])
            self.assertEqual(interface.get_job(job.job_id).value, 2)

    async def test_product_readiness_notification_invalidates_in_flight_claim(self):
        """A changed external readiness condition invalidates its stale evaluation."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _BlockingReadinessJob()
            interface.submit(job)
            claim_task = asyncio.create_task(asyncio.to_thread(interface.claim_runnable_jobs))
            await asyncio.wait_for(asyncio.to_thread(_BlockingReadinessJob.readiness_entered.wait), 2)
            external_changes = []
            external_subscription = interface.subscribe_external_conditions_changed(
                lambda: external_changes.append("external")
            )

            # Act
            interface.notify_schedule_conditions_changed()
            _BlockingReadinessJob.release_readiness.set()
            stale_claim = await asyncio.wait_for(claim_task, 2)
            current_claim = await asyncio.to_thread(interface.claim_runnable_jobs)

            # Assert
            self.assertEqual(stale_claim, [])
            self.assertEqual(current_claim, [job.job_id])
            self.assertEqual(external_changes, ["external"])
            del external_subscription

    async def test_start_during_stop_does_not_create_second_generation(self):
        """The scheduler owner task blocks restart until stop fully settles active work."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            active = _LaneA(value=1)
            queued = _LaneA(value=2)
            for job in (active, queued):
                _LaneJob.started[job.job_id] = asyncio.Event()
                interface.submit(job)
            scheduler = JobScheduler(interface)
            self.scheduler = scheduler
            scheduler.start()
            await asyncio.wait_for(_LaneJob.started[active.job_id].wait(), 2)
            owner = scheduler._task

            # Act
            stop_task = asyncio.create_task(scheduler.stop())
            await asyncio.sleep(0)
            with self.assertRaisesRegex(RuntimeError, "stopping"):
                scheduler.start()
            _LaneJob.release.set()
            await asyncio.wait_for(stop_task, 2)
            self.scheduler = None

            # Assert
            self.assertIsNotNone(owner)
            self.assertFalse(scheduler.is_running())
            self.assertIs(interface.get_job_snapshot(queued.job_id).state, JobState.QUEUED)

    async def test_run_failure_releases_scheduler_ownership(self):
        """An unexpected dispatch failure closes subscriptions and permits a later generation."""
        # Arrange
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            scheduler = JobScheduler(interface)
            self.scheduler = scheduler

            # Act
            with (
                mock.patch.object(interface, "claim_runnable_jobs", side_effect=RuntimeError("claim failed")),
                mock.patch("omni.flux.job_queue.core.execute.carb.log_error") as log_error,
            ):
                scheduler.start()
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                with self.assertRaisesRegex(RuntimeError, "claim failed"):
                    await scheduler.stop()
            scheduler.start()
            restarted = scheduler.is_running()
            await scheduler.stop()
            self.scheduler = None

            # Assert
            self.assertTrue(restarted)
            self.assertIsNone(scheduler._task)
            self.assertIsNone(scheduler._mutation_subscription)
            self.assertIsNone(scheduler._conditions_subscription)
            self.assertIsNone(scheduler._loop)
            log_error.assert_called_once_with("Job scheduler failed: claim failed")
