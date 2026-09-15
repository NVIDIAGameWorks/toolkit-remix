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
from omni.flux.stage_manager.plugin.tree.usd import custom_tag_groups, light_groups, skeleton_groups
from omni.flux.stage_manager.plugin.tree.usd.custom_tag_groups import CustomTagGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.light_groups import LightGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.material_groups import MaterialGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.prim_groups import PrimGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.skeleton_groups import SkeletonGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsModel
from omni.flux.utils.common.lights import LightTypes
from pxr import Sdf, UsdGeom, UsdShade, Vt

from ... import prim_groups

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
    """Test grouped-tree worker preparation and context-data consumption."""

    async def test_requires_context_ancestors_with_concrete_grouped_models_returns_false(self):
        """Request sparse context candidates for concrete grouped-tree models."""
        # Arrange
        grouped_models = (LightGroupsModel(), MaterialGroupsModel(), SkeletonGroupsModel(), CustomTagGroupsModel())

        # Act
        capabilities = [model.requires_context_ancestors for model in grouped_models]

        # Assert
        self.assertEqual([False, False, False, False], capabilities)

    async def test_requires_context_ancestors_with_virtual_groups_model_returns_true(self):
        """Retain ancestor candidates for the reusable virtual-groups model."""
        # Arrange
        model = VirtualGroupsModel()

        # Act
        requires_context_ancestors = model.requires_context_ancestors

        # Assert
        self.assertTrue(requires_context_ancestors)

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

    async def test_prim_groups_path_hash_supports_parent_insertion_without_display_path_cache(self):
        """Insert path-hashed Prim items without populating the display-path cache."""
        # Arrange
        model = PrimGroupsModel()
        parent = model._build_item("World", None)
        parent.path = "/World"
        child = model._build_item("Cube", None)
        child.path = "/World/Cube"

        # Act
        child.parent = parent

        # Assert
        self.assertEqual("/World/Cube", child.path)
        self.assertIs(parent, child.parent)
        self.assertIs(child, parent.children[0])
        self.assertEqual(hash("/World/Cube"), hash(child))
        self.assertIsNone(child._long_display_path_name)

    async def test_prim_groups_pathless_hash_falls_back_to_display_hierarchy(self):
        """Fall back to the display hierarchy when hashing a pathless item."""
        # Arrange
        model = PrimGroupsModel()
        parent = model._build_item("Group", None)
        child = model._build_item("Child", None)

        # Act
        child.parent = parent

        # Assert
        self.assertEqual(hash("Group/Child"), hash(child))
        self.assertEqual("Group/Child", child._long_display_path_name)
        self.assertIs(child, parent.children[0])

    async def test_prim_groups_item_construction_does_not_request_icon_map(self):
        """Construct an item without requesting the prim type icon map."""
        # Arrange
        model = PrimGroupsModel()

        # Act
        with mock.patch.object(prim_groups, "_get_prim_type_icons") as get_prim_type_icons:
            item = model._build_item("Cube", _make_prim("/Cube", "Mesh"))
            item.path = "/Cube"
        self.addCleanup(item.destroy)

        # Assert
        get_prim_type_icons.assert_not_called()

    async def test_prim_groups_item_icon_loads_map_once_and_returns_type_icon(self):
        """Load the icon map once and return the matching prim type icon."""
        # Arrange
        model = PrimGroupsModel()
        with mock.patch.object(
            prim_groups,
            "_get_prim_type_icons",
            return_value={"Mesh": "MeshIcon"},
        ) as get_prim_type_icons:
            item = model._build_item("Cube", _make_prim("/Cube", "Mesh"))
            item.path = "/Cube"
            get_prim_type_icons.reset_mock()

            # Act
            result = item.icon
        self.addCleanup(item.destroy)

        # Assert
        self.assertEqual("MeshIcon", result)
        get_prim_type_icons.assert_called_once_with()

    async def test_prim_groups_item_icon_for_invalid_prim_returns_xform(self):
        """Return the Xform icon for an invalid prim."""
        # Arrange
        model = PrimGroupsModel()
        prim = _make_prim("/Cube", "Mesh")
        prim.IsValid.return_value = False
        with mock.patch.object(
            prim_groups,
            "_get_prim_type_icons",
            return_value={"Mesh": "MeshIcon"},
        ) as get_prim_type_icons:
            item = model._build_item("Cube", prim)
            item.path = "/Cube"

            # Act
            result = item.icon
        self.addCleanup(item.destroy)

        # Assert
        self.assertEqual("Xform", result)
        get_prim_type_icons.assert_called_once_with()

    async def test_prim_groups_item_icon_for_unknown_prim_type_returns_xform(self):
        """Return the Xform icon when the prim type is unknown."""
        # Arrange
        model = PrimGroupsModel()
        with mock.patch.object(
            prim_groups,
            "_get_prim_type_icons",
            return_value={"Mesh": "MeshIcon"},
        ) as get_prim_type_icons:
            item = model._build_item("Scope", _make_prim("/Scope", "Scope"))
            item.path = "/Scope"

            # Act
            result = item.icon
        self.addCleanup(item.destroy)

        # Assert
        self.assertEqual("Xform", result)
        get_prim_type_icons.assert_called_once_with()

    async def test_prim_groups_item_icon_with_empty_map_raises_attribute_error(self):
        """Raise AttributeError when the prim type icon map is empty."""
        # Arrange
        model = PrimGroupsModel()
        item = model._build_item("Cube", _make_prim("/Cube", "Mesh"))
        item.path = "/Cube"
        self.addCleanup(item.destroy)

        # Act
        with (
            mock.patch.object(prim_groups, "_get_prim_type_icons", return_value={}) as get_prim_type_icons,
            self.assertRaisesRegex(AttributeError, "No icons available"),
        ):
            _ = item.icon

        # Assert
        get_prim_type_icons.assert_called_once_with()

    async def test_light_groups_should_build_from_worker_data(self):
        """Build light groups from prepared worker data and cached names."""
        # Arrange
        model = LightGroupsModel()
        items = [
            StageManagerItem("/KeyLight", data=_make_prim("/KeyLight", "SphereLight")),
            StageManagerItem("/World/KeyLight", data=_make_prim("/World/KeyLight", "SphereLight")),
        ]
        items[0].prepare_display_name(("KeyLight", "/"))
        items[1].prepare_display_name(("KeyLight", "World"))

        # Act
        root_items = _build(model, items)

        # Assert
        self.assertEqual(["Sphere Lights"], [item.display_name for item in root_items])
        self.assertEqual(["KeyLight", "KeyLight"], [item.display_name for item in root_items[0].children])
        self.assertEqual(["/", "World"], [item.display_name_ancestor for item in root_items[0].children])

    async def test_build_items_with_unsupported_light_type_skips_candidate(self):
        """Skip a stale light candidate whose live type is no longer groupable."""
        # Arrange
        model = LightGroupsModel()
        valid_item = StageManagerItem("/KeyLight", data=_make_prim("/KeyLight", "SphereLight"))
        stale_item = StageManagerItem("/StaleLight", data=_make_prim("/StaleLight", "Capsule"))
        valid_item.prepare_display_name(("KeyLight", None))
        stale_item.prepare_display_name(("StaleLight", None))

        # Act
        with mock.patch.object(
            light_groups,
            "_get_light_type",
            side_effect=(LightTypes.SphereLight, None),
        ):
            root_items = _build(model, [valid_item, stale_item])

        # Assert
        self.assertEqual(["Sphere Lights"], [item.display_name for item in root_items])
        self.assertEqual(["KeyLight"], [item.display_name for item in root_items[0].children])
        stale_item.data.GetPath.assert_not_called()

    async def test_material_groups_should_build_from_worker_data(self):
        """Build material groups from cached bindings while preserving empty groups."""
        # Arrange
        model = MaterialGroupsModel()
        root_material_prim = _make_prim("/Mat", "Material")
        empty_material_prim = _make_prim("/Empty", "Material")
        material_prim = _make_prim("/World/Mat", "Material")
        mesh_prim = _make_prim("/World/Cube", "Mesh")
        root_material_prim.IsA.side_effect = lambda schema: schema is UsdShade.Material
        empty_material_prim.IsA.side_effect = lambda schema: schema is UsdShade.Material
        material_prim.IsA.side_effect = lambda schema: schema is UsdShade.Material
        mesh_prim.IsA.side_effect = lambda schema: schema is UsdGeom.Mesh
        mesh_item = StageManagerItem("/World/Cube", data=mesh_prim)
        mesh_item.prepare_group_memberships(
            (
                "/Mat",
                "/World/Mat",
                "/World/Mat",
                "/Missing/Material",
            )
        )
        items = [
            StageManagerItem("/Mat", data=root_material_prim),
            StageManagerItem("/Empty", data=empty_material_prim),
            StageManagerItem("/World/Mat", data=material_prim),
            mesh_item,
        ]

        # Act
        root_items = _build(model, items)

        # Assert
        self.assertEqual(["Empty", "Mat", "Mat"], [item.display_name for item in root_items])
        self.assertEqual(["/Empty", "/Mat", "/World/Mat"], [item.path for item in root_items])
        self.assertEqual([], root_items[0].children)
        self.assertEqual(["Cube"], [item.display_name for item in root_items[1].children])
        self.assertEqual(["Cube"], [item.display_name for item in root_items[2].children])
        self.assertIsNot(root_items[1].children[0], root_items[2].children[0])
        self.assertEqual(["World"], [item.display_name_ancestor for item in root_items[2].children])

    async def test_build_items_with_stale_material_candidate_skips_only_stale_item(self):
        """Keep valid material rows when a stale candidate no longer matches."""
        # Arrange
        model = MaterialGroupsModel()
        material_prim = _make_prim("/World/Material", "Material")
        material_prim.IsA.side_effect = lambda schema: schema is UsdShade.Material
        stale_prim = _make_prim("/World/Stale", "Xform")
        stale_prim.IsA.return_value = False
        items = [
            StageManagerItem("/World/Material", data=material_prim),
            StageManagerItem("/World/Stale", data=stale_prim),
        ]

        # Act
        root_items = _build(model, items)

        # Assert
        self.assertEqual(["Material"], [item.display_name for item in root_items])
        self.assertEqual(["/World/Material"], [item.path for item in root_items])
        self.assertEqual([], root_items[0].children)
        stale_prim.GetPath.assert_not_called()

    async def test_custom_tag_groups_should_build_from_worker_data(self):
        """Build populated and empty custom-tag groups from prepared worker data."""
        # Arrange
        model = CustomTagGroupsModel()
        items = [
            StageManagerItem("/Cube", data=_make_prim("/Cube", "Mesh")),
            StageManagerItem("/World/Cube", data=_make_prim("/World/Cube", "Mesh")),
            StageManagerItem("/World/Missing", data=_make_prim("/World/Missing", "Mesh")),
        ]
        items[0].prepare_group_memberships(("/Tags/Car", "/Tags/Red", "/Tags/Red"))
        items[1].prepare_group_memberships(("/Tags/Red",))
        items[2].prepare_group_memberships(("/Tags/Missing",))
        items[0].prepare_display_name(("Cube", "/"))
        items[1].prepare_display_name(("Cube", "World"))
        items[2].prepare_display_name(("Missing", None))

        class _FakeCustomTagsCore:
            """Provide tag definitions without querying tag memberships."""

            destroyed = False
            get_tag_prims_calls = 0

            def __init__(self, context_name=""):
                """Accept the context expected by the production model."""
                pass

            def get_all_tags(self):
                """Return populated and empty tag definitions."""
                return [Sdf.Path("/Tags/Red"), Sdf.Path("/Tags/Car"), Sdf.Path("/Tags/Empty")]

            def get_tag_name(self, tag_path):
                """Return the tag path's display name."""
                return tag_path.name

            def get_tag_prims(self, _tag_path):
                """Record an unexpected target-membership query."""
                type(self).get_tag_prims_calls += 1
                return []

            def destroy(self):
                """Record resource cleanup."""
                type(self).destroyed = True

        with mock.patch.object(custom_tag_groups, "_CustomTagsCore", new=_FakeCustomTagsCore):
            # Act
            root_items = _build(model, items)

        # Assert
        self.assertEqual(["Car", "Empty", "Red"], [item.display_name for item in root_items])
        self.assertEqual("/Tags/Car", root_items[0].path)
        self.assertEqual(["Cube"], [item.display_name for item in root_items[0].children])
        self.assertEqual(["/"], [item.display_name_ancestor for item in root_items[0].children])
        self.assertEqual([], root_items[1].children)
        self.assertEqual(["Cube", "Cube"], [item.display_name for item in root_items[2].children])
        self.assertEqual(["/", "World"], [item.display_name_ancestor for item in root_items[2].children])
        self.assertEqual(0, _FakeCustomTagsCore.get_tag_prims_calls)
        self.assertTrue(_FakeCustomTagsCore.destroyed)

    async def test_skeleton_groups_should_build_from_worker_data(self):
        """Build skeleton and joint hierarchy from worker data."""
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
            """Expose the prepared joint attribute for the skeleton prim."""

            def __init__(self, _prim):
                """Bind the prepared joints attribute."""
                self.GetJointsAttr = mock.Mock(return_value=joints_attr)

        with mock.patch.object(skeleton_groups.UsdSkel, "Skeleton", new=_FakeSkeleton):
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
        """Keep display-name disambiguation local to concurrent skeleton builds."""
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
            """Synchronize both builds before computing unique names."""
            barrier.wait(timeout=2)
            return original_get_unique_names(items)

        # Act
        with mock.patch.object(
            skeleton_groups._StageManagerUtils,
            "get_unique_names",
            get_unique_names_after_both_builds_start,
        ):
            result_a, result_b = await asyncio.gather(
                asyncio.to_thread(model._build_items, items_a, threading.Event()),
                asyncio.to_thread(model._build_items, items_b, threading.Event()),
            )

        # Assert
        self.assertEqual({"/", "A"}, {item.display_name_ancestor for item in result_a})
        self.assertEqual({"/", "B"}, {item.display_name_ancestor for item in result_b})
