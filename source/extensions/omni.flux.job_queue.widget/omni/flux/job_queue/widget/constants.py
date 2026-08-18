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

import pathlib
import re
import sqlite3

from omni import ui
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, JobState

from .enums import ColumnKey, DisplayState

__all__ = (
    "ABSOLUTE_TIMESTAMP_FORMAT",
    "ACTIONS_COLUMN_WIDTH",
    "ACTIVE_APPLY_OPERATIONS",
    "ADAPTER_ERRORS",
    "AGGREGATE_PRECEDENCE",
    "ALL_APPLY_FILTERS",
    "ALL_STATUS_FILTERS",
    "APPLY_COLUMN_WIDTH",
    "APPLY_DISPOSITION_LABELS",
    "APPLY_DISPOSITION_TO_DISPLAY",
    "APPLY_FILTER_OPTIONS",
    "APPLY_MODE_BADGE_HEIGHT",
    "APPLY_MODE_BADGE_WIDTH",
    "APPLY_OPERATION_TO_DISPLAY",
    "BRANCH_COLUMN_WIDTH",
    "BRANCH_ICON_SIZE",
    "COMPLETED_COLUMN_WIDTH",
    "EMPTY_STATE_ICON_SIZE",
    "FAILED_FILTER_STATES",
    "GRAPH_DELETE_ERRORS",
    "HANDLER_AVAILABILITY_ERRORS",
    "ICON_SIZE_LARGE",
    "ICON_SIZE_MEDIUM",
    "ICON_SIZE_SMALL",
    "JOB_LOAD_ERRORS",
    "JOB_STATE_TO_DISPLAY",
    "LOG_TIMESTAMP_PATTERN",
    "MONOSPACE_FONT_PATH",
    "OPERATION_ERRORS",
    "PADDING_EXTRA_LARGE",
    "PADDING_LARGE",
    "PADDING_MEDIUM",
    "PADDING_SMALL",
    "PROBLEM_DISPLAY_STATES",
    "READY_TO_APPLY_FILTER_STATES",
    "RELATIVE_TIME_THRESHOLDS",
    "ROW_COLUMNS",
    "ROW_HEIGHT",
    "SCROLLBAR_SPACING",
    "SNAPSHOT_READ_ERRORS",
    "STANDALONE_APP_NAMES",
    "STATUS_COLUMN_WIDTH",
    "STATUS_FILTER_OPTIONS",
    "STATUS_PILL_HEIGHT",
    "TASK_SCHEDULING_ERRORS",
    "TERMINAL_JOB_STATES",
    "TOOLBAR_HEIGHT",
    "UUID_TEXT_PATTERN",
)

PADDING_SMALL = ui.Pixel(4)
PADDING_MEDIUM = ui.Pixel(8)
PADDING_LARGE = ui.Pixel(12)
PADDING_EXTRA_LARGE = ui.Pixel(16)
ICON_SIZE_SMALL = ui.Pixel(16)
ICON_SIZE_MEDIUM = ui.Pixel(20)
ICON_SIZE_LARGE = ui.Pixel(24)
APPLY_MODE_BADGE_HEIGHT = ui.Pixel(16)
APPLY_MODE_BADGE_WIDTH = ui.Pixel(48)
EMPTY_STATE_ICON_SIZE = ui.Pixel(36)
BRANCH_COLUMN_WIDTH = ui.Pixel(16)
BRANCH_ICON_SIZE = ui.Pixel(10)
ROW_HEIGHT = ui.Pixel(28)
SCROLLBAR_SPACING = ui.Pixel(12)
COLUMN_SEPARATOR_HALF_WIDTH = ui.Pixel(1)
STATUS_PILL_HEIGHT = ui.Pixel(20)
TOOLBAR_HEIGHT = ui.Pixel(36)
STATUS_COLUMN_WIDTH = ui.Pixel(260)
COMPLETED_COLUMN_WIDTH = ui.Pixel(180)
APPLY_COLUMN_WIDTH = ui.Pixel(80)
ACTIONS_COLUMN_WIDTH = ui.Pixel(108)
MONOSPACE_FONT_PATH = str(pathlib.Path(__file__).parents[4] / "data" / "fonts" / "RobotoMono-SemiBold.ttf")

ROW_COLUMNS: tuple[tuple[ColumnKey, str, ui.Length], ...] = (
    (ColumnKey.JOB_STAGE, "Job / Stage", ui.Fraction(2)),
    (ColumnKey.STATUS, "Status", STATUS_COLUMN_WIDTH),
    (ColumnKey.COMPLETED, "Completed", COMPLETED_COLUMN_WIDTH),
    (ColumnKey.APPLY, "Apply", APPLY_COLUMN_WIDTH),
    (ColumnKey.ACTIONS, "Actions", ACTIONS_COLUMN_WIDTH),
)
ABSOLUTE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
RELATIVE_TIME_THRESHOLDS: tuple[tuple[int, int, str], ...] = (
    (60, 1, "minute"),
    (1440, 60, "hour"),
    (10080, 1440, "day"),
    (43800, 10080, "week"),
    (525600, 43800, "month"),
    (0, 525600, "year"),
)

STANDALONE_APP_NAMES = frozenset({"rtx_remix_job_queue"})

APPLY_FILTER_OPTIONS: tuple[tuple[ApplyDisposition, str], ...] = (
    (ApplyDisposition.NOT_READY, "Not Ready"),
    (ApplyDisposition.NOT_APPLICABLE, "No Apply Needed"),
    (ApplyDisposition.PENDING, "Ready to Apply"),
    (ApplyDisposition.APPLIED, "Applied"),
    (ApplyDisposition.DECLINED, "Declined"),
)
APPLY_DISPOSITION_LABELS: dict[ApplyDisposition, str] = dict(APPLY_FILTER_OPTIONS)
ALL_APPLY_FILTERS: frozenset[ApplyDisposition] = frozenset(disposition for disposition, _ in APPLY_FILTER_OPTIONS)

ACTIVE_APPLY_OPERATIONS = frozenset((ApplyOperation.APPLYING, ApplyOperation.REAPPLYING, ApplyOperation.REVERTING))
APPLY_OPERATION_TO_DISPLAY: dict[ApplyOperation, DisplayState] = {
    ApplyOperation.APPLYING: DisplayState.APPLYING,
    ApplyOperation.REAPPLYING: DisplayState.REAPPLYING,
    ApplyOperation.REVERTING: DisplayState.REVERTING,
    ApplyOperation.APPLY_FAILED: DisplayState.APPLY_FAILED,
    ApplyOperation.REAPPLY_FAILED: DisplayState.REAPPLY_FAILED,
    ApplyOperation.REVERT_FAILED: DisplayState.REVERT_FAILED,
}
APPLY_DISPOSITION_TO_DISPLAY: dict[ApplyDisposition, DisplayState] = {
    ApplyDisposition.PENDING: DisplayState.READY_TO_APPLY,
    ApplyDisposition.APPLIED: DisplayState.APPLIED,
    ApplyDisposition.DECLINED: DisplayState.DECLINED,
}
READY_TO_APPLY_FILTER_STATES = frozenset(
    (DisplayState.READY_TO_APPLY, DisplayState.APPLYING, DisplayState.REAPPLYING, DisplayState.REVERTING)
)
FAILED_FILTER_STATES = frozenset(
    (
        DisplayState.FAILED,
        DisplayState.APPLY_FAILED,
        DisplayState.REAPPLY_FAILED,
        DisplayState.REVERT_FAILED,
        DisplayState.HANDLER_UNAVAILABLE,
        DisplayState.CORRUPTED,
    )
)
AGGREGATE_PRECEDENCE = (
    DisplayState.CORRUPTED,
    DisplayState.FAILED,
    DisplayState.APPLY_FAILED,
    DisplayState.REAPPLY_FAILED,
    DisplayState.REVERT_FAILED,
    DisplayState.HANDLER_UNAVAILABLE,
    DisplayState.APPLYING,
    DisplayState.REAPPLYING,
    DisplayState.REVERTING,
    DisplayState.IN_PROGRESS,
    DisplayState.WAITING_FOR_DEPENDENCIES,
    DisplayState.WAITING,
    DisplayState.QUEUED,
    DisplayState.READY_TO_APPLY,
)
PROBLEM_DISPLAY_STATES = frozenset(
    (
        DisplayState.FAILED,
        DisplayState.SKIPPED,
        DisplayState.WAITING_FOR_DEPENDENCIES,
        DisplayState.WAITING,
        DisplayState.APPLY_FAILED,
        DisplayState.REAPPLY_FAILED,
        DisplayState.REVERT_FAILED,
        DisplayState.HANDLER_UNAVAILABLE,
        DisplayState.CORRUPTED,
    )
)
TERMINAL_JOB_STATES = frozenset((JobState.DONE, JobState.FAILED, JobState.SKIPPED))

ADAPTER_ERRORS = (KeyError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error)
HANDLER_AVAILABILITY_ERRORS = (KeyError, RuntimeError, TypeError, ValueError, sqlite3.Error)
JOB_LOAD_ERRORS = (KeyError, RuntimeError, TypeError, ValueError, sqlite3.Error)
SNAPSHOT_READ_ERRORS = (KeyError, RuntimeError, sqlite3.Error)
GRAPH_DELETE_ERRORS = (KeyError, OSError, RuntimeError, sqlite3.Error)
OPERATION_ERRORS = (KeyError, OSError, RuntimeError, TypeError, ValueError)
TASK_SCHEDULING_ERRORS = (RuntimeError, TypeError)

LOG_TIMESTAMP_PATTERN = re.compile(r"^\[(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\]")
UUID_TEXT_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)

JOB_STATE_TO_DISPLAY: dict[JobState, DisplayState] = {
    JobState.UNKNOWN: DisplayState.CORRUPTED,
    JobState.QUEUED: DisplayState.QUEUED,
    JobState.SCHEDULED: DisplayState.QUEUED,
    JobState.IN_PROGRESS: DisplayState.IN_PROGRESS,
    JobState.DONE: DisplayState.DONE,
    JobState.FAILED: DisplayState.FAILED,
    JobState.SKIPPED: DisplayState.SKIPPED,
    JobState.WAITING_FOR_DEPENDENCIES: DisplayState.WAITING_FOR_DEPENDENCIES,
}

STATUS_FILTER_OPTIONS: tuple[tuple[DisplayState, str], ...] = (
    (DisplayState.QUEUED, "Queued"),
    (DisplayState.WAITING, "Waiting"),
    (DisplayState.WAITING_FOR_DEPENDENCIES, "Waiting for Other Jobs"),
    (DisplayState.IN_PROGRESS, "Running"),
    (DisplayState.DONE, "Done"),
    (DisplayState.READY_TO_APPLY, "Ready to Apply"),
    (DisplayState.FAILED, "Failed"),
    (DisplayState.SKIPPED, "Skipped"),
    (DisplayState.APPLIED, "Applied"),
    (DisplayState.DECLINED, "Declined"),
)
ALL_STATUS_FILTERS: frozenset[DisplayState] = frozenset(display_state for display_state, _ in STATUS_FILTER_OPTIONS)
