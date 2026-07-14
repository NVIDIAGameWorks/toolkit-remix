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

import threading
from unittest.mock import Mock

import omni.kit.test
from omni.flux.stage_manager.plugin.context.usd.current_stage import CurrentStageContextPlugin

__all__ = ["TestCurrentStageContextPlugin"]


class TestCurrentStageContextPlugin(omni.kit.test.AsyncTestCase):
    def _make_plugin(self, stage):
        plugin = CurrentStageContextPlugin.model_construct(context_name="")
        plugin._stage = stage
        plugin._listener_event_occurred_subs = [Mock()]
        return plugin

    async def test_get_items_without_stage_returns_empty_list(self):
        # Arrange
        plugin = self._make_plugin(None)

        # Act
        result = plugin.get_items()

        # Assert
        self.assertEqual([], result)

    async def test_get_items_builds_parent_before_child_hierarchy(self):
        # Arrange
        root = Mock()
        child = Mock()
        root.GetParent.return_value = Mock()
        root.GetFilteredChildren.return_value = [child]
        child.GetParent.return_value = root
        child.GetFilteredChildren.return_value = []
        pseudo_root = Mock()
        pseudo_root.GetChildren.return_value = [root]
        stage = Mock()
        stage.GetPseudoRoot.return_value = pseudo_root
        plugin = self._make_plugin(stage)

        # Act
        result = plugin.get_items()

        # Assert
        self.assertEqual([root, child], [item.data for item in result])
        self.assertIsNone(result[0].parent)
        self.assertIs(result[1].parent, result[0])

    async def test_get_items_with_cancelled_event_returns_none(self):
        # Arrange
        pseudo_root = Mock()
        pseudo_root.GetChildren.return_value = [Mock()]
        stage = Mock()
        stage.GetPseudoRoot.return_value = pseudo_root
        plugin = self._make_plugin(stage)
        cancel_event = threading.Event()
        cancel_event.set()

        # Act
        result = plugin.get_items(cancel_event)

        # Assert
        self.assertIsNone(result)
