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

from typing import Optional

import omni.usd
from omni.flux.property_widget_builder.widget import ItemModel as _ItemModel
from pxr import Sdf


class UsdAttributeNameModel(_ItemModel):
    def __init__(
        self,
        context_name: str,
        attribute_path: Sdf.Path,
        channel_index: int,
        display_attr_name: Optional[str] = None,
        display_attr_name_tooltip: Optional[str] = None,
    ):
        """
        The value model for the name of an USD attribute

        Args:
            context_name: the context name
            attribute_path: the path of the attribute
            channel_index: the channel index of the attribute
            display_attr_name: override the name of the attribute to show
            display_attr_name_tooltip: tooltip to show on the attribute name
        """
        super().__init__()
        self._stage = omni.usd.get_context(context_name).get_stage()
        self._attribute_path = attribute_path
        self._display_attr_name = display_attr_name
        self._display_attr_name_tooltip = display_attr_name_tooltip
        self._channel_index = channel_index
        self._value = None  # The value to be displayed on widget
        self._read_value_from_usd()

    def refresh(self):
        """Name of the attribute doesn't refresh here"""
        pass

    def get_value(self) -> str:
        return self.get_value_as_string()

    def set_display_attr_name(self, display_attr_name):
        self._display_attr_name = display_attr_name
        self._read_value_from_usd()

    def set_display_attr_name_tooltip(self, display_attr_name_tooltip):
        self._display_attr_name_tooltip = display_attr_name_tooltip

    def get_tool_tip(self):
        if self._display_attr_name_tooltip:
            return self._display_attr_name_tooltip
        return self._attribute_path.name

    def _get_value_as_string(self) -> str:
        if self._value is None:
            return ""
        return str(self._value[self._channel_index])

    def _get_value_as_float(self) -> float:
        if self._value is None:
            return 0.0
        return float(self._value[self._channel_index])

    def _get_value_as_bool(self) -> bool:
        if self._value is None:
            return False
        return bool(self._value[self._channel_index])

    def _get_value_as_int(self) -> int:
        if self._value is None:
            return 0
        return int(self._value[self._channel_index])

    def _read_value_from_usd(self):
        if not self._stage:
            assert self._value is None
            return

        if self._value is None:
            self._value = {}
        self._value[self._channel_index] = (
            self._attribute_path.name if self._display_attr_name is None else self._display_attr_name
        )


class UsdAttributeNameModelVirtual(UsdAttributeNameModel):
    def get_tool_tip(self):
        return f"[VIRTUAL] {self._attribute_path.name}"
