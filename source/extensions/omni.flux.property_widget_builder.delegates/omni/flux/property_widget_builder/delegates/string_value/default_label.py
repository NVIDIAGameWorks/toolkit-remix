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
    "DefaultLabelField",
    "NameField",
)

import functools
from collections.abc import Callable

import omni.ui as ui

from ..base import AbstractField


class DefaultLabelField(AbstractField):
    """Delegate of the tree"""

    def __init__(self, widget_type_name: str, style_name: str = "PropertiesWidgetField", identifier: None | str = None):
        super().__init__(style_name=style_name, identifier=identifier)
        self.widget_type_name = widget_type_name

    def build_ui(self, item) -> list[ui.Widget]:
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer(height=ui.Pixel(4))
            with ui.HStack(width=ui.Percent(60), height=ui.Pixel(16)):
                ui.Spacer(width=ui.Pixel(8))
                widget = ui.Label(
                    f"{item.value_models[0].get_value_as_string()}: {self.widget_type_name}",
                    name="USDPropertiesWidgetLabelValue",
                    alignment=ui.Alignment.LEFT,
                    height=0,
                    identifier=self.identifier or "",
                )
                self.set_dynamic_tooltip_fn(widget, item.value_models[0])
                ui.Spacer()
            ui.Spacer(height=ui.Pixel(4))
        return [widget]


class NameField(AbstractField):
    """Build property name labels with optional selected behavior."""

    @staticmethod
    def _set_selected_style(widget: ui.Widget, selected: bool) -> None:
        """Apply the existing selected style suffix to a property label."""
        suffix = "Selected" if selected else ""
        widget.style_type_name_override = f"PropertiesWidgetLabel{suffix}"

    def _create_attribute_name_build_fn(
        self,
        item,
        right_aligned: bool,
        selected: bool,
        subscribe_selected_changed: Callable[[Callable[[bool], None]], object] | None,
        register_subscription: Callable[[object], None] | None,
    ) -> None:
        """Build property labels with optional selection behavior."""
        from omni.flux.property_widget_builder.widget import ItemGroup  # noqa: PLC0415

        widgets = []
        with ui.HStack():
            with ui.VStack(height=ui.Pixel(24)):
                ui.Spacer(height=ui.Pixel(4))
                with ui.HStack(height=ui.Pixel(16)):
                    if not isinstance(item, ItemGroup) and right_aligned:
                        ui.Spacer()
                    for name_model in item.name_models:
                        value = name_model.get_value_as_string()
                        tooltip = name_model.get_tool_tip()
                        widget = ui.Label(
                            value,
                            width=0,
                            name="PropertiesWidgetLabel",
                            style_type_name_override=(
                                "PropertiesWidgetLabelSelected" if selected else "PropertiesWidgetLabel"
                            ),
                            identifier=self.identifier or "",
                        )
                        if tooltip:
                            widget.set_tooltip(tooltip)
                        if subscribe_selected_changed is not None and register_subscription is not None:
                            register_subscription(
                                subscribe_selected_changed(functools.partial(self._set_selected_style, widget))
                            )
                        widgets.append(widget)

                    ui.Spacer(width=ui.Pixel(8))
                ui.Spacer(height=ui.Pixel(4))

            if isinstance(item, ItemGroup):
                ui.Spacer(height=0)

    def build_ui(
        self,
        item,
        right_aligned: bool = True,
        selected: bool = False,
        subscribe_selected_changed: Callable[[Callable[[bool], None]], object] | None = None,
        register_subscription: Callable[[object], None] | None = None,
    ) -> list[ui.Widget]:
        """Build the property name cell and optional persistent selection behavior."""
        stack = ui.VStack()
        with stack:
            frame = ui.Frame()
            frame.set_build_fn(
                functools.partial(
                    self._create_attribute_name_build_fn,
                    item,
                    right_aligned,
                    selected,
                    subscribe_selected_changed,
                    register_subscription,
                )
            )
            ui.Spacer(width=0)
        return [stack]
