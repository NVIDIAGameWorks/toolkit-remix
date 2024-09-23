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

__all__ = ("FloatSliderField",)

import carb
import omni.kit.undo
import omni.ui as ui

from ..base import AbstractField


class FloatSliderField(AbstractField):
    def __init__(self, min_value, max_value, step: int | None = None, style_name: str = "FloatSliderField"):
        super().__init__(style_name=style_name)
        assert min_value < max_value, "Min value must be less than max value"
        self.min_value = min_value
        self.max_value = max_value

        self._step = step

        self._subs: list[carb.Subscription] = []

    def begin_edit(self, _):
        omni.kit.undo.begin_group()

    def end_edit(self, _):
        omni.kit.undo.end_group()

    @property
    def step(self) -> int:
        if self._step is not None:
            return self._step
        return (self.max_value - self.min_value) * 0.005

    def build_ui(self, item) -> list[ui.Widget]:
        widgets = []
        with ui.HStack(height=ui.Pixel(24)):
            for i in range(item.element_count):

                # Create subscriptions on the begin/end edits so we can undo the slider changes all at once.
                value_model = item.value_models[i]
                self._subs.append(value_model.subscribe_begin_edit_fn(self.begin_edit))
                self._subs.append(value_model.subscribe_end_edit_fn(self.end_edit))

                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    style_type_name_override = (
                        f"{self.style_name}Read" if item.value_models[i].read_only else self.style_name
                    )
                    widget = ui.FloatDrag(
                        model=value_model,
                        style_type_name_override=style_type_name_override,
                        read_only=value_model.read_only,
                        min=self.min_value,
                        max=self.max_value,
                        step=self.step,
                    )
                    self.set_dynamic_tooltip_fn(widget, value_model)
                    widgets.append(widget)
                    ui.Spacer(height=ui.Pixel(2))
        return widgets
