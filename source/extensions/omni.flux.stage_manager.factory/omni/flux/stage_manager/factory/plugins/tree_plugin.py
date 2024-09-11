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
from typing import TYPE_CHECKING, Any, Callable, Generic, Iterable, TypeVar

from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase
from omni.flux.utils.widget.tree_widget import TreeItemBase as _TreeItemBase
from omni.flux.utils.widget.tree_widget import TreeModelBase as _TreeModelBase

from .base import StageManagerPluginBase as _StageManagerPluginBase

if TYPE_CHECKING:
    from .column_plugin import StageManagerColumnPlugin as _StageManagerColumnPlugin


DataType = TypeVar("DataType")


class StageManagerTreeItem(_TreeItemBase):
    """
    A TreeView item used in TreeView models
    """

    def __init__(
        self,
        display_name: str,
        tooltip: str,
        children: list["StageManagerTreeItem"] | None = None,
        data: dict = None,
    ):
        super().__init__(children=children)

        for child in children or []:
            child.parent = self

        self._display_name = display_name
        self._tooltip = tooltip
        self._data = data or {}

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
    def data(self) -> dict:
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
        return bool(self._children)

    def __eq__(self, other):
        if isinstance(other, StageManagerTreeItem):
            return self.display_name == other.display_name and self.tooltip == other.tooltip and self.data == other.data
        return False

    def __hash__(self):
        return hash(self.display_name + self.tooltip + str(self.data))


class StageManagerTreeModel(_TreeModelBase[StageManagerTreeItem], Generic[DataType]):
    """
    A TreeView model used to define the structure of the tree
    """

    def __init__(self):
        super().__init__()

        self._context_items: list[Any] = []
        self._filter_functions: list[Callable[[Iterable[Any]], list[Any]]] = []
        self._column_count = 0

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_items": None,
                "_context_items": None,
                "_filter_functions": None,
                "_column_count": None,
            }
        )
        return default_attr

    @property
    def items_dict(self) -> dict[int, StageManagerTreeItem]:
        """
        Get a dictionary of item hashes and items
        """
        return {hash(item): item for item in self.iter_items_children()}

    @property
    def context_items(self) -> list[Any]:
        """
        Get items set by the context plugin
        """
        return self.filter_items(self._context_items)

    @context_items.setter
    def context_items(self, items: Iterable[StageManagerTreeItem]):
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

    def refresh(self):
        """
        Method called when the `self._items` attribute should be refreshed
        """
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

    def add_filter_functions(self, value: list[Callable[[Iterable[DataType]], list[DataType]]]):
        """
        Extend the filter functions to apply to the items
        """
        self._filter_functions.extend(value)

    def clear_filter_functions(self):
        """
        Clear the filter functions to apply to the items
        """
        self._filter_functions.clear()

    def filter_items(self, items: Iterable[DataType]) -> list[DataType]:
        """
        Filter the given items using the active filter plugins

        Args:
            items: A list of items to filter

        Returns:
            The filtered list of items
        """
        filtered_items = items

        for filter_function in self._filter_functions:
            filtered_items = filter_function(filtered_items)

        return filtered_items


class StageManagerTreeDelegate(_TreeDelegateBase):
    """
    A TreeView delegate used to define the look of every element in the tree
    """

    def __init__(self):
        super().__init__()

        self._column_widget_builders = {}
        self._column_header_builders = {}

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_column_widget_builders": None,
                "_column_header_builders": None,
            }
        )
        return default_attr

    def set_column_builders(self, columns: list["_StageManagerColumnPlugin"]):
        for index, column in enumerate(columns):
            self._column_widget_builders[index] = column.build_ui
            self._column_header_builders[index] = column.build_header

    def _build_widget(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
        column_id: int,
        level: int,
        expanded: bool,
    ):
        if column_id in self._column_widget_builders:
            self._column_widget_builders[column_id](model, item, level, expanded)

    def _build_header(self, column_id: int):
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
