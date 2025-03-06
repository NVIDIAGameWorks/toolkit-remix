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
from functools import partial
from typing import Any, Callable

import omni.kit.app
from lightspeed.common.constants import USD_EXTENSIONS
from lightspeed.trex.utils.widget import TrexMessageDialog
from omni import ui
from omni.flux.utils.common import Event, EventSubscription, reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.widget.file_pickers import open_file_picker
from omni.flux.utils.widget.tree_widget import AlternatingRowWidget

from .tree import AssetValidationError, PackagingActions, PackagingErrorDelegate, PackagingErrorModel


class PackagingErrorWindow:
    _PADDING = ui.Pixel(8)

    def __init__(self, assets: list[tuple[str, str, str]], context_name: str = ""):
        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_action_changed_sub": None,
            "_actions_applied_sub": None,
            "_file_picker_opened_dub": None,
            "_file_picker_closed_dub": None,
            "_window": None,
            "_tree": None,
            "_alternating_rows": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name

        self._model = PackagingErrorModel(context_name=self._context_name)
        self._model.refresh(assets)

        self._delegate = PackagingErrorDelegate()

        self._action_changed_sub = self._model.subscribe_action_changed(self._refresh_delegates)

        self._file_picker_opened_dub = self._delegate.subscribe_file_picker_opened(self.hide)
        self._file_picker_closed_dub = self._delegate.subscribe_file_picker_closed(self.show)

        self._window = None
        self._tree = None
        self._alternating_rows = None

        self.__on_actions_applied = Event()

        self._build_ui()

    def show(self):
        """
        Show the window
        """
        self._window.visible = True

    def hide(self):
        """
        Hide the window
        """
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
                                tooltip=(
                                    "Apply the actions to the unresolved assets and retry packaging the mod\n\n"
                                    "NOTE: Make sure to save the stage before retrying packaging or replaced/removed "
                                    "references will not be applied. "
                                ),
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
                if (
                    self._model.validate_selected_path(
                        item, file.suffix in USD_EXTENSIONS, str(file.parent_url), file.name
                    )
                    != AssetValidationError.NONE
                ):
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

        def apply_action(*_):
            ignored_items = self._model.apply_new_paths()
            omni.kit.window.file.save(on_save_done=lambda *_: self.__on_actions_applied(ignored_items))

        self.hide()

        if any(item for item in self._model.get_item_children(None) if item.action != PackagingActions.IGNORE):
            title = "Retry Packaging the Mod"
            message = (
                "The stage must be saved before retrying packaging or replaced/removed references will not be applied."
                "\n\n"
                "Do you want to save the stage and retry packaging the mod?"
            )
            confirm_text = "Save and Retry"

            ensure_future(
                self._display_confirmation_dialog(
                    message, title=title, ok_label=confirm_text, ok_handler=apply_action, cancel_handler=self.show
                )
            )
        else:
            apply_action()

    def _refresh_delegates(self):
        """
        Refresh the tree's delegates
        """
        if not self._tree:
            return
        self._tree.dirty_widgets()

    def subscribe_actions_applied(self, callback: Callable[[list], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return EventSubscription(self.__on_actions_applied, callback)

    def destroy(self):
        reset_default_attrs(self)
