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

from typing import TYPE_CHECKING, Any

import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.drag import FloatDragFieldGroup
from omni.flux.property_widget_builder.delegates.int_value.drag import IntDragFieldGroup

if TYPE_CHECKING:
    from ..items import USDAttributeItem


def _apply_item_constraints(widget: Any, item: "USDAttributeItem") -> None:
    """Attach normalized bounds/step metadata to the drag widget delegate.

    Why this exists:
        ``AbstractDragFieldGroup`` is intentionally generic and should not know about
        USD item metadata contracts. This helper is the USD-specific seam that
        transfers normalized adapter output from ``USDAttributeItem`` into the
        generic drag delegate fields used by float/int widgets.

    Args:
        widget: Drag delegate instance receiving bounds and step configuration.
        item: USD attribute item providing normalized adapter metadata.
    """
    bounds = item.get_min_max_bounds()
    if bounds:
        min_value, max_value, hard_min, hard_max = bounds
        widget.min_value = min_value
        widget.max_value = max_value
        widget.hard_min_value = hard_min
        widget.hard_max_value = hard_max

    step_value = item.get_step_value()
    if step_value is not None:
        widget.step = step_value


class USDFloatDragField(FloatDragFieldGroup):
    """USD float drag delegate that applies adapter-normalized constraints.

    Why this exists:
        Provides the USD integration layer over the generic ``FloatDragFieldGroup``
        by injecting item-level bounds/step metadata before constructing UI.
    """

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:
        """Apply USD metadata bounds and step, then build the drag UI."""
        _apply_item_constraints(self, item)
        return super().build_ui(item, **kwargs)


class USDIntDragField(IntDragFieldGroup):
    """USD int drag delegate that applies adapter-normalized constraints.

    Why this exists:
        Mirrors ``USDFloatDragField`` behavior for integer attributes so both
        numeric delegate types consume the same normalized USD metadata path.
    """

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:
        """Apply USD metadata bounds and step, then build the drag UI."""
        _apply_item_constraints(self, item)
        return super().build_ui(item, **kwargs)
