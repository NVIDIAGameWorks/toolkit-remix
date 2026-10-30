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

__all__ = ["ApplyStageWatcher", "get_apply_stage_watcher"]

from functools import partial
from typing import Any

from carb.eventdispatcher import get_eventdispatcher
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.enums import ApplyDisposition
from omni.flux.job_queue.core.extension import get_job_queue
from omni.usd import StageEventType, get_context


class ApplyStageWatcher:
    """Refresh the Apply jobs of a USD context when its stage opens or closes.

    A stage target applies only to the project it was submitted from, so opening or closing a project changes whether
    its jobs can Apply or Revert. `get_block_reason()` watches the context of every target it checks, so any handler
    with a stage target gets the refresh, and only contexts that have such jobs are watched.
    """

    def __init__(self):
        """Start with no watched context."""
        self._subscriptions: dict[str, list[Any]] = {}

    def watch(self, context_name: str) -> None:
        """Follow the stage of a USD context. Watching it again does nothing."""
        context = get_context(context_name)
        if context is None or context_name in self._subscriptions:
            return
        self._subscriptions[context_name] = [
            get_eventdispatcher().observe_event(
                event_name=context.stage_event_name(event_type),
                on_event=partial(self._on_stage_changed, event_type is StageEventType.OPENED),
                observer_name=f"ApplyStageWatcher:{context_name or 'default'}",
            )
            for event_type in (StageEventType.OPENED, StageEventType.CLOSED)
        ]

    def destroy(self) -> None:
        """Stop following every context."""
        self._subscriptions.clear()

    @staticmethod
    def _on_stage_changed(opened: bool, _event: Any) -> None:
        """Refresh Apply availability, and retry the pending automatic Apply jobs when a project opens."""
        try:
            queue = get_job_queue()
            executor = handlers.get_apply_executor()
        except RuntimeError:
            return  # The Job Queue is shutting down.
        queue.notify_schedule_conditions_changed()
        if not opened:
            return
        # The executor applies only automatic jobs whose handler accepts the opened stage, so every context is safe.
        for snapshot in queue.iter_snapshot():
            if snapshot.apply_disposition is ApplyDisposition.PENDING:
                executor.request_reconcile(snapshot.job_id)


_INSTANCE = ApplyStageWatcher()


def get_apply_stage_watcher() -> ApplyStageWatcher:
    """Return the process-wide stage watcher."""
    return _INSTANCE
