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
from unittest import mock

from omni.kit.test import AsyncTestCase
from omni.flux.stage_manager.factory import StageManagerItem
from pxr import Sdf

from ...category_groups import CategoryGroupsModel

__all__ = ["TestCategoryGroupsModel"]

_SKY_ATTRIBUTE = "remix_category:sky"
_WORLD_UI_ATTRIBUTE = "remix_category:world_ui"


def _make_prim(path: str, type_name: str):
    """Create a valid prim mock with the supplied path and type name."""
    prim = mock.Mock()
    prim.GetPath.return_value = Sdf.Path(path)
    prim.GetTypeName.return_value = type_name
    prim.IsValid.return_value = True
    return prim


def _build(model: CategoryGroupsModel, items: list[StageManagerItem]):
    """Build category tree items with a non-cancelled worker event."""
    return model._build_items(items, threading.Event())


class TestCategoryGroupsModel(AsyncTestCase):
    """Tests category grouped-tree construction from prepared context data."""

    async def test_build_items_with_cancelled_refresh_returns_without_work(self):
        """Return without building category groups when the refresh is cancelled."""
        # Arrange
        cancel_event = threading.Event()
        cancel_event.set()

        # Act
        result = CategoryGroupsModel()._build_items([], cancel_event)

        # Assert
        self.assertIsNone(result)

    async def test_build_items_with_worker_data_creates_category_groups(self):
        """Build category groups from prepared category and display-name data."""
        # Arrange
        category_attr = _SKY_ATTRIBUTE
        category_display_name = "Sky"
        model = CategoryGroupsModel()
        items = []
        for path in ("/Cube", "/World/Cube"):
            prim = _make_prim(path, "Mesh")
            prim.GetAttributes.side_effect = AssertionError("Category groups must not rescan USD attributes")
            item = StageManagerItem(path, data=prim)
            item.prepare_group_memberships((category_attr,))
            item.prepare_display_name(("Cube", "/" if path == "/Cube" else "World"))
            items.append(item)

        # Act
        root_items = _build(model, items)

        # Assert
        self.assertEqual([category_display_name], [item.display_name for item in root_items])
        self.assertEqual(["Cube", "Cube"], [item.display_name for item in root_items[0].children])
        self.assertEqual(["/", "World"], [item.display_name_ancestor for item in root_items[0].children])

    async def test_build_items_with_multiple_categories_adds_item_to_each_group(self):
        """Attach an item to every prepared category group."""
        # Arrange
        categories = (_WORLD_UI_ATTRIBUTE, _SKY_ATTRIBUTE)
        prim = _make_prim("/World/Cube", "Mesh")
        prim.GetAttributes.side_effect = AssertionError("Category groups must not rescan USD attributes")
        item = StageManagerItem("/World/Cube", data=prim)
        item.prepare_group_memberships(categories)
        item.prepare_display_name(("Cube", None))

        # Act
        root_items = _build(CategoryGroupsModel(), [item])

        # Assert
        self.assertEqual(["Sky", "World UI"], [root_item.display_name for root_item in root_items])
        self.assertEqual([1, 1], [len(root_item.children) for root_item in root_items])
        sky_child = root_items[0].children[0]
        world_ui_child = root_items[1].children[0]
        self.assertEqual(["Cube", "Cube"], [sky_child.display_name, world_ui_child.display_name])
        self.assertIsNot(sky_child, world_ui_child)
        self.assertIs(root_items[0], sky_child.parent)
        self.assertIs(root_items[1], world_ui_child.parent)

    async def test_requires_context_ancestors_with_category_groups_model_returns_false(self):
        """Request sparse candidates because category groups use prepared item data."""
        # Arrange
        model = CategoryGroupsModel()

        # Act
        result = model.requires_context_ancestors

        # Assert
        self.assertFalse(result)
