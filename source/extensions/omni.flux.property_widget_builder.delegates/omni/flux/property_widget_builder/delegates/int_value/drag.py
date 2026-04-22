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

__all__ = ("IntDragFieldGroup",)

from typing import Any
import omni.ui as ui
from omni.flux.utils.widget import IntBoundedDrag

from ..base import AbstractDragFieldGroup, BoundsValue, RealNumber


class IntDragFieldGroup(AbstractDragFieldGroup):
    """An integer drag field delegate with optional min/max bounds and step."""

    def __init__(
        self,
        min_value: BoundsValue | None = None,
        max_value: BoundsValue | None = None,
        hard_min_value: BoundsValue | None = None,
        hard_max_value: BoundsValue | None = None,
        step: BoundsValue | None = None,
        **kwargs,
    ):
        """Initialize the int drag field.

        Args:
            min_value: Soft minimum for the drag range. May be scalar or
                sequence-like for per-channel resolution. ``None`` = unbounded.
            max_value: Soft maximum for the drag range. May be scalar or
                sequence-like for per-channel resolution. ``None`` = unbounded.
            hard_min_value: Hard minimum bound forwarded to the drag widget for
                typed-value clamping via widget pre-set callbacks. May be scalar
                or sequence-like for per-channel resolution.
            hard_max_value: Hard maximum bound forwarded to the drag widget for
                typed-value clamping via widget pre-set callbacks. May be scalar
                or sequence-like for per-channel resolution.
            step: Optional step size; explicit values may be scalar or
                sequence-like. If unset and both scalar bounds are set, ``1``
                for range <= 100, else ``max(1, int(range * 0.01))``; otherwise ``1``.
            **kwargs: Passed to AbstractDragFieldGroup (e.g. style_name, default "DragField").
        """
        style_name = kwargs.get("style_name", "DragField")
        kwargs["style_name"] = style_name
        super().__init__(
            min_value=min_value,
            max_value=max_value,
            hard_min_value=hard_min_value,
            hard_max_value=hard_max_value,
            step=step,
            **kwargs,
        )

    @property
    def step(self) -> BoundsValue:
        """Step size; uses explicit step if set, else derives from range or falls back to 1."""
        if self._step is not None:
            return self._step
        if isinstance(self.min_value, RealNumber) and isinstance(self.max_value, RealNumber):
            range_size = self.max_value - self.min_value
            if range_size <= 100:
                return 1
            return max(1, int(range_size * 0.01))
        return 1

    @step.setter
    def step(self, value: BoundsValue) -> None:
        self._step = value

    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int | None,
        max_val: float | int | None,
        hard_min_val: float | int | None,
        hard_max_val: float | int | None,
        step: float | int | None,
    ) -> ui.Widget:
        """Build a ui.IntDrag widget, only passing bounds/step that are set."""
        kwargs: dict[str, Any] = {
            "model": model,
            "style_type_name_override": style_type_name_override,
            "read_only": read_only,
            "identifier": self.identifier or "",
            "hard_min_value": hard_min_val,
            "hard_max_value": hard_max_val,
        }
        if min_val is not None:
            kwargs["min"] = min_val
        if max_val is not None:
            kwargs["max"] = max_val
        if step is not None:
            kwargs["step"] = step
        return IntBoundedDrag(**kwargs)
