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

from unittest.mock import Mock

import omni.kit.test
from omni.flux.stage_manager.factory.items import StageManagerItem
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel
from pxr import Sdf

__all__ = ["TestStageManagerTreeModelSelection"]


class _ConcreteTreeModel(StageManagerTreeModel):
    """Minimal concrete subclass for testing (StageManagerTreeModel has abstract default_attr)."""

    @property
    def default_attr(self) -> dict:
        return super().default_attr


class TestStageManagerTreeModelSelection(omni.kit.test.AsyncTestCase):
    def _make_model(self):
        return _ConcreteTreeModel()

    def _make_item(self, prim_path="/World/Prim"):
        item = Mock()
        item.data = Mock()
        item.data.GetPath.return_value = prim_path
        return item

    def _make_context_item(self, prim_path="/World/Prim"):
        prim = Mock()
        prim.GetPath.return_value = Sdf.Path(prim_path)
        return StageManagerItem(prim_path, data=prim)

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------

    async def test_selection_property_owns_assigned_items_and_can_be_cleared(self):
        # Arrange
        model = self._make_model()
        self.addCleanup(model.destroy)
        items = [self._make_item("/A")]

        # Act
        default_selection = model.selection
        model.selection = items
        assigned_selection = model.selection
        items.append(self._make_item("/B"))
        selection_after_input_mutation = model.selection
        model.selection = []

        # Assert
        self.assertEqual([], default_selection)
        self.assertEqual([items[0]], assigned_selection)
        self.assertEqual([items[0]], selection_after_input_mutation)
        self.assertEqual([], model.selection)

    # ------------------------------------------------------------------
    # refresh() clears selection for the interaction to restore from its active source
    # ------------------------------------------------------------------

    async def test_refresh_clears_stale_selection(self):
        """refresh() should clear model.selection when the selected prim no longer exists."""
        # Arrange
        model = self._make_model()
        self.addCleanup(model.destroy)
        model.selection = [self._make_item("/World/Stale")]
        model.set_context_items([])

        # Act
        await model.refresh()

        # Assert
        self.assertEqual(model.selection, [])

    async def test_refresh_clears_selection_when_rebuilt_item_still_exists(self):
        """refresh() should not preserve selection captured from the previous tree."""
        # Arrange
        model = self._make_model()
        self.addCleanup(model.destroy)
        prim_path = "/World/Prim"

        model.set_context_items([self._make_context_item(prim_path)])
        await model.refresh()

        selected_item = model.get_item_children(None)[0]
        model.selection = [selected_item]

        # Act
        model.set_context_items([self._make_context_item(prim_path)])
        await model.refresh()

        # Assert
        self.assertEqual([], model.selection)
        self.assertIsNot(selected_item, model.get_item_children(None)[0])
