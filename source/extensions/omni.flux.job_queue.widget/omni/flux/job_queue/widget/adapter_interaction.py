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

import carb
from omni.flux.job_queue.core.models import QueueJobDetailsSnapshot

from .constants import ADAPTER_ERRORS
from .display_adapter_base import JobAction, JobDetailDirectories, JobDetailSection
from .row import Row

__all__ = (
    "execute_action",
    "get_detail_directories",
    "get_detail_sections",
    "get_graph_actions",
    "get_job_actions",
)


def get_detail_directories(
    row: Row,
    details: QueueJobDetailsSnapshot,
    context_name: str,
) -> JobDetailDirectories:
    """Return safe local detail directories from the row's adapter.

    Args:
        row: Child presentation data with an optional exact-type adapter.
        details: Public typed details snapshot.
        context_name: Product context used to resolve detail directories.

    Returns:
        Explicit input and output directories, or an empty value on failure.
    """
    if row.adapter is None or row.job is None:
        return JobDetailDirectories()
    try:
        return row.adapter.get_detail_directories(row.job, details, context_name)
    except ADAPTER_ERRORS as error:
        carb.log_warn(f"Could not resolve detail directories for queue job {row.job_id}: {error}")
        return JobDetailDirectories()


def get_graph_actions(row: Row, context_name: str) -> tuple[JobAction, ...]:
    """Return safe ordered graph actions from the row's adapter.

    Args:
        row: Child whose adapter contributes actions to its parent graph.
        context_name: Product context used to resolve actions.

    Returns:
        Ordered graph actions, or an empty tuple on failure.
    """
    if row.adapter is None or row.job is None:
        return ()
    try:
        return row.adapter.get_graph_actions(row.job, context_name)
    except ADAPTER_ERRORS as error:
        carb.log_warn(f"Could not resolve graph actions for queue job {row.job_id}: {error}")
        return ()


def get_job_actions(row: Row, context_name: str) -> tuple[JobAction, ...]:
    """Return safe ordered child actions from the row's adapter.

    Args:
        row: Child presentation data with an optional exact-type adapter.
        context_name: Product context used to resolve actions.

    Returns:
        Ordered child actions, or an empty tuple on failure.
    """
    if row.adapter is None or row.job is None:
        return ()
    try:
        return row.adapter.get_job_actions(row.job, context_name)
    except ADAPTER_ERRORS as error:
        carb.log_warn(f"Could not resolve child actions for queue job {row.job_id}: {error}")
        return ()


def get_detail_sections(
    row: Row,
    details: QueueJobDetailsSnapshot,
    context_name: str,
) -> tuple[JobDetailSection, ...]:
    """Return safe ordered product sections from the row's adapter.

    Args:
        row: Child presentation data with an optional exact-type adapter.
        details: Public typed details snapshot.
        context_name: Product context used to resolve detail sections.

    Returns:
        Ordered safe product sections, or an empty tuple on failure.
    """
    if row.adapter is None or row.job is None:
        return ()
    try:
        return row.adapter.get_detail_sections(row.job, details, context_name)
    except ADAPTER_ERRORS as error:
        carb.log_warn(f"Could not resolve product details for queue job {row.job_id}: {error}")
        return ()


def execute_action(row: Row, action_id: str, context_name: str) -> None:
    """Execute one stable product action behind the shared failure boundary.

    Args:
        row: Child presentation data with an optional exact-type adapter.
        action_id: Stable selected action identifier.
        context_name: Product context used for the action.
    """
    if row.adapter is None or row.job is None:
        return
    try:
        row.adapter.execute_action(action_id, row.job, context_name)
    except ADAPTER_ERRORS as error:
        carb.log_warn(f"Could not execute action {action_id} for queue job {row.job_id}: {error}")
