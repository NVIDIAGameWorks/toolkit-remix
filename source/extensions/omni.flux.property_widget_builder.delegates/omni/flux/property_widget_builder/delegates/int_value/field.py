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

__all__ = ("IntField",)

import omni.ui as ui

from ..base import AbstractValueField


class IntField(AbstractValueField):
    """General-purpose integer input field with optional min/max clamping on edit."""

    def __init__(
        self,
        clamp_min: int | None = None,
        clamp_max: int | None = None,
        **kwargs,
    ):
        kwargs.setdefault("style_name", "PropertiesWidgetField")
        super().__init__(widget_type=ui.IntField, clamp_min=clamp_min, clamp_max=clamp_max, **kwargs)

    def _get_value_from_model(self, model) -> int:
        return model.get_value_as_int()
