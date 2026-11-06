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
from collections.abc import Callable

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import PrivateAttr

from .base import StageManagerUIPluginBase as _StageManagerUIPluginBase

if TYPE_CHECKING:
    from .tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from .tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class StageManagerWidgetPlugin(_StageManagerUIPluginBase, abc.ABC):
    """
    A plugin that provides a widget for the TreeView
    """

    _action_row_only: ClassVar[bool] = False

    _on_item_clicked: _Event = PrivateAttr(default=_Event())
    _icon_size: ui.Length = PrivateAttr(default=0)

    @abc.abstractmethod
    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        pass

    def build_overview_ui(self, model: "_StageManagerTreeModel"):
        """Default implementation creates a spacer matching the icon size for alignment."""
        with ui.HStack(width=self._icon_size):
            ui.Spacer()

    def subscribe_item_clicked(
        self, callback: Callable[[int, bool, "_StageManagerTreeModel", "_StageManagerTreeItem"], None]
    ) -> _EventSubscription:
        """
        Subscribe to the event that is triggered when a widget is clicked.

        Args:
            callback: A function that will be called when the widget is clicked.

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self._on_item_clicked, callback)

    def _get_action_items(
        self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"
    ) -> list["_StageManagerTreeItem"]:
        """Return published canonical action rows without changing tree selection.

        A selected clicked row uses selection order unless ``_action_row_only`` is set.
        Otherwise only the clicked row is considered. Override to customize action targets.
        """
        clicked_proxy = item.proxy
        selection = model.selection
        candidates = (
            selection
            if not self._action_row_only and any(proxy is clicked_proxy for proxy in selection)
            else [clicked_proxy]
        )
        published_items = model.items_dict
        return [
            proxy.original_tree_item
            for proxy in candidates
            if proxy is not None and published_items.get(hash(proxy)) is proxy
        ]

    def _item_clicked(
        self, button: int, should_validate: bool, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"
    ):
        """
        Callback called whenever a widget is clicked on.

        Args:
            button: The mouse button that triggered the event
            should_validate: Whether the TreeView selection should be validated or not
            model: The tree model
            item: The tree item that was clicked
        """
        self._on_item_clicked(button, should_validate, model, item)
