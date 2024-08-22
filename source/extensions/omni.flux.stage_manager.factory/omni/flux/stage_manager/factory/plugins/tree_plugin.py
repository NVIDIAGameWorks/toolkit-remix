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
from typing import Any, Callable, Iterable

from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase
from omni.flux.utils.widget.tree_widget import TreeItemBase as _TreeItemBase
from omni.flux.utils.widget.tree_widget import TreeModelBase as _TreeModelBase

from .base import StageManagerPluginBase as _StageManagerPluginBase


class StageManagerTreeItem(_TreeItemBase):
    """
    A TreeView item used in TreeView models
    """

    def __init__(
        self, display_name: str, tooltip: str, children: list["StageManagerTreeItem"] | None = None, data: Any = None
    ):
        super().__init__(children=children)

        self._display_name = display_name
        self._tooltip = tooltip
        self._data = data

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_display_name": None,
                "_tooltip": None,
                "_data": None,
            }
        )
        return default_attr

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def tooltip(self) -> str:
        return self._tooltip

    @property
    def data(self) -> Any:
        return self._data

    @property
    def can_have_children(self) -> bool:
        return bool(self._children)

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
        super().__init__()

        self._context_items: list[Any] = []
        self._context_filters: list[Callable[[Iterable[Any]], list[Any]]] = []
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
                "_context_filters": None,
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
    def context_filters(self) -> list[Any]:
        """
        Get items set by the context plugin
        """
        return self._context_filters

    @context_filters.setter
    def context_filters(self, items: Iterable[StageManagerTreeItem]):
        """
        Set items fetched in the context plugin
        """
        self._context_filters = list(items)

    @property
    def filter_functions(self) -> list[Callable[[Iterable[Any]], list[Any]]]:
        """
        Get the filter functions to apply to the items
        """
        return self._filter_functions

    @filter_functions.setter
    def filter_functions(self, value: list[Callable[[Iterable[Any]], list[Any]]]):
        """
        Set the filter functions to apply to the items
        """
        self._filter_functions = value

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

    def get_item_children(self, item: StageManagerTreeItem | None):
        """
        Returns all the children of any given item.
        """
        if item is None:
            return self._items
        return item.children or []

    def get_item_value_model_count(self, item: StageManagerTreeItem):
        return self.column_count

    def filter_items(self, items: Iterable[Any]) -> list[Any]:
        """
        Filter the given items using the active filter plugins

        Args:
            items: A list of items to filter

        Returns:
            The filtered list of items
        """
        filtered_items = items

        for filter_function in self.context_filters + self.filter_functions:
            filtered_items = filter_function(filtered_items)

        return filtered_items


class StageManagerTreeDelegate(_TreeDelegateBase):
    """
    A TreeView delegate used to define the look of every element in the tree
    """

    def __init__(self):
        super().__init__()

        self._column_widget_builders = {}
        self._column_headers = {}

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_column_widget_builders": None,
                "_column_headers": None,
            }
        )
        return default_attr

    @property
    def column_widget_builders(
        self,
    ) -> dict[int, Callable[[StageManagerTreeModel, StageManagerTreeItem, int, bool], None]]:
        return self._column_widget_builders

    @column_widget_builders.setter
    def column_widget_builders(
        self, value: dict[int, Callable[[StageManagerTreeModel, StageManagerTreeItem, int, bool], None]]
    ):
        self._column_widget_builders = value

    @property
    def column_header_builders(self) -> dict[int, Callable[[], None]]:
        return self._column_headers

    @column_header_builders.setter
    def column_header_builders(self, value: dict[int, Callable[[], None]]):
        self._column_headers = value

    def _build_widget(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
        column_id: int,
        level: int,
        expanded: bool,
    ):
        if column_id in self.column_widget_builders:
            self.column_widget_builders[column_id](model, item, level, expanded)

    def _build_header(self, column_id: int):
        if column_id in self.column_header_builders:
            self.column_header_builders[column_id]()


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
