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
from typing import TYPE_CHECKING, ClassVar

from omni.flux.stage_manager.factory.plugins import StageManagerWidgetPlugin as _StageManagerWidgetPlugin
from pydantic import PrivateAttr
from pxr import UsdGeom

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class StageManagerUSDWidgetPlugin(_StageManagerWidgetPlugin, abc.ABC):
    _action_imageable_only: ClassVar[bool] = False

    _context_name: str = PrivateAttr(default="")

    def set_context_name(self, name: str):
        """Set usd context to initialize plugin before items are rebuilt."""
        self._context_name = name

    def _get_action_items(
        self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"
    ) -> list["_StageManagerTreeItem"]:
        """Return valid prim rows, optionally restricted to Imageable prims."""
        return [
            action_item
            for action_item in super()._get_action_items(model, item)
            if action_item.data
            and action_item.data.IsValid()
            and (not self._action_imageable_only or UsdGeom.Imageable(action_item.data))
        ]
