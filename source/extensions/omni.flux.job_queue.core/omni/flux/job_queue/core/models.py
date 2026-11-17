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
import os
import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import carb
from omni.flux.utils.common.path_utils import get_local_path

from .enums import ApplyDisposition, ApplyOperation, JobState
from .errors import JobError
from .job import JobInputPort, JobInputs, JobOutputPort, JobOutputs, JobProgress

if TYPE_CHECKING:
    from .interface import QueueInterface

__all__ = (
    "FileReference",
    "QueueControlEdgeSnapshot",
    "QueueDataConnectionSnapshot",
    "QueueGraphSnapshot",
    "QueueJob",
    "QueueJobDetailsSnapshot",
    "QueueJobSnapshot",
    "QueueLiteralInputSnapshot",
    "UsageSnapshot",
)


@dataclasses.dataclass(frozen=True, slots=True)
class FileReference:
    """Identify a referenced file and the file that refers to it."""

    path: str
    referrer: str


@dataclasses.dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Keep local paths in use and project folders whose dependencies were inspected.

    `used` paths are always kept. A `FileReference` comes from a closed file, so it keeps a folder only when its
    referrer is outside that folder. An output that refers to its own files can still be removed.
    Use `from_urls` to build a snapshot: the fields contain normalized local paths only.
    """

    used: frozenset[str] = frozenset()
    verified_roots: frozenset[str] = frozenset()
    references: frozenset[FileReference] = frozenset()

    @classmethod
    def from_urls(
        cls,
        used: Iterable[str] = (),
        verified_roots: Iterable[str] = (),
        references: Iterable[FileReference] = (),
    ) -> UsageSnapshot:
        """Normalize local paths and remove remote URLs."""
        normalized_paths: dict[str, str | None] = {}

        def normalize(url: str) -> str | None:
            """Normalize each URL once within this snapshot."""
            if url not in normalized_paths:
                normalized_paths[url] = cls._local_path(url)
            return normalized_paths[url]

        normalized_references = (
            FileReference(path=path, referrer=referrer)
            for reference in references
            if (path := normalize(reference.path)) is not None
            and (referrer := normalize(reference.referrer)) is not None
        )
        return cls(
            frozenset(filter(None, map(normalize, used))),
            frozenset(filter(None, map(normalize, verified_roots))),
            frozenset(normalized_references),
        )

    @staticmethod
    def _local_path(url: str) -> str | None:
        """Return the normalized local path of a URL, or None for a remote URL."""
        path = get_local_path(url) if url else None
        return None if path is None else os.path.normcase(os.path.realpath(path))


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
    has_outputs: bool = False


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
            RuntimeError: If the job fails or is skipped without outputs.
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
                RuntimeError: If the job fails or is skipped without outputs.
            """
            while True:
                changed.clear()
                snapshot = self.snapshot()
                if snapshot.state is JobState.DONE or (snapshot.state is JobState.SKIPPED and snapshot.has_outputs):
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
