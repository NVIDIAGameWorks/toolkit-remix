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

from ... import mesh_groups
from ...mesh_groups import MeshGroupsModel

__all__ = ["TestMeshGroupsModel"]


def _make_prim(path: str, type_name: str):
    """Create a valid prim mock with the supplied path and type name."""
    prim = mock.Mock()
    prim.GetPath.return_value = Sdf.Path(path)
    prim.GetTypeName.return_value = type_name
    prim.IsValid.return_value = True
    return prim


def _build(model: MeshGroupsModel, items: list[StageManagerItem]):
    """Build mesh tree items with a non-cancelled worker event."""
    return model._build_items(items, threading.Event())


class TestMeshGroupsModel(AsyncTestCase):
    """Tests mesh grouped-tree construction from prepared context data."""

    async def test_build_items_with_cancelled_refresh_returns_without_work(self):
        """Return without building mesh groups when the refresh is cancelled."""
        # Arrange
        cancel_event = threading.Event()
        cancel_event.set()

        # Act
        result = MeshGroupsModel()._build_items([], cancel_event)

        # Assert
        self.assertIsNone(result)

    async def test_requires_context_ancestors_with_mesh_groups_model_returns_false(self):
        """Request sparse candidates because mesh groups use prepared item data."""
        # Arrange
        model = MeshGroupsModel()

        # Act
        result = model.requires_context_ancestors

        # Assert
        self.assertFalse(result)

    async def test_build_items_with_duplicate_root_and_nested_names_keeps_both_paths(self):
        """Build distinct mesh groups for duplicate names on separate paths."""
        # Arrange
        model = MeshGroupsModel()
        items = [
            StageManagerItem("/Mesh", data=_make_prim("/Mesh", "Mesh")),
            StageManagerItem("/World/Mesh", data=_make_prim("/World/Mesh", "Mesh")),
        ]

        # Act
        with (
            mock.patch.object(mesh_groups, "_is_mesh_prototype", return_value=False),
            mock.patch.object(mesh_groups, "_is_instance", return_value=False),
            mock.patch.object(mesh_groups, "_is_empty_mesh_prim", return_value=True),
        ):
            root_items = _build(model, items)

        # Assert
        self.assertEqual(["Mesh", "Mesh"], [item.display_name for item in root_items])
        self.assertEqual(["/Mesh", "/World/Mesh"], [item.path for item in root_items])

    async def test_build_items_with_worker_data_creates_mesh_and_instance_groups(self):
        """Build mesh and instance groups from worker-provided candidates."""
        # Arrange
        model = MeshGroupsModel()
        mesh_prim = _make_prim("/RootNode/meshes/mesh_0AB745B8BEE1F16B", "Mesh")
        instance_prim = _make_prim("/RootNode/instances/inst_0AB745B8BEE1F16B_0", "Xform")
        items = [
            StageManagerItem("/RootNode/meshes/mesh_0AB745B8BEE1F16B", data=mesh_prim),
            StageManagerItem("/RootNode/instances/inst_0AB745B8BEE1F16B_0", data=instance_prim),
        ]

        # Act
        with (
            mock.patch.object(mesh_groups, "_is_mesh_prototype", side_effect=lambda prim: prim is mesh_prim),
            mock.patch.object(mesh_groups, "_is_instance", side_effect=lambda prim: prim is instance_prim),
            mock.patch.object(mesh_groups, "_is_empty_mesh_prim", return_value=False),
        ):
            root_items = _build(model, items)

        # Assert
        self.assertEqual(["mesh_0AB745B8BEE1F16B"], [item.display_name for item in root_items])
        self.assertEqual(["inst_0AB745B8BEE1F16B_0"], [item.display_name for item in root_items[0].children])
