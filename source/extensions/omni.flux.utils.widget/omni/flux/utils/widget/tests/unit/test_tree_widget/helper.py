"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["MockTreeItem", "MockTreeModel", "MockTreeDelegate", "MockTreeWidget"]

from omni import ui
from omni.flux.utils.widget.tree_widget import TreeDelegateBase, TreeItemBase, TreeModelBase, TreeWidget


class MockTreeItem(TreeItemBase):
    """A simple mock tree item for testing."""

    def __init__(self, name: str, children: list["MockTreeItem"] | None = None):
        super().__init__()
        self._name = name

        # Set up children using the new parent-based API
        if children:
            for child in children:
                child.parent = self

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_name": None,
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def can_have_children(self) -> bool:
        return len(self.children) > 0

    def __repr__(self) -> str:
        return f"MockTreeItem({self._name})"


class MockTreeModel(TreeModelBase[MockTreeItem]):
    """A simple mock tree model for testing."""

    def __init__(self, items: list[MockTreeItem] | None = None):
        super().__init__()
        self._items = items if items is not None else []

    @property
    def default_attr(self) -> dict[str, None]:
        return {"_items": None}

    def get_item_children(self, item: MockTreeItem | None) -> list[MockTreeItem]:
        if item is None:
            return self._items
        return item.children

    def get_item_value_model_count(self, item) -> int:
        return 1


class MockTreeDelegate(TreeDelegateBase):
    """A simple mock tree delegate for testing."""

    @property
    def default_attr(self) -> dict[str, None]:
        return {"_selection": None}

    def _build_widget(self, model, item, column_id, level, expanded) -> None:
        """
        Build a widget for the given tree item.

        Note:
            Always called within a context manager, so no return value is needed.
        """
        label = item.name if item and hasattr(item, "name") else "None"
        ui.Label(label, height=24)


class MockTreeWidget(TreeWidget):
    """A concrete implementation of TreeWidget for testing."""

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_model": None,
            "_delegate": None,
            "_select_all_children": None,
            "_validate_action_selection": None,
            "_sub_selection_changed": None,
        }
