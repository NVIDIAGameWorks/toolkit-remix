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

import omni.kit.test
from lightspeed.common.constants import REMIX_CATEGORIES_DISPLAY_NAMES
from lightspeed.trex.stage_manager.plugin.tree.usd.category_groups import CategoryGroupsModel
from lightspeed.trex.stage_manager.plugin.tree.usd.mesh_groups import MeshGroupsModel
from omni.flux.stage_manager.factory import StageManagerItem
from pxr import Sdf

__all__ = ["TestRemixUSDGroupedTreeWorkerPreparation"]


def _make_prim(path: str, type_name: str):
    prim = mock.Mock()
    prim.GetPath.return_value = Sdf.Path(path)
    prim.GetTypeName.return_value = type_name
    prim.IsValid.return_value = True
    return prim


def _build(model, items):
    cancel_event = threading.Event()
    return model._build_items(items, cancel_event)


class TestRemixUSDGroupedTreeWorkerPreparation(omni.kit.test.AsyncTestCase):
    async def test_grouped_tree_builders_with_cancelled_refresh_return_without_work(self):
        # Arrange
        cancel_event = threading.Event()
        cancel_event.set()
        models = (CategoryGroupsModel(), MeshGroupsModel())

        # Act
        results = [model._build_items([], cancel_event) for model in models]

        # Assert
        self.assertEqual([None] * len(models), results)

    async def test_category_groups_should_build_from_worker_data(self):
        # Arrange
        category_attr, category_display_name = next(iter(REMIX_CATEGORIES_DISPLAY_NAMES.items()))
        model = CategoryGroupsModel()
        items = []
        for path in ("/Cube", "/World/Cube"):
            prim = _make_prim(path, "Mesh")
            attr = mock.Mock()
            attr.GetName.return_value = category_attr
            attr.Get.return_value = True
            prim.GetAttributes.return_value = [attr]
            items.append(StageManagerItem(path, data=prim))

        # Act
        root_items = _build(model, items)

        # Assert
        self.assertEqual([category_display_name], [item.display_name for item in root_items])
        self.assertEqual(["Cube", "Cube"], [item.display_name for item in root_items[0].children])
        self.assertEqual(["/", "World"], [item.display_name_ancestor for item in root_items[0].children])

    async def test_mesh_groups_should_build_duplicate_root_and_nested_names_from_worker_data(self):
        # Arrange
        model = MeshGroupsModel()
        items = [
            StageManagerItem("/Mesh", data=_make_prim("/Mesh", "Mesh")),
            StageManagerItem("/World/Mesh", data=_make_prim("/World/Mesh", "Mesh")),
        ]

        with (
            mock.patch(
                "lightspeed.trex.stage_manager.plugin.tree.usd.mesh_groups._is_mesh_prototype", return_value=False
            ),
            mock.patch("lightspeed.trex.stage_manager.plugin.tree.usd.mesh_groups._is_instance", return_value=False),
            mock.patch(
                "lightspeed.trex.stage_manager.plugin.tree.usd.mesh_groups._is_empty_mesh_prim", return_value=True
            ),
        ):
            # Act
            root_items = _build(model, items)

        # Assert
        self.assertEqual(["Mesh", "Mesh"], [item.display_name for item in root_items])
        self.assertEqual(["/Mesh", "/World/Mesh"], [item.path for item in root_items])

    async def test_mesh_groups_should_build_from_worker_data(self):
        # Arrange
        model = MeshGroupsModel()
        mesh_prim = _make_prim("/RootNode/meshes/mesh_0AB745B8BEE1F16B", "Mesh")
        instance_prim = _make_prim("/RootNode/instances/inst_0AB745B8BEE1F16B_0", "Xform")
        items = [
            StageManagerItem("/RootNode/meshes/mesh_0AB745B8BEE1F16B", data=mesh_prim),
            StageManagerItem("/RootNode/instances/inst_0AB745B8BEE1F16B_0", data=instance_prim),
        ]

        with (
            mock.patch(
                "lightspeed.trex.stage_manager.plugin.tree.usd.mesh_groups._is_mesh_prototype",
                side_effect=lambda prim: prim is mesh_prim,
            ),
            mock.patch(
                "lightspeed.trex.stage_manager.plugin.tree.usd.mesh_groups._is_instance",
                side_effect=lambda prim: prim is instance_prim,
            ),
            mock.patch(
                "lightspeed.trex.stage_manager.plugin.tree.usd.mesh_groups._is_empty_mesh_prim",
                return_value=False,
            ),
        ):
            # Act
            root_items = _build(model, items)

        # Assert
        self.assertEqual(["mesh_0AB745B8BEE1F16B"], [item.display_name for item in root_items])
        self.assertEqual(["inst_0AB745B8BEE1F16B_0"], [item.display_name for item in root_items[0].children])
