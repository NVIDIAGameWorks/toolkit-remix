"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["PackagingErrorWindow"]

from asyncio import ensure_future
from collections.abc import Callable
from functools import partial
from typing import Any

import carb
import omni.kit.app
from lightspeed.trex.packaging.core.repair import PackagingRepairFailure, PackagingRepairProgress
from lightspeed.trex.utils.widget import TrexMessageDialog
from omni import ui
from omni.flux.utils.common import Event, EventSubscription, reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.dialog import ProgressPopup as _ProgressPopup
from omni.flux.utils.widget.file_pickers import open_file_picker
from omni.flux.utils.widget.tree_widget import AlternatingRowWidget

from .tree import (
    PackagingErrorDelegate,
    PackagingErrorModel,
)


class PackagingErrorWindow:
    _PADDING = ui.Pixel(8)
    _MAX_FAILED_REPAIRS_IN_DIALOG = 5

    def __init__(self, assets: list[tuple[str, str, str]], context_name: str = ""):
        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_context_name": None,
            "_action_changed_sub": None,
            "_actions_applied_sub": None,
            "_file_picker_opened_sub": None,
            "_file_picker_closed_sub": None,
            "_on_actions_applied": None,
            "_window": None,
            "_tree": None,
            "_alternating_rows": None,
            "_progress_popup": None,
            "_apply_cancel_requested": False,
            "_apply_cancel_enabled": False,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name

        self._model = PackagingErrorModel(context_name=self._context_name)
        self._model.refresh(assets)

        self._delegate = PackagingErrorDelegate()

        self._action_changed_sub = self._model.subscribe_action_changed(self._refresh_delegates)

        self._file_picker_opened_sub = self._delegate.subscribe_file_picker_opened(self.hide)
        self._file_picker_closed_sub = self._delegate.subscribe_file_picker_closed(self.show)

        self._on_actions_applied = Event()

        self._build_ui()

    def show(self):
        """Show the packaging error window."""
        self._window.visible = True

    def hide(self):
        """Hide the packaging error window."""
        self._window.visible = False

    def _build_ui(self):
        """
        Build the UI for the window
        """
        self._window = ui.Window(
            "Mod Packaging Errors",
            width=900,
            height=600,
            visible=True,
            dockPreference=ui.DockPreference.DISABLED,
            flags=ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_DOCKING,
        )

        with self._window.frame:
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground")
                with ui.HStack(spacing=self._PADDING):
                    ui.Spacer(height=0, width=0)
                    with ui.VStack(spacing=self._PADDING):
                        ui.Spacer(height=0, width=0)
                        with ui.VStack(height=0, spacing=ui.Pixel(4)):
                            ui.Label(
                                "The following assets could not be resolved while packaging the mod.",
                                name="PropertiesWidgetLabel",
                                height=0,
                                alignment=ui.Alignment.CENTER,
                            )
                            ui.Label(
                                "Specify which actions should be taken to resolve the packaging errors.",
                                height=0,
                                alignment=ui.Alignment.CENTER,
                            )
                        ui.Spacer(height=0, width=0)
                        with ui.ZStack():
                            self._alternating_rows = AlternatingRowWidget(
                                self._delegate.ROW_HEIGHT, self._delegate.ROW_HEIGHT
                            )
                            with ui.ScrollingFrame(
                                name="TreePanelBackground",
                                scroll_y_changed_fn=self._alternating_rows.sync_scrolling_frame,
                                computed_content_size_changed_fn=lambda: self._alternating_rows.sync_frame_height(
                                    self._tree.computed_height
                                ),
                                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            ):
                                self._tree = ui.TreeView(
                                    self._model,
                                    delegate=self._delegate,
                                    root_visible=False,
                                    header_visible=True,
                                    columns_resizable=True,
                                    column_widths=[ui.Fraction(3), ui.Fraction(2), ui.Fraction(2), ui.Pixel(200)],
                                )
                        with ui.HStack(spacing=self._PADDING, height=0):
                            ui.Button(
                                "Ignore All",
                                tooltip="Set all the missing assets actions to 'Ignore'",
                                clicked_fn=partial(self._model.reset_asset_paths, self._model.get_item_children(None)),
                            )
                            ui.Button(
                                "Remove All",
                                tooltip="Set all the missing assets actions to 'Remove Reference'",
                                clicked_fn=partial(self._model.remove_asset_paths, self._model.get_item_children(None)),
                            )
                            ui.Button(
                                "Scan Directory",
                                tooltip="Scan a directory to attempt to resolve the missing assets automatically",
                                clicked_fn=self._scan_directory,
                            )
                        ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")
                        with ui.HStack(spacing=self._PADDING, height=0):
                            ui.Button(
                                "Cancel", tooltip="Close the window without applying any actions", clicked_fn=self.hide
                            )
                            ui.Button(
                                "Retry Packaging",
                                tooltip="Apply the actions to the unresolved assets and retry packaging the mod",
                                clicked_fn=partial(self._apply_actions),
                            )
                        ui.Spacer(height=0, width=0)
                    ui.Spacer(height=0, width=0)

    async def _display_confirmation_dialog(self, *args, **kwargs):
        """
        Display a confirmation dialog after 1 frame to ensure the window is centered.

        Args:
            args: The arguments to pass to the TrexMessageDialog
            kwargs: The keyword arguments to pass to the TrexMessageDialog
        """
        await omni.kit.app.get_app().next_update_async()
        TrexMessageDialog(*args, **kwargs)

    def _scan_directory(self):
        """
        Open the file picker to select a directory to scan.
        """

        def scan_directory(path):
            unresolved_paths = {OmniUrl(item.asset_path).name: item for item in self._model.get_item_children(None)}
            asset_path = {}

            for file in OmniUrl(path).iterdir():
                if not file.is_file:
                    continue
                # Check if the file is in the unresolved paths
                if file.name not in unresolved_paths:
                    continue
                item = unresolved_paths[file.name]
                # If the item was already replaced, skip it
                if item.fixed_asset_path and item.fixed_asset_path != item.asset_path:
                    continue
                # If the file path is invalid, skip it
                if not self._model.is_replacement_asset_valid(item, str(file)):
                    continue
                asset_path[item] = str(file)

            self._model.replace_asset_paths(asset_path)
            self.show()

        self.hide()
        open_file_picker(
            "Select a directory to scan",
            scan_directory,
            lambda *_: self.show(),
            select_directory=True,
        )

    def _apply_actions(self):
        """
        Apply the actions to the unresolved assets
        """
        self.hide()
        self._apply_cancel_requested = False
        ensure_future(self._apply_actions_async())

    def _show_apply_progress(self, current: int, total: int, status: str, cancel_enabled: bool = False):
        """
        Show progress while repaired references are authored and saved.
        """
        self._apply_cancel_enabled = cancel_enabled
        if self._progress_popup is None:
            self._progress_popup = _ProgressPopup(title="Applying Packaging Repairs")
        self._progress_popup.set_cancel_fn(self._cancel_apply_actions if cancel_enabled else None)
        self._progress_popup.set_cancel_enabled(cancel_enabled)

        if not self._progress_popup.is_visible():
            self._progress_popup.show()

        status_text = status
        if total > 0:
            status_text = f"{status}\n{current} / {total}"
        if self._progress_popup.status_text != status_text:
            self._progress_popup.set_status_text(status_text)
        self._progress_popup.set_progress(current / total if total > 0 else 0.5)

    def _hide_apply_progress(self):
        self._apply_cancel_enabled = False
        if self._progress_popup is None:
            return
        if self._progress_popup.is_visible():
            self._progress_popup.hide()
        self._progress_popup = None

    def _cancel_apply_actions(self):
        if not self._apply_cancel_enabled:
            return
        self._apply_cancel_requested = True
        self._show_apply_progress(0, 0, "Cancelling packaging repairs...")

    def _show_if_apply_cancelled(self) -> bool:
        if not self._apply_cancel_requested:
            return False
        self.show()
        return True

    async def _next_update_or_apply_cancelled(self) -> bool:
        await omni.kit.app.get_app().next_update_async()
        return self._show_if_apply_cancelled()

    @staticmethod
    def _get_apply_progress_status(progress: PackagingRepairProgress) -> str:
        if progress == PackagingRepairProgress.APPLYING:
            return "Applying packaging repairs..."
        return "Saving repaired layers..."

    def _on_apply_progress(self, current: int, total: int, progress: PackagingRepairProgress):
        self._show_apply_progress(
            current,
            total,
            self._get_apply_progress_status(progress),
            progress == PackagingRepairProgress.APPLYING and not self._apply_cancel_requested,
        )

    async def _wait_apply_completion_frames(self) -> bool:
        for _ in range(2):
            if await self._next_update_or_apply_cancelled():
                return True
        return False

    async def _apply_actions_async(self):
        try:
            # Let Kit settle the error window visibility before centering the progress popup.
            if await self._next_update_or_apply_cancelled():
                return
            self._show_apply_progress(0, 0, self._get_apply_progress_status(PackagingRepairProgress.APPLYING), True)
            if await self._next_update_or_apply_cancelled():
                return
            repair_result = await self._model.apply_new_paths_async(
                progress_callback=self._on_apply_progress,
                is_cancelled=lambda: self._apply_cancel_requested,
            )
            if repair_result is None:
                self.show()
                return
            if repair_result.failed_repairs:
                self.show()
                ensure_future(
                    self._display_confirmation_dialog(
                        self._format_failed_repairs_message(repair_result.failed_repairs),
                        title="Packaging Repair Incomplete",
                        ok_label="Okay",
                        disable_cancel_button=True,
                    )
                )
                return
            if self._show_if_apply_cancelled():
                return
            if await self._wait_apply_completion_frames():
                return
        except RuntimeError as exc:
            carb.log_error(str(exc))
            self.show()
            ensure_future(
                self._display_confirmation_dialog(
                    str(exc),
                    title="Packaging Repair Failed",
                    ok_label="Okay",
                    disable_cancel_button=True,
                )
            )
            return
        finally:
            self._hide_apply_progress()

        self._on_actions_applied(repair_result.ignored_items)

    def _format_failed_repairs_message(self, failed_repairs: list[PackagingRepairFailure]) -> str:
        shown_repairs = failed_repairs[: self._MAX_FAILED_REPAIRS_IN_DIALOG]
        repair_lines = [f"- {repair.prim_path}: {repair.asset_path}\n  {repair.message}" for repair in shown_repairs]
        remaining_count = len(failed_repairs) - len(shown_repairs)
        if remaining_count:
            repair_lines.append(f"- {remaining_count} more repair(s) failed.")
        return "Some repairs could not be applied. The unresolved assets were left in the list.\n\n" + "\n".join(
            repair_lines
        )

    def _refresh_delegates(self):
        """
        Refresh the tree's delegates
        """
        if not self._tree:
            return
        self._tree.dirty_widgets()

    def subscribe_actions_applied(self, callback: Callable[[list], Any]):
        """Subscribe to repair action applied events.

        Args:
            callback: Callback invoked with ignored unresolved assets that could not be applied.

        Returns:
            A subscription object that unsubscribes when destroyed.
        """
        return EventSubscription(self._on_actions_applied, callback)

    def destroy(self):
        """Destroy the packaging error window and release UI objects."""
        self._hide_apply_progress()
        window = self._window
        if window is not None:
            window.visible = False
            window.destroy()
        reset_default_attrs(self)
