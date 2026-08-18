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
import datetime
import uuid
from typing import TYPE_CHECKING, Any

import carb

from .enums import ApplyDisposition, ApplyOperation, JobState
from .errors import JobError
from .job import JobInputPort, JobInputs, JobOutputPort, JobOutputs, JobProgress

if TYPE_CHECKING:
    from .interface import QueueInterface

__all__ = (
    "QueueControlEdgeSnapshot",
    "QueueDataConnectionSnapshot",
    "QueueGraphSnapshot",
    "QueueJob",
    "QueueJobDetailsSnapshot",
    "QueueJobSnapshot",
    "QueueLiteralInputSnapshot",
)


@dataclasses.dataclass(frozen=True, slots=True)
class QueueJobSnapshot:
    """Represent immutable current state for one persisted child job."""

    graph_id: uuid.UUID
    graph_name: str
    graph_position: int
    job_id: uuid.UUID
    job_name: str
    job_type: str
    position: int
    submitted_at: datetime.datetime
    state: JobState
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    state_reason: str | None
    progress: JobProgress | None
    error: JobError | None
    apply_disposition: ApplyDisposition
    apply_operation: ApplyOperation
    apply_handler_id: str | None
    apply_reason: str | None
    apply_error: JobError | None


@dataclasses.dataclass(frozen=True, slots=True)
class QueueGraphSnapshot:
    """Represent one graph root and its ordered current child snapshots."""

    graph_id: uuid.UUID
    name: str
    position: int
    submitted_at: datetime.datetime
    jobs: tuple[QueueJobSnapshot, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class QueueDataConnectionSnapshot:
    """Describe one typed graph data edge related to a selected job."""

    source_job_id: uuid.UUID
    source_port: JobOutputPort[Any]
    target_job_id: uuid.UUID
    target_port: JobInputPort[Any]


@dataclasses.dataclass(frozen=True, slots=True)
class QueueLiteralInputSnapshot:
    """Describe one typed literal binding, optionally including its value."""

    job_id: uuid.UUID
    port: JobInputPort[Any]
    value: Any | None


@dataclasses.dataclass(frozen=True, slots=True)
class QueueControlEdgeSnapshot:
    """Describe one control-only graph edge related to a selected job."""

    target_job_id: uuid.UUID
    prerequisite_job_id: uuid.UUID


@dataclasses.dataclass(frozen=True, slots=True)
class QueueJobDetailsSnapshot:
    """Expose targeted read-only topology and optional typed values for one job."""

    job: QueueJobSnapshot
    input_ports: tuple[JobInputPort[Any], ...]
    output_ports: tuple[JobOutputPort[Any], ...]
    connections: tuple[QueueDataConnectionSnapshot, ...]
    literal_inputs: tuple[QueueLiteralInputSnapshot, ...]
    control_edges: tuple[QueueControlEdgeSnapshot, ...]
    inputs: JobInputs | None
    outputs: JobOutputs | None


@dataclasses.dataclass(frozen=True, slots=True)
class QueueJob:
    """Provide a stable handle to one submitted child job."""

    interface: QueueInterface = dataclasses.field(repr=False, compare=False)
    graph_id: uuid.UUID
    job_id: uuid.UUID

    def snapshot(self) -> QueueJobSnapshot:
        """Return current immutable job state.

        Returns:
            Current snapshot.
        """
        return self.interface.get_job_snapshot(self.job_id)

    async def outputs(self, timeout: float | None = None) -> JobOutputs:
        """Wait for and return terminal successful outputs.

        Args:
            timeout: Optional maximum wait in seconds.

        Returns:
            Exact typed outputs.

        Raises:
            KeyError: If the job is deleted while waiting.
            RuntimeError: If the job fails or is skipped.
            TimeoutError: If the timeout expires.
        """
        changed = asyncio.Event()
        loop = asyncio.get_running_loop()

        def wake() -> None:
            """Wake this waiter from a queue callback on any thread."""
            if loop.is_closed():
                return
            try:
                loop.call_soon_threadsafe(changed.set)
            except RuntimeError as error:
                carb.log_error(f"Could not wake output waiter for job {self.job_id}: {error}")

        def on_job_changed(changed_id: uuid.UUID) -> None:
            """Wake this waiter after its target job changes.

            Args:
                changed_id: Identifier emitted by the queue change event.
            """
            if changed_id == self.job_id:
                wake()

        subscriptions = [self.interface.subscribe_job_changed(on_job_changed)]
        try:
            subscriptions.append(self.interface.subscribe_mutation(wake))
        except Exception:
            subscriptions.clear()
            raise

        async def wait() -> JobOutputs:
            """Wait on targeted state changes until terminal.

            Returns:
                Exact typed outputs from a successfully completed job.

            Raises:
                KeyError: If the job is deleted while waiting.
                RuntimeError: If the job fails or is skipped.
            """
            while True:
                changed.clear()
                snapshot = self.snapshot()
                if snapshot.state is JobState.DONE:
                    return self.interface.get_job_outputs(self.job_id)
                if snapshot.state is JobState.FAILED:
                    if snapshot.error is not None:
                        snapshot.error.reraise()
                    raise RuntimeError(snapshot.state_reason or "Job failed")
                if snapshot.state is JobState.SKIPPED:
                    raise RuntimeError(snapshot.state_reason or "Job was skipped")
                await changed.wait()

        try:
            return await wait() if timeout is None else await asyncio.wait_for(wait(), timeout)
        finally:
            subscriptions.clear()
