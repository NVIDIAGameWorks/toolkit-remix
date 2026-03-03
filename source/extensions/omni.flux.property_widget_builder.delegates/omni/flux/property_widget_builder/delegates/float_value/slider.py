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

from typing import Any

import omni.ui as ui
from ..base import AbstractSliderField


class FloatSliderField(AbstractSliderField):
    """A float slider field delegate for building float-based slider widgets."""

    def __init__(
        self,
        min_value: float = 0.0,
        max_value: float = 100.0,
        hard_min_value: float | None = None,
        hard_max_value: float | None = None,
        step: float | None = None,
        **kwargs,
    ):
        """Initialize the float slider.

        Args:
            min_value: Minimum value of the slider. Defaults to 0.0.
            max_value: Maximum value of the slider. Defaults to 100.0.
            hard_min_value: Hard minimum bound for clamping. Both hard_min_value and
                hard_max_value must be provided for clamping to take effect.
            hard_max_value: Hard maximum bound for clamping. Both hard_min_value and
                hard_max_value must be provided for clamping to take effect.
            step: Optional step size; if None, step is computed as (max_value - min_value) * 0.005.
            **kwargs: Passed to AbstractSliderField (e.g. style_name, default "FloatSliderField").
        """
        style_name = kwargs.get("style_name", "FloatSliderField")
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
        """Step size for the slider; uses explicit step if set, else (max_value - min_value) * 0.005."""
        if self._step is not None:
            return self._step
        return (self.max_value - self.min_value) * 0.005

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
        min_val: float | int,
        max_val: float | int,
        step: float | int,
    ) -> Any:
        """Build a ui.FloatDrag widget bound to the given model and bounds."""
        return ui.FloatDrag(
            model=model,
            style_type_name_override=style_type_name_override,
            read_only=read_only,
            min=min_val,
            max=max_val,
            step=step,
        )
