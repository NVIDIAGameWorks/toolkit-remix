"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import contextlib
import datetime
import os
import pathlib
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable, Container, Iterator, Sequence
from typing import Any

import carb
from omni.flux.utils.common import Event, EventSubscription

from . import persistence
from .constants import QUEUE_SCHEMA_VERSION
from .enums import (
    ApplyDisposition,
    ApplyOperation,
    JobState,
)
from .errors import JobError, QueueSubmissionError
from .job import Job, JobGraph, JobInputPort, JobInputs, JobOutputPort, JobOutputs, JobProgress
from .models import (
    QueueControlEdgeSnapshot,
    QueueDataConnectionSnapshot,
    QueueGraphSnapshot,
    QueueJob,
    QueueJobDetailsSnapshot,
    QueueJobSnapshot,
    QueueLiteralInputSnapshot,
)
from .serializer import deserialize, serialize

__all__ = ("QueueInterface",)


def _isolated_subscription(event: Event, callback: Callable[..., Any], channel: str) -> EventSubscription:
    """Subscribe one callback behind a failure-isolating notification boundary.

    Args:
        event: Process-local event channel.
        callback: Product callback invoked by the channel.
        channel: Human-readable channel name used for diagnostics.

    Returns:
        Subscription retained by the caller.
    """

    def isolated_callback(*args: Any, **kwargs: Any) -> None:
        """Log one subscriber failure without stopping committed-state dispatch."""
        try:
            callback(*args, **kwargs)
        except Exception as error:  # noqa: BLE001 - arbitrary product subscribers must remain isolated.
            carb.log_error(f"Queue {channel} subscriber failed: {error}")

    return EventSubscription(event, isolated_callback)


class QueueInterface:
    """Persist current typed job graphs with conditional atomic transitions."""

    def __init__(self, db_path: str, *, clear_incompatible_database: bool = False) -> None:
        """Open a queue stored at an explicit SQLite path.

        Args:
            db_path: Path to the SQLite queue database.
            clear_incompatible_database: Whether an incompatible database at this exact path may be deleted. This is
                intended only for an application-owned queue path.
        """
        self.db_path = db_path
        self._clear_incompatible_database = clear_incompatible_database
        self._job_changed_event = Event(copy=True)
        self._job_progress_changed_event = Event(copy=True)
        self._mutation_event = Event(copy=True)
        self._schedule_conditions_changed_event = Event(copy=True)
        self._external_conditions_changed_event = Event(copy=True)
        self._schedule_conditions_lock = threading.Lock()
        self._schedule_conditions_revision = 0
        self._accepting_submissions = True
        self._initialize()

    @contextlib.contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open one configured SQLite connection.

        Yields:
            Connection with dictionary rows and foreign keys enabled.
        """
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        """Create the fresh queue schema, replacing an incompatible database file."""
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }

        incompatible = version not in (0, QUEUE_SCHEMA_VERSION) or (version == 0 and tables)
        if incompatible and not self._clear_incompatible_database:
            raise RuntimeError(
                f"Queue database schema {version} is incompatible with schema {QUEUE_SCHEMA_VERSION}: {self.db_path}"
            )
        if incompatible:
            database_path = pathlib.Path(self.db_path)
            for path in (database_path, pathlib.Path(f"{database_path}-wal"), pathlib.Path(f"{database_path}-shm")):
                path.unlink(missing_ok=True)

        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS job_graphs (
                    graph_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL UNIQUE,
                    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    job_data TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('QUEUED', 'SCHEDULED', 'IN_PROGRESS', 'DONE', 'FAILED', 'SKIPPED')),
                    state_reason TEXT,
                    started_at DATETIME,
                    completed_at DATETIME,
                    outputs TEXT,
                    progress_completed INTEGER,
                    progress_total INTEGER,
                    progress_detail TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    error_traceback TEXT,
                    apply_disposition TEXT NOT NULL,
                    apply_operation TEXT NOT NULL,
                    apply_handler_id TEXT,
                    apply_reason TEXT,
                    apply_receipt TEXT,
                    apply_error_type TEXT,
                    apply_error_message TEXT,
                    apply_error_traceback TEXT,
                    UNIQUE(graph_id, position),
                    FOREIGN KEY(graph_id) REFERENCES job_graphs(graph_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS job_connections (
                    source_job_id TEXT NOT NULL,
                    source_port TEXT NOT NULL,
                    target_job_id TEXT NOT NULL,
                    target_port TEXT NOT NULL,
                    PRIMARY KEY(target_job_id, target_port),
                    FOREIGN KEY(source_job_id) REFERENCES jobs(job_id),
                    FOREIGN KEY(target_job_id) REFERENCES jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS job_input_values (
                    job_id TEXT NOT NULL,
                    port TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY(job_id, port),
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS job_control_edges (
                    target_job_id TEXT NOT NULL,
                    prerequisite_job_id TEXT NOT NULL,
                    PRIMARY KEY(target_job_id, prerequisite_job_id),
                    FOREIGN KEY(target_job_id) REFERENCES jobs(job_id),
                    FOREIGN KEY(prerequisite_job_id) REFERENCES jobs(job_id)
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state, graph_id, position);
                CREATE TRIGGER IF NOT EXISTS prevent_direct_job_delete
                BEFORE DELETE ON jobs
                WHEN EXISTS(SELECT 1 FROM job_graphs WHERE graph_id = OLD.graph_id)
                BEGIN
                    SELECT RAISE(ABORT, 'child jobs must be deleted through their graph');
                END;
                """
            )
            connection.execute(f"PRAGMA user_version = {QUEUE_SCHEMA_VERSION}")
            connection.commit()
        self._reconcile_staged_graph_deletions()
        self._accepting_submissions = True

    def shutdown(self) -> None:
        """Reject new manual submissions while preserving reads and active cleanup."""
        self._accepting_submissions = False

    def submit(self, job_or_graph: Job | JobGraph) -> list[QueueJob]:
        """Validate and atomically persist one job or graph.

        Args:
            job_or_graph: Job or graph to submit.

        Returns:
            Stable handles for submitted children in topological order.

        Raises:
            RuntimeError: If this interface has begun shutdown.
            QueueSubmissionError: If validation, serialization, or persistence fails.
        """
        if not self._accepting_submissions:
            raise RuntimeError("The job queue is shutting down and no longer accepts submissions")
        try:
            graph, jobs, job_types, job_payloads = self._prepare_graph_for_persistence(job_or_graph)
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                position = connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM job_graphs").fetchone()[0]
                self._insert_graph(connection, graph, jobs, job_types, job_payloads, position)
                connection.commit()
        except Exception as error:
            raise QueueSubmissionError(str(error)) from error
        self._notify_mutation()
        return [QueueJob(self, graph.graph_id, job.job_id) for job in jobs]

    def submit_graphs(self, graphs: Sequence[JobGraph]) -> list[QueueJob]:
        """Validate and persist many graphs in a single transaction, notifying subscribers once.

        Adds every graph in one atomic transaction and emits exactly one structural-change
        notification, so a subscribed widget rebuilds a single time for the whole batch instead of
        once per graph. Submission is all-or-nothing: if any graph fails validation or persistence,
        none are added.

        Args:
            graphs: Graphs to submit together, added in order after the current queue tail.

        Returns:
            Stable handles for every submitted child, graph by graph in topological order.

        Raises:
            RuntimeError: If this interface has begun shutdown.
            QueueSubmissionError: If validation, serialization, or persistence fails for any graph.
        """
        if not self._accepting_submissions:
            raise RuntimeError("The job queue is shutting down and no longer accepts submissions")
        graphs = list(graphs)
        if not graphs:
            return []
        handles: list[QueueJob] = []
        try:
            prepared = [self._prepare_graph_for_persistence(graph) for graph in graphs]
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                position = connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM job_graphs").fetchone()[0]
                for offset, (graph, jobs, job_types, job_payloads) in enumerate(prepared):
                    self._insert_graph(connection, graph, jobs, job_types, job_payloads, position + offset)
                    handles.extend(QueueJob(self, graph.graph_id, job.job_id) for job in jobs)
                connection.commit()
        except Exception as error:
            raise QueueSubmissionError(str(error)) from error
        self._notify_mutation()
        return handles

    def _prepare_graph_for_persistence(
        self, job_or_graph: Job | JobGraph
    ) -> tuple[JobGraph, list[Job], dict[uuid.UUID, str], dict[uuid.UUID, str]]:
        """Validate one job or graph and serialize its jobs before any database write.

        Args:
            job_or_graph: Job or graph to validate and serialize.

        Returns:
            The resolved graph, its jobs in topological order, and their persistence types and payloads.

        Raises:
            TypeError: If the input or a job persistence type is not a registered graph/job.
            ValueError: If the graph contains no jobs.
        """
        graph = JobGraph(name=job_or_graph.name, jobs=[job_or_graph]) if isinstance(job_or_graph, Job) else job_or_graph
        if not isinstance(graph, JobGraph):
            raise TypeError("job_or_graph must be a Job or JobGraph")
        if not graph.jobs:
            raise ValueError("JobGraph must contain at least one job")
        jobs = list(graph.iter_jobs())
        job_types: dict[uuid.UUID, str] = {}
        job_payloads: dict[uuid.UUID, str] = {}
        for job in jobs:
            job_type = persistence.get_registry().get_name(type(job))
            if job_type is None:
                raise TypeError(f"Job type {type(job).__name__} is not registered for persistence")
            concrete_job_type = type(job)
            required_types = {
                port.value_type for port in (*concrete_job_type.input_ports, *concrete_job_type.output_ports)
            }
            if job.apply_binding is not None:
                handler_type = job.apply_binding.handler_type
                handler_type_name = persistence.get_registry().get_name(handler_type)
                if handler_type_name != handler_type.name:
                    raise TypeError(f"Apply handler persistence name must match its handler name '{handler_type.name}'")
                required_types.update(
                    (
                        handler_type,
                        handler_type.input_type,
                        handler_type.target_type,
                        handler_type.receipt_type,
                    )
                )
            unavailable = sorted(
                value_type.__name__
                for value_type in required_types
                if persistence.get_registry().get_name(value_type) is None
            )
            if unavailable:
                raise TypeError(f"Job persistence types are not registered: {', '.join(unavailable)}")
            job_types[job.job_id] = job_type
            job_payloads[job.job_id] = serialize(job)
        return graph, jobs, job_types, job_payloads

    def _insert_graph(
        self,
        connection: sqlite3.Connection,
        graph: JobGraph,
        jobs: list[Job],
        job_types: dict[uuid.UUID, str],
        job_payloads: dict[uuid.UUID, str],
        position: int,
    ) -> None:
        """Insert one validated graph and its children within an open transaction.

        Args:
            connection: Open connection whose transaction already began.
            graph: Validated graph to persist.
            jobs: Graph jobs in topological order.
            job_types: Persistence type name per job identifier.
            job_payloads: Serialized payload per job identifier.
            position: Queue position assigned to this graph.
        """
        connection.execute(
            "INSERT INTO job_graphs(graph_id, name, position) VALUES (?, ?, ?)",
            (str(graph.graph_id), graph.name, position),
        )
        for child_position, job in enumerate(jobs):
            state = JobState.SKIPPED if job.skip_reason is not None else JobState.QUEUED
            disposition = (
                ApplyDisposition.NOT_APPLICABLE
                if job.apply_binding is None or state is JobState.SKIPPED
                else ApplyDisposition.NOT_READY
            )
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, graph_id, name, job_type, job_data, position, state, state_reason, completed_at,
                    apply_disposition, apply_operation, apply_handler_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                    CASE WHEN ? = 'SKIPPED' THEN CURRENT_TIMESTAMP END, ?, ?, ?)
                """,
                (
                    str(job.job_id),
                    str(graph.graph_id),
                    job.name,
                    job_types[job.job_id],
                    job_payloads[job.job_id],
                    child_position,
                    state.value,
                    job.skip_reason,
                    state.value,
                    disposition.value,
                    ApplyOperation.IDLE.value,
                    None if job.apply_binding is None else job.apply_binding.handler_type.name,
                ),
            )
        for edge in graph.connections:
            connection.execute(
                "INSERT INTO job_connections VALUES (?, ?, ?, ?)",
                (
                    str(edge.source_job_id),
                    edge.source_port.name,
                    str(edge.target_job_id),
                    edge.target_port.name,
                ),
            )
        for binding in graph.literal_inputs:
            connection.execute(
                "INSERT INTO job_input_values VALUES (?, ?, ?)",
                (str(binding.job_id), binding.port.name, serialize(binding.value)),
            )
        for dependency in graph.control_dependencies:
            connection.execute(
                "INSERT INTO job_control_edges VALUES (?, ?)",
                (str(dependency.target_job_id), str(dependency.prerequisite_job_id)),
            )
        for job in jobs:
            if job.skip_reason is not None:
                self._skip_descendants(connection, job.job_id)

    def get_job(self, job_id: uuid.UUID) -> Job:
        """Load one exact explicitly registered job.

        Args:
            job_id: Job identifier.

        Returns:
            Persisted concrete job.

        Raises:
            KeyError: If the job is absent.
            TypeError: If persisted type identity does not match its registered payload.
        """
        with self.connection() as connection:
            row = connection.execute("SELECT job_type, job_data FROM jobs WHERE job_id = ?", (str(job_id),)).fetchone()
        if row is None:
            raise KeyError(f"Unknown job {job_id}")
        job = deserialize(row["job_data"])
        registered_type = persistence.get_registry().get_type(row["job_type"])
        if registered_type is None or type(job) is not registered_type:
            raise TypeError(f"Persisted job type {row['job_type']} is unavailable or mismatched")
        return job

    def try_update_queued_job(self, updated_job: Job) -> bool:
        """Conditionally replace one queued job's persisted payload.

        Args:
            updated_job: Replacement with identical identity, type, ports, and Apply binding.

        Returns:
            Whether the job was still queued and the replacement won.

        Raises:
            TypeError: If the replacement type is unavailable or incompatible.
            ValueError: If immutable queue topology metadata changed.
        """
        updated_job.validate()
        job_type = persistence.get_registry().get_name(type(updated_job))
        if job_type is None:
            raise TypeError(f"Job type {type(updated_job).__name__} is not registered for persistence")
        with self.connection() as connection:
            row = connection.execute(
                "SELECT job_type, job_data FROM jobs WHERE job_id = ?", (str(updated_job.job_id),)
            ).fetchone()
        if row is None:
            return False
        current_job = deserialize(row["job_data"])
        if row["job_type"] != job_type or type(current_job) is not type(updated_job):
            raise TypeError("Updated job must preserve its exact persisted type")
        if updated_job.skip_reason is not None:
            raise ValueError("A queued job replacement cannot add a skip reason")
        if (
            type(current_job).input_ports != type(updated_job).input_ports
            or type(current_job).output_ports != type(updated_job).output_ports
            or current_job.apply_binding != updated_job.apply_binding
        ):
            raise ValueError("Updated job must preserve ports and Apply binding")
        payload = serialize(updated_job)
        with self.connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET name = ?, job_data = ? WHERE job_id = ? AND state = ? AND job_type = ?",
                (updated_job.name, payload, str(updated_job.job_id), JobState.QUEUED.value, job_type),
            )
            connection.commit()
        if cursor.rowcount:
            self._notify_job_changed(updated_job.job_id)
            self._notify_mutation()
            return True
        return False

    def get_job_outputs(self, job_id: uuid.UUID) -> JobOutputs:
        """Load exact typed outputs for one completed job.

        Args:
            job_id: Completed job identifier.

        Returns:
            Immutable typed outputs.

        Raises:
            KeyError: If the job or outputs are unavailable.
        """
        with self.connection() as connection:
            row = connection.execute("SELECT job_type, outputs FROM jobs WHERE job_id = ?", (str(job_id),)).fetchone()
        if row is None or row["outputs"] is None:
            raise KeyError(f"Job {job_id} has no outputs")
        _input_ports, output_ports = _job_ports(row["job_type"])
        return _decode_outputs(row["outputs"], output_ports)

    def resolve_job_inputs(self, job_id: uuid.UUID) -> JobInputs:
        """Resolve one job's literal and completed producer inputs.

        Args:
            job_id: Consumer job identifier.

        Returns:
            Immutable exact typed inputs.

        Raises:
            KeyError: If an input or producer output is unavailable.
        """
        with self.connection() as connection:
            job_row = connection.execute("SELECT job_type FROM jobs WHERE job_id = ?", (str(job_id),)).fetchone()
            if job_row is None:
                raise KeyError(f"Unknown job {job_id}")
            input_ports, _output_ports = _job_ports(job_row["job_type"])
            inputs = self._resolve_available_inputs(connection, job_id, input_ports)
        missing = [port.name for port in input_ports if port not in inputs]
        if missing:
            raise KeyError(f"Missing input bindings for job {job_id}: {', '.join(missing)}")
        return inputs

    def _resolve_available_inputs(
        self,
        connection: sqlite3.Connection,
        job_id: uuid.UUID,
        input_ports: tuple[JobInputPort[Any], ...],
    ) -> JobInputs:
        """Reconstruct currently available literal and connected inputs.

        Args:
            connection: Read transaction shared by the caller's operation.
            job_id: Target job identifier.
            input_ports: Exact declared ports used to reconstruct typed keys.

        Returns:
            Available literal and completed-producer values. Callers decide whether
            missing values are valid for their operation.
        """
        ports_by_name = {port.name: port for port in input_ports}
        values: dict[JobInputPort[Any], Any] = {}
        literal_rows = connection.execute(
            "SELECT port, value FROM job_input_values WHERE job_id = ?", (str(job_id),)
        ).fetchall()
        connection_rows = connection.execute(
            """
            SELECT edge.source_job_id, edge.source_port, edge.target_port,
                source.job_type AS source_job_type, source.outputs
            FROM job_connections AS edge
            JOIN jobs AS source ON source.job_id = edge.source_job_id
            WHERE edge.target_job_id = ?
            """,
            (str(job_id),),
        ).fetchall()
        for row in literal_rows:
            values[ports_by_name[row["port"]]] = deserialize(row["value"])
        outputs_by_job: dict[str, JobOutputs] = {}
        for row in connection_rows:
            source_job_id = row["source_job_id"]
            if row["outputs"] is None:
                continue
            if source_job_id not in outputs_by_job:
                _source_inputs, source_outputs = _job_ports(row["source_job_type"])
                outputs_by_job[source_job_id] = _decode_outputs(row["outputs"], source_outputs)
            source_outputs = outputs_by_job[source_job_id]
            source_port = next((port for port in source_outputs if port.name == row["source_port"]), None)
            if source_port is None:
                continue
            values[ports_by_name[row["target_port"]]] = source_outputs[source_port]
        return JobInputs(values)

    def get_job_snapshot(self, job_id: uuid.UUID) -> QueueJobSnapshot:
        """Return one immutable current child snapshot.

        Args:
            job_id: Job identifier.

        Returns:
            Current job snapshot.

        Raises:
            KeyError: If the job is absent.
        """
        snapshots = self._iter_snapshots("WHERE jobs.job_id = ?", (str(job_id),))
        try:
            snapshot = next(snapshots, None)
        finally:
            snapshots.close()
        if snapshot is None:
            raise KeyError(f"Unknown job {job_id}")
        return snapshot

    def iter_snapshot(self) -> Iterator[QueueJobSnapshot]:
        """Iterate current child snapshots in graph and child position order.

        Yields:
            Current normalized job snapshots without loading payload or output blobs.
        """
        yield from self._iter_snapshots()

    def get_job_details(self, job_id: uuid.UUID, include_values: bool = False) -> QueueJobDetailsSnapshot:
        """Return targeted typed topology and optionally persisted values for one job.

        This query never reads the serialized job payload. Values are decoded only when
        ``include_values`` is true.

        Args:
            job_id: Selected job identifier.
            include_values: Whether to decode available inputs and outputs.

        Returns:
            Read-only targeted details.

        Raises:
            KeyError: If the selected job is absent.
            TypeError: If ``include_values`` is not a bool.
        """
        if type(include_values) is not bool:
            raise TypeError("include_values must be a bool")
        with self.connection() as connection:
            connection.execute("BEGIN")
            snapshots = self._iter_snapshots("WHERE jobs.job_id = ?", (str(job_id),), connection)
            try:
                snapshot = next(snapshots, None)
            finally:
                snapshots.close()
            if snapshot is None:
                raise KeyError(f"Unknown job {job_id}")
            selected_columns = "job_type, outputs" if include_values else "job_type"
            row = connection.execute(f"SELECT {selected_columns} FROM jobs WHERE job_id = ?", (str(job_id),)).fetchone()
            if row is None:
                raise KeyError(f"Unknown job {job_id}")
            input_ports, output_ports = _job_ports(row["job_type"])
            connection_rows = connection.execute(
                """
                SELECT edge.source_job_id, edge.source_port, edge.target_job_id, edge.target_port,
                    source.job_type AS source_job_type, target.job_type AS target_job_type
                FROM job_connections edge
                JOIN jobs source ON source.job_id = edge.source_job_id
                JOIN jobs target ON target.job_id = edge.target_job_id
                WHERE edge.source_job_id = ? OR edge.target_job_id = ?
                ORDER BY edge.source_job_id, edge.source_port, edge.target_job_id, edge.target_port
                """,
                (str(job_id), str(job_id)),
            ).fetchall()
            connections = tuple(
                QueueDataConnectionSnapshot(
                    source_job_id=uuid.UUID(edge["source_job_id"]),
                    source_port=_port_by_name(_job_ports(edge["source_job_type"])[1], edge["source_port"]),
                    target_job_id=uuid.UUID(edge["target_job_id"]),
                    target_port=_port_by_name(_job_ports(edge["target_job_type"])[0], edge["target_port"]),
                )
                for edge in connection_rows
            )
            literal_rows = connection.execute(
                "SELECT port, value FROM job_input_values WHERE job_id = ? ORDER BY port", (str(job_id),)
            ).fetchall()
            literal_inputs = tuple(
                QueueLiteralInputSnapshot(
                    job_id=job_id,
                    port=_port_by_name(input_ports, literal["port"]),
                    value=deserialize(literal["value"]) if include_values else None,
                )
                for literal in literal_rows
            )
            control_edges = tuple(
                QueueControlEdgeSnapshot(
                    target_job_id=uuid.UUID(edge["target_job_id"]),
                    prerequisite_job_id=uuid.UUID(edge["prerequisite_job_id"]),
                )
                for edge in connection.execute(
                    """
                    SELECT target_job_id, prerequisite_job_id FROM job_control_edges
                    WHERE target_job_id = ? OR prerequisite_job_id = ?
                    ORDER BY prerequisite_job_id, target_job_id
                    """,
                    (str(job_id), str(job_id)),
                )
            )
            inputs = self._resolve_available_inputs(connection, job_id, input_ports) if include_values else None
            outputs = (
                _decode_outputs(row["outputs"], output_ports) if include_values and row["outputs"] is not None else None
            )
        return QueueJobDetailsSnapshot(
            job=snapshot,
            input_ports=input_ports,
            output_ports=output_ports,
            connections=connections,
            literal_inputs=literal_inputs,
            control_edges=control_edges,
            inputs=inputs,
            outputs=outputs,
        )

    def get_graph_snapshots(self) -> list[QueueGraphSnapshot]:
        """Return ordered graph roots with ordered child snapshots.

        Returns:
            Current graph hierarchy.
        """
        with self.connection() as connection:
            connection.execute("BEGIN")
            jobs_by_graph: dict[uuid.UUID, list[QueueJobSnapshot]] = {}
            for snapshot in self._iter_snapshots(connection=connection):
                jobs_by_graph.setdefault(snapshot.graph_id, []).append(snapshot)
            rows = connection.execute(
                "SELECT graph_id, name, position, submitted_at FROM job_graphs ORDER BY position"
            ).fetchall()
        return [
            QueueGraphSnapshot(
                graph_id=uuid.UUID(row["graph_id"]),
                name=row["name"],
                position=row["position"],
                submitted_at=_parse_datetime(row["submitted_at"]),
                jobs=tuple(jobs_by_graph.get(uuid.UUID(row["graph_id"]), ())),
            )
            for row in rows
        ]

    def _transition_job(
        self,
        job_id: uuid.UUID,
        expected_state: JobState | Container[JobState],
        new_state: JobState,
        reason: str | None = None,
    ) -> bool:
        """Conditionally perform one runtime-owned state transition.

        Args:
            job_id: Job identifier.
            expected_state: Required current state or states.
            new_state: State to persist.
            reason: Optional transition detail.

        Returns:
            Whether this caller won the conditional transition.

        Raises:
            TypeError: If ``new_state`` is not a JobState.
            ValueError: If ``new_state`` is a derived state.
        """
        expected = _states(expected_state)
        if not isinstance(new_state, JobState):
            raise TypeError("new_state must be a JobState")
        if not new_state.is_persisted:
            raise ValueError("new_state must be a persisted JobState")
        placeholders = ", ".join("?" for _ in expected)
        with self.connection() as connection:
            cursor = connection.execute(
                f"""
                UPDATE jobs
                SET state = ?, state_reason = ?
                WHERE job_id = ? AND state IN ({placeholders})
                """,
                (new_state.value, reason, str(job_id), *(state.value for state in expected)),
            )
            connection.commit()
        if cursor.rowcount:
            self._notify_execution_changed(job_id)
            return True
        return False

    def start_job(self, job_id: uuid.UUID) -> bool:
        """Conditionally start one scheduled job.

        Args:
            job_id: Scheduled job identifier.

        Returns:
            Whether the job entered progress.
        """
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET state = ?, state_reason = NULL, started_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND state = ?
                """,
                (JobState.IN_PROGRESS.value, str(job_id), JobState.SCHEDULED.value),
            )
            connection.commit()
        if cursor.rowcount:
            self._notify_execution_changed(job_id)
            return True
        return False

    def update_progress(self, job_id: uuid.UUID, progress: JobProgress) -> bool:
        """Persist progress only while a job is scheduled or running.

        Args:
            job_id: Active job identifier.
            progress: Structured progress value.

        Returns:
            Whether progress was accepted.

        Raises:
            TypeError: If progress is not a JobProgress value.
        """
        if not isinstance(progress, JobProgress):
            raise TypeError("progress must be a JobProgress")
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET progress_completed = ?, progress_total = ?, progress_detail = ?
                WHERE job_id = ? AND state IN (?, ?)
                """,
                (
                    progress.completed,
                    progress.total,
                    progress.detail,
                    str(job_id),
                    JobState.SCHEDULED.value,
                    JobState.IN_PROGRESS.value,
                ),
            )
            connection.commit()
        if cursor.rowcount:
            self._job_progress_changed_event(job_id, progress)
            return True
        return False

    def complete_job(self, job_id: uuid.UUID, outputs: JobOutputs) -> bool:
        """Conditionally persist exact outputs and complete one running job.

        Args:
            job_id: Running job identifier.
            outputs: Exact typed output mapping.

        Returns:
            Whether the job completed.

        Raises:
            TypeError: If outputs are not the concrete container or do not match declared ports.
        """
        if not isinstance(outputs, JobOutputs):
            raise TypeError("outputs must be JobOutputs")
        job = self.get_job(job_id)
        if set(outputs) != set(type(job).output_ports):
            raise TypeError("Job outputs must exactly match all declared output ports")
        payload = serialize({port.name: outputs[port] for port in outputs})
        disposition = ApplyDisposition.NOT_APPLICABLE if job.apply_binding is None else ApplyDisposition.PENDING
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE jobs
                SET state = ?, state_reason = NULL, outputs = ?,
                    progress_completed = progress_total, completed_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND state = ?
                """,
                (JobState.DONE.value, payload, str(job_id), JobState.IN_PROGRESS.value),
            )
            if cursor.rowcount:
                connection.execute(
                    "UPDATE jobs SET apply_disposition = ?, apply_operation = ? WHERE job_id = ?",
                    (disposition.value, ApplyOperation.IDLE.value, str(job_id)),
                )
            connection.commit()
        if cursor.rowcount:
            self._notify_execution_changed(job_id)
            return True
        return False

    def fail_job(self, job_id: uuid.UUID, error: JobError, reason: str) -> bool:
        """Fail one active job and recursively skip queued descendants.

        Args:
            job_id: Active job identifier.
            error: Durable failure details.
            reason: Safe user-facing failure text propagated to descendants.

        Returns:
            Whether the active job entered failure.

        Raises:
            TypeError: If error is not a JobError.
            ValueError: If reason is not a non-empty string.
        """
        if not isinstance(error, JobError):
            raise TypeError("error must be a JobError")
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE jobs SET state = ?, state_reason = ?,
                    error_type = ?, error_message = ?, error_traceback = ?,
                    apply_disposition = ?, apply_operation = ?, completed_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND state IN (?, ?)
                """,
                (
                    JobState.FAILED.value,
                    reason,
                    error.exception_type,
                    error.message,
                    error.traceback,
                    ApplyDisposition.NOT_APPLICABLE.value,
                    ApplyOperation.IDLE.value,
                    str(job_id),
                    JobState.SCHEDULED.value,
                    JobState.IN_PROGRESS.value,
                ),
            )
            skipped = self._skip_descendants(connection, job_id) if cursor.rowcount else []
            connection.commit()
        if cursor.rowcount:
            self._notify_execution_changed(job_id)
            for skipped_id in skipped:
                self._notify_execution_changed(skipped_id)
            return True
        return False

    def skip_job(self, job_id: uuid.UUID, reason: str) -> bool:
        """Skip one queued job and recursively skip queued descendants.

        Args:
            job_id: Queued job identifier.
            reason: Durable skip detail.

        Returns:
            Whether the job entered skipped state.

        Raises:
            ValueError: If reason is not a non-empty string.
        """
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE jobs SET state = ?, state_reason = ?, apply_disposition = ?, apply_operation = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND state = ?
                """,
                (
                    JobState.SKIPPED.value,
                    reason,
                    ApplyDisposition.NOT_APPLICABLE.value,
                    ApplyOperation.IDLE.value,
                    str(job_id),
                    JobState.QUEUED.value,
                ),
            )
            skipped = self._skip_descendants(connection, job_id) if cursor.rowcount else []
            connection.commit()
        if cursor.rowcount:
            self._notify_execution_changed(job_id)
            for skipped_id in skipped:
                self._notify_execution_changed(skipped_id)
            return True
        return False

    def claim_runnable_jobs(self) -> list[uuid.UUID]:
        """Atomically claim every runnable job allowed by exact type concurrency.

        Returns:
            Newly scheduled job identifiers in graph and child order.
        """
        with self._schedule_conditions_lock:
            readiness_revision = self._schedule_conditions_revision
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT jobs.job_id, jobs.job_type, jobs.job_data
                FROM jobs JOIN job_graphs ON job_graphs.graph_id = jobs.graph_id
                WHERE jobs.state = ?
                    AND NOT EXISTS (
                        SELECT 1 FROM (
                            SELECT source_job_id AS predecessor
                            FROM job_connections WHERE target_job_id = jobs.job_id
                            UNION
                            SELECT prerequisite_job_id
                            FROM job_control_edges WHERE target_job_id = jobs.job_id
                        ) edges
                        JOIN jobs AS predecessor_jobs ON predecessor_jobs.job_id = edges.predecessor
                        WHERE predecessor_jobs.state != ?
                    )
                ORDER BY job_graphs.position, jobs.position
                """,
                (JobState.QUEUED.value, JobState.DONE.value),
            ).fetchall()
            source_type_rows = connection.execute(
                """
                SELECT DISTINCT edges.target_job_id, sources.job_type
                FROM job_connections AS edges
                JOIN jobs AS sources ON sources.job_id = edges.source_job_id
                JOIN jobs AS targets ON targets.job_id = edges.target_job_id
                WHERE targets.state = ?
                """,
                (JobState.QUEUED.value,),
            ).fetchall()
        source_types_by_target: dict[str, set[str]] = {}
        for source_row in source_type_rows:
            source_types_by_target.setdefault(source_row["target_job_id"], set()).add(source_row["job_type"])
        ready = []
        failed_job_ids: list[uuid.UUID] = []
        for row in rows:
            job_id = uuid.UUID(row["job_id"])
            registered_type = _registered_job_type(row["job_type"])
            if registered_type is None or any(
                _registered_job_type(source_type) is None
                for source_type in source_types_by_target.get(row["job_id"], ())
            ):
                continue
            try:
                job = deserialize(row["job_data"])
                if type(job) is not registered_type:
                    raise TypeError(f"Persisted job type {row['job_type']} does not match its payload")
            except Exception as error:  # noqa: BLE001 - registered codecs are an extension boundary.
                failed_job_ids.extend(
                    self._fail_queued_job(
                        job_id,
                        row["job_data"],
                        JobError.from_exception(error),
                        "The saved job data is invalid and could not be loaded.",
                        notify=False,
                    )
                )
                continue
            try:
                block_reason = job.get_schedule_block_reason()
            except Exception as error:  # noqa: BLE001 - isolate arbitrary product readiness hooks.
                failed_job_ids.extend(
                    self._fail_queued_job(
                        job_id,
                        row["job_data"],
                        JobError.from_exception(error),
                        "The job could not be scheduled.",
                        notify=False,
                    )
                )
                continue
            if block_reason is None:
                ready.append((job_id, row["job_type"], row["job_data"], type(job).max_concurrency))

        claimed = []
        stale_readiness = False
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            with self._schedule_conditions_lock:
                if readiness_revision != self._schedule_conditions_revision:
                    connection.rollback()
                    stale_readiness = True
                else:
                    active_counts = {
                        row["job_type"]: row["count"]
                        for row in connection.execute(
                            """
                            SELECT job_type, COUNT(*) AS count FROM jobs
                            WHERE state IN (?, ?) GROUP BY job_type
                            """,
                            (JobState.SCHEDULED.value, JobState.IN_PROGRESS.value),
                        )
                    }
                    for job_id, job_type, job_data, max_concurrency in ready:
                        if active_counts.get(job_type, 0) >= max_concurrency:
                            continue
                        cursor = connection.execute(
                            """
                            UPDATE jobs SET state = ?
                            WHERE job_id = ? AND state = ? AND job_type = ? AND job_data = ?
                                AND NOT EXISTS (
                                    SELECT 1 FROM (
                                        SELECT source_job_id AS predecessor
                                        FROM job_connections WHERE target_job_id = ?
                                        UNION
                                        SELECT prerequisite_job_id
                                        FROM job_control_edges WHERE target_job_id = ?
                                    ) edges
                                    JOIN jobs AS predecessor_jobs ON predecessor_jobs.job_id = edges.predecessor
                                    WHERE predecessor_jobs.state != ?
                                )
                            """,
                            (
                                JobState.SCHEDULED.value,
                                str(job_id),
                                JobState.QUEUED.value,
                                job_type,
                                job_data,
                                str(job_id),
                                str(job_id),
                                JobState.DONE.value,
                            ),
                        )
                        if cursor.rowcount:
                            claimed.append(job_id)
                            active_counts[job_type] = active_counts.get(job_type, 0) + 1
                    connection.commit()
        for job_id in failed_job_ids:
            self._notify_execution_changed(job_id)
        if stale_readiness:
            return []
        for job_id in claimed:
            self._notify_execution_changed(job_id)
        return claimed

    def _fail_queued_job(
        self,
        job_id: uuid.UUID,
        job_data: str,
        error: JobError,
        reason: str,
        *,
        notify: bool = True,
    ) -> list[uuid.UUID]:
        """Fail one queued job whose product-owned scheduling hook raised.

        Args:
            job_id: Queued job identifier.
            job_data: Exact persisted payload that failed evaluation.
            error: Exact diagnostic raised by product readiness code.
            reason: Safe user-facing scheduling failure reason.
            notify: Whether to publish committed execution notifications immediately.

        Returns:
            Job identifiers changed by the failure and descendant propagation.
        """
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE jobs SET state = ?, state_reason = ?,
                    error_type = ?, error_message = ?, error_traceback = ?, completed_at = CURRENT_TIMESTAMP,
                    apply_disposition = ?, apply_operation = ?
                WHERE job_id = ? AND state = ? AND job_data = ?
                """,
                (
                    JobState.FAILED.value,
                    reason,
                    error.exception_type,
                    error.message,
                    error.traceback,
                    ApplyDisposition.NOT_APPLICABLE.value,
                    ApplyOperation.IDLE.value,
                    str(job_id),
                    JobState.QUEUED.value,
                    job_data,
                ),
            )
            skipped = self._skip_descendants(connection, job_id) if cursor.rowcount else []
            connection.commit()
        if cursor.rowcount:
            changed_job_ids = [job_id, *skipped]
            if notify:
                for changed_job_id in changed_job_ids:
                    self._notify_execution_changed(changed_job_id)
            return changed_job_ids
        return []

    def release_scheduled_jobs(self, job_ids: Sequence[uuid.UUID]) -> None:
        """Return unstarted scheduler claims to queued state.

        Args:
            job_ids: Scheduled job identifiers not dispatched before a stop.
        """
        for job_id in job_ids:
            self._transition_job(job_id, JobState.SCHEDULED, JobState.QUEUED)

    def get_job_directory(self, job_id: uuid.UUID) -> pathlib.Path:
        """Return the queue-owned directory for one job.

        Args:
            job_id: Job identifier.

        Returns:
            Queue-owned job directory.
        """
        return pathlib.Path(self.db_path).parent / "jobs" / str(job_id)

    def get_graphs_artifact_file_count(self, graph_ids: Sequence[uuid.UUID]) -> int:
        """Count regular files owned by all jobs in selected graphs.

        Args:
            graph_ids: Unique graph identifiers.

        Returns:
            Exact recursive regular-file count.

        Raises:
            KeyError: If a graph is absent.
            OSError: If an owned path cannot be inventoried safely.
            ValueError: If no graph is provided or identifiers repeat.
        """
        selected_graph_ids = self._require_unique_graph_ids(graph_ids)
        with self.connection() as connection:
            job_ids = tuple(
                job_id for graph_id in selected_graph_ids for job_id in self._get_graph_job_ids(connection, graph_id)
            )
        return self._inventory_job_directories(job_ids)[1]

    def delete_graphs(self, graph_ids: Sequence[uuid.UUID]) -> tuple[pathlib.Path, ...]:
        """Delete selected idle graphs in one transaction, then remove staged directories.

        Args:
            graph_ids: Unique graph identifiers.

        Returns:
            Inactive paths whose postcommit cleanup failed.

        Raises:
            KeyError: If a graph is absent.
            RuntimeError: If execution or Apply work is active.
            OSError: If queue-owned directories cannot be staged or restored safely.
            ValueError: If no graph is provided or identifiers repeat.
        """
        selected_graph_ids = self._require_unique_graph_ids(graph_ids)
        active_operations = (
            ApplyOperation.APPLYING.value,
            ApplyOperation.REAPPLYING.value,
            ApplyOperation.REVERTING.value,
        )
        staged_graphs: list[tuple[pathlib.Path, list[tuple[pathlib.Path, pathlib.Path]]]] = []
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            graph_jobs = tuple(
                (graph_id, self._get_graph_job_ids(connection, graph_id)) for graph_id in selected_graph_ids
            )
            placeholders = ", ".join("?" for _graph_id in selected_graph_ids)
            active = connection.execute(
                f"""
                SELECT 1 FROM jobs
                WHERE graph_id IN ({placeholders})
                  AND (state IN (?, ?) OR apply_operation IN (?, ?, ?))
                LIMIT 1
                """,
                (
                    *(str(graph_id) for graph_id in selected_graph_ids),
                    JobState.SCHEDULED.value,
                    JobState.IN_PROGRESS.value,
                    *active_operations,
                ),
            ).fetchone()
            if active is not None:
                connection.rollback()
                raise RuntimeError("Cannot delete a graph with active work")
            graph_directories = tuple(
                (graph_id, self._inventory_job_directories(job_ids)[0]) for graph_id, job_ids in graph_jobs
            )
            committed = False
            try:
                for graph_id, directories in graph_directories:
                    if not directories:
                        continue
                    staging_directory = self._graph_staging_directory(graph_id)
                    staging_directory.mkdir(parents=True, exist_ok=False)
                    staged: list[tuple[pathlib.Path, pathlib.Path]] = []
                    staged_graphs.append((staging_directory, staged))
                    for source in directories:
                        destination = staging_directory / source.name
                        source.replace(destination)
                        staged.append((source, destination))
                for graph_id in selected_graph_ids:
                    child_query = "SELECT job_id FROM jobs WHERE graph_id = ?"
                    connection.execute(
                        f"DELETE FROM job_connections WHERE source_job_id IN ({child_query}) OR target_job_id IN ({child_query})",
                        (str(graph_id), str(graph_id)),
                    )
                    connection.execute(
                        f"DELETE FROM job_control_edges WHERE target_job_id IN ({child_query}) OR prerequisite_job_id IN ({child_query})",
                        (str(graph_id), str(graph_id)),
                    )
                    connection.execute(
                        f"DELETE FROM job_input_values WHERE job_id IN ({child_query})",
                        (str(graph_id),),
                    )
                    connection.execute("DELETE FROM job_graphs WHERE graph_id = ?", (str(graph_id),))
                self._compact_graph_positions(connection)
                connection.commit()
                committed = True
            finally:
                if not committed:
                    connection.rollback()
                    restoration_errors: list[OSError] = []
                    for staging_directory, staged in reversed(staged_graphs):
                        try:
                            self._restore_staged_job_directories(staging_directory, staged)
                        except OSError as error:
                            restoration_errors.append(error)
                    if restoration_errors:
                        raise restoration_errors[0]
        self._notify_mutation()
        return tuple(
            retained_path
            for staging_directory, _staged in staged_graphs
            if (retained_path := self._remove_staged_graph_directory(staging_directory)) is not None
        )

    @staticmethod
    def _require_unique_graph_ids(graph_ids: Sequence[uuid.UUID]) -> tuple[uuid.UUID, ...]:
        """Require a non-empty graph selection without implicit deduplication.

        Args:
            graph_ids: Requested graph identifiers.

        Returns:
            Immutable identifiers in caller order.

        Raises:
            ValueError: If no graph is provided or identifiers repeat.
        """
        selected_graph_ids = tuple(graph_ids)
        if not selected_graph_ids:
            raise ValueError("At least one graph is required")
        if len(set(selected_graph_ids)) != len(selected_graph_ids):
            raise ValueError("Graph identifiers must be unique")
        return selected_graph_ids

    def _get_graph_job_ids(self, connection: sqlite3.Connection, graph_id: uuid.UUID) -> tuple[uuid.UUID, ...]:
        """Return ordered child identifiers for an existing graph.

        Args:
            connection: Active queue connection or transaction.
            graph_id: Graph identifier.

        Returns:
            Child identifiers in stable graph order.

        Raises:
            KeyError: If the graph is absent.
        """
        exists = connection.execute("SELECT 1 FROM job_graphs WHERE graph_id = ?", (str(graph_id),)).fetchone()
        if exists is None:
            raise KeyError(f"Unknown graph {graph_id}")
        rows = connection.execute(
            "SELECT job_id FROM jobs WHERE graph_id = ? ORDER BY position",
            (str(graph_id),),
        )
        return tuple(uuid.UUID(row["job_id"]) for row in rows)

    def _inventory_job_directories(
        self,
        job_ids: Sequence[uuid.UUID],
    ) -> tuple[tuple[pathlib.Path, ...], int]:
        """Inventory existing queue-owned job directories and regular files.

        Args:
            job_ids: Ordered job identifiers owned by one graph.

        Returns:
            Existing job directories and their recursive regular-file count.

        Raises:
            OSError: If any existing path cannot be inventoried safely.
        """
        directories: list[pathlib.Path] = []
        file_count = 0

        def raise_walk_error(error: OSError) -> None:
            """Propagate a recursive inventory failure.

            Args:
                error: Filesystem error raised while walking a job directory.

            Raises:
                OSError: Always, preserving the original failure.
            """
            raise error

        for job_id in job_ids:
            directory = self.get_job_directory(job_id)
            if not directory.exists():
                continue
            if not directory.is_dir():
                raise OSError(f'Expected queue job directory at "{directory}"')
            directories.append(directory)
            for _root, _child_directories, files in os.walk(directory, onerror=raise_walk_error):
                file_count += len(files)
        return tuple(directories), file_count

    def _graph_staging_directory(self, graph_id: uuid.UUID) -> pathlib.Path:
        """Return the same-volume inactive directory for one graph deletion.

        Args:
            graph_id: Graph identifier.

        Returns:
            Queue-owned staging directory.
        """
        return pathlib.Path(self.db_path).parent / "jobs" / ".trash" / str(graph_id)

    @staticmethod
    def _restore_staged_job_directories(
        staging_directory: pathlib.Path,
        staged: Sequence[tuple[pathlib.Path, pathlib.Path]],
    ) -> None:
        """Restore every staged job directory after a precommit failure.

        Args:
            staging_directory: Inactive graph directory.
            staged: Original and staged path pairs in move order.

        Raises:
            OSError: If any staged directory cannot be restored.
        """
        failures: list[pathlib.Path] = []
        for original, inactive in reversed(staged):
            try:
                inactive.replace(original)
            except OSError as error:
                carb.log_error(f"Could not restore staged queue directory {inactive}: {error}")
                failures.append(inactive)
        if not failures:
            try:
                staging_directory.rmdir()
                staging_directory.parent.rmdir()
            except OSError:
                pass
            return
        joined = ", ".join(str(path) for path in failures)
        raise OSError(f"Could not restore staged queue directories: {joined}")

    @staticmethod
    def _remove_staged_graph_directory(staging_directory: pathlib.Path) -> pathlib.Path | None:
        """Remove committed inactive files or retain their path for recovery.

        Args:
            staging_directory: Inactive committed graph directory.

        Returns:
            Retained path when cleanup failed, otherwise ``None``.
        """
        try:
            shutil.rmtree(staging_directory)
        except FileNotFoundError:
            return None
        except OSError as error:
            carb.log_warn(f"Could not remove inactive queue directory {staging_directory}: {error}")
            return staging_directory
        try:
            staging_directory.parent.rmdir()
        except OSError:
            return None
        return None

    def _reconcile_staged_graph_deletions(self) -> None:
        """Recover precommit staging or finish cleanup after an interrupted deletion."""
        trash_directory = pathlib.Path(self.db_path).parent / "jobs" / ".trash"
        if not trash_directory.exists():
            return
        try:
            staged_graphs = tuple(trash_directory.iterdir())
        except OSError as error:
            carb.log_warn(f"Could not inspect inactive queue directories at {trash_directory}: {error}")
            return
        for staging_directory in staged_graphs:
            try:
                graph_id = uuid.UUID(staging_directory.name)
            except ValueError:
                carb.log_warn(f"Ignoring unexpected inactive queue path {staging_directory}")
                continue
            with self.connection() as connection:
                graph_exists = connection.execute(
                    "SELECT 1 FROM job_graphs WHERE graph_id = ?",
                    (str(graph_id),),
                ).fetchone()
            if graph_exists is None:
                self._remove_staged_graph_directory(staging_directory)
                continue
            try:
                staged_jobs = tuple(staging_directory.iterdir())
                restore_pairs = tuple(
                    (pathlib.Path(self.db_path).parent / "jobs" / path.name, path) for path in staged_jobs
                )
                self._restore_staged_job_directories(staging_directory, restore_pairs)
            except OSError as error:
                carb.log_error(f"Could not recover inactive queue directories for graph {graph_id}: {error}")

    def update_graph_positions(self, graph_ids: Sequence[uuid.UUID]) -> None:
        """Replace root positions with one exact permutation of all graphs.

        Args:
            graph_ids: Graph identifiers in desired order.

        Raises:
            ValueError: If identifiers are duplicated, missing, or foreign.
        """
        if len(graph_ids) != len(set(graph_ids)):
            raise ValueError("Graph positions cannot contain duplicate identifiers")
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = {uuid.UUID(row[0]) for row in connection.execute("SELECT graph_id FROM job_graphs")}
            if set(graph_ids) != existing:
                connection.rollback()
                raise ValueError("Graph positions must include every graph exactly once")
            for temporary, graph_id in enumerate(graph_ids, start=len(graph_ids)):
                connection.execute("UPDATE job_graphs SET position = ? WHERE graph_id = ?", (temporary, str(graph_id)))
            for position, graph_id in enumerate(graph_ids):
                connection.execute("UPDATE job_graphs SET position = ? WHERE graph_id = ?", (position, str(graph_id)))
            connection.commit()
        self._notify_mutation()

    def get_apply_receipt(self, job_id: uuid.UUID) -> Any | None:
        """Return one durable Apply receipt.

        Args:
            job_id: Job identifier.

        Returns:
            Deserialized receipt or ``None``.

        Raises:
            KeyError: If the job is absent.
        """
        with self.connection() as connection:
            row = connection.execute("SELECT apply_receipt FROM jobs WHERE job_id = ?", (str(job_id),)).fetchone()
        if row is None:
            raise KeyError(f"Unknown job {job_id}")
        return None if row["apply_receipt"] is None else deserialize(row["apply_receipt"])

    def start_apply_operation(
        self,
        job_id: uuid.UUID,
        dispositions: Container[ApplyDisposition],
        operations: Container[ApplyOperation],
        new_operation: ApplyOperation,
    ) -> bool:
        """Conditionally claim one Apply lifecycle operation.

        Args:
            job_id: Job identifier.
            dispositions: Allowed durable dispositions.
            operations: Allowed current operations.
            new_operation: Active operation to persist.

        Returns:
            Whether this caller claimed the operation.
        """
        disposition_values = tuple(value.value for value in dispositions)
        operation_values = tuple(value.value for value in operations)
        disposition_slots = ",".join("?" for _ in disposition_values)
        operation_slots = ",".join("?" for _ in operation_values)
        with self.connection() as connection:
            cursor = connection.execute(
                f"""
                UPDATE jobs SET apply_operation = ?, apply_error_type = NULL,
                    apply_error_message = NULL, apply_error_traceback = NULL, apply_reason = NULL
                WHERE job_id = ? AND apply_disposition IN ({disposition_slots})
                    AND apply_operation IN ({operation_slots})
                """,
                (
                    new_operation.value,
                    str(job_id),
                    *disposition_values,
                    *operation_values,
                ),
            )
            connection.commit()
        if cursor.rowcount:
            self._notify_job_changed(job_id)
            return True
        return False

    def persist_apply_receipt(
        self,
        job_id: uuid.UUID,
        expected_operation: ApplyOperation,
        receipt: Any,
    ) -> bool:
        """Conditionally persist pre-mutation state for one active Apply operation.

        Args:
            job_id: Job identifier.
            expected_operation: Active operation owned by the caller.
            receipt: Exact typed state captured before the external mutation.

        Returns:
            Whether the receipt was persisted for the active operation.
        """
        receipt_payload = serialize(receipt)
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET apply_receipt = ?
                WHERE job_id = ? AND apply_operation = ? AND apply_receipt IS NULL
                """,
                (receipt_payload, str(job_id), expected_operation.value),
            )
            connection.commit()
        return bool(cursor.rowcount)

    def complete_apply_operation(
        self,
        job_id: uuid.UUID,
        expected_operation: ApplyOperation,
        disposition: ApplyDisposition,
        clear_receipt: bool = False,
    ) -> bool:
        """Conditionally complete one Apply lifecycle operation.

        Args:
            job_id: Job identifier.
            expected_operation: Active operation owned by the caller.
            disposition: Durable success disposition.
            clear_receipt: Whether success explicitly removes the durable receipt.

        Returns:
            Whether the operation completed.
        """
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET apply_disposition = ?, apply_operation = ?,
                    apply_receipt = CASE WHEN ? THEN NULL ELSE apply_receipt END,
                    apply_reason = NULL,
                    apply_error_type = NULL,
                    apply_error_message = NULL, apply_error_traceback = NULL
                WHERE job_id = ? AND apply_operation = ?
                """,
                (
                    disposition.value,
                    ApplyOperation.IDLE.value,
                    int(clear_receipt),
                    str(job_id),
                    expected_operation.value,
                ),
            )
            connection.commit()
        if cursor.rowcount:
            self._notify_job_changed(job_id)
            return True
        return False

    def fail_apply_operation(
        self,
        job_id: uuid.UUID,
        expected_operation: ApplyOperation,
        failure_operation: ApplyOperation,
        failure_disposition: ApplyDisposition,
        error: JobError,
        reason: str,
    ) -> bool:
        """Persist one active Apply operation failure.

        Args:
            job_id: Job identifier.
            expected_operation: Active operation owned by the caller.
            failure_operation: Durable failure operation.
            failure_disposition: Stable disposition safe to expose after failure.
            error: Durable failure details.
            reason: Safe operation-specific user-facing text.

        Returns:
            Whether the failure was persisted.

        Raises:
            ValueError: If reason is not a non-empty string.
        """
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET apply_disposition = ?, apply_operation = ?, apply_reason = ?, apply_error_type = ?,
                    apply_error_message = ?, apply_error_traceback = ?
                WHERE job_id = ? AND apply_operation = ?
                """,
                (
                    failure_disposition.value,
                    failure_operation.value,
                    reason,
                    error.exception_type,
                    error.message,
                    error.traceback,
                    str(job_id),
                    expected_operation.value,
                ),
            )
            connection.commit()
        if cursor.rowcount:
            self._notify_job_changed(job_id)
            return True
        return False

    def decline_apply(self, job_id: uuid.UUID) -> bool:
        """Conditionally decline one pending output without future latching.

        Args:
            job_id: Job identifier.

        Returns:
            Whether the output entered declined disposition.
        """
        allowed = (ApplyOperation.IDLE, ApplyOperation.APPLY_FAILED)
        slots = ",".join("?" for _ in allowed)
        with self.connection() as connection:
            cursor = connection.execute(
                f"""
                UPDATE jobs SET apply_disposition = ?, apply_operation = ?,
                    apply_reason = NULL, apply_error_type = NULL,
                    apply_error_message = NULL, apply_error_traceback = NULL
                WHERE job_id = ? AND apply_disposition = ? AND apply_operation IN ({slots})
                    AND apply_receipt IS NULL
                """,
                (
                    ApplyDisposition.DECLINED.value,
                    ApplyOperation.IDLE.value,
                    str(job_id),
                    ApplyDisposition.PENDING.value,
                    *(operation.value for operation in allowed),
                ),
            )
            connection.commit()
        if cursor.rowcount:
            self._notify_job_changed(job_id)
            return True
        return False

    def recover_interrupted_jobs(self) -> None:
        """Recover conditional execution and Apply operations after process interruption."""
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE jobs SET state = ? WHERE state = ?",
                (JobState.QUEUED.value, JobState.SCHEDULED.value),
            )
            interrupted = [
                uuid.UUID(row[0])
                for row in connection.execute("SELECT job_id FROM jobs WHERE state = ?", (JobState.IN_PROGRESS.value,))
            ]
            for job_id in interrupted:
                connection.execute(
                    """
                    UPDATE jobs SET state = ?, state_reason = ?,
                        error_type = ?, error_message = ?, error_traceback = ?, completed_at = CURRENT_TIMESTAMP,
                        apply_disposition = ?, apply_operation = ?, apply_reason = NULL,
                        apply_error_type = NULL, apply_error_message = NULL, apply_error_traceback = NULL
                    WHERE job_id = ?
                    """,
                    (
                        JobState.FAILED.value,
                        "Application stopped while the job was running",
                        "InterruptedError",
                        "Application stopped while the job was running",
                        "",
                        ApplyDisposition.NOT_APPLICABLE.value,
                        ApplyOperation.IDLE.value,
                        str(job_id),
                    ),
                )
                self._skip_descendants(connection, job_id)
            interrupted_apply_operations = (
                (
                    ApplyOperation.APPLYING,
                    ApplyOperation.APPLY_FAILED,
                    ApplyDisposition.PENDING,
                    "The output could not be applied because the application stopped.",
                ),
                (
                    ApplyOperation.REAPPLYING,
                    ApplyOperation.REAPPLY_FAILED,
                    None,
                    "The applied output could not be updated because the application stopped.",
                ),
                (
                    ApplyOperation.REVERTING,
                    ApplyOperation.REVERT_FAILED,
                    None,
                    "The applied output could not be reverted because the application stopped.",
                ),
            )
            for active_operation, failed_operation, failure_disposition, reason in interrupted_apply_operations:
                connection.execute(
                    """
                    UPDATE jobs SET apply_disposition = COALESCE(?, apply_disposition),
                        apply_operation = ?, apply_reason = ?,
                        apply_error_type = ?, apply_error_message = ?, apply_error_traceback = ?
                    WHERE apply_operation = ?
                    """,
                    (
                        failure_disposition.value if failure_disposition is not None else None,
                        failed_operation.value,
                        reason,
                        "InterruptedError",
                        "Application stopped during an Apply operation",
                        "",
                        active_operation.value,
                    ),
                )
            connection.commit()
        self._notify_mutation()

    def subscribe_job_changed(self, callback: Callable[[uuid.UUID], None]) -> EventSubscription:
        """Subscribe to targeted child changes.

        Args:
            callback: Callback receiving the changed job identifier.

        Returns:
            Subscription retained by the caller.
        """
        return _isolated_subscription(self._job_changed_event, callback, "job-change")

    def subscribe_job_progress_changed(
        self,
        callback: Callable[[uuid.UUID, JobProgress], None],
    ) -> EventSubscription:
        """Subscribe to targeted progress changes.

        Progress is emitted separately from other job changes so presentation consumers can update existing widgets
        without reloading or rebuilding a job row.

        Args:
            callback: Callback receiving the changed job identifier and committed progress.

        Returns:
            Subscription retained by the caller.
        """
        return _isolated_subscription(self._job_progress_changed_event, callback, "job-progress-change")

    def subscribe_mutation(self, callback: Callable[[], None]) -> EventSubscription:
        """Subscribe to graph insert, delete, and reorder changes.

        Args:
            callback: Callback invoked after structural mutation.

        Returns:
            Subscription retained by the caller.
        """
        return _isolated_subscription(self._mutation_event, callback, "mutation")

    def subscribe_schedule_conditions_changed(self, callback: Callable[[], None]) -> EventSubscription:
        """Subscribe to product-owned runnable-condition changes.

        Args:
            callback: Callback invoked when queued readiness may have changed.

        Returns:
            Subscription retained by the caller.
        """
        return _isolated_subscription(
            self._schedule_conditions_changed_event,
            callback,
            "schedule-condition",
        )

    def subscribe_external_conditions_changed(self, callback: Callable[[], None]) -> EventSubscription:
        """Subscribe to product-owned readiness changes that may affect presentation.

        Execution transitions wake the scheduler without emitting this event because their targeted job event already
        gives presentation consumers the exact row to update.

        Args:
            callback: Callback invoked when external readiness may have changed for multiple jobs.

        Returns:
            Subscription retained by the caller.
        """
        return _isolated_subscription(
            self._external_conditions_changed_event,
            callback,
            "external-condition",
        )

    def notify_schedule_conditions_changed(self) -> None:
        """Notify the scheduler and presentation consumers that product readiness changed."""
        self._external_conditions_changed_event()
        self._publish_schedule_conditions_changed()

    def _iter_snapshots(
        self,
        where: str = "",
        parameters: tuple[Any, ...] = (),
        connection: sqlite3.Connection | None = None,
    ) -> Iterator[QueueJobSnapshot]:
        """Iterate current snapshots with an optional trusted SQL filter.

        Args:
            where: Internal SQL WHERE clause.
            parameters: Bound WHERE parameters.
            connection: Optional transaction shared with a composite read.

        Yields:
            Ordered current snapshots.
        """
        if connection is None:
            with self.connection() as owned_connection:
                yield from self._iter_snapshots(where, parameters, owned_connection)
            return
        rows = connection.execute(
            f"""
                WITH dependency_states AS (
                    SELECT edges.target_job_id,
                        MIN(CASE WHEN predecessor.state = ? THEN 1 ELSE 0 END) AS dependencies_done
                    FROM (
                        SELECT target_job_id, source_job_id AS predecessor_job_id FROM job_connections
                        UNION
                        SELECT target_job_id, prerequisite_job_id FROM job_control_edges
                    ) edges
                    LEFT JOIN jobs predecessor ON predecessor.job_id = edges.predecessor_job_id
                    GROUP BY edges.target_job_id
                )
                SELECT job_graphs.graph_id, job_graphs.name AS graph_name,
                    job_graphs.position AS graph_position,
                    jobs.job_id, jobs.name, jobs.job_type, jobs.position, job_graphs.submitted_at,
                    jobs.state, jobs.state_reason, jobs.started_at, jobs.completed_at,
                    jobs.progress_completed, jobs.progress_total, jobs.progress_detail,
                    jobs.error_type, jobs.error_message, jobs.error_traceback,
                    jobs.apply_disposition, jobs.apply_operation, jobs.apply_handler_id,
                    jobs.apply_reason,
                    jobs.apply_error_type, jobs.apply_error_message, jobs.apply_error_traceback,
                    COALESCE(dependency_states.dependencies_done, 1) AS dependencies_done
                FROM jobs
                JOIN job_graphs ON job_graphs.graph_id = jobs.graph_id
                LEFT JOIN dependency_states ON dependency_states.target_job_id = jobs.job_id
                {where}
                ORDER BY job_graphs.position, jobs.position
                """,
            (JobState.DONE.value, *parameters),
        )
        for row in rows:
            state = JobState(row["state"])
            if state is JobState.QUEUED and not row["dependencies_done"]:
                state = JobState.WAITING_FOR_DEPENDENCIES
            progress = None
            if any(row[name] is not None for name in ("progress_completed", "progress_total", "progress_detail")):
                progress = JobProgress(row["progress_completed"], row["progress_total"], row["progress_detail"])
            yield QueueJobSnapshot(
                graph_id=uuid.UUID(row["graph_id"]),
                graph_name=row["graph_name"],
                graph_position=row["graph_position"],
                job_id=uuid.UUID(row["job_id"]),
                job_name=row["name"],
                job_type=row["job_type"],
                position=row["position"],
                submitted_at=_parse_datetime(row["submitted_at"]),
                state=state,
                started_at=_parse_datetime(row["started_at"]),
                completed_at=_parse_datetime(row["completed_at"]),
                state_reason=row["state_reason"],
                progress=progress,
                error=_row_error(row, "error"),
                apply_disposition=ApplyDisposition(row["apply_disposition"]),
                apply_operation=ApplyOperation(row["apply_operation"]),
                apply_handler_id=row["apply_handler_id"],
                apply_reason=row["apply_reason"],
                apply_error=_row_error(row, "apply_error"),
            )

    def _skip_descendants(
        self,
        connection: sqlite3.Connection,
        job_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Recursively skip queued descendants through all edge kinds.

        Args:
            connection: Active queue transaction.
            job_id: Failed or skipped producer identifier.
        Returns:
            Descendant identifiers changed by this call.
        """
        rows = connection.execute(
            """
            WITH RECURSIVE edges(prerequisite_job_id, target_job_id) AS (
                SELECT source_job_id, target_job_id FROM job_connections
                UNION
                SELECT prerequisite_job_id, target_job_id FROM job_control_edges
            ), descendants(job_id, skip_reason) AS (
                SELECT target.job_id,
                    'Prerequisite "' || prerequisite.name || '" '
                    || CASE WHEN prerequisite.state = ? THEN 'failed' ELSE 'was skipped' END
                    || ': ' || COALESCE(prerequisite.state_reason, 'No additional details are available.')
                FROM edges
                JOIN jobs prerequisite ON prerequisite.job_id = edges.prerequisite_job_id
                JOIN jobs target ON target.job_id = edges.target_job_id
                WHERE prerequisite.job_id = ? AND target.state = ?
                UNION ALL
                SELECT target.job_id,
                    'Prerequisite "' || prerequisite.name || '" was skipped: ' || descendants.skip_reason
                FROM descendants
                JOIN jobs prerequisite ON prerequisite.job_id = descendants.job_id
                JOIN edges ON edges.prerequisite_job_id = descendants.job_id
                JOIN jobs target ON target.job_id = edges.target_job_id
                WHERE target.state = ?
            ), reasons AS (
                SELECT job_id, MIN(skip_reason) AS skip_reason FROM descendants GROUP BY job_id
            )
            UPDATE jobs SET state = ?,
                state_reason = (SELECT skip_reason FROM reasons WHERE reasons.job_id = jobs.job_id),
                apply_disposition = ?, apply_operation = ?, completed_at = CURRENT_TIMESTAMP
            WHERE job_id IN (SELECT job_id FROM reasons) AND state = ?
            RETURNING job_id
            """,
            (
                JobState.FAILED.value,
                str(job_id),
                JobState.QUEUED.value,
                JobState.QUEUED.value,
                JobState.SKIPPED.value,
                ApplyDisposition.NOT_APPLICABLE.value,
                ApplyOperation.IDLE.value,
                JobState.QUEUED.value,
            ),
        ).fetchall()
        return [uuid.UUID(row["job_id"]) for row in rows]

    @staticmethod
    def _compact_graph_positions(connection: sqlite3.Connection) -> None:
        """Compact graph positions after deletion.

        Args:
            connection: Active queue transaction.
        """
        offset = connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM job_graphs").fetchone()[0]
        connection.execute("UPDATE job_graphs SET position = position + ?", (offset,))
        connection.execute(
            """
            WITH ordered AS (
                SELECT graph_id, ROW_NUMBER() OVER (ORDER BY position) - 1 AS compact_position FROM job_graphs
            )
            UPDATE job_graphs SET position = (
                SELECT compact_position FROM ordered WHERE ordered.graph_id = job_graphs.graph_id
            )
            """
        )

    def _notify_job_changed(self, job_id: uuid.UUID) -> None:
        """Emit one targeted committed child change.

        Args:
            job_id: Changed child identifier.
        """
        self._job_changed_event(job_id)

    def _notify_execution_changed(self, job_id: uuid.UUID) -> None:
        """Emit one targeted execution change and wake runnable scanning.

        Args:
            job_id: Changed child identifier.
        """
        self._job_changed_event(job_id)
        self._publish_schedule_conditions_changed()

    def _notify_mutation(self) -> None:
        """Emit one committed structural queue change."""
        self._mutation_event()
        self._publish_schedule_conditions_changed()

    def _publish_schedule_conditions_changed(self) -> None:
        """Advance readiness revision and notify scheduler subscribers."""
        with self._schedule_conditions_lock:
            self._schedule_conditions_revision += 1
        self._schedule_conditions_changed_event()


def _states(state_or_states: JobState | Container[JobState]) -> tuple[JobState, ...]:
    """Normalize one state or state container to a non-empty tuple.

    Args:
        state_or_states: Expected state specification.

    Returns:
        Non-empty state tuple.

    Raises:
        TypeError: If any value is not a JobState.
        ValueError: If a container is empty.
    """
    states = (state_or_states,) if isinstance(state_or_states, JobState) else tuple(state_or_states)
    if not states:
        raise ValueError("Expected states must not be empty")
    if not all(isinstance(state, JobState) for state in states):
        raise TypeError("Expected states must contain only JobState values")
    if not all(state.is_persisted for state in states):
        raise ValueError("Expected states must contain only persisted JobState values")
    return states


def _parse_datetime(value: str | datetime.datetime | None) -> datetime.datetime | None:
    """Parse one SQLite timestamp.

    Args:
        value: SQLite timestamp or existing datetime.

    Returns:
        Parsed datetime or ``None``.
    """
    if value is None or isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.fromisoformat(value)


def _row_error(row: sqlite3.Row, prefix: str) -> JobError | None:
    """Build durable failure details from prefixed row columns.

    Args:
        row: Current queue row.
        prefix: Column prefix for error fields.

    Returns:
        Durable error or ``None``.
    """
    exception_type = row[f"{prefix}_type"]
    if exception_type is None:
        return None
    return JobError(exception_type, row[f"{prefix}_message"] or "", row[f"{prefix}_traceback"] or "")


def _job_ports(job_type_name: str) -> tuple[tuple[JobInputPort[Any], ...], tuple[JobOutputPort[Any], ...]]:
    """Return immutable port declarations for one exact registered job type.

    Args:
        job_type_name: Stable persisted job type identifier.

    Returns:
        Declared input and output port tuples.

    Raises:
        TypeError: If the exact job type is unavailable.
    """
    job_type = _registered_job_type(job_type_name)
    if job_type is None:
        raise TypeError(f"Persisted job type {job_type_name} is unavailable")
    return job_type.input_ports, job_type.output_ports


def _registered_job_type(job_type_name: str) -> type[Job] | None:
    """Return one exact registered job type without accepting other persisted value types.

    Args:
        job_type_name: Stable persisted-type identifier.

    Returns:
        Registered ``Job`` subclass, or ``None`` while its plugin is unavailable.
    """
    value_type = persistence.get_registry().get_type(job_type_name)
    if value_type is None or not issubclass(value_type, Job):
        return None
    return value_type


def _port_by_name(ports: Sequence[Any], name: str) -> Any:
    """Return one declared port by its stable name.

    Args:
        ports: Declared input or output port descriptors.
        name: Stable persisted port name.

    Returns:
        Matching declared port descriptor.

    Raises:
        ValueError: If no declared port has the persisted name.
    """
    try:
        return next(port for port in ports if port.name == name)
    except StopIteration as error:
        raise ValueError(f"Unknown persisted port {name}") from error


def _decode_outputs(payload: str, output_ports: tuple[JobOutputPort[Any], ...]) -> JobOutputs:
    """Decode outputs and require their names to exactly match declared metadata.

    Args:
        payload: Serialized output mapping keyed by stable port name.
        output_ports: Exact declared output-port descriptors.

    Returns:
        Exact typed output mapping.

    Raises:
        ValueError: If persisted names do not exactly match declared output names.
        TypeError: If a decoded value violates its declared exact type.
    """
    values_by_name = deserialize(payload)
    if type(values_by_name) is not dict or set(values_by_name) != {port.name for port in output_ports}:
        raise ValueError("Persisted output names do not exactly match declared output ports")
    ports_by_name = {port.name: port for port in output_ports}
    return JobOutputs({ports_by_name[name]: value for name, value in values_by_name.items()})
