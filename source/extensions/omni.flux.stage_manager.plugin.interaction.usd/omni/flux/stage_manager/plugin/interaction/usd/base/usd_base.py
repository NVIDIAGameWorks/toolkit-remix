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
from typing import Iterable

from omni.flux.stage_manager.factory import StageManagerDataTypes as _StageManagerDataTypes
from omni.flux.stage_manager.factory.plugins import StageManagerInteractionPlugin as _StageManagerInteractionPlugin
from pxr import Usd
from pydantic import PrivateAttr


class StageManagerUSDInteractionPlugin(_StageManagerInteractionPlugin, abc.ABC):

    _context_name: str | None = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._context_name = ""

    @classmethod
    @property
    def compatible_data_type(cls):
        return _StageManagerDataTypes.USD

    @classmethod
    @property
    def recursive_traversal(cls) -> bool:
        """
        Whether the interaction plugin should perform a recursive traversal of the context items.

        Returns:
            bool: True if the interaction plugin should perform a recursive traversal, False otherwise.
        """
        return False

    def _update_context_items(self):
        self._set_context_name()

        context_items = self._context.get_items()
        if self.recursive_traversal:
            context_items = self._traverse_children_recursive(context_items)
        else:
            context_items = self._filter_context_items(context_items)

        self.tree.model.context_items = context_items
        self.tree.model.refresh()

    def _set_context_name(self):
        """
        Set the context name in the interaction and all children USD plugins using the USD context plugin.
        """
        attribute_name = "context_name"

        if not hasattr(self._context, attribute_name):
            return

        value = getattr(self._context, attribute_name, "")
        self._context_name = value

        # Propagate the value
        if hasattr(self.tree, attribute_name):
            self.tree.context_name = value

        for filter_plugin in self.filters:
            if hasattr(filter_plugin, attribute_name):
                filter_plugin.context_name = value

        for column_plugin in self.columns:
            if hasattr(column_plugin, attribute_name):
                column_plugin.context_name = value

            for widget_plugin in column_plugin.widgets:
                if hasattr(widget_plugin, attribute_name):
                    widget_plugin.context_name = value

    def _traverse_children_recursive(self, prims: Iterable[Usd.Prim], filter_prims: bool = True) -> list[Usd.Prim]:
        """
        Get a filtered list of all the prims and their children recursively.

        Args:
            prims: The list of prims to traverse

        Returns:
            A filtered list of all the prims and their children
        """
        filtered_prims = self._filter_context_items(prims) if filter_prims else list(prims)
        children = filtered_prims.copy()
        for prim in filtered_prims:
            children.extend(
                self._traverse_children_recursive(
                    prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate), filter_prims=filter_prims
                )
            )
        return children
