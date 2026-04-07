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

__all__ = ("FloatDragField",)

import omni.ui as ui

from ..base import AbstractDragField


class FloatDragField(AbstractDragField):
    """A float drag field delegate with optional min/max bounds and step."""

    def __init__(
        self,
        min_value: float | None = None,
        max_value: float | None = None,
        hard_min_value: float | None = None,
        hard_max_value: float | None = None,
        step: float | None = None,
        **kwargs,
    ):
        """Initialize the float drag field.

        Args:
            min_value: Soft minimum for the drag range.  ``None`` = unbounded.
            max_value: Soft maximum for the drag range.  ``None`` = unbounded.
            hard_min_value: Hard minimum bound for clamping on end-edit.
            hard_max_value: Hard maximum bound for clamping on end-edit.
            step: Optional step size; if None and both bounds are set, computed
                as ``(max_value - min_value) * 0.005``; otherwise ``1.0``.
            **kwargs: Passed to AbstractDragField (e.g. style_name, default "DragField").
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
    def step(self) -> float:
        """Step size; uses explicit step if set, else derives from range or falls back to 1.0."""
        if self._step is not None:
            return self._step
        if self.min_value is not None and self.max_value is not None:
            return (self.max_value - self.min_value) * 0.005
        return 1.0

    @step.setter
    def step(self, value: float) -> None:
        self._step = value

    def _get_value_from_model(self, model) -> int | float:
        return model.get_value_as_float()

    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int | None,
        max_val: float | int | None,
        step: float | int | None,
    ) -> ui.Widget:
        """Build a ui.FloatDrag widget, only passing bounds/step that are set."""
        kwargs: dict[str, object] = {
            "model": model,
            "style_type_name_override": style_type_name_override,
            "read_only": read_only,
        }
        if min_val is not None:
            kwargs["min"] = min_val
        if max_val is not None:
            kwargs["max"] = max_val
        if step is not None:
            kwargs["step"] = step
        return ui.FloatDrag(**kwargs)
