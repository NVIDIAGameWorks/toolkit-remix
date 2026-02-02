"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("TestItemGroupExpansion",)

import omni.kit.app
import omni.kit.test
import omni.ui as ui
from omni.flux.property_widget_builder.widget import ItemGroup, Model, PropertyWidget

from ..ui_components import TestItem


class TestItemGroupExpansion(omni.kit.test.AsyncTestCase):
    """
    Tests for ItemGroup default expansion in PropertyWidget.

    Validates that ItemGroup(expanded=True) auto-expands regardless of
    whether the widget or items are created first. This is critical for
    consumers like setup_ui.py where set_items() is called before rebuild().
    """

    async def setUp(self):
        self.window = ui.Window("TestExpansionWindow", width=400, height=300)
        self.model = Model()
        self.widget = None

    async def tearDown(self):
        if self.widget:
            self.widget.destroy()
        self.window.destroy()
        await omni.kit.app.get_app().next_update_async()

    def _create_group_with_child(self, name: str, expanded: bool = False) -> ItemGroup:
        group = ItemGroup(name, expanded=expanded)
        child = TestItem([("Child", "value")])
        child.parent = group
        return group

    async def _wait_for_ui(self, frames: int = 2):
        for _ in range(frames):
            await omni.kit.app.get_app().next_update_async()

    async def test_expanded_group_widget_created_first(self):
        """ItemGroup(expanded=True) auto-expands when widget exists before items."""
        # Arrange
        with self.window.frame:
            self.widget = PropertyWidget(model=self.model)
        group = self._create_group_with_child("Inputs", expanded=True)

        # Act
        self.model.set_items([group])
        await self._wait_for_ui(3)

        # Assert
        self.assertTrue(self.widget.tree_view.is_expanded(group))

    async def test_expanded_group_items_created_first(self):
        """ItemGroup(expanded=True) auto-expands when items exist before widget."""
        # Arrange
        group = self._create_group_with_child("Inputs", expanded=True)
        self.model.set_items([group])

        # Act
        with self.window.frame:
            self.widget = PropertyWidget(model=self.model)
        await self._wait_for_ui(3)

        # Assert
        self.assertTrue(self.widget.tree_view.is_expanded(group))

    async def test_collapsed_group_remains_collapsed(self):
        """ItemGroup without expanded=True stays collapsed (backward compatibility)."""
        # Arrange
        with self.window.frame:
            self.widget = PropertyWidget(model=self.model)
        group = self._create_group_with_child("Inputs", expanded=False)

        # Act
        self.model.set_items([group])
        await self._wait_for_ui()

        # Assert
        self.assertFalse(self.widget.tree_view.is_expanded(group))

    async def test_user_interaction_overrides_default(self):
        """User manually collapsing overrides ItemGroup's default expanded state."""
        # Arrange
        with self.window.frame:
            self.widget = PropertyWidget(model=self.model)
        group = self._create_group_with_child("Inputs", expanded=True)
        self.model.set_items([group])
        await self._wait_for_ui(3)

        # Act
        self.widget.tree_view.set_expanded(group, False, False)
        await self._wait_for_ui()

        # Assert
        self.assertFalse(self.widget.tree_view.is_expanded(group))

    async def test_mixed_expansion_states(self):
        """Multiple groups with different expanded states work correctly."""
        # Arrange
        with self.window.frame:
            self.widget = PropertyWidget(model=self.model)
        expanded_group = self._create_group_with_child("Inputs", expanded=True)
        collapsed_group = self._create_group_with_child("Outputs", expanded=False)

        # Act
        self.model.set_items([expanded_group, collapsed_group])
        await self._wait_for_ui(3)

        # Assert
        self.assertTrue(self.widget.tree_view.is_expanded(expanded_group))
        self.assertFalse(self.widget.tree_view.is_expanded(collapsed_group))
