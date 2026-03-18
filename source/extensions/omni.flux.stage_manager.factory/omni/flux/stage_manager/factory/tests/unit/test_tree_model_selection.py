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

from unittest.mock import AsyncMock, Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel

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

    # ------------------------------------------------------------------
    # set_selection / selection
    # ------------------------------------------------------------------

    async def test_set_selection_stores_items(self):
        """set_selection(items) should make items accessible via .selection."""
        model = self._make_model()
        self.addCleanup(model.destroy)
        items = [self._make_item("/A"), self._make_item("/B")]

        model.set_selection(items)

        self.assertEqual(model.selection, items)

    async def test_set_selection_empty_clears_selection(self):
        """set_selection([]) should clear a previously stored selection."""
        model = self._make_model()
        self.addCleanup(model.destroy)
        model.set_selection([self._make_item()])

        model.set_selection([])

        self.assertEqual(model.selection, [])

    async def test_set_selection_returns_copy_not_reference(self):
        """Mutating the list passed to set_selection must not change model.selection."""
        model = self._make_model()
        self.addCleanup(model.destroy)
        items = [self._make_item("/A")]

        model.set_selection(items)
        items.append(self._make_item("/B"))  # mutate the original list

        self.assertEqual(len(model.selection), 1)

    async def test_selection_default_is_empty(self):
        """A freshly created model should have an empty selection."""
        model = self._make_model()
        self.addCleanup(model.destroy)

        self.assertEqual(model.selection, [])

    # ------------------------------------------------------------------
    # refresh() clears stale selection
    # ------------------------------------------------------------------

    async def test_refresh_clears_stale_selection(self):
        """refresh() must clear model.selection before rebuilding items.

        Note: refresh() calls omni.kit.app.get_app().next_update_async() internally,
        so this test requires the live Kit runtime (provided by the .bat test runner).
        get_context_items is patched to avoid hitting the telemetry layer.
        """
        model = self._make_model()
        self.addCleanup(model.destroy)
        model.set_selection([self._make_item("/World/Stale")])

        with patch.object(model, "get_context_items", new_callable=AsyncMock, return_value=[]):
            await model.refresh()

        self.assertEqual(model.selection, [])
