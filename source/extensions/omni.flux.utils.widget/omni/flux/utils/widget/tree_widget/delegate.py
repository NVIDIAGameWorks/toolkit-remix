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
from typing import TYPE_CHECKING, Callable, Iterable

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from .item import TreeItemBase as _TreeItemBase
    from .model import TreeModelBase as _TreeModelBase


class TreeDelegateBase(ui.AbstractItemDelegate):

    DEFAULT_IMAGE_ICON_SIZE = ui.Pixel(24)

    def __init__(self):
        """
        A base Delegate class to be overridden and used with the TreeWidget.
        """
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._selection = []

        self.__on_item_clicked = _Event()
        self.__on_item_expanded = _Event()
        self.__on_context_menu_shown = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return {"_selection": None}

    @property
    def selection(self) -> list[_TreeItemBase]:
        """
        Get the currently selected items
        """
        return self._selection

    @selection.setter
    def selection(self, value: Iterable[_TreeItemBase]):
        """
        Set the currently selected items
        """
        self._selection = list(value)

    def build_widget(self, model: _TreeModelBase, item: _TreeItemBase, column_id: int, level: int, expanded: bool):
        """
        Create a widget per item. To define the build function, override `_build_widget`. This function wraps the widget
        in a frame with an on-click listener.
        """
        if item is None:
            return

        with ui.Frame(mouse_pressed_fn=lambda x, y, b, m: self._item_clicked(b, b == 1, model, item)):
            self._build_widget(model, item, column_id, level, expanded)

    def build_branch(self, model: _TreeModelBase, item: _TreeItemBase, column_id: int, level: int, expanded: bool):
        """
        Create a branch widget that opens or closes the subtree. To define the build function, override `_build_branch`.
        """
        if column_id == 0:
            with ui.HStack(width=ui.Pixel(16 * (level + 2)), height=self.DEFAULT_IMAGE_ICON_SIZE):
                ui.Spacer()
                if model.can_item_have_children(item):
                    with ui.Frame(
                        width=0, mouse_released_fn=lambda x, y, b, m: self._item_expanded(b, item, not expanded)
                    ):
                        self._build_branch(model, item, column_id, level, expanded)

    def build_header(self, column_id: int):
        """
        Create a header at the top of the tree. To define the build function, override `_build_header`.
        """
        self._build_header(column_id=column_id)

    @abc.abstractmethod
    def _build_widget(self, model: _TreeModelBase, item: _TreeItemBase, column_id: int, level: int, expanded: bool):
        """
        Define how the widget should be built. Must be overridden.
        """
        raise NotImplementedError()

    def _build_branch(self, _model: _TreeModelBase, item: _TreeItemBase, _column_id: int, _level: int, expanded: bool):
        """
        Define how the expansion branch should be built.
        """
        style_type_name_override = "TreeView.Item.Minus" if expanded else "TreeView.Item.Plus"
        with ui.VStack(width=ui.Pixel(16)):
            ui.Spacer(width=0)
            ui.Image(
                "", width=10, height=10, style_type_name_override=style_type_name_override, identifier="property_branch"
            )
            ui.Spacer(width=0)

    def _build_header(self, column_id: int):
        """
        Define how the tree header should be built.
        """
        pass

    def _show_context_menu(self, model: _TreeModelBase, item: _TreeItemBase):
        """
        Function called to display the context menu on right click. Should be overridden or not menu will be displayed.
        """
        self._context_menu_shown(model, item)

    def _item_clicked(self, button: int, should_validate: bool, model: _TreeModelBase, item: _TreeItemBase):
        """
        Callback called whenever an item is clicked on.
        """
        # First emit the event which allows the parent tree to potentially modify the selection.
        self.__on_item_clicked(should_validate, model, item)
        if button == 1:
            self._show_context_menu(model, item)

    def subscribe_item_clicked(self, function: Callable[[bool, _TreeModelBase, _TreeItemBase], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_clicked, function)

    def _item_expanded(self, button: int, item: _TreeItemBase, expanded: bool):
        """Call the event object that has the list of functions"""
        if button != 0:
            return
        self.__on_item_expanded(item, expanded)

    def subscribe_item_expanded(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_expanded, function)

    def _context_menu_shown(self, model: _TreeModelBase, item: _TreeItemBase):
        """
        Callback called whenever an item is clicked on.
        """
        # First emit the event which allows the parent tree to potentially modify the selection.
        self.__on_context_menu_shown(model, item)

    def subscribe_context_menu_shown(self, function: Callable[[_TreeModelBase, _TreeItemBase], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_context_menu_shown, function)

    def destroy(self):
        _reset_default_attrs(self)


class AlternatingRowDelegate(ui.AbstractItemDelegate):
    def __init__(self, row_height: int, scrollbar_spacing: bool = True):
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._row_height = row_height
        self._scrollbar_spacing = scrollbar_spacing

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_row_height": None,
            "_scrollbar_spacing": None,
        }

    def build_branch(self, model, item, column_id, level, expanded):
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        if item is None:
            return
        with ui.HStack():
            ui.Rectangle(name=("Alternate" if item.alternate else "") + "Row", height=ui.Pixel(self._row_height))
            # Don't hide the stacked tree scrollbar
            if self._scrollbar_spacing:
                ui.Spacer(width=ui.Pixel(12))

    def destroy(self):
        _reset_default_attrs(self)
