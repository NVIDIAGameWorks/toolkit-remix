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
from enum import Enum
from typing import TYPE_CHECKING

from omni import ui
from pydantic import BaseModel, Field

from .base import StageManagerUIPluginBase as _StageManagerUIPluginBase
from .widget_plugin import StageManagerWidgetPlugin

if TYPE_CHECKING:
    from .tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from .tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class LengthUnit(Enum):
    FRACTION = "Fraction"
    PERCENT = "Percent"
    PIXEL = "Pixel"


class ColumnWidth(BaseModel):
    unit: LengthUnit = Field(..., description="The unit of the column width")
    value: float = Field(..., description="The value of the column width")


class StageManagerColumnPlugin(_StageManagerUIPluginBase, abc.ABC):
    """
    A plugin that allows the grouping of multiple widgets in a column
    """

    display_name: str = Field(..., description="The name to display in the column header")
    tooltip: str = Field("", description="The tooltip to display when hovering over the column header")
    widgets: list[StageManagerWidgetPlugin] = Field(..., description="Widgets to be displayed in the column")

    width: ColumnWidth = Field(ColumnWidth(unit=LengthUnit.FRACTION, value=1), description="Width of the column")

    def build_header(self):
        """
        Build the UI for the given column header.
        """
        ui.Label(self.display_name, height=ui.Pixel(24), alignment=ui.Alignment.CENTER, tooltip=self.tooltip)

    @abc.abstractmethod
    def build_ui(  # noqa PLW0221
        self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool
    ):
        """
        Build the UI for the given column. This function will be used within a delegate and should therefore only build
        the UI for a single element.
        """
        pass

    @abc.abstractmethod
    def build_result_ui(self, model: "_StageManagerTreeModel"):
        """
        Build the result UI for the given column. The result UI is displayed at the bottom the TreeView widget. It
        should be used to display additional information about all the items in the column.
        """
        pass
