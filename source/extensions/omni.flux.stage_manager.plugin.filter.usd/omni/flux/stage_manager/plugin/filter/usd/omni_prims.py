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

from typing import TYPE_CHECKING, Iterable

import carb
from omni import ui
from omni.flux.utils.common import get_omni_prims as _get_omni_prims
from pydantic import PrivateAttr

from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin

if TYPE_CHECKING:
    from pxr import Usd


class OmniPrimsFilterPlugin(_StageManagerUSDFilterPlugin):
    display_name: str = "Omniverse Prims"
    tooltip: str = "Filter out Omniverse prims"

    filter_active: bool = True

    _checkbox: ui.CheckBox = PrivateAttr()
    _value_changed_sub: carb.Subscription = PrivateAttr()

    def filter_items(self, prims: Iterable["Usd.Prim"]) -> list["Usd.Prim"]:
        if self.filter_active:
            return [prim for prim in prims if prim.GetPath() not in _get_omni_prims()]
        return list(prims)

    def build_ui(self):  # noqa PLW0221
        with ui.VStack(width=0):
            ui.Spacer(width=0)
            with ui.HStack(height=0, spacing=ui.Pixel(8)):
                ui.Label(self.display_name, width=0)
                self._checkbox = ui.CheckBox()
            ui.Spacer(width=0)

        # Checked means we include, unchecked means we filter
        self._checkbox.model.set_value(not self.filter_active)
        self._value_changed_sub = self._checkbox.model.subscribe_value_changed_fn(self._on_checkbox_toggled)

    def _on_checkbox_toggled(self, model: ui.AbstractValueModel):
        self.filter_active = not model.as_bool
        self._filter_items_changed()
