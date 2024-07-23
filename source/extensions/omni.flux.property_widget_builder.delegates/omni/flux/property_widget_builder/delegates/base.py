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

__all__ = ("AbstractField",)

import abc
from typing import TYPE_CHECKING, Generic, TypeVar

import omni.ui as ui

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item


ItemT = TypeVar("ItemT", bound="Item")


class AbstractField(Generic[ItemT]):
    """
    AbstractField that stores a style_name attribute to be used within `build_ui` for styling widgets.
    """

    def __init__(self, style_name: str = "PropertiesWidgetField", identifier: None | str = None) -> None:
        self.style_name = style_name
        self.identifier = identifier

    def __call__(self, item: ItemT) -> ui.Widget | list[ui.Widget] | None:
        return self.build_ui(item)

    @abc.abstractmethod
    def build_ui(self, item: ItemT) -> ui.Widget | list[ui.Widget] | None:
        raise NotImplementedError
