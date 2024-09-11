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

import abc
from typing import TYPE_CHECKING, Iterable

from omni import ui
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, PrivateAttr

from .usd_base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin

if TYPE_CHECKING:
    from pxr import Usd


class ToggleableUSDFilterPlugin(_StageManagerUSDFilterPlugin, abc.ABC):
    filter_active: bool = True

    include_results: bool = Field(True, description="Include or exclude prims")

    _checkbox: ui.CheckBox | None = PrivateAttr()
    _value_changed_sub: _EventSubscription | None = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._checkbox = None
        self._value_changed_sub = None

    def filter_items(self, prims: Iterable["Usd.Prim"]) -> list["Usd.Prim"]:
        if self.filter_active:

            def filter_prim(prim: "Usd.Prim") -> bool:
                result = self._filter_predicate(prim)
                return result if self.include_results else not result

            return [prim for prim in prims if filter_prim(prim)]
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
        """
        Callback executed when the checkbox is toggled.

        Args:
            model: The checkbox model.
        """
        self.filter_active = not model.as_bool
        self._filter_items_changed()

    @abc.abstractmethod
    def _filter_predicate(self, prim: "Usd.Prim") -> bool:
        """
        The predicate function to filter prims.

        Args:
            prim: The USD prim to inspect.

        Returns:
            True if the prim should be included in the results, False otherwise.
        """
        pass
