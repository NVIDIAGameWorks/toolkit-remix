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
from typing import TYPE_CHECKING, Callable

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import limit_recursion as _limit_recursion

if TYPE_CHECKING:
    from .delegate import TreeDelegateBase as _TreeDelegateBase
    from .item import TreeItemBase as _TreeItemBase
    from .model import TreeModelBase as _TreeModelBase


class TreeWidget(ui.TreeView):
    def __init__(
        self,
        model: "_TreeModelBase",
        delegate: "_TreeDelegateBase",
        select_all_children: bool = True,
        validate_action_selection: bool = True,
        **kwargs,
    ):
        """
        A tree widget that extends the built-in ui.TreeView.

        Args:
            model: The tree widget's model
            delegate: The tree widget's delegate
            select_all_children: Whether the tree should select all children items when selecting a parent item or not
            validate_action_selection: Whether the selection should be validated & updated to include the item being
                                       right-clicked on or not
            kwargs: The same arguments ui.TreeView exposes
        """
        super().__init__(model, delegate=delegate, **kwargs)

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._model = model
        self._delegate = delegate
        self._select_all_children = select_all_children
        self._validate_action_selection = validate_action_selection

        if self._validate_action_selection:
            self._sub_selection_changed = self._delegate.subscribe_item_clicked(self._on_item_clicked)

        if self._select_all_children:
            self.set_selection_changed_fn(self.on_selection_changed)

        self.__on_selection_changed = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return {
            "_model": None,
            "_delegate": None,
            "_select_all_children": None,
            "_update_right_click_selection": None,
            "_sub_selection_changed": None,
        }

    def _on_item_clicked(self, should_validate: bool, model: "_TreeModelBase", item: "_TreeItemBase"):
        """
        This makes sure the right-clicked items is in the selection
        """
        if not self._validate_action_selection:
            return

        if should_validate and item not in self.selection:
            to_select = [item]
            if self._select_all_children:
                to_select.extend(model.iter_items_children([item]))
            self.selection = to_select
            self._delegate.selection = to_select

    @_limit_recursion()
    def on_selection_changed(self, items: list["_TreeItemBase"]):
        """
        Function to be called whenever the tree widget selection widget changes (`set_selection_changed_fn`).

        The base implementation selects children when selecting a parent if `_select_all_children` is `True`

        Args:
            items: The list of items selected
        """
        if not self._select_all_children:
            return

        selection = set(self.selection)
        for item in items:
            selection.update(self._model.iter_items_children([item]))

        selection_list = list(selection)
        self.selection = selection_list
        self._delegate.selection = selection_list

        self.__on_selection_changed(selection_list)

    def subscribe_selection_changed(self, callback: Callable[[list["_TreeItemBase"]], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_selection_changed, callback)

    def destroy(self):
        _reset_default_attrs(self)
