# noqa PLC0302
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
__all__ = ["FeatureFlagDelegate"]

from omni import ui

from .item import FeatureFlagItem
from .model import FeatureFlagModel


class FeatureFlagDelegate(ui.AbstractItemDelegate):
    _ROW_HEIGHT = ui.Pixel(24)
    _HORIZONTAL_PADDING = ui.Pixel(8)

    def build_widget(self, model: FeatureFlagModel, item: FeatureFlagItem, column_id: int, level: int, expanded: bool):
        if item is None:
            return
        if column_id == 0:
            with ui.HStack(height=self._ROW_HEIGHT, tooltip=item.tooltip):
                ui.Spacer(height=0)
                with ui.VStack():
                    ui.Spacer(width=0)
                    checkbox = ui.CheckBox(width=0, height=0, identifier="feature_flag_checkbox")
                    ui.Spacer(width=0)
                ui.Spacer(height=0)

                checkbox.model.set_value(item.value)
                checkbox.model.add_value_changed_fn(
                    lambda value_model: model.set_enabled(item, value_model.get_value_as_bool())
                )
        if column_id == 1:
            with ui.HStack(height=self._ROW_HEIGHT, spacing=self._HORIZONTAL_PADDING, tooltip=item.tooltip):
                ui.Spacer(width=0, height=0)
                ui.Label(item.display_name, identifier="feature_flag_label")

    def build_header(self, column_id: int):
        with ui.HStack(height=self._ROW_HEIGHT, spacing=self._HORIZONTAL_PADDING):
            ui.Spacer(width=0, height=0)
            ui.Label(
                FeatureFlagModel.headers.get(column_id),
                alignment=ui.Alignment.LEFT_CENTER,
                style_type_name_override="TreeView.Header",
                identifier="feature_flag_title",
            )
