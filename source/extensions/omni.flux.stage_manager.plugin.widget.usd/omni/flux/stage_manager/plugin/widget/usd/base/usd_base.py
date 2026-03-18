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

from omni.flux.stage_manager.factory.plugins import StageManagerWidgetPlugin as _StageManagerWidgetPlugin
from pydantic import PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class StageManagerUSDWidgetPlugin(_StageManagerWidgetPlugin, abc.ABC):
    _context_name: str = PrivateAttr(default="")

    def set_context_name(self, name: str):
        """Set usd context to initialize plugin before items are rebuilt."""
        self._context_name = name

    def _get_action_paths(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem") -> list[str]:
        """
        Resolve which prim paths an action widget should operate on.

        - If the clicked item is already in the current tree selection, the action applies to
          all selected prims (preserving multi-selection).
        - If the clicked item is *not* in the selection, the action applies to that item alone
          (same behaviour as the original single-item case, without mutating the selection).
        - If ``item.data`` is ``None``, falls back to the current selection.

        Selection state is read from ``model.selection`` — no USD API is queried.
        """
        current = [str(i.data.GetPath()) for i in model.selection if i.data]
        if item.data:
            item_path = str(item.data.GetPath())
            if item_path in current:
                return current
            return [item_path]
        return current
