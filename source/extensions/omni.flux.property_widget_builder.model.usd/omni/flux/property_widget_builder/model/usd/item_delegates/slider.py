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

__all__ = ("USDFloatSliderField", "USDIntSliderField")

import carb
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.slider import FloatSliderField
from omni.flux.property_widget_builder.delegates.int_value.slider import IntSliderField


def _adjust_min_max_range(widget, item):
    """Adjust the slider's min/max from the item's bound metadata (ui_metadata or USD attribute customData)."""

    bounds = item.get_min_max_bounds()
    if not bounds:
        return

    min_value, max_value = bounds

    if min_value >= max_value:
        carb.log_warn(
            f"Slider bounds ignored: min ({min_value}) must be less than max ({max_value}) "
            f"for attribute(s) {item.attribute_paths}"
        )
        return

    widget.min_value = min_value
    widget.max_value = max_value


def _adjust_step(widget, item):
    """Set the widget's step from the item's step metadata (ui_metadata or USD attribute customData) if present."""
    step_value = item.get_step_value()
    if step_value is None:
        return
    widget.step = abs(step_value)


class USDFloatSliderField(FloatSliderField):
    """Float slider that adjusts min/max and step from USD attribute ``customData`` (limits, ui:step)."""

    def build_ui(self, item) -> list[ui.Widget]:
        """Apply USD metadata bounds and step, then build the slider UI."""
        _adjust_min_max_range(self, item)
        _adjust_step(self, item)
        return super().build_ui(item)


class USDIntSliderField(IntSliderField):
    """Int slider that adjusts min/max and step from USD attribute ``customData`` (limits, ui:step)."""

    def build_ui(self, item) -> list[ui.Widget]:
        """Apply USD metadata bounds and step, then build the slider UI."""
        _adjust_min_max_range(self, item)
        _adjust_step(self, item)
        return super().build_ui(item)
