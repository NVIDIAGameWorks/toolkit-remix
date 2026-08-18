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

__all__ = ["SubmitComfyUIJobActionWidgetPlugin"]

import asyncio
import functools
import threading
from typing import TYPE_CHECKING, ClassVar

import carb
from lightspeed.common.constants import LayoutFiles
from lightspeed.trex.comfyui.core.core import ComfyUICore, ComfyUISubmission
from lightspeed.trex.comfyui.core.extension import get_comfyui_core_instance
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.dialog.progress_popup import ProgressPopup
from omni.flux.utils.widget.resources import get_icons as _get_icons
from omni.flux.utils.widget.resources import get_quicklayout_config
from omni.kit.notification_manager import NotificationButtonInfo, NotificationStatus, post_notification

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel

from .constants import COMFYUI_SUBMISSION_FAILURE_MESSAGE


class SubmitComfyUIJobActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Provide Stage Manager controls for submitting selected prims to ComfyUI."""

    _submit_tasks: ClassVar[dict[str, asyncio.Task[None]]] = {}
    _pending_confirmations: ClassVar[set[str]] = set()
    _layout_task: ClassVar[asyncio.Task | None] = None

    def build_icon_ui(
        self,
        model: _StageManagerTreeModel,
        item: _StageManagerTreeItem,
        level: int,
        expanded: bool,
    ):
        """Build the context-aware ComfyUI submission action icon.

        Args:
            model: Tree model forwarded to the icon click handler.
            item: Tree item whose row receives the icon.
            level: Tree nesting depth supplied by Stage Manager; unused.
            expanded: Whether the tree item is expanded; unused.
        """
        core = get_comfyui_core_instance(self._context_name)
        comfy_ready = self._is_comfy_ready(self._context_name)

        if not comfy_ready:
            icon = "AIToolsDisabled"
            tooltip = "ComfyUI is not connected, or no workflow is selected. Select to open AI Tools."
        else:
            workflow_name = core.workflow.name if core.workflow else "Unknown"
            icon = "AITools"
            tooltip = f"Run '{workflow_name}' for this selection using the current AI Tools settings."

        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name=icon,
            tooltip=tooltip,
            identifier="submit_comfyui_job_widget_image",
            mouse_released_fn=lambda x, y, b, m: self._on_icon_clicked(b, model, item),
        )

    def _on_icon_clicked(
        self,
        button: int,
        model: _StageManagerTreeModel,
        item: _StageManagerTreeItem,
    ) -> None:
        """Validate and submit the explicit selection for a left-button release.

        Args:
            button: Mouse button that was released; zero identifies the left button.
            model: Tree model that owns the clicked item.
            item: Tree item whose action icon was clicked.
        """
        if button != 0:
            return

        if not self._is_comfy_ready(self._context_name):
            self._open_ai_tools_layout()
            return

        selected_paths = self._get_action_paths(model, item)
        self._item_clicked(button, True, model, item)
        self._on_submit_comfyui_job(
            {
                "context_name": self._context_name,
                "right_clicked_item": item,
                "selected_paths": selected_paths,
            }
        )

    @classmethod
    def _get_menu_items(cls):
        """Return ComfyUI submit and layout context-menu descriptors.

        Returns:
            Menu descriptors for submitting selected prims or opening the AI Tools layout.
        """
        submenu_icon = _get_icons("ai-tools-icon")

        submit_btn = {
            "name": _MenuItem.AI_TOOLS_SUBMIT.value,
            "glyph": submenu_icon,
            "onclick_fn": cls._on_submit_comfyui_job,
            "enabled_fn": cls._is_menu_item_enabled,
        }

        open_layout_btn = {
            "name": _MenuItem.AI_TOOLS_OPEN_LAYOUT.value,
            "glyph": submenu_icon,
            "onclick_fn": cls._open_ai_tools_layout,
        }

        btn_list = [submit_btn, open_layout_btn]
        menu_item_dict = {_MenuItem.AI_TOOLS.value: btn_list}

        return [
            (
                {
                    "name": menu_item_dict,
                    "glyph": submenu_icon,
                    "appear_after": _MenuItem.LOGIC_GRAPH.value,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
        ]

    @classmethod
    def _is_menu_item_enabled(cls, payload: dict) -> bool:
        """Return whether the payload contains a valid ComfyUI submission target.

        Args:
            payload: Stage Manager menu payload with a context name and optional clicked item.

        Returns:
            True when ComfyUI is ready and the payload identifies a clicked item.

        Raises:
            KeyError: If the payload does not contain a context name.
        """
        context_name = payload["context_name"]
        if not cls._is_comfy_ready(context_name):
            return False
        item = payload.get("right_clicked_item")
        return bool(item)

    @classmethod
    def _on_submit_comfyui_job(cls, payload: dict) -> None:
        """Schedule an explicit Stage Manager selection for ComfyUI submission.

        Args:
            payload: Stage Manager action payload with the context, clicked item, and selected prim paths.

        Raises:
            KeyError: If the payload does not contain a context name.
        """
        context_name = payload["context_name"]
        item = payload.get("right_clicked_item")
        selected_paths = list(payload.get("selected_paths") or ())
        if not cls._is_comfy_ready(context_name) or not item or not selected_paths:
            return
        if context_name in cls._pending_confirmations:
            return
        pending_task = cls._submit_tasks.get(context_name)
        if pending_task and not pending_task.done():
            return

        cls._submit_tasks[context_name] = asyncio.ensure_future(
            cls._prepare_and_submit(context_name, list(selected_paths))
        )
        cls._submit_tasks[context_name].set_name(f"ComfyUISubmit:{context_name}")

    @classmethod
    async def _prepare_and_submit(cls, context_name: str, selected_paths: list[str]) -> None:
        """Prepare a Stage Manager selection and submit it or request confirmation.

        Args:
            context_name: USD context that owns the selected prims.
            selected_paths: Explicit prim paths to prepare for submission.

        Raises:
            asyncio.CancelledError: If the owning submission task is cancelled.
        """
        task = asyncio.current_task()
        try:
            core = get_comfyui_core_instance(context_name)
            submission, cancelled = await cls._prepare_with_progress(core, selected_paths)
            if cancelled:
                return
            if submission.skipped_count:
                material_label = "material" if submission.skipped_count == 1 else "materials"
                provide_label = "does" if submission.skipped_count == 1 else "do"
                _TrexMessageDialog(
                    f"{submission.skipped_count} selected {material_label} {provide_label} not provide the inputs "
                    "required by "
                    "the active workflow.\n\n"
                    "These jobs will be skipped.\n\n"
                    "Do you want to proceed anyway?",
                    "Skipped ComfyUI Jobs",
                    ok_handler=functools.partial(cls._submit_prepared_submission, context_name, submission),
                    ok_label="Proceed",
                    on_window_closed_fn=functools.partial(cls._on_confirmation_closed, context_name),
                )
                cls._pending_confirmations.add(context_name)
                return
            await cls._submit_submission(context_name, submission)
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_warn(f"Failed to submit ComfyUI jobs: {error}")
            post_notification(COMFYUI_SUBMISSION_FAILURE_MESSAGE, status=NotificationStatus.WARNING)
        finally:
            if cls._submit_tasks.get(context_name) is task:
                cls._submit_tasks.pop(context_name, None)

    @classmethod
    async def _prepare_with_progress(cls, core: ComfyUICore, prim_paths: list[str]) -> tuple[ComfyUISubmission, bool]:
        """Prepare a submission behind a cancellable progress popup.

        Args:
            core: ComfyUI core instance that prepares the submission.
            prim_paths: Explicit prim paths to prepare for submission.

        Returns:
            The prepared submission and whether the user cancelled preparation.
        """
        cancel_event = threading.Event()
        progress_popup = ProgressPopup(title="Preparing ComfyUI Jobs", status_text="Preparing jobs...")
        progress_popup.set_cancel_fn(cancel_event.set)
        progress_popup.show()
        try:
            submission = await core.prepare_submission(
                prim_paths=prim_paths,
                progress=functools.partial(cls._update_prepare_progress, progress_popup),
                is_cancelled=cancel_event.is_set,
            )
            return submission, cancel_event.is_set()
        finally:
            progress_popup.hide()
            progress_popup.destroy()

    @staticmethod
    def _update_prepare_progress(progress_popup: ProgressPopup, current: int, total: int, status: object) -> None:
        """Render the latest preparation progress on the main thread.

        Args:
            progress_popup: Popup rendering job-preparation progress.
            current: Latest processed count reported by the worker.
            total: Latest total count, or a non-positive value while the total is unknown.
            status: Latest status message, if any.
        """
        if status:
            progress_popup.set_status_text(str(status))
        if total and total > 0:
            progress_popup.set_progress(max(0.0, min(1.0, current / total)))

    @classmethod
    def _on_confirmation_closed(cls, context_name: str) -> None:
        """Release a context after its skipped-job dialog closes.

        Args:
            context_name: USD context released by the closed dialog.
        """
        cls._pending_confirmations.discard(context_name)

    @classmethod
    def _submit_prepared_submission(cls, context_name: str, submission: ComfyUISubmission) -> None:
        """Schedule a confirmed submission after validating dialog ownership.

        Args:
            context_name: USD context that owns the confirmation.
            submission: Core-prepared material submission approved by the user.
        """
        if context_name not in cls._pending_confirmations:
            return
        cls._pending_confirmations.discard(context_name)
        pending_task = cls._submit_tasks.get(context_name)
        if pending_task and not pending_task.done():
            return
        cls._submit_tasks[context_name] = asyncio.ensure_future(cls._submit_confirmed(context_name, submission))
        cls._submit_tasks[context_name].set_name(f"ComfyUIConfirmedSubmit:{context_name}")

    @classmethod
    async def _submit_confirmed(cls, context_name: str, submission: ComfyUISubmission) -> None:
        """Submit a confirmed core-prepared request and release task ownership.

        Args:
            context_name: USD context that owns the submission task.
            submission: Confirmed material submission to add to the queue.

        Raises:
            asyncio.CancelledError: If the owning submission task is cancelled.
        """
        task = asyncio.current_task()
        try:
            await cls._submit_submission(context_name, submission)
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_warn(f"Failed to submit ComfyUI jobs: {error}")
            post_notification(COMFYUI_SUBMISSION_FAILURE_MESSAGE, status=NotificationStatus.WARNING)
        finally:
            if cls._submit_tasks.get(context_name) is task:
                cls._submit_tasks.pop(context_name, None)

    @classmethod
    async def _submit_submission(cls, context_name: str, submission: ComfyUISubmission) -> None:
        """Submit one core-prepared request and render its exact result.

        Args:
            context_name: USD context whose core owns the prepared submission.
            submission: Prepared material submission to add to the queue.

        Raises:
            asyncio.CancelledError: If submission is cancelled.
        """
        result = await get_comfyui_core_instance(context_name).submit_prepared_submission(submission)
        if result.failed_count:
            submitted_suffix = "" if result.submitted_count == 1 else "s"
            submitted_verb = "was" if result.submitted_count == 1 else "were"
            failed_suffix = "" if result.failed_count == 1 else "s"
            failed_verb = "was" if result.failed_count == 1 else "were"
            message = (
                f"{result.submitted_count} selected material{submitted_suffix} {submitted_verb} added to the AI Tools "
                f"job queue. {result.failed_count} selected material{failed_suffix} {failed_verb} not added."
            )
            if result.submitted_count:
                message += f" To avoid duplicates, select only the failed material{failed_suffix} before trying again."
            else:
                message += " Check the workflow inputs and ComfyUI connection, then try again."
            button_infos = None
            if result.submitted_count:
                button_infos = [NotificationButtonInfo("Open AI Tools layout", on_complete=cls._open_ai_tools_layout)]
            post_notification(message, status=NotificationStatus.WARNING, button_infos=button_infos)
            return

        post_notification(
            "The selection was added to the AI Tools job queue. Open the AI Tools layout to view the job queue.",
            button_infos=[NotificationButtonInfo("Open AI Tools layout", on_complete=cls._open_ai_tools_layout)],
        )

    @classmethod
    def cancel_pending_submissions(cls) -> None:
        """Cancel pending ComfyUI submissions and AI Tools layout loads."""
        for task in cls._submit_tasks.values():
            if not task.done():
                task.cancel()
        cls._pending_confirmations.clear()
        if cls._layout_task and not cls._layout_task.done():
            cls._layout_task.cancel()

    @classmethod
    def _open_ai_tools_layout(cls, _=None):
        """Open the AI Tools layout through a single owned task.

        Args:
            _: Notification callback result; unused.
        """
        layout = get_quicklayout_config(LayoutFiles.TEXTURECRAFT)
        if not layout:
            carb.log_warn("The AI Tools layout resource is unavailable.")
            return
        if cls._layout_task and not cls._layout_task.done():
            cls._layout_task.cancel()
        task = load_layout(layout)
        if task is None:
            carb.log_warn(f"The AI Tools layout file does not exist: {layout}")
            return
        cls._layout_task = task
        task.add_done_callback(cls._on_layout_load_done)

    @classmethod
    def _on_layout_load_done(cls, task: asyncio.Task) -> None:
        """Release a completed layout task and report expected load failures.

        Args:
            task: Shared quick-layout task that completed.
        """
        if cls._layout_task is task:
            cls._layout_task = None
        if task.cancelled():
            return
        try:
            task.result()
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_warn(f"Failed to open the AI Tools layout: {error}")

    @classmethod
    def _is_comfy_ready(cls, context_name: str) -> bool:
        """Return whether ComfyUI is ready for the requested context.

        Args:
            context_name: USD context whose ComfyUI core should be checked.

        Returns:
            True when ComfyUI is connected and has an active workflow.
        """
        core = get_comfyui_core_instance(context_name)
        return core.is_ready
