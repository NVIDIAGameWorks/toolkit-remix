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

__all__ = ("USDFloatDragField", "USDIntDragField")

import carb
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.drag import FloatDragField
from omni.flux.property_widget_builder.delegates.int_value.drag import IntDragField


def _adjust_bounds(widget, item):
    """Adjust the widget's soft and hard bounds from item metadata.

    When both min and max are present the soft drag range is set.  Hard bounds
    are resolved independently (preferring explicit hard bounds, falling back
    to the soft value) so that single-bound clamping works for partially-bounded
    attributes.
    """
    bounds = item.get_min_max_bounds()
    if not bounds:
        return

    min_value, max_value, hard_min, hard_max = bounds

    if min_value is not None and max_value is not None:
        if min_value >= max_value:
            carb.log_warn(
                f"Drag bounds ignored: min ({min_value}) must be less than max ({max_value}) "
                f"for attribute(s) {item.attribute_paths}"
            )
        else:
            widget.min_value = min_value
            widget.max_value = max_value

    resolved_hard_min = hard_min if hard_min is not None else min_value
    resolved_hard_max = hard_max if hard_max is not None else max_value

    if resolved_hard_min is not None and resolved_hard_max is not None and resolved_hard_min >= resolved_hard_max:
        carb.log_warn(
            f"Hard bounds ignored: hard_min ({resolved_hard_min}) must be less than "
            f"hard_max ({resolved_hard_max}) for attribute(s) {item.attribute_paths}"
        )
        return

    widget.hard_min_value = resolved_hard_min
    widget.hard_max_value = resolved_hard_max


def _adjust_step(widget, item):
    """Set the widget's step from the item's step metadata (ui_metadata or USD attribute customData) if present."""
    step_value = item.get_step_value()
    if step_value is None:
        return
    widget.step = abs(step_value)


class USDFloatDragField(FloatDragField):
    """Float drag that adjusts bounds and step from USD attribute ``customData``."""

    def build_ui(self, item) -> list[ui.Widget]:
        """Apply USD metadata bounds and step, then build the drag UI."""
        _adjust_bounds(self, item)
        _adjust_step(self, item)
        return super().build_ui(item)


class USDIntDragField(IntDragField):
    """Int drag that adjusts bounds and step from USD attribute ``customData``."""

    def build_ui(self, item) -> list[ui.Widget]:
        """Apply USD metadata bounds and step, then build the drag UI."""
        _adjust_bounds(self, item)
        _adjust_step(self, item)
        return super().build_ui(item)
