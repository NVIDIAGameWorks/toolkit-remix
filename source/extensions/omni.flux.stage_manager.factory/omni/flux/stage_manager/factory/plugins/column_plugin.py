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
from typing import TYPE_CHECKING

from omni import ui
from pydantic import Field

from .base import StageManagerUIPluginBase as _StageManagerUIPluginBase
from .widget_plugin import StageManagerWidgetPlugin

if TYPE_CHECKING:
    from .tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from .tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class StageManagerColumnPlugin(_StageManagerUIPluginBase, abc.ABC):
    """
    A plugin that allows the grouping of multiple widgets in a column
    """

    widgets: list[StageManagerWidgetPlugin] = Field(...)

    def build_header(self, _):
        ui.Label(self.display_name)

    @abc.abstractmethod
    def build_ui(  # noqa PLW0221
        self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", column_id: int, level: int, expanded: bool
    ):
        """
        Build the UI for the given column. This function will be used within a delegate and should therefore only build
        the UI for a single element.
        """
        pass

    @abc.abstractmethod
    def build_result_ui(self, model: "_StageManagerTreeModel", column_id: int):
        """
        Build the result UI for the given column. The result UI is displayed at the bottom the TreeView widget. It
        should be used to display additional information about all the items in the column.
        """
        pass
