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
    "BulkOperationPhase",
    "ColumnKey",
    "DisplayState",
    "JobDetailSectionPlacement",
    "LogStream",
]

from enum import Enum, StrEnum, auto


class BulkOperationPhase(Enum):
    """Identify whether a bulk-operation notification starts or finishes work."""

    STARTING = auto()
    FINISHED = auto()


class JobDetailSectionPlacement(Enum):
    """Place product-owned details relative to the generic typed-port sections."""

    BEFORE_INPUTS = auto()
    AFTER_OUTPUTS = auto()


class LogStream(StrEnum):
    """Known log streams produced by queued jobs."""

    STDOUT = "stdout"
    STDERR = "stderr"


class ColumnKey(StrEnum):
    """Stable identifiers for visible job queue columns."""

    JOB_STAGE = "job_stage"
    STATUS = "status"
    COMPLETED = "completed"
    APPLY = "apply"
    ACTIONS = "actions"


class DisplayState(StrEnum):
    """Represent a job state as presented by the queue UI.

    Core job states map through the queue model, while waiting, apply-lifecycle,
    and corrupted states incorporate runtime and adapter context.
    """

    def __new__(
        cls,
        value: str,
        label: str,
        status_style_name: str,
        tooltip: str | None,
        detail_tooltip: str | None = None,
    ):
        """Construct one display state with compact and detailed presentation metadata.

        Args:
            value: Stable serialized state value.
            label: User-facing status label.
            status_style_name: Compact status-pill style selector.
            tooltip: Compact status help, when generic help is available.
            detail_tooltip: Optional details-specific help override.

        Returns:
            Initialized display-state enum member.
        """
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        obj.status_style_name = status_style_name
        obj.tooltip = tooltip
        obj.detail_tooltip = tooltip if detail_tooltip is None else detail_tooltip
        return obj

    QUEUED = ("queued", "Queued", "StatusQueued", "Waiting for this job to start.")
    WAITING = ("waiting", "Waiting", "StatusWaiting", None, "This job is waiting.")
    WAITING_FOR_DEPENDENCIES = (
        "waiting_for_dependencies",
        "Waiting",
        "StatusWaiting",
        None,
        "Waiting for other jobs to finish.",
    )
    IN_PROGRESS = (
        "in_progress",
        "Running",
        "StatusProcessing",
        "This job is running.",
    )
    DONE = ("done", "Done", "StatusApplied", "This job is complete.")
    READY_TO_APPLY = (
        "ready_to_apply",
        "Ready to Apply",
        "StatusReadyToApply",
        "The results are ready to add to the project.",
    )
    APPLY_FAILED = (
        "apply_failed",
        "Apply Failed",
        "StatusFailed",
        "The results could not be added to the project. Select Apply to try again.",
    )
    APPLYING = (
        "applying",
        "Applying...",
        "StatusApplying",
        "Adding the results to the project.",
    )
    REAPPLYING = (
        "reapplying",
        "Reapplying...",
        "StatusApplying",
        "Updating the project with these results.",
    )
    REVERTING = (
        "reverting",
        "Reverting...",
        "StatusApplying",
        "Restoring the project to its previous values.",
    )
    APPLIED = (
        "applied",
        "Applied",
        "StatusApplied",
        "The results were added to the project.",
    )
    PARTIALLY_APPLIED = (
        "partially_applied",
        "Partially Applied",
        "StatusApplied",
        "Some results were added to the project and others were declined.",
    )
    DECLINED = (
        "declined",
        "Declined",
        "StatusWaiting",
        "These results will not be added to the project.",
    )
    REAPPLY_FAILED = (
        "reapply_failed",
        "Reapply Failed",
        "StatusFailed",
        "The project could not be updated. Select Apply to try again.",
    )
    REVERT_FAILED = (
        "revert_failed",
        "Revert Failed",
        "StatusFailed",
        "The previous project values could not be restored. Select Revert to try restoring them again.",
    )
    HANDLER_UNAVAILABLE = (
        "handler_unavailable",
        "Unavailable",
        "StatusFailed",
        "The feature needed for this action is unavailable.",
    )
    FAILED = (
        "failed",
        "Failed",
        "StatusFailed",
        None,
        "This job could not finish. Edit and submit it again.",
    )
    SKIPPED = (
        "skipped",
        "Skipped",
        "StatusWaiting",
        "This job was skipped.",
    )
    CORRUPTED = (
        "corrupted",
        "Unavailable",
        "StatusFailed",
        "This job cannot be displayed. Delete it and submit it again.",
    )
