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
import dataclasses
import datetime
import enum
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, TypeVar
from collections.abc import Callable, Container, Iterator

import omni.flux.job_queue.core.events
import omni.flux.job_queue.core.job
import omni.flux.job_queue.core.serializer
import omni.flux.job_queue.core.utils
from omni.flux.job_queue.core.constants import job_queue_config

EventT = TypeVar("EventT", bound=omni.flux.job_queue.core.events.JobEvent)


class JobState(str, enum.Enum):
    """
    Enum representing the state of a job.

    TODO: Add CANCELLED state to support cancelling in-progress jobs. For long-running
    workflows (e.g., ComfyUI), users will want to cancel jobs. This requires changes to
    the executor and scheduler to support cooperative cancellation.
    """

    # Fallback state that should not appear in normal operation.
    UNKNOWN = "UNKNOWN"
    # Default initial state when a job is submitted.
    QUEUED = "QUEUED"
    # Set when the job is about to be sent to the executor pool.
    SCHEDULED = "SCHEDULED"
    # Set when the job is currently being executed by the executor.
    IN_PROGRESS = "IN_PROGRESS"
    # Job completed successfully. Result event should be available.
    DONE = "DONE"
    # Job errored during execution. Error event with traceback should be available.
    FAILED = "FAILED"
    # This state is not intended to be set directly, but is used to indicate that a job
    # has dependent jobs that are not in the DONE state. This state is only used when using
    # the `QueueInterface.get_snapshot` or `QueueInterface.get_job_state` methods which
    # may be confusing.
    PENDING = "PENDING"


@dataclasses.dataclass(frozen=True)
class QueueJobSnapshot:
    """
    Snapshot of a job in the queue, including its current state.
    """

    graph_id: uuid.UUID
    graph_name: str
    job_id: uuid.UUID
    job_name: str
    queue: str
    priority: int
    timestamp: datetime.datetime
    state: JobState
    state_change_timestamp: datetime.datetime | None = None

    updated: datetime.datetime = dataclasses.field(default_factory=datetime.datetime.now)


class QueueInterface:
    """
    Interface for interacting with the job queue database.
    """

    @staticmethod
    def _delete_default_db_path():
        # Utility for debugging / tests.
        if os.path.exists(job_queue_config.db_path):
            os.remove(job_queue_config.db_path)

    def __init__(self, db_path: str | None = None, initialize: bool = True):
        self.db_path = db_path if db_path is not None else job_queue_config.db_path
        if initialize:
            self.initialize()

    @contextlib.contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Specify the row factory to return rows as dictionaries
        conn.row_factory = sqlite3.Row
        # Enable foreign key support
        conn.execute("PRAGMA foreign_keys = ON")
        # Configure WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self):
        """
        Initialize the database schema if it does not already exist.
        """

        #  +-------------------+         +-------------------+         +-------------------+
        #  |   job_graphs      |         |      jobs         |         |   job_events      |
        #  +-------------------+         +-------------------+         +-------------------+
        #  | graph_id (PK)     |<--------| job_id (PK)       |<--------| id (PK)           |
        #  | name              |         | graph_id (FK)     |         | job_id (FK)       |
        #  | timestamp         |         | ...               |         | ...               |
        #  +-------------------+         +-------------------+         +-------------------+
        #                                   ^         ^
        #                                   |         |
        #                                   |         |
        #                                   |         |
        #                                   |         |
        #  +-------------------+            |         |
        #  | job_dependencies  |------------+         |
        #  +-------------------+                      |
        #  | job_id (FK, PK)   |----------------------+
        #  | depend_job_id (FK, PK)                   |
        #  +-------------------+                      |
        #                                             |
        #  (ON DELETE CASCADE propagates deletions    |
        #   from job_graphs -> jobs -> job_events     |
        #   and job_dependencies)                     |
        #                                             |
        #  -------------------------------------------+

        # I'm not currently tackling schema migrations, but I believe we would be able to add that to a future
        # version without doing any additional prep work now. We can tackle that when/if we need it.

        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_graphs (
                    graph_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    queue TEXT NOT NULL DEFAULT 'default',
                    name TEXT NOT NULL,
                    job TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(graph_id) REFERENCES job_graphs(graph_id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_dependencies (
                    job_id TEXT NOT NULL,
                    depend_job_id TEXT NOT NULL,
                    PRIMARY KEY (job_id, depend_job_id),
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
                    FOREIGN KEY(depend_job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                )
                """
            )

            conn.commit()

    def purge(self):
        """
        Remove all records from the database.
        """
        with self.connection() as conn:
            conn.execute("DELETE FROM job_graphs")
            conn.commit()

    def submit(
        self,
        job_graph: omni.flux.job_queue.core.job.JobGraph,
        initial_state: JobState = JobState.QUEUED,
    ) -> None:
        """
        Submit all jobs in a JobGraph to the queue.
        """
        initial_state_event = omni.flux.job_queue.core.events.StateChange(initial_state)
        with self.connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO job_graphs (graph_id, name) VALUES (?, ?)
                    """,
                    (str(job_graph.graph_id), job_graph.name),
                )

                # Enter jobs in topological order to ensure dependencies are valid.
                for job in job_graph.iter_jobs():
                    conn.execute(
                        "INSERT INTO jobs (job_id, graph_id, queue, name, job, priority) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            str(job.job_id),
                            str(job_graph.graph_id),
                            job.queue,
                            job.name,
                            omni.flux.job_queue.core.serializer.serialize(job),
                            job.priority,
                        ),
                    )

                    if job.dependencies:
                        for dep in job.dependencies:
                            conn.execute(
                                "INSERT INTO job_dependencies (job_id, depend_job_id) VALUES (?, ?)",
                                (
                                    str(job.job_id),
                                    str(dep),
                                ),
                            )

                    conn.execute(
                        "INSERT INTO job_events (job_id, event_type, event) VALUES (?, ?, ?)",
                        (
                            str(job.job_id),
                            initial_state_event.name,
                            omni.flux.job_queue.core.serializer.serialize(initial_state_event),
                        ),
                    )

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def update_job(self, job: omni.flux.job_queue.core.job.Job) -> None:
        """
        Update an existing job in the database.
        """
        with self.connection() as conn:
            conn.execute(
                "UPDATE jobs SET queue = ?, name = ?, job = ?, priority = ? WHERE job_id = ?",
                (
                    job.queue,
                    job.name,
                    omni.flux.job_queue.core.serializer.serialize(job),
                    job.priority,
                    str(job.job_id),
                ),
            )
            conn.commit()

    def get_snapshot(self) -> list[QueueJobSnapshot]:
        """
        Return a list of QueueJobSnapshot objects for all jobs in the queue. Results are sorted by priority
        (descending) and timestamp (descending).

        Jobs that have dependencies not in JobState.DONE state will use JobState.PENDING instead of whatever the
        latest StateChange event indicates.
        """

        # FIXME: This implementation assumes there are a reasonable number of jobs to fit in memory...

        # FIXME: Marking jobs as PENDING when any dependency is not DONE does not account for retries.
        #  A job may be marked DONE, but if a dependency transitions out of DONE (e.g., due to a retry),
        #  this logic will incorrectly set the job's state to PENDING.

        with self.connection() as conn:
            # Fetch all jobs and their latest event
            sql = """
                SELECT
                    jobs.*,
                    job_graphs.name AS graph_name,
                    latest_events.event AS latest_event,
                    latest_events.timestamp AS state_change_timestamp
                FROM jobs
                JOIN job_graphs ON jobs.graph_id = job_graphs.graph_id
                LEFT JOIN (
                    SELECT job_id, event, timestamp FROM job_events
                    WHERE event_type = ?
                      AND id IN (
                        SELECT MAX(id) FROM job_events
                        WHERE event_type = ?
                        GROUP BY job_id
                      )
                ) AS latest_events
                ON jobs.job_id = latest_events.job_id
            """
            params = [
                omni.flux.job_queue.core.events.StateChange.name,
                omni.flux.job_queue.core.events.StateChange.name,
            ]
            jobs_cur = conn.execute(sql, params)
            jobs = jobs_cur.fetchall()

            # Fetch all dependencies
            dep_cur = conn.execute("SELECT job_id, depend_job_id FROM job_dependencies")
            dependencies = {}
            for row in dep_cur.fetchall():
                dependencies.setdefault(row["job_id"], []).append(row["depend_job_id"])

            # Build state map for all jobs
            state_map = {}
            for row in jobs:
                job_id = row["job_id"]
                if row["latest_event"]:
                    event: omni.flux.job_queue.core.events.StateChange = (
                        omni.flux.job_queue.core.serializer.deserialize(row["latest_event"])
                    )
                    state_map[job_id] = event.value
                else:
                    state_map[job_id] = JobState.UNKNOWN

            results: list[QueueJobSnapshot] = []

            for job_row in jobs:
                job_id = job_row["job_id"]

                state = state_map.get(job_id, JobState.UNKNOWN)
                dep_ids = dependencies.get(job_id, [])
                if dep_ids and any(state_map.get(dep_id, JobState.UNKNOWN) != JobState.DONE for dep_id in dep_ids):
                    state = JobState.PENDING

                state_change_timestamp = job_row["state_change_timestamp"]

                qjob = QueueJobSnapshot(
                    graph_id=uuid.UUID(job_row["graph_id"]),
                    graph_name=job_row["graph_name"],
                    job_id=uuid.UUID(job_id),
                    job_name=job_row["name"],
                    queue=job_row["queue"],
                    priority=job_row["priority"],
                    timestamp=datetime.datetime.fromisoformat(job_row["timestamp"]),
                    state_change_timestamp=(
                        datetime.datetime.fromisoformat(state_change_timestamp) if state_change_timestamp else None
                    ),
                    state=state,
                )
                results.append(qjob)

            results.sort(key=lambda jr: (-jr.priority, jr.timestamp))

            return results

    def get_jobs_by_graph_id(self, graph_id: uuid.UUID | str) -> list[omni.flux.job_queue.core.job.Job]:
        """
        Get all jobs associated with a graph ID.
        """
        with self.connection() as conn:
            cur = conn.execute(
                "SELECT * FROM jobs WHERE graph_id = ?",
                (str(graph_id),),
            )
            jobs = []
            for row in cur.fetchall():
                jobs.append(omni.flux.job_queue.core.serializer.deserialize(row["job"]))
            return jobs

    def get_job_by_id(self, job_id: uuid.UUID | str) -> omni.flux.job_queue.core.job.Job | None:
        """
        Get a job by its ID.
        """
        with self.connection() as conn:
            cur = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (str(job_id),),
            )
            row = cur.fetchone()
            if row:
                return omni.flux.job_queue.core.serializer.deserialize(row["job"])
            return None

    def get_job_state(self, job_id: uuid.UUID | str) -> JobState:
        job_id_str = str(job_id)
        with self.connection() as conn:
            # Get latest state for all dependencies in one query
            dep_states = conn.execute(
                """
                SELECT je.event
                FROM job_dependencies jd
                JOIN job_events je
                  ON jd.depend_job_id = je.job_id
                WHERE jd.job_id = ?
                  AND je.event_type = ?
                  AND je.id = (
                      SELECT MAX(id) FROM job_events
                      WHERE job_id = jd.depend_job_id AND event_type = ?
                  )
                """,
                (
                    job_id_str,
                    omni.flux.job_queue.core.events.StateChange.name,
                    omni.flux.job_queue.core.events.StateChange.name,
                ),
            ).fetchall()

            for row in dep_states:
                event = omni.flux.job_queue.core.serializer.deserialize(row["event"])
                if event.value != JobState.DONE:
                    return JobState.PENDING

            # Get latest state change event for the job itself
            event_row = conn.execute(
                """
                SELECT event FROM job_events
                WHERE job_id = ? AND event_type = ?
                ORDER BY timestamp DESC, id DESC LIMIT 1
                """,
                (job_id_str, omni.flux.job_queue.core.events.StateChange.name),
            ).fetchone()
            if event_row:
                event = omni.flux.job_queue.core.serializer.deserialize(event_row["event"])
                return event.value
            return JobState.UNKNOWN

    def iter_events(
        self,
    ) -> Iterator[tuple[uuid.UUID, omni.flux.job_queue.core.events.JobEvent]]:
        """
        Iterate over all events in the job_events table.
        """
        with self.connection() as conn:
            cur = conn.execute("SELECT job_id, event FROM job_events ORDER BY timestamp, id")
            for row in cur:
                job_id, event = row
                yield (
                    uuid.UUID(job_id),
                    omni.flux.job_queue.core.serializer.deserialize(event),
                )

    def append_event(self, job_id: uuid.UUID | str, event: omni.flux.job_queue.core.events.JobEvent) -> None:
        """
        Append a new event to the events table.
        """
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO job_events (job_id, event_type, event) VALUES (?, ?, ?)",
                (
                    str(job_id),
                    event.name,
                    omni.flux.job_queue.core.serializer.serialize(event),
                ),
            )
            conn.commit()

    def get_latest_event(self, job_id: uuid.UUID | str, event_type: type[EventT] | str) -> EventT | None:
        """
        Get the latest event of a specific type for a given job.

        NOTE: Use `get_job_state` to get the latest StateChange event to get a more accurate JobState value.

        Args:
            job_id (uuid.UUID | str): The ID of the job.
            event_type (type[EventT] | str): The type of the event.

        Returns:
            EventT | None: The latest event of the specified type for the job, or None if not found.
        """
        if not isinstance(event_type, str):
            event_type = event_type.name
        with self.connection() as conn:
            cur = conn.execute(
                "SELECT event FROM job_events WHERE job_id=? AND event_type=? ORDER BY timestamp DESC, id DESC LIMIT 1",
                (str(job_id), event_type),
            )
            row = cur.fetchone()
            return omni.flux.job_queue.core.serializer.deserialize(row[0]) if row else None

    def delete_job(self, job_id: uuid.UUID | str) -> None:
        """
        Delete a job by job_id. Cascades to job_events and job_dependencies.
        """
        with self.connection() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (str(job_id),))
            conn.commit()

    def delete_job_graph(self, graph_id: uuid.UUID | str) -> None:
        """
        Delete a job_graph by graph_id. Cascades to jobs, job_events, and job_dependencies.
        """
        with self.connection() as conn:
            conn.execute("DELETE FROM job_graphs WHERE graph_id = ?", (str(graph_id),))
            conn.commit()


@dataclasses.dataclass
class QueueJob:
    """
    Wraps a Job that exists within a queue, providing methods to check its state,
    wait for completion, and retrieve results.

    This is returned when submitting a JobGraph and provides a convenient API
    for monitoring and waiting on job completion.

    Example::

        queue_jobs = graph.submit()
        for qj in queue_jobs:
            qj.wait()
            result = qj.result()

    Attributes:
        interface: The queue interface for database access.
        graph_id: ID of the graph containing this job.
        graph_name: Human-readable name of the graph.
        job_id: Unique identifier for the job.
    """

    interface: QueueInterface
    graph_id: uuid.UUID
    graph_name: str
    job_id: uuid.UUID

    def exists(self) -> bool:
        """
        Check if the job exists in the queue.
        """
        return bool(self.interface.get_job_by_id(self.job_id))

    def get_state(self) -> JobState:
        """
        Get the jobs current state from the queue.
        """
        return self.interface.get_job_state(self.job_id)

    def get_job(self) -> omni.flux.job_queue.core.job.Job | None:
        """
        Get the Job object from the queue.
        """
        return self.interface.get_job_by_id(self.job_id)

    def wait(
        self,
        states: Container[JobState] = (
            JobState.DONE,
            JobState.FAILED,
        ),
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> None:
        """
        Wait for the job to reach one of the specified `states`.

        Args:
            states (Container[JobState]): The states to wait for. Default is (JobState.DONE, JobState.FAILED).
            poll_interval (float): How often to poll the job state in seconds. Default is 1.0 second.
            timeout (float | None): How long to wait for the job to reach one of the specified states in seconds.
        """
        start_time = time.time()
        while True:
            state = self.get_state()
            if state in states:
                return
            if timeout is not None and (time.time() - start_time) > timeout:
                target_states = ", ".join(target_state.value for target_state in states)
                raise TimeoutError(
                    f"Timeout waiting for job {self.job_id} to reach one of {target_states}; current state is {state}"
                )
            time.sleep(poll_interval)

    def result(self, wait: bool = True, timeout: float | None = None) -> Any:
        """
        Get the results of the job.

        Args:
            wait (bool): If True, wait for the job to reach the DONE or FAILED state before reading the result.
            timeout (float | None): Number of seconds to wait for the job to complete if `wait` is True.
        """

        if wait:
            self.wait(timeout=timeout)

        state = self.get_state()

        if state == JobState.FAILED:
            error_event: omni.flux.job_queue.core.events.Error = self.interface.get_latest_event(
                self.job_id, omni.flux.job_queue.core.events.Error
            )
            if error_event is None:
                raise ValueError("Job failed but no error event found for job")
            error_event.reraise()

        if state == JobState.DONE:
            result_event: omni.flux.job_queue.core.events.Result = self.interface.get_latest_event(
                self.job_id, omni.flux.job_queue.core.events.Result
            )
            if result_event is None:
                raise ValueError("No result event found for job")
            return result_event.value

        raise ValueError(f"Job state {state} not done")


class EventSubscriber:
    """
    Polls for new events and dispatches them to subscribers.

    Useful for UI components that need to react to job state changes.
    Runs in a background thread and uses weak references to avoid
    preventing callback owners from being garbage collected.

    Attributes:
        interface: The queue interface for database access.
        poll_interval: How often to check for new events (seconds).
    """

    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        poll_interval: float = 5.0,
        last_event_id: int | None = None,
    ):
        self.interface = interface
        self.poll_interval = poll_interval
        self._last_event_id = last_event_id
        self._stop_event = threading.Event()
        self._thread = None
        self._callbacks: list[
            omni.flux.job_queue.core.utils.WeakRef[
                Callable[[uuid.UUID, omni.flux.job_queue.core.events.JobEvent], None]
            ]
        ] = []

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.stop()

    def _get_max_event_id(self) -> int:
        with self.interface.connection() as conn:
            row = conn.execute("SELECT MAX(id) FROM job_events").fetchone()
            return row[0] if row[0] is not None else 0

    def subscribe(self, callback: Callable[[uuid.UUID, omni.flux.job_queue.core.events.JobEvent], None]):
        self._callbacks.append(omni.flux.job_queue.core.utils.WeakRef(callback))

    def _poll(self):
        if self._last_event_id is None:
            self._last_event_id = self._get_max_event_id()

        while not self._stop_event.is_set():
            with self.interface.connection() as conn:
                cur = conn.execute(
                    "SELECT id, job_id, event FROM job_events WHERE id > ? ORDER BY id",
                    (self._last_event_id,),
                )
                for row in cur.fetchall():
                    event_id, job_id, event_data = row
                    event = omni.flux.job_queue.core.serializer.deserialize(event_data)

                    # Call callbacks, removing dead references
                    alive_callbacks = []
                    for callback_ref in self._callbacks:
                        callback = callback_ref.get()
                        if callback is None:
                            continue
                        callback(uuid.UUID(job_id), event)
                        alive_callbacks.append(callback_ref)

                    self._callbacks = alive_callbacks
                    self._last_event_id = event_id
            self._stop_event.wait(self.poll_interval)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()
            self._thread = None
