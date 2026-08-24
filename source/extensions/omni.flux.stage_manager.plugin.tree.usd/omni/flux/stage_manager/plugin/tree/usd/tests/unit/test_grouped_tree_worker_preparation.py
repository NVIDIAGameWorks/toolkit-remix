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

import asyncio
import threading
from unittest import mock

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem, StageManagerUtils
from omni.flux.stage_manager.plugin.tree.usd.custom_tag_groups import CustomTagGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.light_groups import LightGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.material_groups import MaterialGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.prim_groups import PrimGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.skeleton_groups import SkeletonGroupsModel
from pxr import Sdf, UsdGeom, UsdShade, Vt

__all__ = ["TestUSDGroupedTreeWorkerPreparation"]


def _make_prim(path: str, type_name: str):
    prim = mock.Mock()
    prim.GetPath.return_value = Sdf.Path(path)
    prim.GetTypeName.return_value = type_name
    prim.IsValid.return_value = True
    return prim


def _build(model, items):
    cancel_event = threading.Event()
    return model._build_items(items, cancel_event)


class TestUSDGroupedTreeWorkerPreparation(omni.kit.test.AsyncTestCase):
    async def test_grouped_tree_builders_with_cancelled_refresh_return_without_work(self):
        # Arrange
        cancel_event = threading.Event()
        cancel_event.set()
        models = (LightGroupsModel(), MaterialGroupsModel(), CustomTagGroupsModel(), SkeletonGroupsModel())

        # Act
        results = [model._build_items([], cancel_event) for model in models]

        # Assert
        self.assertEqual([None] * len(models), results)

    async def test_prim_groups_should_build_from_worker_data(self):
        # Arrange
        model = PrimGroupsModel()
        items = [
            StageManagerItem("/Cube", data=_make_prim("/Cube", "Mesh")),
            StageManagerItem("/World/Cube", data=_make_prim("/World/Cube", "Mesh")),
        ]

        # Act
        root_items = _build(model, items)

        # Assert
        self.assertEqual(["Cube", "Cube"], [item.display_name for item in root_items])
        self.assertEqual(["/Cube", "/World/Cube"], [item.path for item in root_items])

    async def test_light_groups_should_build_from_worker_data(self):
        # Arrange
        model = LightGroupsModel()
        items = [
            StageManagerItem("/KeyLight", data=_make_prim("/KeyLight", "SphereLight")),
            StageManagerItem("/World/KeyLight", data=_make_prim("/World/KeyLight", "SphereLight")),
        ]

        # Act
        root_items = _build(model, items)

        # Assert
        self.assertEqual(["Sphere Lights"], [item.display_name for item in root_items])
        self.assertEqual(["KeyLight", "KeyLight"], [item.display_name for item in root_items[0].children])
        self.assertEqual(["/", "World"], [item.display_name_ancestor for item in root_items[0].children])

    async def test_material_groups_should_build_from_worker_data(self):
        # Arrange
        model = MaterialGroupsModel()
        root_material_prim = _make_prim("/Mat", "Material")
        material_prim = _make_prim("/World/Mat", "Material")
        mesh_prim = _make_prim("/World/Cube", "Mesh")
        root_material_prim.IsA.side_effect = lambda schema: schema is UsdShade.Material
        material_prim.IsA.side_effect = lambda schema: schema is UsdShade.Material
        mesh_prim.IsA.side_effect = lambda schema: schema is UsdGeom.Mesh
        material = mock.Mock()
        material.GetPrim.return_value.GetPath.return_value = Sdf.Path("/World/Mat")
        items = [
            StageManagerItem("/Mat", data=root_material_prim),
            StageManagerItem("/World/Mat", data=material_prim),
            StageManagerItem("/World/Cube", data=mesh_prim),
        ]

        with mock.patch(
            "omni.flux.stage_manager.plugin.tree.usd.material_groups._get_materials_from_prim_paths",
            return_value=[material],
        ):
            # Act
            root_items = _build(model, items)

        # Assert
        self.assertEqual(["Mat", "Mat"], [item.display_name for item in root_items])
        self.assertEqual(["/Mat", "/World/Mat"], [item.path for item in root_items])
        self.assertEqual(["Cube"], [item.display_name for item in root_items[1].children])

    async def test_custom_tag_groups_should_build_from_worker_data(self):
        # Arrange
        model = CustomTagGroupsModel()
        items = [
            StageManagerItem("/Cube", data=_make_prim("/Cube", "Mesh")),
            StageManagerItem("/World/Cube", data=_make_prim("/World/Cube", "Mesh")),
        ]

        class _FakeCustomTagsCore:
            destroyed = False

            def __init__(self, context_name=""):
                pass

            def get_all_tags(self):
                return [Sdf.Path("/Tags/Car")]

            def get_tag_name(self, _tag_path):
                return "Car"

            def get_tag_prims(self, _tag_path):
                return [Sdf.Path("/Cube"), Sdf.Path("/World/Cube")]

            def destroy(self):
                type(self).destroyed = True

        with mock.patch(
            "omni.flux.stage_manager.plugin.tree.usd.custom_tag_groups._CustomTagsCore",
            new=_FakeCustomTagsCore,
        ):
            # Act
            root_items = _build(model, items)

        # Assert
        self.assertEqual(["Car"], [item.display_name for item in root_items])
        self.assertEqual("/Tags/Car", root_items[0].path)
        self.assertEqual(["Cube", "Cube"], [item.display_name for item in root_items[0].children])
        self.assertEqual(["/", "World"], [item.display_name_ancestor for item in root_items[0].children])
        self.assertTrue(_FakeCustomTagsCore.destroyed)

    async def test_skeleton_groups_should_build_from_worker_data(self):
        # Arrange
        model = SkeletonGroupsModel()
        root_prim = _make_prim("/World/Root", "SkelRoot")
        skeleton_prim = _make_prim("/World/Root/Skeleton", "Skeleton")
        skeleton_prim.GetParent.return_value = root_prim
        root_item = StageManagerItem("/World/Root", data=root_prim)
        skeleton_item = StageManagerItem("/World/Root/Skeleton", data=skeleton_prim, parent=root_item)
        joints_attr = mock.Mock()
        joints_attr.Get.return_value = Vt.TokenArray(["RootJoint", "RootJoint/ChildJoint"])

        class _FakeSkeleton:
            def __init__(self, _prim):
                self.GetJointsAttr = mock.Mock(return_value=joints_attr)

        with mock.patch("omni.flux.stage_manager.plugin.tree.usd.skeleton_groups.UsdSkel.Skeleton", new=_FakeSkeleton):
            # Act
            root_items = _build(model, [root_item, skeleton_item])

        # Assert
        self.assertEqual(["Root"], [item.display_name for item in root_items])
        skeleton = root_items[0].children[0]
        root_joint = skeleton.children[0]
        child_joint = root_joint.children[0]
        self.assertEqual("Skeleton", skeleton.display_name)
        self.assertEqual("RootJoint", root_joint.display_name)
        self.assertEqual("ChildJoint", child_joint.display_name)
        self.assertIsNone(root_joint.path)
        self.assertIsNone(child_joint.path)
        self.assertIs(skeleton, root_joint.parent)
        self.assertIs(root_joint, child_joint.parent)
        self.assertFalse(hasattr(model, "_unique_item_names"))
        self.assertFalse(hasattr(root_item, "tree_item"))
        self.assertFalse(hasattr(skeleton_item, "tree_item"))

    async def test_concurrent_skeleton_builds_keep_unique_names_local(self):
        # Arrange
        model = SkeletonGroupsModel()
        items_a = [
            StageManagerItem("/Root", data=_make_prim("/Root", "SkelRoot")),
            StageManagerItem("/A/Root", data=_make_prim("/A/Root", "SkelRoot")),
        ]
        items_b = [
            StageManagerItem("/Bone", data=_make_prim("/Bone", "SkelRoot")),
            StageManagerItem("/B/Bone", data=_make_prim("/B/Bone", "SkelRoot")),
        ]
        barrier = threading.Barrier(2)
        original_get_unique_names = StageManagerUtils.get_unique_names

        def get_unique_names_after_both_builds_start(items):
            barrier.wait(timeout=2)
            return original_get_unique_names(items)

        # Act
        with mock.patch(
            "omni.flux.stage_manager.plugin.tree.usd.skeleton_groups._StageManagerUtils.get_unique_names",
            get_unique_names_after_both_builds_start,
        ):
            result_a, result_b = await asyncio.gather(
                asyncio.to_thread(model._build_items, items_a, threading.Event()),
                asyncio.to_thread(model._build_items, items_b, threading.Event()),
            )

        # Assert
        self.assertEqual({"/", "A"}, {item.display_name_ancestor for item in result_a})
        self.assertEqual({"/", "B"}, {item.display_name_ancestor for item in result_b})
