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

__all__ = ["AssetModifierSubmitter"]

from collections.abc import Callable
from functools import partial
from typing import ClassVar

import carb
from lightspeed.common.constants import WindowNames
from lightspeed.trex.asset_modifiers.core import AssetModifiersCore
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from omni import ui
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.widget import get_job_result_notifier
from omni.flux.job_queue.widget.notifications import post_submission_notification
from omni.flux.utils.common.task_tracker import TaskTracker
from omni.flux.utils.dialog.progress_popup import ProgressPopup
from omni.kit.app import get_app
from omni.kit.notification_manager import NotificationButtonInfo, NotificationStatus, post_notification


class AssetModifierSubmitter:
    """Submit the active modifier with a cancellable progress popup and report the result, once per USD context."""

    _submissions: ClassVar[TaskTracker] = TaskTracker()
    _focus_requests: ClassVar[TaskTracker] = TaskTracker()
    _result_listeners: ClassVar[dict[str, Callable[[str], None]]] = {}

    @classmethod
    def submit(cls, context_name: str, prim_paths: list[str] | None = None) -> None:
        """Prepare and submit the active modifier unless the context already has a pending submission."""
        cls._submissions.start(context_name, partial(cls._prepare_and_submit, context_name, prim_paths))

    @classmethod
    def set_result_listener(cls, context_name: str, callback: Callable[[str], None] | None) -> None:
        """Set or clear the current panel's result callback for one USD context."""
        if callback is None:
            cls._result_listeners.pop(context_name, None)
        else:
            cls._result_listeners[context_name] = callback

    @classmethod
    def cancel_pending_submissions(cls) -> None:
        """Cancel pending submissions. Each keeps its context until its cancellation settles."""
        cls._submissions.cancel_all()
        cls.cancel_pending_window_focus()

    @classmethod
    def cancel_pending_window_focus(cls) -> None:
        """Cancel deferred focus requests before their owner shuts down."""
        cls._focus_requests.cancel_all()

    @classmethod
    def show_window(cls, title: str) -> None:
        """Show and focus a workspace window without changing the layout."""
        ui.Workspace.show_window(title, True)
        cls._focus_requests.start(title, partial(cls._focus_window, title))

    @staticmethod
    async def _focus_window(title: str) -> None:
        """Focus the tab after the workspace applies its visibility change."""
        await get_app().next_update_async()
        if window := ui.Workspace.get_window(title):
            window.focus()

    @classmethod
    async def _prepare_and_submit(cls, context_name: str, prim_paths: list[str] | None) -> None:
        """Prepare graphs behind a cancellable progress popup, submit them, and report the result."""
        try:
            core = AssetModifiersCore(context_name)
            modifier_type = core.active_modifier
            modifier = modifier_type() if modifier_type is not None else None
            (graphs, skipped), cancelled = await ProgressPopup.run_cancellable(
                "Preparing Asset Modifier Jobs",
                "Preparing jobs...",
                partial(core.prepare_submission, prim_paths=prim_paths),
            )
            if cancelled:
                return
            if graphs:
                queue = get_job_queue()
                try:
                    await run_in_worker_thread(queue.submit_graphs, graphs)
                finally:
                    get_job_result_notifier().register_graphs(
                        graphs,
                        summarize=(lambda job_id: modifier.summarize_result(queue.get_job_outputs(job_id)))
                        if modifier is not None
                        else None,
                        on_result=partial(cls._on_result, context_name),
                    )
            post_submission_notification(
                len(graphs),
                list(skipped.values()),
                button_infos=[
                    NotificationButtonInfo(
                        "Open Job Queue", on_complete=lambda *_: cls.show_window(WindowNames.JOB_QUEUE.value)
                    )
                ],
            )
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_warn(f"Failed to submit asset modifier jobs: {error}")
            post_notification(f"No jobs were added to the job queue. {error}", status=NotificationStatus.WARNING)

    @classmethod
    def _on_result(cls, context_name: str, message: str) -> None:
        """Deliver a result to the context's current panel, if one exists."""
        if listener := cls._result_listeners.get(context_name):
            listener(message)
