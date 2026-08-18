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

import dataclasses
import datetime
import uuid

import carb
from omni import ui
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, JobState
from omni.flux.job_queue.core.errors import JobError
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.models import QueueJobSnapshot
from omni.flux.job_queue.core.job import Job, JobProgress

from .constants import ADAPTER_ERRORS, JOB_LOAD_ERRORS, ROW_COLUMNS
from .display_adapter_base import JobDisplayAdapter
from .enums import ColumnKey
from .extension import get_display_adapter_registry

__all__ = ("Row",)


@dataclasses.dataclass
class Row:
    """Mutable presentation data for one persisted job snapshot."""

    job_id: uuid.UUID
    graph_id: uuid.UUID
    graph_name: str
    graph_position: int
    name: str
    job_type: str
    position: int
    submitted_at: datetime.datetime
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    state: JobState
    state_reason: str | None
    progress: JobProgress | None
    error: JobError | None
    apply_disposition: ApplyDisposition
    apply_operation: ApplyOperation
    apply_reason: str | None
    apply_error: JobError | None
    interface: QueueInterface = dataclasses.field(repr=False, compare=False)
    job: Job | None = dataclasses.field(default=None, repr=False, compare=False)
    adapter: JobDisplayAdapter | None = dataclasses.field(default=None, repr=False, compare=False)
    source: str = "Unknown"
    is_corrupted: bool = False

    @classmethod
    def keys(cls) -> list[ColumnKey]:
        """Return visible column keys in display order.

        Returns:
            Visible column keys.
        """
        return [key for key, _header, _width in ROW_COLUMNS]

    @classmethod
    def get_column_headers(cls) -> list[str]:
        """Return visible column labels.

        Returns:
            User-facing column labels.
        """
        return [header for _key, header, _width in ROW_COLUMNS]

    @classmethod
    def get_column_widths(cls) -> list[ui.Length]:
        """Return visible column widths.

        Returns:
            Native UI lengths in display order.
        """
        return [width for _key, _header, width in ROW_COLUMNS]

    @classmethod
    def from_snapshot(cls, snapshot: QueueJobSnapshot, interface: QueueInterface) -> Row:
        """Create a row from a core snapshot and exact-type adapter lookup.

        Args:
            snapshot: Immutable core presentation snapshot.
            interface: Queue interface used to load the typed job.

        Returns:
            Mutable row that can be updated without replacing its tree item.
        """
        job = None
        adapter = None
        source = "Unknown"
        name = snapshot.job_name
        is_corrupted = False
        try:
            job = interface.get_job(snapshot.job_id)
        except JOB_LOAD_ERRORS as error:
            carb.log_error(f"Failed to load queue job {snapshot.job_id}: {error}")
            is_corrupted = True

        if job is not None:
            try:
                adapter = get_display_adapter_registry().get_adapter(job)
            except ADAPTER_ERRORS as error:
                carb.log_warn(f"No display adapter is available for queue job {snapshot.job_id}: {error}")
            if adapter is not None:
                try:
                    name = adapter.get_name_display(job)
                except ADAPTER_ERRORS as error:
                    carb.log_warn(f"Could not resolve the display name for queue job {snapshot.job_id}: {error}")
                try:
                    source = adapter.get_source_name(job)
                except ADAPTER_ERRORS as error:
                    carb.log_warn(f"Could not resolve the source name for queue job {snapshot.job_id}: {error}")

        return cls(
            job_id=snapshot.job_id,
            graph_id=snapshot.graph_id,
            graph_name=snapshot.graph_name,
            graph_position=snapshot.graph_position,
            name=f"{name} (unavailable)" if is_corrupted else name,
            job_type=snapshot.job_type,
            position=snapshot.position,
            submitted_at=snapshot.submitted_at,
            started_at=snapshot.started_at,
            completed_at=snapshot.completed_at,
            state=snapshot.state,
            state_reason=snapshot.state_reason,
            progress=snapshot.progress,
            error=snapshot.error,
            apply_disposition=snapshot.apply_disposition,
            apply_operation=snapshot.apply_operation,
            apply_reason=snapshot.apply_reason,
            apply_error=snapshot.apply_error,
            interface=interface,
            job=job,
            adapter=adapter,
            source=source,
            is_corrupted=is_corrupted,
        )

    def update_from(self, other: Row) -> bool:
        """Copy refreshed presentation values while preserving this row object.

        Args:
            other: Newly built row for the same durable job.

        Returns:
            True when any presentation value changed.
        """
        changed = (
            self.graph_name,
            self.graph_position,
            self.name,
            self.job_type,
            self.position,
            self.submitted_at,
            self.started_at,
            self.completed_at,
            self.state,
            self.state_reason,
            self.progress,
            self.error,
            self.apply_disposition,
            self.apply_operation,
            self.apply_reason,
            self.apply_error,
            self.source,
            self.is_corrupted,
        ) != (
            other.graph_name,
            other.graph_position,
            other.name,
            other.job_type,
            other.position,
            other.submitted_at,
            other.started_at,
            other.completed_at,
            other.state,
            other.state_reason,
            other.progress,
            other.error,
            other.apply_disposition,
            other.apply_operation,
            other.apply_reason,
            other.apply_error,
            other.source,
            other.is_corrupted,
        )
        self.graph_name = other.graph_name
        self.graph_position = other.graph_position
        self.name = other.name
        self.job_type = other.job_type
        self.position = other.position
        self.submitted_at = other.submitted_at
        self.started_at = other.started_at
        self.completed_at = other.completed_at
        self.state = other.state
        self.state_reason = other.state_reason
        self.progress = other.progress
        self.error = other.error
        self.apply_disposition = other.apply_disposition
        self.apply_operation = other.apply_operation
        self.apply_reason = other.apply_reason
        self.apply_error = other.apply_error
        self.job = other.job
        self.adapter = other.adapter
        self.source = other.source
        self.is_corrupted = other.is_corrupted
        return changed
