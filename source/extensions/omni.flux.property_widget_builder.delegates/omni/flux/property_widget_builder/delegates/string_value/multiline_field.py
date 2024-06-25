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

__all__ = ("MultilineField",)

import omni.ui as ui

from ..base import AbstractField


class MultilineField(AbstractField):
    def __init__(self, line_count, style_name: str = "PropertiesWidgetField") -> None:
        super().__init__(style_name=style_name)
        self._line_count = line_count

    def build_ui(self, item) -> list[ui.Widget]:
        # TODO: build "mixed" overlay (when multiple selection have different values)
        widgets = []
        with ui.HStack(height=ui.Pixel(20 * self._line_count)):
            for i in range(item.element_count):
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    # string field is bigger than 16px
                    style_override = self.style_name
                    if item.value_models[i].read_only:
                        style_override = style_override + "Read"
                    widget = ui.StringField(
                        model=item.value_models[i],
                        multiline=True,
                        read_only=item.value_models[i].read_only,
                        style_type_name_override=style_override,
                    )
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(2))
        return widgets
