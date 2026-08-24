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

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory.plugins import StageManagerTreeItemProxy
from omni.flux.stage_manager.plugin.tree.usd.base import StageManagerUSDTreeItem, StageManagerUSDTreeModel

__all__ = ["TestUSDTreeContextMenuPayload"]


class _ConcreteUSDTreeItem(StageManagerUSDTreeItem):
    @property
    def default_attr(self) -> dict:
        return super().default_attr


class _ConcreteUSDTreeModel(StageManagerUSDTreeModel):
    @property
    def default_attr(self) -> dict:
        return super().default_attr


class TestUSDTreeContextMenuPayload(omni.kit.test.AsyncTestCase):
    async def test_context_menu_payload_uses_canonical_item_for_every_action_key(self):
        # Arrange
        model = _ConcreteUSDTreeModel("test")
        self.addCleanup(model.destroy)
        canonical_item = _ConcreteUSDTreeItem("Prim", Mock(), path="/World/Prim")
        proxy_item = StageManagerTreeItemProxy(canonical_item)
        self.addCleanup(canonical_item.destroy)
        self.addCleanup(proxy_item.destroy)
        usd_context = Mock()
        usd_context.get_selection.return_value.get_selected_prim_paths.return_value = ["/World/Prim"]

        # Act
        with patch(
            "omni.flux.stage_manager.plugin.tree.usd.base.usd_base.usd.get_context",
            return_value=usd_context,
        ):
            payload = model.get_context_menu_payload(proxy_item)

        # Assert
        self.assertIs(canonical_item, payload["right_clicked_item"])
        self.assertIs(canonical_item, payload["item"])
        self.assertEqual(["/World/Prim"], payload["selected_paths"])
