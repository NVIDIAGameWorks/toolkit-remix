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

__all__ = ("ColorField",)

from functools import partial

import omni.ui as ui

from ..base import AbstractField


class ColorValueModel(ui.AbstractValueModel):
    """
    Wrapper value model that allows for tweaking how the value is displayed as a string.
    """

    def __init__(self, parent: ui.AbstractValueModel, display_precision: int = 2):
        super().__init__()
        self._parent = parent
        self.display_precision = display_precision
        # Echo any value changes to ensure the widget updates
        self._sub = parent.subscribe_value_changed_fn(lambda _: self._value_changed())

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self._parent, attr)

    def get_value_as_string(self):
        return f"{self._parent.get_value_as_float():.{self.display_precision}f}"


class ColorField(AbstractField):
    """Delegate of the tree"""

    def __init__(self, display_precision: int = 2, style_name: str = "ColorsWidgetFieldRead"):
        super().__init__(style_name=style_name)

        self.display_precision = display_precision

        # The color widget is a bit unique as the provided item's model is not used directly within the widget. We
        # instead connect change events between the two models to ensure that updates properly flow both ways.
        self._color_widget_changed_sub = None
        self._value_model_value_changed_sub = None

        # Used to supress redundant change events.
        self._ignore_value_change_events = False

    def build_ui(self, item) -> list[ui.Widget]:

        if len(item.value_models) != 1:
            raise ValueError("Expected 1 value_model that holds the vector values")

        value_model = item.value_models[0]
        vec = value_model.get_attributes_raw_value(0)

        widgets = []

        with ui.HStack(height=ui.Pixel(24)):
            ui.Spacer(width=ui.Pixel(8))
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(2))
                color_widget = ui.ColorWidget(*vec, name=self.style_name)
                widgets.append(color_widget)
                ui.Spacer(height=ui.Pixel(2))

            ui.Spacer(width=ui.Pixel(4))

            for index, child in enumerate(color_widget.model.get_item_children()):
                child_model = color_widget.model.get_item_value_model(child)
                ui.Spacer(width=ui.Pixel(4))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    widgets.append(
                        ui.StringField(
                            model=ColorValueModel(child_model, display_precision=self.display_precision),
                            style_type_name_override=self.style_name,
                            read_only=True,
                        )
                    )
                    ui.Spacer(height=ui.Pixel(2))
                if index < len(vec) - 1:
                    ui.Spacer(width=ui.Pixel(4))
                    with ui.VStack(width=ui.Pixel(1)):
                        ui.Spacer(height=ui.Pixel(4))
                        ui.Rectangle(name="ColorsWidgetSeparator")
                        ui.Spacer(height=ui.Pixel(4))

            self._color_widget_changed_sub = color_widget.model.subscribe_end_edit_fn(
                partial(self._color_widget_changed, type(vec), value_model)
            )

        self._value_model_value_changed_sub = value_model.subscribe_value_changed_fn(
            partial(self._value_model_changed, color_widget)
        )

        return widgets

    def _value_model_changed(self, color_widget, value_model):
        if self._ignore_value_change_events:
            return
        vec = value_model.get_attributes_raw_value(0)
        children = color_widget.model.get_item_children()
        assert len(children) == len(vec), f"{vec} does not match expected length for ColorWidget"
        for child, value in zip(children, vec):
            child_value_model = color_widget.model.get_item_value_model(child)
            child_value_model.set_value(value)

    def _color_widget_changed(self, vec_type, value_model, model, _):
        new_value = vec_type(*[model.get_item_value_model(c).get_value_as_float() for c in model.get_item_children()])
        self._ignore_value_change_events = True
        value_model.set_value(new_value)
        self._ignore_value_change_events = False
