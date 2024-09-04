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
from pathlib import Path
from typing import Any, Callable, List, Optional

import carb
import omni.appwindow
from omni import kit, ui, usd
from omni.flux.asset_importer.core import destroy_scanner_dialog as _destroy_scanner_dialog
from omni.flux.asset_importer.core import scan_folder as _scan_folder
from omni.flux.asset_importer.core import setup_scanner_dialog as _setup_scanner_dialog
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.info_icon.widget import InfoIconWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import get_invalid_extensions as _get_invalid_extensions
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker

from ..common.ingestion_checker import texture_validation_failed_callback as _texture_validation_failed_callback
from ..common.ingestion_checker import validate_texture_selection as _validate_texture_selection
from .delegate import TextureImportListDelegate
from .items import TextureImportItem as _TextureImportItem
from .model import TextureImportListModel


class TextureImportListWidget:
    __DEFAULT_TREE_HEIGHT_PIXEL = 200
    __DEFAULT_SPACER_PIXEL = 8
    __DEFAULT_UI_HEIGHT_PIXEL = 24
    __MANIPULATOR_WIDTH_PERCENT = 50
    __MANIPULATOR_HEIGHT_PIXEL = 4
    __DEFAULT_UI_ICON_SIZE_PIXEL = 16

    def __init__(
        self,
        model: TextureImportListModel = None,
        delegate: TextureImportListDelegate = None,
        allow_empty_input_files_list: bool = False,
        enable_drop: bool = False,
        drop_filter_fn: Callable[[List[str]], List[str]] = None,
        drop_callback: Callable[[List[str]], Any] = None,
    ):
        self._default_attr = {
            "_model": None,
            "_delegate": None,
            "_sub_on_item_changed": None,
            "_sub_on_texture_type_changed": None,
            "_sub_on_texture_changed": None,
            "_file_tree_frame": None,
            "_file_tree_view": None,
            "_add_button": None,
            "_remove_button": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._model = model or TextureImportListModel()
        self._delegate = delegate or TextureImportListDelegate()
        self._allow_empty_input_files_list = allow_empty_input_files_list
        self.__drop_filter_fn = drop_filter_fn
        self.__drop_callback = drop_callback

        self._sub_on_item_changed = self._model.subscribe_item_changed_fn(self.__update_tree_view_width_deferred)

        self._file_tree_frame = None
        self._file_tree_view = None
        self._add_button = None
        self._remove_button = None

        self.__update_width_task = None

        self._normals_type_info_icon = None

        self._preferred_normal_type: Optional[_TextureTypes] = None
        self._normal_types = [_TextureTypes.NORMAL_OGL, _TextureTypes.NORMAL_DX, _TextureTypes.NORMAL_OTH]

        self.__root_frame = ui.Frame()
        self.__create_ui()

        if enable_drop:
            app_window = omni.appwindow.get_default_app_window()
            self._dropsub = app_window.get_window_drop_event_stream().create_subscription_to_pop(
                self._on_drag_drop_external, name="ExternalDragDrop event", order=0
            )
        # Will be set to False during validation failure
        self._allow_drop = True

        _setup_scanner_dialog(callback={"texture_import": [self._model.add_items]})

    def _on_drag_drop_external(self, event: carb.events.IEvent):
        async def do_drag_drop():
            if not self._allow_drop:
                # In validation failure dialog; don't allow more drops.
                return

            paths = event.payload.get("paths", ())
            if not paths:
                return
            if not _validate_texture_selection(paths):

                def reset_drop():
                    self._allow_drop = True

                self._allow_drop = False
                _texture_validation_failed_callback(paths, callback=reset_drop)
                bad_exts = _get_invalid_extensions(file_paths=paths, valid_extensions=_SUPPORTED_TEXTURE_EXTENSIONS)
                paths = [path for path in paths if (pth := Path(path)).suffix not in bad_exts and not pth.is_dir()]
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
    def model(self) -> TextureImportListModel:
        return self._model

    def __create_ui(self):
        with self.__root_frame:
            with ui.VStack(height=ui.Pixel(self.__DEFAULT_TREE_HEIGHT_PIXEL), key_pressed_fn=self.__on_key_pressed):
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
                            self._sub_on_texture_type_changed = self._model.subscribe_texture_type_changed(
                                self._file_tree_view.dirty_widgets
                            )
                            self._sub_on_texture_changed = self._model.subscribe_changed(self.__on_texture_changed)

                ui.Spacer(height=ui.Pixel(self.__DEFAULT_SPACER_PIXEL))

                # normals type
                with ui.HStack(
                    height=ui.Pixel(self.__DEFAULT_UI_HEIGHT_PIXEL), spacing=ui.Pixel(self.__DEFAULT_SPACER_PIXEL)
                ):
                    ui.Label("Convention", name="PropertiesWidgetLabel", alignment=ui.Alignment.LEFT_CENTER, width=0)

                    try:
                        selected_normals_type = self._normal_types.index(self._preferred_normal_type)
                    except ValueError:
                        selected_normals_type = 0

                    normals_type_field = ui.ComboBox(
                        selected_normals_type,
                        *[t.value for t in self._normal_types],
                        identifier="normals_type_combobox",
                    )

                    with ui.VStack(width=0):
                        ui.Spacer()
                        self._normals_type_info_icon = InfoIconWidget(
                            message="Type convention for normal maps.\n\n"
                            "The default type for normals we should use for this batch of textures.\n"
                            "Generally, the application used to create normal maps will explain display\n"
                            "the convention used.\n"
                            "If selected incorrectly, the normal map when applied in meshes will appear as \n"
                            "indentations rather than bumps."
                        )
                        ui.Spacer()

                ui.Spacer(height=ui.Pixel(self.__DEFAULT_SPACER_PIXEL))

                with ui.HStack(height=ui.Pixel(self.__DEFAULT_UI_HEIGHT_PIXEL)):
                    self._add_button = ui.Button("Add", clicked_fn=self.__add_item, identifier="add_file")
                    self._scan_folder_button = ui.Button(
                        "Scan Folder", clicked_fn=_scan_folder, identifier="scan_folder"
                    )
                    self._remove_button = ui.Button("Remove", clicked_fn=self.__remove_items, identifier="remove_file")

        self._normals_type_field_sub = normals_type_field.model.subscribe_item_changed_fn(
            partial(self.__update_normal_type)
        )

    def __on_texture_changed(self, *_):
        self._file_tree_view.dirty_widgets()

    def __on_selection_changed(self, selection: List[_TextureImportItem]):
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

        _open_file_picker(
            "Select a texture to import",
            self._model.add_items,
            lambda *_: None,
            apply_button_label="Import",
            file_extension_options=[(", ".join(_SUPPORTED_TEXTURE_EXTENSIONS), "")],
            select_directory=False,
            current_file=str(current_file) if current_file else None,
            validate_selection=_validate_texture_selection,
            validation_failed_callback=_texture_validation_failed_callback,
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

    def __update_normal_type(self, model: ui.AbstractValueModel, _):
        try:
            selected_index = model.get_item_value_model().get_value_as_int()
            self._model.set_preferred_normal_type(_TextureTypes[self._normal_types[selected_index].name])
        except ValueError as e:
            carb.log_warn("Could not set normal type.  Message:" + str(e))

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

        if self._normals_type_info_icon is not None:
            self._normals_type_info_icon.destroy()
            self._normals_type_info_icon = None

        _reset_default_attrs(self)
        _destroy_scanner_dialog()
