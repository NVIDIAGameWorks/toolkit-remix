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

__all__ = ("FileTexturePicker",)

import functools
import os
import re
import struct
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, List, Pattern, Tuple

import carb
import omni.client
import omni.ui as ui
import omni.usd
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.property_widget_builder.delegates.string_value.file_picker import FilePicker as _FilePicker
from omni.flux.property_widget_builder.model.file import CustomFileAttributeItem as _CustomFileAttributeItem
from omni.flux.property_widget_builder.model.file import FileAttributeItem as _FileAttributeItem
from omni.flux.property_widget_builder.model.file import FileDelegate as _FileDelegate
from omni.flux.property_widget_builder.model.file import FileModel as _FileModel
from omni.flux.property_widget_builder.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import path_utils as _path_utils
from PIL import Image

from ..item_model.attr_value import UsdAttributeValueModel as _UsdAttributeValueModel

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import ItemModelBase


class FileTexturePicker(_FilePicker):
    """Delegate of the tree"""

    POPUP_OFFSET = 40
    POPUP_WIDTH = 600
    POPUP_HEIGHT = 320

    def __init__(
        self,
        file_extension_options: List[Tuple[str, str]] | None = None,
        style_name: str = "PropertiesWidgetField",
        regex_hash: Pattern[str] = None,
    ):
        if file_extension_options is None:
            file_extension_options = [(f"{', '.join(_SUPPORTED_TEXTURE_EXTENSIONS)}", "Image files")]

        super().__init__(file_extension_options=file_extension_options, style_name=style_name)

        self._regex_hash = regex_hash
        self._preview_window = None
        self._preview_button = None

        # Populated during a right click event within `_show_copy_menu` to avoid garbage collection
        self._context_menu: ui.Menu | None = None

        self.__field_changed_by_user = False

    def build_ui(self, item) -> list[ui.Widget]:
        widgets = []
        self._sub_field_begin_edit = []
        self._sub_field_end_edit = []
        self._sub_field_changed = []
        with ui.ZStack():
            with ui.HStack(height=ui.Pixel(20)):
                for i in range(item.element_count):
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(2))
                        read_only = item.value_models[i].read_only
                        # string field is bigger than 16px h
                        widget = ui.StringField(
                            model=item.value_models[i],
                            read_only=read_only,
                            style_type_name_override=f"{self.style_name}Read" if read_only else self.style_name,
                            identifier="file_texture_string_field",
                            mouse_pressed_fn=functools.partial(self._show_copy_menu, item.value_models[i]),
                        )

                        def _update_tooltip_value(hovered: bool, value_index=i, string_field_widget=widget):
                            if item.value_models[value_index].is_mixed:
                                # TODO: We should probably display resolved paths here too. We
                                #  need to store assetPath object in `value_model._values` to make that happen.
                                tooltip = item.value_models[value_index].get_tool_tip()
                            else:
                                tooltip = None
                                value = item.value_models[value_index].get_value()
                                if value:
                                    tooltip = value.resolvedPath
                                # If there was no resolved path, use fallback paths
                                if tooltip is None or tooltip == "":
                                    tooltip = self.__get_value_model_fallback_path(
                                        item.value_models[value_index], must_be_absolute=False
                                    )
                            string_field_widget.tooltip = str(tooltip)

                        widget.set_mouse_hovered_fn(_update_tooltip_value)

                        self._sub_field_begin_edit.append(
                            widget.model.subscribe_begin_edit_fn(
                                functools.partial(self._on_field_begin, widget, item.value_models[i], i)
                            )
                        )
                        self._sub_field_end_edit.append(
                            widget.model.subscribe_end_edit_fn(
                                functools.partial(self._on_field_end, widget, item.value_models[i], i)
                            )
                        )
                        self._sub_field_changed.append(
                            widget.model.subscribe_value_changed_fn(
                                functools.partial(self._on_field_changed, widget, item.value_models[i], i)
                            )
                        )
                        widgets.append(widget)
                        ui.Spacer(height=ui.Pixel(2))
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack(width=ui.Pixel(20)):
                        ui.Spacer()
                        ui.Image(
                            "",
                            name="OpenFolder",
                            height=ui.Pixel(20),
                            mouse_pressed_fn=functools.partial(
                                self._on_open_file_pressed, widget, item.value_models[i], i
                            ),
                        )
                        ui.Spacer()
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack(width=ui.Pixel(20)):
                        ui.Spacer()
                        self._preview_button = ui.Image(
                            "",
                            name="Preview",
                            height=ui.Pixel(20),
                            mouse_pressed_fn=functools.partial(self._preview_image, item.value_models[i], i),
                        )
                        ui.Spacer()

            # Initialize the preview window with a unique title/window ID so that it has its own instance in memory
            item_raw_value = item.value_models[0].get_attributes_raw_value(0)
            # Use the texture path as part of the title and fallback on using the asset name
            if item_raw_value is not None and item_raw_value != "":
                title_path = os.path.basename(item_raw_value.resolvedPath)
            else:
                title_path = item.value_models[0].attribute_paths[0].pathString.split("/")[3]

            self._preview_window = ui.Window(
                title=f"{title_path} - {item.name_models[0].get_value_as_string()}",
                name="PropertiesPaneSectionWindow",
                width=self.POPUP_WIDTH,
                height=self.POPUP_HEIGHT,
                visible=False,
                flags=(ui.WINDOW_FLAGS_NO_DOCKING | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLLBAR),
            )
        return widgets

    def _preview_image(self, value_model: "ItemModelBase", element_index, x, y, button, modifier):
        if button != 0:
            return

        # Get the raw path attribute to get the resolved path
        raw_value = value_model.get_attributes_raw_value(element_index)
        resolved_path = raw_value.resolvedPath if raw_value is not None else None

        self._preview_window.frame.clear()
        if not resolved_path or not _path_utils.is_file_path_valid(resolved_path):
            self._build_no_image_ui()
        else:
            self._build_image_preview_ui(resolved_path)

        self._preview_window.setPosition(
            self._preview_button.screen_position_x + ui.Pixel(self.POPUP_OFFSET),
            self._preview_button.screen_position_y - ui.Pixel(self.POPUP_HEIGHT / 2),
        )
        self._preview_window.visible = True

    def _build_no_image_ui(self):
        with self._preview_window.frame:
            with ui.ZStack():
                with ui.ScrollingFrame(
                    name="PreviewWindowBackground",
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    scroll_y_max=0,
                ):
                    with ui.HStack():
                        for _ in range(5):
                            with ui.VStack():
                                for _ in range(5):
                                    ui.Image(
                                        "",
                                        name="TreePanelLinesBackground",
                                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                        height=ui.Pixel(256),
                                        width=ui.Pixel(256),
                                    )
                with ui.Frame(separate_window=True):
                    ui.Label(
                        "No texture to preview",
                        alignment=ui.Alignment.CENTER,
                        name="PropertiesPaneSectionCaptureTreeItemNoImage",
                    )

    @staticmethod
    def _get_resolution(path: str) -> Tuple[int, int]:
        """
        Get the width and height of the provided image file.
        """
        try:
            im = Image.open(path)
        except NotImplementedError as exc:

            carb.log_warn(f"Error reading image {path!r}, attempting workaround to extract resolution")

            # TODO: REMIX-2468
            #  There is an issue with BC4 dds images in PIL. The issue is nvtt uses the DX10 header so it can
            #  specify the exact DXGI format, but PIL lacks support for BC4 with this header. The ticket above
            #  is for opening a PR with PIL and once that is merged we can update the PIL dependency and remove
            #  this fix.

            # Below code extracted from Pillow's DdsImagePlugin implementation
            # https://github.com/python-pillow/Pillow/blob/main/src/PIL/DdsImagePlugin.py

            with open(path, "rb") as fp:
                if fp.read(4)[:4] != b"DDS ":
                    # Re-raise the original error here if the file isn't a candidate for our hack
                    raise
                (header_size,) = struct.unpack("<I", fp.read(4))
                if header_size != 124:
                    raise OSError(f"Unsupported header size {repr(header_size)}") from exc
                header_bytes = fp.read(header_size - 4)
                if len(header_bytes) != 120:
                    raise OSError(f"Incomplete header: {len(header_bytes)} bytes") from exc
                header = BytesIO(header_bytes)
                _, height, width = struct.unpack("<3I", header.read(12))
            return width, height

        width, height = im.width, im.height
        im.close()
        return width, height

    def _build_image_preview_ui(self, resolved_path):
        # Get the image file attributes
        file_attributes = []

        width, height = self._get_resolution(resolved_path)
        file_attributes.append(_CustomFileAttributeItem([f"{width} px", f"{height} px"], "Resolution"))

        for attr in [attr for attr in dir(omni.client.ListEntry) if not attr.startswith("_")]:
            file_attributes.append(
                _FileAttributeItem(resolved_path, attr, display_attr_name=attr.replace("_", " ").capitalize())
            )
        file_attributes_delegate = _FileDelegate()
        file_attributes_model = _FileModel(resolved_path)
        file_attributes_model.set_items(file_attributes)

        with self._preview_window.frame:
            with ui.HStack():
                with ui.ZStack():
                    with ui.ScrollingFrame(
                        name="PreviewWindowBackground",
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        scroll_y_max=0,
                    ):
                        with ui.HStack():
                            for _ in range(5):
                                with ui.VStack():
                                    for _ in range(5):
                                        ui.Image(
                                            "",
                                            name="TreePanelLinesBackground",
                                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                            height=ui.Pixel(256),
                                            width=ui.Pixel(256),
                                        )
                    with ui.CanvasFrame(style_type_name_override="ImagePreviewCanvas"):
                        with Image.open(resolved_path) as im:
                            provider = ui.ByteImageProvider()
                            channels = im.getdata().mode
                            if len(channels) == 1:
                                im = im.convert("RGBA")
                            provider.set_bytes_data(list(im.getdata()), [im.size[0], im.size[1]])
                            self._texture_viewer_widget = ui.ImageWithProvider(provider)
                with ui.ScrollingFrame(name="WorkspaceBackground", width=ui.Pixel(300)):
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(16))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(16))
                            self._texture_attributes_widget = _PropertyWidget(
                                file_attributes_model, file_attributes_delegate
                            )
                            ui.Spacer(height=ui.Pixel(8))
                            ui.Button(
                                "Show File in Explorer",
                                height=ui.Pixel(24),
                                mouse_released_fn=lambda x, y, b, m: self._open_explorer(b, resolved_path),
                            )
                            ui.Spacer(height=ui.Pixel(16))
                        ui.Spacer(width=ui.Pixel(8))

    def _open_explorer(self, button, file_path):
        if button != 0:
            return
        path = Path(file_path)
        os.startfile(path.parent if path.is_file() else path)

    def _on_navigate_to(
        self, path, value_model: "_UsdAttributeValueModel", element_current_idx: int
    ) -> Tuple[bool, str]:
        """
        Function that defines the path to navigate to by default when we open the file picker

        Args:
            path: the default path given to the file picker

        Returns:
            The fallback value of the file picker and the path to navigate to
        """
        # Open the file picker to current asset location
        fallback = False
        path = value_model.get_attributes_raw_value(element_current_idx)
        stage = value_model.stage
        if path and path.path.strip():
            path = path.resolvedPath
            if not path.strip():
                path = None
                fallback = True
        else:
            if stage and not stage.GetRootLayer().anonymous:
                # If asset path is empty, open the USD rootlayer folder
                # But only if filepicker didn't already have a folder remembered (thus fallback)
                path = os.path.dirname(stage.GetRootLayer().identifier)
            else:
                path = None
            fallback = True

        if not path or not _path_utils.is_file_path_valid(path):
            fallback = True
            path = None
        else:
            path = omni.client.normalize_url(path).replace("\\", "/")
        return fallback, path

    def __is_field_path_valid(
        self, path, widget: ui.AbstractField, value_model: "_UsdAttributeValueModel", element_current_idx: int
    ) -> bool:
        edit_target_layer = value_model.stage.GetEditTarget().GetLayer()
        if not self.__field_changed_by_user:  # we grab the layer that the attribute use
            attribute_path = value_model.attribute_paths[element_current_idx]
            prim = value_model.stage.GetPrimAtPath(attribute_path.GetPrimPath())
            if prim.IsValid():
                attr = prim.GetAttribute(attribute_path.name)
                if attr.IsValid() and not attr.IsHidden():
                    _, layer = omni.usd.get_attribute_effective_defaultvalue_layer_info(value_model.stage, attr)
                    if layer is None:
                        # no edit was done, we can check the resolved value
                        value = attr.Get()
                        if not value:
                            widget.style_type_name_override = "Field"
                            return True
                        edit_target_layer = None
                        resolved_value = value.resolvedPath
                        if resolved_value:
                            path = str(resolved_value)
                        else:
                            # we can't check
                            widget.style_type_name_override = "Field"
                            return True
                    else:
                        edit_target_layer = layer

        valid = not path or _path_utils.is_file_path_valid(path, layer=edit_target_layer)
        if not valid:
            widget.style_type_name_override = "FieldError"
            return False
        widget.style_type_name_override = "Field"
        return True

    def __get_value_model_fallback_path(
        self, value_model: "_UsdAttributeValueModel", must_be_absolute: bool = False
    ) -> str:
        fallback_path = ""
        if value_model.get_value_as_string() and isinstance(value_model, _UsdAttributeValueModel):
            asset_path = value_model.get_value_as_string()

            # At least use a relative path as the fallback
            if not must_be_absolute:
                fallback_path = asset_path

            # Obtain a value model attribute to derive a prim
            value_model_attribute = None
            for attr in value_model.attributes:
                value_model_attribute = attr
                break
            if value_model_attribute is None:
                return fallback_path

            # Find an absolute path with the attr prim if possible, otherwise leave the fallback path as ""
            prim_stack = value_model_attribute.GetPrim().GetPrimStack()
            if prim_stack:
                layer = None
                for prim_spec in prim_stack:
                    if not prim_spec.layer.anonymous:
                        layer = prim_spec.layer
                        break

                if layer:
                    absolute_asset_path = layer.ComputeAbsolutePath(asset_path)
                    if absolute_asset_path:
                        fallback_path = absolute_asset_path

        return fallback_path

    def _on_field_begin(
        self, widget: ui.AbstractField, value_model: "_UsdAttributeValueModel", element_current_idx: int, model
    ):
        # we only set the value of the texture at the end of the edit
        self.__field_changed_by_user = True
        value_model.block_set_value(True)

    def _on_field_end(
        self, widget: ui.AbstractField, value_model: "_UsdAttributeValueModel", element_current_idx: int, model
    ):
        self.__field_changed_by_user = False
        value_model.block_set_value(False)
        value_model.set_value(value_model.cached_blocked_value)

    def _on_field_changed(
        self, widget: ui.AbstractField, value_model: "_UsdAttributeValueModel", element_current_idx: int, model
    ):
        value_model.block_set_value(True)
        path = (
            value_model.cached_blocked_value
            if value_model.cached_blocked_value is not None
            else widget.model.get_value_as_string()
        )
        self.__is_field_path_valid(path, widget, value_model, element_current_idx)

    def _set_field(
        self, widget: ui.AbstractField, value_model: "_UsdAttributeValueModel", element_current_idx: int, path: str
    ):
        """
        Set the field. For texture from USD, we always set relative paths

        Args:
            widget: the widget field to set
            path: the path that was selected from the file picker
        """
        self.__field_changed_by_user = True
        value_model.block_set_value(False)
        if not self.__is_field_path_valid(path, widget, value_model, element_current_idx):
            return
        relative_path = omni.client.normalize_url(
            omni.usd.make_path_relative_to_current_edit_target(path, stage=value_model.stage)
        ).replace("\\", "/")
        super()._set_field(widget, value_model, element_current_idx, relative_path)
        self.__field_changed_by_user = False

    def _show_copy_menu(self, value_model: "_UsdAttributeValueModel", x: float, y: float, b: int, m: int):
        """
        Display a menu if the string field was right-clicked to show the copy full file path button.
        """
        # Only show the menu with right click
        if b != 1:
            return

        # Obtain the absolute asset path
        absolute_asset_path = value_model.get_value().resolvedPath
        if not absolute_asset_path:
            absolute_asset_path = self.__get_value_model_fallback_path(value_model, must_be_absolute=True)

        # Avoid menu if value_model is invalid type or has no path
        if not isinstance(value_model, _UsdAttributeValueModel) or not absolute_asset_path:
            return

        # NOTE: This menu is stored on the object to avoid garbage collection and being prematurely destroyed
        if self._context_menu is not None:
            self._context_menu.destroy()
        self._context_menu = ui.Menu("Context Menu")

        with self._context_menu:
            ui.MenuItem(
                "Copy Full File Path",
                identifier="copy_full_file_path",
                triggered_fn=lambda: omni.kit.clipboard.copy(absolute_asset_path),
            )
            if self._regex_hash is not None:
                hash_match = re.match(self._regex_hash, absolute_asset_path)
                ui.MenuItem(
                    "Copy File Path Hash",
                    enabled=hash_match is not None,
                    identifier="copy_file_path_hash",
                    triggered_fn=lambda: omni.kit.clipboard.copy(hash_match.group(2)),
                )

        self._context_menu.show()
