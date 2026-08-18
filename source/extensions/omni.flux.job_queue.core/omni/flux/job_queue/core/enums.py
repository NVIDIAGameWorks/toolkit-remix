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
    "EXECUTING_JOB_STATES",
    "TERMINAL_JOB_STATES",
    "ApplyCommand",
    "ApplyDisposition",
    "ApplyOperation",
    "ApplyPolicy",
    "JobState",
    "TimestampMode",
]

from enum import Enum, StrEnum, auto


class TimestampMode(StrEnum):
    """Display mode for job queue timestamps."""

    RELATIVE = "relative"
    ABSOLUTE = "absolute"


class ApplyDisposition(StrEnum):
    """Describe the durable user-facing disposition of one job output."""

    NOT_READY = "not_ready"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    APPLIED = "applied"
    DECLINED = "declined"


class ApplyCommand(Enum):
    """Identify one in-memory command submitted to the Apply executor."""

    APPLY = auto()
    REVERT = auto()
    RECONCILE = auto()


class ApplyOperation(StrEnum):
    """Describe the latest or active operation without replacing disposition."""

    IDLE = "idle"
    APPLYING = "applying"
    REAPPLYING = "reapplying"
    REVERTING = "reverting"
    APPLY_FAILED = "apply_failed"
    REAPPLY_FAILED = "reapply_failed"
    REVERT_FAILED = "revert_failed"


class ApplyPolicy(StrEnum):
    """Control whether a newly ready output is applied automatically."""

    ALWAYS_AUTOMATIC = "always_automatic"
    ALWAYS_MANUAL = "always_manual"
    FOLLOW_GLOBAL = "follow_global"


class JobState(StrEnum):
    """Persisted and derived states of a queue job.

    TODO: Add CANCELLED state to support cancelling in-progress jobs. For long-running
    workflows (e.g., ComfyUI), users will want to cancel jobs. This requires changes to
    the executor and scheduler to support cooperative cancellation.
    """

    UNKNOWN = "UNKNOWN"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    WAITING_FOR_DEPENDENCIES = "WAITING_FOR_DEPENDENCIES"

    @property
    def is_persisted(self) -> bool:
        """Return whether this state may be stored in SQLite.

        Returns:
            ``False`` for UI-only derived states.
        """
        return self not in (JobState.UNKNOWN, JobState.WAITING_FOR_DEPENDENCIES)


EXECUTING_JOB_STATES = frozenset((JobState.SCHEDULED, JobState.IN_PROGRESS))
TERMINAL_JOB_STATES = frozenset((JobState.DONE, JobState.FAILED, JobState.SKIPPED))
