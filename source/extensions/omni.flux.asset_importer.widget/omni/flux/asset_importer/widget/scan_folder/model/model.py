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

from pathlib import Path

import omni.ui as ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.widget.tree_widget import TreeModelBase as _TreeModelBase


class Item(ui.AbstractItem):
    """Represent one discovered file and its selection state."""

    def __init__(self, path: Path):
        """Initialize a selected result item.

        Args:
            path: Path of the discovered file represented by the item.
        """
        super().__init__()
        self.path = path
        self.value = True
        self.selected = False

    def __repr__(self):
        """Return the quoted file path for debugging.

        Returns:
            Quoted string representation of the result path.
        """
        return f'"{self.path}"'


class Model(_TreeModelBase):
    """Store flat scan results and their row-selection state."""

    def __init__(self):
        """Initialize an empty result list."""
        super().__init__()
        self.__children = []
        self.__on_items_selected_changed = _Event()

    def refresh(self):
        """Clear every scan result and notify the tree view."""
        self.__children = []
        self._item_changed(None)

    def get_item_children(self, item):
        """Return root results for the flat tree model.

        Args:
            item: Parent item, or None when requesting root results.

        Returns:
            Root result items, or an empty list for any child item.
        """
        if item is None:
            return self.__children
        return []

    def set_items(self, paths: list[Path]) -> None:
        """Replace the scan results and notify the tree once.

        Args:
            paths: Discovered file paths displayed by the result tree.
        """
        self.__children = [Item(path) for path in paths]
        self._item_changed(None)

    def get_item_value_model_count(self, item):
        """Return the single column used by every result item.

        Args:
            item: Result item whose value-model count is requested.

        Returns:
            One column for the result path and checkbox controls.
        """
        return 1

    def set_items_selected(self, items: list[Item]):
        """Update which result rows are selected in the tree.

        Args:
            items: Result items selected by the tree view.
        """
        for item in self.__children:
            item.selected = item in items
        self.__on_items_selected_changed()

    def get_selected_items(self):
        """Return result items selected in the tree.

        Returns:
            Result items whose row-selection state is active.
        """
        return [item for item in self.__children if item.selected is True]
