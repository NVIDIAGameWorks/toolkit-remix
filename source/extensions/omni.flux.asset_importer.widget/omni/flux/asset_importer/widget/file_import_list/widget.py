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

import asyncio
from functools import partial
from typing import Any, Callable, List

import carb
import carb.events
import omni.appwindow
from omni import kit, ui, usd
from omni.flux.asset_importer.core import destroy_scanner_dialog as _destroy_scanner_dialog
from omni.flux.asset_importer.core import scan_folder as _scan_folder
from omni.flux.asset_importer.core import setup_scanner_dialog as _setup_scanner_dialog
from omni.flux.asset_importer.core.data_models import SUPPORTED_ASSET_EXTENSIONS as _SUPPORTED_ASSET_EXTENSIONS
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.common.path_utils import get_invalid_extensions as _get_invalid_extensions
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager

from ..common.asset_browser import AssetBrowserWindow as _AssetBrowserWindow
from .delegate import FileImportListDelegate
from .items import FileImportItem
from .model import FileImportListModel


class FileImportListWidget:
    __DEFAULT_TREE_HEIGHT_PIXEL = 100
    __DEFAULT_SPACER_PIXEL = 8
    __DEFAULT_UI_HEIGHT_PIXEL = 24
    __MANIPULATOR_WIDTH_PERCENT = 50
    __MANIPULATOR_HEIGHT_PIXEL = 4

    def __init__(
        self,
        model: FileImportListModel = None,
        delegate: FileImportListDelegate = None,
        allow_empty_input_files_list: bool = False,
        enable_drop: bool = False,
        drop_filter_fn: Callable[[List[str]], List[str]] = None,
        drop_callback: Callable[[List[str]], Any] = None,
    ):
        """
        General file lister

        Args:
            model: model that will feed this widget
            delegate: custom delegate (that should not be initialized)
            allow_empty_input_files_list: allow to show nothing
            enable_drop: enable handling of drop or not
            drop_filter_fn: function that will filter what we drop
            drop_callback: function that will called when items are dropped
        """
        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_sub_on_item_changed": None,
            "_file_tree_frame": None,
            "_file_tree_view": None,
            "_add_button": None,
            "_add_from_library_button": None,
            "_remove_button": None,
            "_sub_on_file_changed": None,
            "_asset_browser": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._model = model or FileImportListModel()
        self._delegate = delegate or FileImportListDelegate()
        self.__drop_filter_fn = drop_filter_fn
        self.__drop_callback = drop_callback
        self._allow_empty_input_files_list = allow_empty_input_files_list

        self._sub_on_item_changed = self._model.subscribe_item_changed_fn(self.__update_tree_view_width_deferred)

        self._file_tree_frame = None
        self._file_tree_view = None
        self._add_button = None
        self._add_from_library_button = None
        self._remove_button = None

        self._asset_browser = _AssetBrowserWindow(self._model.add_items)

        self.__update_width_task = None

        self.__root_frame = ui.Frame()
        self.__create_ui()

        if enable_drop:
            app_window = omni.appwindow.get_default_app_window()
            self._dropsub = app_window.get_window_drop_event_stream().create_subscription_to_pop(
                self._on_drag_drop_external, name="ExternalDragDrop event", order=0
            )

        _setup_scanner_dialog(callback={"file_import": [self._model.add_items]})

    def _on_drag_drop_external(self, event: carb.events.IEvent):
        async def do_drag_drop():
            paths = event.payload.get("paths", ())
            if not paths:
                return
            if self.__drop_filter_fn:
                paths = self.__drop_filter_fn(paths)
            if not paths:
                return
            if self.__drop_callback:
                self.__drop_callback(paths)
            self._model.add_items(paths)

        if not self.__root_frame.enabled:
            return
        asyncio.ensure_future(do_drag_drop())

    @property
    def model(self) -> FileImportListModel:
        return self._model

    def __create_ui(self):
        with self.__root_frame:
            with ui.VStack(key_pressed_fn=self.__on_key_pressed):
                self._manipulator_frame = ui.Frame(visible=True)
                with self._manipulator_frame:
                    with ui.ZStack():
                        ui.Rectangle(name="TreePanelBackground")
                        self._file_tree_frame = ui.ScrollingFrame(name="PropertiesPaneSection")
                        self._file_tree_frame.set_computed_content_size_changed_fn(
                            self.__update_tree_view_width_deferred
                        )
                        with self._file_tree_frame:
                            self._file_tree_view = ui.TreeView(self._model, delegate=self._delegate, root_visible=False)
                            self._file_tree_view.set_selection_changed_fn(self.__on_selection_changed)
                            self._sub_on_file_changed = self._model.subscribe_changed(self.__on_file_changed)

                ui.Spacer(height=ui.Pixel(self.__DEFAULT_SPACER_PIXEL))

                with ui.HStack(height=ui.Pixel(self.__DEFAULT_UI_HEIGHT_PIXEL)):
                    self._add_button = ui.Button("Add", clicked_fn=self.__add_item, identifier="add_file")
                    self._scan_folder_button = ui.Button(
                        "Scan Folder", clicked_fn=_scan_folder, identifier="scan_folder"
                    )
                    self._add_from_library_button = ui.Button(
                        "Add from library",
                        clicked_fn=partial(self._asset_browser.show_window, True),
                        identifier="add_from_library",
                    )
                    self._remove_button = ui.Button("Remove", clicked_fn=self.__remove_items, identifier="remove_file")

    def __on_file_changed(self, *_):
        self._file_tree_view.dirty_widgets()

    def __on_selection_changed(self, selection: List[FileImportItem]):
        if self._allow_empty_input_files_list:
            return
        will_have_items_left = len(selection) < len(self._model.get_item_children(None))
        self._remove_button.enabled = will_have_items_left
        self._remove_button.tooltip = (
            ""
            if will_have_items_left
            else "INVALID: You cannot remove all items. The list must contain at least 1 item to be valid."
        )

    def __add_item(self):
        current_file = self._model.get_item_children(None)[-1].path if self._model.get_item_children(None) else None
        if self._file_tree_view.selection:
            current_file = self._file_tree_view.selection[0].path

        def validate_selection(filenames):
            return all(_OmniUrl(filename).suffix in _SUPPORTED_ASSET_EXTENSIONS for filename in filenames)

        def validation_failed_callback(filenames):
            invalid_extensions = _get_invalid_extensions(
                file_paths=filenames, valid_extensions=_SUPPORTED_ASSET_EXTENSIONS, case_sensitive=True
            )
            if len(filenames) == 0:
                error_message = "No file was selected."
            else:
                error_message = (
                    "One or multiple of the selected files are invalid. "
                    f"The following file type(s) are unsupported:\n\n     {', '.join(invalid_extensions)}"
                    f"\n\nThese are the supported file types:\n\n     {', '.join(_SUPPORTED_ASSET_EXTENSIONS)}"
                )

            PromptManager.post_simple_prompt(
                "Invalid file selected",
                error_message,
                ok_button_info=PromptButtonInfo("Okay", None),
                modal=True,
            )

        _open_file_picker(
            "Select a file to import",
            self._model.add_items,
            lambda *_: None,
            apply_button_label="Import",
            file_extension_options=[(", ".join(_SUPPORTED_ASSET_EXTENSIONS), "")],
            select_directory=False,
            current_file=str(current_file) if current_file else None,
            validate_selection=validate_selection,
            validation_failed_callback=validation_failed_callback,
            allow_multi_selection=True,
        )

    def __remove_items(self):
        for item in self._file_tree_view.selection:
            if id(item) in self._delegate.frames:
                self._delegate.frames.pop(id(item))
        self._model.remove_items(self._file_tree_view.selection)

    def __on_key_pressed(self, key, modifiers, is_down):
        if (
            key == int(carb.input.KeyboardInput.A)
            and modifiers == carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
            and is_down
        ):
            self.__select_all_items()
        elif key == int(carb.input.KeyboardInput.DEL) and not is_down:
            self.__remove_items()

    def __select_all_items(self):
        self._file_tree_view.selection = self._model.get_item_children(None)

    def __update_tree_view_width_deferred(self, *_):
        if self.__update_width_task:
            self.__update_width_task.cancel()
        self.__update_width_task = asyncio.ensure_future(self.__update_tree_view_width_async())

    @usd.handle_exception
    async def __update_tree_view_width_async(self):
        await kit.app.get_app().next_update_async()

        if not self._file_tree_frame:
            return

        max_width = self._file_tree_frame.computed_width
        for frame in self._delegate.frames.values():
            max_width = max(frame.computed_width, max_width)

        self._file_tree_view.width = ui.Pixel(max_width)

    def destroy(self):
        if self.__update_width_task:
            self.__update_width_task.cancel()
        self.__update_width_task = None

        _reset_default_attrs(self)
        _destroy_scanner_dialog()
