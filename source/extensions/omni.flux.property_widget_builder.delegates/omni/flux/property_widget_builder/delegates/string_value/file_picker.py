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

__all__ = ("FilePicker",)

import functools
import typing

import omni.client
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker

from ..base import AbstractField

if typing.TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import ItemModelBase


class FilePicker(AbstractField):
    def __init__(
        self,
        file_extension_options: list[tuple[str, str]] | None = None,
        style_name: str = "PropertiesWidgetField",
        use_relative_paths: bool = False,
    ):
        """
        A delegate that will show a stringField with a file picker

        Args:
            file_extension_options: A list of filename extension options. Each list element is an (extension name,
                  description) pair.

                Examples: ``("*.usdc", "Binary format")`` or ``(".usd*", "USD format")``
                    or ``("*.png, *.jpg, *.exr", "Image format")``
            use_relative_paths: If True, convert selected file paths to be relative to the current USD edit target.
                  Requires the value_model to have a `stage` attribute.
        """
        super().__init__(style_name=style_name)
        self._file_extension_options = file_extension_options
        self._use_relative_paths = use_relative_paths
        self._sub_field_begin_edit = []
        self._sub_field_end_edit = []
        self._sub_field_changed = []

    def build_ui(self, item) -> list[ui.Widget]:  # noqa PLW0221
        widgets = []
        self._sub_field_begin_edit = []
        self._sub_field_end_edit = []
        self._sub_field_changed = []
        with ui.HStack(height=ui.Pixel(20)):
            for i in range(item.element_count):
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))

                    style_name = f"{self.style_name}Read" if item.value_models[i].read_only else self.style_name

                    widget = ui.StringField(
                        model=item.value_models[i],
                        read_only=item.value_models[i].read_only,
                        style_type_name_override=style_name,
                    )
                    self.set_dynamic_tooltip_fn(widget, item.value_models[i])

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
                        mouse_pressed_fn=functools.partial(self._on_open_file_pressed, widget, item.value_models[i], i),
                    )
                    ui.Spacer()
        return widgets

    def _on_field_begin(self, widget: ui.AbstractField, value_model: "ItemModelBase", element_current_idx: int, model):
        pass

    def _on_field_end(self, widget: ui.AbstractField, value_model: "ItemModelBase", element_current_idx: int, model):
        pass

    def _on_field_changed(
        self, widget: ui.AbstractField, value_model: "ItemModelBase", element_current_idx: int, model
    ):
        pass

    def _on_navigate_to(self, path, value_model: "ItemModelBase", element_current_idx: int) -> tuple[bool, str]:
        """
        Function that defines the path to navigate to by default when we open the file picker

        Args:
            path: the default path given to the file picker

        Returns:
            The fallback value of the file picker and the path to navigate to
        """
        # Open the file picker to current asset location
        fallback = False
        if not _path_utils.is_file_path_valid(path, log_error=False):
            fallback = True
            path = None
        return fallback, path

    def _on_open_file_pressed(
        self, widget: ui.AbstractField, value_model: "ItemModelBase", element_current_idx: int, x, y, button, modifier
    ):
        if button != 0:
            return
        navigate_to = widget.model.get_value_as_string()

        # Open the file picker to current asset location
        fallback, navigate_to = self._on_navigate_to(navigate_to, value_model, element_current_idx)

        _open_file_picker(
            "File picker",
            functools.partial(self._set_field, widget, value_model, element_current_idx),
            lambda *args: None,
            current_file=navigate_to,
            fallback=fallback,
            file_extension_options=self._file_extension_options,
        )

    def _set_field(self, widget: ui.AbstractField, value_model: "ItemModelBase", element_current_idx: int, path: str):
        if self._use_relative_paths and hasattr(value_model, "stage") and value_model.stage:
            path = omni.client.normalize_url(
                omni.usd.make_path_relative_to_current_edit_target(path, stage=value_model.stage)
            ).replace("\\", "/")
        widget.model.set_value(path)
