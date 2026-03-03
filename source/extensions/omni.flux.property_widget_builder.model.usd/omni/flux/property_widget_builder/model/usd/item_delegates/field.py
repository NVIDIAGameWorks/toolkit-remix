"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("USDFloatField", "USDIntField")

import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.field import FloatField
from omni.flux.property_widget_builder.delegates.int_value.field import IntField


def _adjust_clamp_bounds(widget, item):
    """Read whatever bounds are available from the item and configure clamping."""
    bounds = item.get_min_max_bounds()
    if not bounds:
        return

    min_value, max_value, hard_min, hard_max = bounds
    widget.clamp_min = hard_min if hard_min is not None else min_value
    widget.clamp_max = hard_max if hard_max is not None else max_value


class USDFloatField(FloatField):
    """Float field that configures clamp bounds from USD attribute metadata."""

    def build_ui(self, item) -> list[ui.Widget]:
        _adjust_clamp_bounds(self, item)
        return super().build_ui(item)


class USDIntField(IntField):
    """Int field that configures clamp bounds from USD attribute metadata."""

    def build_ui(self, item) -> list[ui.Widget]:
        _adjust_clamp_bounds(self, item)
        return super().build_ui(item)
