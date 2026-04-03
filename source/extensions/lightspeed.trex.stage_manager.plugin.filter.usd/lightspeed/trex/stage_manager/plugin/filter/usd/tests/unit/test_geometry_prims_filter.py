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
from lightspeed.trex.stage_manager.plugin.filter.usd.geometry_prims import GeometryPrimsFilterPlugin

__all__ = ["TestGeometryPrimsFilterUnit"]

_PRIM_UTILS = "lightspeed.trex.stage_manager.plugin.filter.usd.geometry_prims.is_empty_mesh_prim"


def _make_item(prim=None):
    item = Mock()
    item.data = prim if prim is not None else Mock()
    return item


def _make_none_item():
    item = Mock()
    item.data = None
    return item


class TestGeometryPrimsFilterUnit(omni.kit.test.AsyncTestCase):
    async def test_returns_true_for_mesh_prim(self):
        # Arrange
        plugin = GeometryPrimsFilterPlugin()
        prim = Mock()
        prim.IsA.return_value = True
        item = _make_item(prim)

        # Act
        with patch(_PRIM_UTILS, return_value=False):
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_returns_true_for_deleted_mesh_asset(self):
        # Arrange
        plugin = GeometryPrimsFilterPlugin()
        prim = Mock()
        prim.IsA.return_value = False
        item = _make_item(prim)

        # Act
        with patch(_PRIM_UTILS, return_value=True):
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_returns_false_for_non_mesh_non_deleted(self):
        # Arrange
        plugin = GeometryPrimsFilterPlugin()
        prim = Mock()
        prim.IsA.return_value = False
        item = _make_item(prim)

        # Act
        with patch(_PRIM_UTILS, return_value=False):
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    async def test_returns_false_for_none_prim(self):
        # Arrange
        plugin = GeometryPrimsFilterPlugin()
        item = _make_none_item()

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
