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
from typing import TYPE_CHECKING, Any, Callable, Iterable

from omni import ui, usd
from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase
from omni.flux.utils.widget.tree_widget import TreeItemBase as _TreeItemBase
from omni.flux.utils.widget.tree_widget import TreeModelBase as _TreeModelBase

from ..utils import StageManagerUtils as _StageManagerUtils
from .base import StageManagerPluginBase as _StageManagerPluginBase

if TYPE_CHECKING:
    from ..items import StageManagerItem as _StageManagerItem
    from .column_plugin import StageManagerColumnPlugin as _StageManagerColumnPlugin


class StageManagerTreeItem(_TreeItemBase):
    """
    A TreeView item used in TreeView models

    Args:
        display_name: The string to display in the TreeView
        data: The data associated with the item
        tooltip: The tooltip to display when hovering over the item
        display_name_ancestor: A string to prepend to the display name with
    """

    def __init__(
        self,
        display_name: str,
        data: Any,
        tooltip: str = "",
        display_name_ancestor: str | None = None,
    ):
        super().__init__()

        self._display_name = display_name
        self._tooltip = tooltip
        self._data = data
        self._display_name_ancestor = display_name_ancestor

        self._parent = None

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_display_name": None,
                "_tooltip": None,
                "_parent": None,
                "_data": None,
                "_parent_name": None,
            }
        )
        return default_attr

    @property
    def display_name(self) -> str:
        """
        The display name for the item. Can be used by the widgets
        """
        return self._display_name

    @property
    def tooltip(self) -> str:
        """
        The tooltip displayed when hovering the item. Can be used by the widgets
        """
        return self._tooltip

    @property
    def parent(self) -> "StageManagerTreeItem":
        """
        The parent item for which this item is a child
        """
        return self._parent

    @parent.setter
    def parent(self, value: "StageManagerTreeItem"):
        """
        Set the parent item for which this item is a child
        """
        self._parent = value

    @property
    def data(self) -> Any:
        """
        Custom data held in the item. Can be used by the widgets
        """
        return self._data

    @property
    def icon(self) -> str | None:
        """
        The icon style name associated with the item. Can be used by the widgets
        """
        return None  # noqa R501

    @property
    def can_have_children(self) -> bool:
        """
        Whether the item can have children or not

        Returns:
            By default, items that have children will return True, and items without children will return False
        """
        return bool(self._children)

    def build_widget(self):
        """
        Method that can be used to build the widgets to build a widget displaying the items
        """
        with ui.HStack(spacing=ui.Pixel(2)):
            if self._display_name_ancestor:
                ui.Label(self._display_name_ancestor, name="FadedLabel", width=0)
                ui.Label("/", name="FadedLabel", width=0)
            ui.Label(self.display_name)

    def add_child(self, item: "StageManagerTreeItem"):
        """
        Add a child item

        Args:
            item: The child item to add
        """
        item.parent = self
        self._children.append(item)

    def __eq__(self, other):
        if isinstance(other, StageManagerTreeItem):
            return self.display_name == other.display_name and self.tooltip == other.tooltip and self.data == other.data
        return False

    def __hash__(self):
        return hash(self.display_name + self.tooltip + str(self.data))


class StageManagerTreeModel(_TreeModelBase[StageManagerTreeItem]):
    """
    A TreeView model used to define the structure of the tree
    """

    def __init__(self):
        self._items = []

        super().__init__()

        self._context_items: list[_StageManagerItem] = []
        self._user_filter_predicates: list[Callable[[_StageManagerItem], bool]] = []
        self._context_predicates: list[Callable[[_StageManagerItem], bool]] = []
        self._column_count = 0
        self._max_workers = None

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_items": None,
                "_context_items": None,
                "_user_filter_predicates": None,
                "_context_predicates": None,
                "_column_count": None,
                "_max_workers": None,
            }
        )
        return default_attr

    @property
    def items_dict(self) -> dict[int, StageManagerTreeItem]:
        """
        Get a dictionary of item hashes and items
        """
        return {hash(item): item for item in self.iter_items_children()}

    @usd.handle_exception
    async def get_context_items(self) -> list[_StageManagerItem]:
        """
        Get items set by the context plugin.

        Items are filtered before they are returned
        """
        return (
            await _StageManagerUtils.filter_items(
                self._context_items, self._user_filter_predicates, max_workers=self._max_workers
            )
            or []
        )

    def set_max_workers(self, max_workers: int | None):
        """
        Set the maximum number of workers to use when filtering context items
        """
        self._max_workers = max_workers

    def set_context_items(self, items: Iterable[_StageManagerItem]):
        """
        Set items fetched in the context plugin
        """
        self._context_items = list(items)

    @property
    def column_count(self) -> int:
        """
        Get the number of columns to build
        """
        return self._column_count

    @column_count.setter
    def column_count(self, value: int):
        """
        Set the number of columns to build
        """
        self._column_count = value

    @usd.handle_exception
    async def refresh(self):
        """
        Method called when the `self._items` attribute should be refreshed
        """
        filtered_items = await self.get_context_items()

        for item in filtered_items:
            item.tree_item = None

        self._items = self._build_items(filtered_items)
        self._item_changed(None)

    def find_items(self, predicate: Callable[[StageManagerTreeItem], bool]) -> list[StageManagerTreeItem]:
        """
        Get a tree item from its data
        """
        results = []
        for item in self.iter_items_children():
            if predicate(item):
                results.append(item)
        return results

    def get_item_children(self, item: StageManagerTreeItem | None):
        """
        Returns all the children of any given item.
        """
        if item is None:
            return self._items
        return item.children or []

    def get_item_value_model_count(self, item: StageManagerTreeItem):
        return self.column_count

    def add_user_filter_predicates(self, value: list[Callable[[_StageManagerItem], bool]]):
        """
        Extend the filter predicates to apply to the items during filtering
        """
        self._user_filter_predicates.extend(value)

    def clear_user_filter_predicates(self):
        """
        Clear the filter predicates to apply to the items during filtering
        """
        self._user_filter_predicates.clear()

    def add_context_predicates(self, value: list[Callable[[_StageManagerItem], bool]]):
        """
        Extend the context filter predicates that can be used by the model if required
        """
        self._context_predicates.extend(value)

    def clear_context_predicates(self):
        """
        Clear the context filter predicates that can be used by the model if required
        """
        self._context_predicates.clear()

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[StageManagerTreeItem] | None:
        """
        Recursively build the model items from Stage Manager items

        Args:
            items: an iterable of Stage Manager items

        Returns:
            A list of Stage Manager items or None if the input items are None
        """

        tree_items = []
        for item in items:
            tree_item = self._build_item(item)
            item.tree_item = tree_item

            if item.parent is None:
                # Add to the root
                tree_items.append(tree_item)
            else:
                # Add to the parent
                item.parent.tree_item.add_child(tree_item)

        return tree_items

    def _build_item(self, item: _StageManagerItem) -> StageManagerTreeItem:
        """
        Function used to transform Stage Manager items into TreeView items

        Args:
            item: Stage Manager item

        Returns:
            A fully built TreeView item
        """
        return StageManagerTreeItem(item.identifier, item.data)


class StageManagerTreeDelegate(_TreeDelegateBase):
    """
    A TreeView delegate used to define the look of every element in the tree
    """

    def __init__(self, header_height: int = 24, row_height: int = 24):
        super().__init__()

        self._header_height = header_height
        self._row_height = row_height

        self._column_widget_builders = {}
        self._column_header_builders = {}

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_header_height": None,
                "_row_height": None,
                "_column_widget_builders": None,
                "_column_header_builders": None,
            }
        )
        return default_attr

    @property
    def header_height(self) -> int:
        return self._header_height

    @header_height.setter
    def header_height(self, value: int):
        self._header_height = max(0, value)

    @property
    def row_height(self) -> int:
        return self._row_height

    @row_height.setter
    def row_height(self, value: int):
        self._row_height = max(0, value)

    def set_column_builders(self, columns: list[_StageManagerColumnPlugin]):
        for index, column in enumerate(columns):
            self._column_widget_builders[index] = column.build_ui
            self._column_header_builders[index] = column.build_header

    def call_item_clicked(
        self, button: int, should_validate: bool, model: "StageManagerTreeModel", item: "StageManagerTreeItem"
    ):
        """
        Trigger the `_item_clicked` event

        Args:
            button: The mouse button that triggered the event
            should_validate: Whether the TreeView selection should be validated or not
            model: The tree model
            item: The tree item that was clicked
        """
        self._item_clicked(button, should_validate, model, item)

    def _build_widget(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
        column_id: int,
        level: int,
        expanded: bool,
    ):
        with ui.Frame(height=self.row_height):
            if column_id in self._column_widget_builders:
                self._column_widget_builders[column_id](model, item, level, expanded)

    def _build_branch(
        self, _model: "_TreeModelBase", item: "_TreeItemBase", column_id: int, level: int, expanded: bool
    ):
        with ui.Frame(height=self.row_height):
            super()._build_branch(_model, item, column_id, level, expanded)

    def _build_header(self, column_id: int):
        with ui.Frame(height=self.header_height):
            if column_id in self._column_header_builders:
                self._column_header_builders[column_id]()


class StageManagerTreePlugin(_StageManagerPluginBase, abc.ABC):
    """
    A plugin that provides a TreeView model and delegate
    """

    @classmethod
    @property
    @abc.abstractmethod
    def model(cls) -> StageManagerTreeModel:
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def delegate(cls) -> StageManagerTreeDelegate:
        pass

    class Config(_StageManagerPluginBase.Config):
        fields = {
            **_StageManagerPluginBase.Config.fields,
            "model": {"exclude": True},
            "delegate": {"exclude": True},
        }
