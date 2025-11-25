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

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, PrivateAttr

from .usd_base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin

if TYPE_CHECKING:
    from pxr import Usd


class ToggleableUSDFilterPlugin(_StageManagerUSDFilterPlugin, abc.ABC):
    filter_active: bool = Field(default=True)
    include_results: bool = Field(default=True, description="Include or exclude prims")

    _checkbox: ui.CheckBox | None = PrivateAttr(default=None)
    _value_changed_sub: _EventSubscription | None = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._checkbox = None
        self._value_changed_sub = None

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        if not self.filter_active:
            return True

        result = self._filter_predicate(item.data)
        return result if self.include_results else not result

    def build_ui(self):  # noqa PLW0221
        with ui.VStack(width=0, spacing=ui.Pixel(4)):
            ui.Spacer(width=0)
            with ui.HStack(height=0, spacing=ui.Pixel(8)):
                ui.Label(self.display_name, width=ui.Pixel(self._LABEL_WIDTH), alignment=ui.Alignment.RIGHT_CENTER)
                ui.Spacer(width=0)
                self._checkbox = ui.CheckBox()
            ui.Spacer(width=0)

        self._checkbox.model.set_value(self.filter_active)
        self._value_changed_sub = self._checkbox.model.subscribe_value_changed_fn(self._on_checkbox_toggled)

    def _on_checkbox_toggled(self, model: ui.AbstractValueModel):
        """
        Callback executed when the checkbox is toggled.

        Args:
            model: The checkbox model.
        """
        self.filter_active = model.as_bool
        self._filter_items_changed()

    @abc.abstractmethod
    def _filter_predicate(self, prim: Usd.Prim) -> bool:
        """
        The predicate function to filter prims.

        Args:
            prim: The USD prim to inspect.

        Returns:
            True if the prim should be included in the results, False otherwise.
        """
        pass
