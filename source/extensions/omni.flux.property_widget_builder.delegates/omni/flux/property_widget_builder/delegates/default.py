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

__all__ = (
    "CreatorField",
    "DefaultField",
)

from collections.abc import Callable

import omni.ui as ui

from .base import AbstractField


class DefaultField(AbstractField):
    """
    A default field can be used to create a simple widget(s) for an item's value_models.
    """

    def __init__(
        self, widget_type: type[ui.Widget], style_name: str = "PropertiesWidgetField", identifier: None | str = None
    ):
        super().__init__(style_name=style_name, identifier=identifier)
        self.widget_type = widget_type

    def build_ui(self, item) -> list[ui.Widget]:
        widgets = []
        with ui.HStack(height=ui.Pixel(24)):
            for i in range(item.element_count):
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    style_name = f"{self.style_name}Read" if item.value_models[i].read_only else self.style_name
                    widget = self.widget_type(
                        model=item.value_models[i],
                        style_type_name_override=style_name,
                        read_only=item.value_models[i].read_only,
                        identifier=self.identifier or "",
                    )
                    self.set_dynamic_tooltip_fn(widget, item.value_models[i])
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(2))
        return widgets


class CreatorField(AbstractField):
    """
    A simple delegate that presents a button that when clicked will trigger the provided callback.
    """

    def __init__(
        self,
        text: str = "Create",
        clicked_callback: Callable[[], None] | None = None,
        style_name: str = "PropertiesWidgetField",
    ) -> None:
        super().__init__(style_name=style_name)
        self._text = text
        self._clicked_callback = clicked_callback

    def build_ui(self, item) -> list[ui.Widget]:
        with ui.HStack(height=ui.Pixel(24)):
            ui.Spacer(width=ui.Pixel(8))
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(2))
                widgets = [
                    ui.Button(self._text, style_type_name_override=self.style_name, clicked_fn=self._clicked_callback)
                ]
                ui.Spacer(height=ui.Pixel(2))
        return widgets
