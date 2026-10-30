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

from functools import partial
from typing import ClassVar

import carb
from lightspeed.common.constants import WindowNames
from lightspeed.trex.asset_modifiers.core import AssetModifiersCore
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from omni import ui
from omni.flux.job_queue.core import get_job_queue
from omni.flux.utils.common.task_tracker import TaskTracker
from omni.flux.utils.dialog.progress_popup import ProgressPopup
from omni.kit.notification_manager import NotificationButtonInfo, NotificationStatus, post_notification


class AssetModifierSubmitter:
    """Submit the active modifier with a cancellable progress popup and report the result, once per USD context."""

    _submissions: ClassVar[TaskTracker] = TaskTracker()

    @classmethod
    def submit(cls, context_name: str, prim_paths: list[str] | None = None) -> None:
        """Prepare and submit the active modifier unless the context already has a pending submission."""
        cls._submissions.start(context_name, partial(cls._prepare_and_submit, context_name, prim_paths))

    @classmethod
    def cancel_pending_submissions(cls) -> None:
        """Cancel pending submissions. Each keeps its context until its cancellation settles."""
        cls._submissions.cancel_all()

    @staticmethod
    def show_window(title: str) -> None:
        """Show and focus a workspace window without changing the layout."""
        ui.Workspace.show_window(title, True)
        if window := ui.Workspace.get_window(title):
            window.focus()

    @classmethod
    async def _prepare_and_submit(cls, context_name: str, prim_paths: list[str] | None) -> None:
        """Prepare graphs behind a cancellable progress popup, submit them, and report the result."""
        try:
            (graphs, skipped), cancelled = await ProgressPopup.run_cancellable(
                "Preparing Asset Modifier Jobs",
                "Preparing jobs...",
                partial(AssetModifiersCore(context_name).prepare_submission, prim_paths=prim_paths),
            )
            if cancelled:
                return
            if graphs:
                await run_in_worker_thread(get_job_queue().submit_graphs, graphs)
            message = f"{len(graphs)} job(s) were added to the job queue."
            if skipped:
                message += f" {len(skipped)} item(s) were skipped: {next(iter(skipped.values()))}"
            post_notification(
                message,
                status=NotificationStatus.WARNING if skipped or not graphs else NotificationStatus.INFO,
                button_infos=[
                    NotificationButtonInfo(
                        "Open Job Queue", on_complete=lambda *_: cls.show_window(WindowNames.JOB_QUEUE.value)
                    )
                ],
            )
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_warn(f"Failed to submit asset modifier jobs: {error}")
            post_notification(f"No jobs were added to the job queue. {error}", status=NotificationStatus.WARNING)
