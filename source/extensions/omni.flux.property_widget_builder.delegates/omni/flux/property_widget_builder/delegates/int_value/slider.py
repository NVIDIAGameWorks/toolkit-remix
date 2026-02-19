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

__all__ = ("IntSliderField",)


from typing import Any

import omni.ui as ui
from ..base import AbstractSliderField


class IntSliderField(AbstractSliderField):
    """A slider delegate for integer values with configurable min, max, and step."""

    def __init__(self, min_value: int = 0, max_value: int = 100, step: int | None = None, **kwargs):
        """Initialize the int slider.

        Args:
            min_value: Minimum value of the slider. Defaults to 0.
            max_value: Maximum value of the slider. Defaults to 100.
            step: Optional step size; if None, step is 1 for range ≤100 else max(1, int(range * 0.01)).
            **kwargs: Passed to AbstractSliderField (e.g. style_name, default "IntSliderField").
        """
        style_name = kwargs.get("style_name", "IntSliderField")
        kwargs["style_name"] = style_name
        super().__init__(min_value=min_value, max_value=max_value, step=step, **kwargs)

    @property
    def step(self) -> int:
        """Step size for the slider; uses explicit step if set, else 1 for range ≤100 else scaled by range."""
        if self._step is not None:
            return self._step

        range_size = self.max_value - self.min_value
        if range_size <= 100:
            return 1
        return max(1, int(range_size * 0.01))

    @step.setter
    def step(self, value: int) -> None:
        self._step = value

    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int,
        max_val: float | int,
        step: float | int,
    ) -> Any:
        """Build a ui.IntDrag widget bound to the given model and bounds."""
        return ui.IntDrag(
            model=model,
            style_type_name_override=style_type_name_override,
            read_only=read_only,
            min=min_val,
            max=max_val,
            step=step,
        )
