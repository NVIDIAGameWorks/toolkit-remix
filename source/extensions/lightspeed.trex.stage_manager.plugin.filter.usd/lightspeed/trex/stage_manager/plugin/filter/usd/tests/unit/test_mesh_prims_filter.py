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

from unittest.mock import MagicMock

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from pxr import Usd, UsdGeom

from ...mesh_prims import MeshPrimsFilterPlugin

__all__ = ["TestMeshPrimsFilterUnit"]

_HASH = "0123456789ABCDEF"
_SECOND_HASH = "FEDCBA9876543210"


class TestMeshPrimsFilterUnit(omni.kit.test.AsyncTestCase):
    """Tests Mesh filter predicates against their documented contract."""

    async def test_filter_predicate_with_representative_prims_matches_documented_contract(self):
        """Match representative USD prims against the documented filter contract."""
        cases = [
            ("mesh_child", "mesh_child", {}, True),
            ("geom_subset", "geom_subset", {}, True),
            ("empty_mesh_root", "empty_mesh_root", {}, True),
            ("nonempty_mesh_root", "mesh_root", {}, False),
            ("instance", "instance", {}, True),
            ("light_group", "light_group", {}, False),
            ("unrelated", "unrelated", {}, False),
            ("nested_instance", "nested_instance", {}, True),
            ("nested_instance_without_instances", "nested_instance", {"include_instances": False}, False),
            ("exclude_matching_instance", "instance", {"include_results": False}, False),
            ("exclude_unrelated_prim", "unrelated", {"include_results": False}, True),
            ("inactive_filter", "unrelated", {"filter_active": False}, True),
        ]

        for title, prim_kind, plugin_kwargs, expected in cases:
            with self.subTest(title=title):
                # Arrange
                stage = Usd.Stage.CreateInMemory()
                mesh_root = UsdGeom.Xform.Define(stage, f"/Root/mesh_{_HASH}").GetPrim()
                mesh_child = UsdGeom.Mesh.Define(stage, f"{mesh_root.GetPath()}/Mesh").GetPrim()
                geom_subset = UsdGeom.Subset.Define(stage, f"{mesh_root.GetPath()}/Subset").GetPrim()
                empty_mesh_root = UsdGeom.Xform.Define(stage, f"/Root/mesh_{_SECOND_HASH}").GetPrim()
                instance = UsdGeom.Xform.Define(stage, f"/Root/inst_{_HASH}/Descendant").GetPrim()
                light_group = UsdGeom.Xform.Define(stage, f"/Root/light_{_HASH}/Descendant").GetPrim()
                unrelated = UsdGeom.Xform.Define(stage, "/Root/Unrelated").GetPrim()
                nested_instance = UsdGeom.Xform.Define(
                    stage, f"/Root/mesh_{_HASH}/inst_{_SECOND_HASH}/Descendant"
                ).GetPrim()
                prims = {
                    "mesh_child": mesh_child,
                    "geom_subset": geom_subset,
                    "empty_mesh_root": empty_mesh_root,
                    "mesh_root": mesh_root,
                    "instance": instance,
                    "light_group": light_group,
                    "unrelated": unrelated,
                    "nested_instance": nested_instance,
                }
                prim = prims[prim_kind]
                item = StageManagerItem(prim.GetPath(), data=prim)
                plugin = MeshPrimsFilterPlugin(**plugin_kwargs)

                # Act
                result = plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected, result)

    async def test_filter_predicate_reads_path_once_for_valid_prim_and_never_for_invalid_prim(self):
        """Read a valid prim path exactly once and skip invalid prim path access."""
        cases = [
            ("valid", True, True, 1),
            ("invalid", False, False, 0),
        ]

        for title, is_valid, expected, expected_path_calls in cases:
            with self.subTest(title=title):
                # Arrange
                if is_valid:
                    stage = Usd.Stage.CreateInMemory()
                    prim = UsdGeom.Xform.Define(stage, f"/Root/mesh_{_HASH}").GetPrim()
                else:
                    prim = Usd.Prim()
                prim_spy = MagicMock(wraps=prim)
                prim_spy.__bool__.return_value = bool(prim)
                item = StageManagerItem(title, data=prim_spy)
                plugin = MeshPrimsFilterPlugin()

                # Act
                result = plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected, result)
                self.assertEqual(expected_path_calls, prim_spy.GetPath.call_count)
