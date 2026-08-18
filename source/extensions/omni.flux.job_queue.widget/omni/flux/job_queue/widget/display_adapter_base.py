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

__all__ = [
    "JobAction",
    "JobDetailDirectories",
    "JobDetailField",
    "JobDetailSection",
    "JobDisplayAdapter",
    "is_standalone",
]

import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import carb.settings
from omni.flux.factory.base import PluginBase
from omni.flux.job_queue.core.job import Job, JobProgress
from omni.flux.job_queue.core.models import QueueJobDetailsSnapshot
from omni.flux.utils.common import EventSubscription

from .constants import STANDALONE_APP_NAMES
from .enums import DisplayState, JobDetailSectionPlacement

if TYPE_CHECKING:
    from .model import QueueModel


def is_standalone() -> bool:
    """Return True if running in a standalone (non-full-app) context.

    Returns:
        Whether the running app name is a known standalone queue app.
    """
    app_name = carb.settings.get_settings().get("/app/name") or ""
    return app_name in STANDALONE_APP_NAMES


@dataclass(frozen=True)
class JobDetailField:
    """Describe one safe ordered product value in a details section."""

    field_id: str
    label: str
    value: str
    tooltip: str = ""

    def __post_init__(self) -> None:
        """Validate stable identifiers and user-facing field text.

        Raises:
            ValueError: If a required identifier or display value is empty.
        """
        if not self.field_id or not self.label or not self.value:
            raise ValueError("Detail fields require non-empty IDs, labels, and values")


@dataclass(frozen=True)
class JobDetailSection:
    """Describe one ordered product-owned details section and its optional local folder."""

    section_id: str
    title: str
    fields: tuple[JobDetailField, ...]
    placement: JobDetailSectionPlacement = JobDetailSectionPlacement.BEFORE_INPUTS
    directory: pathlib.Path | None = None

    def __post_init__(self) -> None:
        """Validate stable identity, content, and placement.

        Raises:
            TypeError: If placement is not a supported enum value.
            ValueError: If identity, title, or fields are empty.
        """
        if not self.section_id or not self.title or not self.fields:
            raise ValueError("Detail sections require non-empty IDs, titles, and fields")
        if not isinstance(self.placement, JobDetailSectionPlacement):
            raise TypeError("Detail section placement must be a JobDetailSectionPlacement")


@dataclass(frozen=True)
class JobDetailDirectories:
    """Identify local directories represented by a job's typed values.

    Attributes:
        input_directory: Shared directory containing the job's input assets, when available.
        output_directory: Shared directory containing the job's output assets, when available.
    """

    input_directory: pathlib.Path | None = None
    output_directory: pathlib.Path | None = None


@dataclass(frozen=True)
class JobAction:
    """Describe one optional product action rendered by the queue.

    Attributes:
        action_id: Stable identifier used for UI lookup and dispatch.
        label: Short user-facing action name.
        style_name: UI style used to render the action icon.
        tooltip: User-facing description of the action.
        enabled: Whether the action accepts interaction for the current job.
    """

    action_id: str
    label: str
    style_name: str
    tooltip: str
    enabled: bool

    def __post_init__(self) -> None:
        """Validate the stable action description.

        Raises:
            ValueError: If a required identifier or user-facing string is empty.
        """
        if not self.action_id or not self.label or not self.style_name or not self.tooltip:
            raise ValueError("Job actions require non-empty IDs, labels, styles, and tooltips")


class JobDisplayAdapter(PluginBase):
    """Extension point for displaying a job type in the queue widget.

    One adapter per job type. Adapters are stateless -- per-job state lives on ``QueueItem``.
    ``context_name`` is passed per-method, not at construction, so the registry can cache
    a single instance per adapter class.
    """

    name: ClassVar[str]
    job_type: ClassVar[type[Job]]
    source_name: ClassVar[str]
    display_name: ClassVar[str]
    active_status_label: ClassVar[str | None] = None

    def get_source_name(self, job: Job) -> str:
        """Return a short product-facing source name.

        Args:
            job: Exact job type owned by this adapter.

        Returns:
            Source label used by filtering and details.
        """
        return self.source_name

    def get_name_display(self, job: Job) -> str:
        """Return a product-facing job name.

        Args:
            job: Exact job type owned by this adapter.

        Returns:
            Compact name rendered in the Job / Stage column.
        """
        return self.display_name

    def get_name_tooltip(self, job: Job) -> str:
        """Return tooltip text for the Name column.

        Args:
            job: Exact job type owned by this adapter.

        Returns:
            Richer name text, such as a full path, for the compact name cell.
        """
        return self.get_name_display(job)

    def get_active_status_label(self, job: Job, progress: JobProgress | None) -> str | None:
        """Return a user-facing active status label.

        Args:
            job: Active exact job type owned by this adapter.
            progress: Latest structured progress, when available.

        Returns:
            Product-specific phrase such as ``Processing textures``, or None
            to retain the generic Running label.
        """
        return self.active_status_label

    def get_active_progress_label(self, job: Job, progress: JobProgress | None) -> str | None:
        """Return a user-facing active progress phrase.

        Args:
            job: Active exact job type owned by this adapter.
            progress: Latest structured progress, when available.

        Returns:
            Product-specific phrase such as ``2 of 4``, or None to use the
            generic structured progress display.
        """
        return None

    def get_waiting_reason(self, job: Job, context_name: str) -> str | None:
        """Return why an otherwise queued product job is temporarily blocked.

        Args:
            job: Exact job type owned by this adapter.
            context_name: Product context used to evaluate the temporary condition.

        Returns:
            Safe user-facing reason, or None when the job is ready to run.
        """
        return None

    def get_state_tooltip(
        self,
        job: Job,
        state: DisplayState,
        state_reason: str | None,
    ) -> str | None:
        """Return product-specific state help for a queue row.

        Args:
            job: Job whose display state needs help text.
            state: Resolved visual state shown by the queue.
            state_reason: Persisted explanation for the job's current core state.

        Returns:
            Product-specific tooltip, or None to use the generic state tooltip.
        """
        return None

    def get_graph_actions(self, job: Job, context_name: str) -> tuple[JobAction, ...]:
        """Return ordered actions owned by the job's graph row.

        Args:
            job: Job contributing actions to its parent graph.
            context_name: USD context in which the product action would run.

        Returns:
            Graph action descriptions in display order, or an empty tuple.
        """
        return ()

    def get_job_actions(self, job: Job, context_name: str) -> tuple[JobAction, ...]:
        """Return ordered actions owned by this child job row.

        Args:
            job: Job for which an action may be available.
            context_name: USD context in which the product action would run.

        Returns:
            Child action descriptions in display order, or an empty tuple.
        """
        return ()

    def subscribe_action_events(self, model: "QueueModel") -> EventSubscription | None:
        """Subscribe a visible queue model to product-owned action changes.

        Args:
            model: Queue model whose product actions should refresh.

        Returns:
            Subscription owned by the queue widget, or None when the adapter has no action events.
        """
        return None

    def get_detail_sections(
        self,
        job: Job,
        details: QueueJobDetailsSnapshot,
        context_name: str,
    ) -> tuple[JobDetailSection, ...]:
        """Return ordered safe product sections for the selected job.

        Args:
            job: Exact typed job represented by the details snapshot.
            details: Public typed ports, topology, and available persisted values.
            context_name: Product context in which the details are displayed.

        Returns:
            Product sections with explicit placement and optional folder ownership, or an empty tuple.
        """
        return ()

    def get_detail_directories(
        self,
        job: Job,
        details: QueueJobDetailsSnapshot,
        context_name: str,
    ) -> JobDetailDirectories:
        """Return local input and output directories represented by this job.

        Args:
            job: Exact typed job represented by the details snapshot.
            details: Public typed ports, topology, and available persisted values.
            context_name: Product context in which the details are displayed.

        Returns:
            Explicit local directories for section-level actions, when available.
        """
        return JobDetailDirectories()

    def execute_action(self, action_id: str, job: Job, context_name: str) -> None:
        """Execute one product action selected by its stable identifier.

        Args:
            action_id: Stable identifier from :meth:`get_graph_actions` or :meth:`get_job_actions`.
            job: Job targeted by the product action.
            context_name: USD context in which to execute the action.
        Raises:
            KeyError: Always unless an adapter implements its advertised action IDs.
        """
        raise KeyError(action_id)
