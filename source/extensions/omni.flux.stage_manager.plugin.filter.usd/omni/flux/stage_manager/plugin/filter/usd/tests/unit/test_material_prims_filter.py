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

from unittest import mock

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from pxr import Sdf, UsdGeom, UsdShade

from ... import material_prims
from ...material_prims import MaterialBindingsFilterPlugin, MaterialPrimsFilterPlugin

__all__ = ["TestMaterialBindingsFilterPlugin", "TestMaterialPrimsFilterPlugin"]


def _make_prim(path: str, schema):
    """Create a prim mock that reports one schema and path."""
    prim = mock.Mock()
    prim.GetPath.return_value = Sdf.Path(path)
    prim.IsA.side_effect = lambda candidate: candidate is schema
    return prim


def _make_material(path: str):
    """Create a material mock with the supplied prim path."""
    material = mock.Mock()
    material.GetPrim.return_value.GetPath.return_value = Sdf.Path(path)
    return material


class TestMaterialPrimsFilterPlugin(omni.kit.test.AsyncTestCase):
    """Tests Material Prims filtering."""

    async def test_filter_predicate_with_material_mesh_or_unrelated_prim_matches_configured_domain(self):
        """Retain materials and configured meshes without resolving bindings."""
        cases = (
            ("material", UsdShade.Material, True, True),
            ("mesh", UsdGeom.Mesh, True, True),
            ("mesh_excluded", UsdGeom.Mesh, False, False),
            ("unrelated", UsdGeom.Xform, True, False),
        )

        for title, schema, include_meshes, expected_result in cases:
            with self.subTest(title=title):
                # Arrange
                plugin = MaterialPrimsFilterPlugin(include_meshes=include_meshes)
                item = StageManagerItem(f"/World/{title}", data=_make_prim(f"/World/{title}", schema))
                predicate = plugin.build_filter_predicate()

                with mock.patch.object(material_prims, "get_materials_from_prim_paths") as get_materials:
                    # Act
                    result = predicate(item)

                # Assert
                self.assertEqual(expected_result, result)
                get_materials.assert_not_called()
                with self.assertRaises(RuntimeError):
                    _ = item.prepared_group_memberships


class TestMaterialBindingsFilterPlugin(omni.kit.test.AsyncTestCase):
    """Tests internal material-binding preparation."""

    async def test_filter_predicate_with_bound_mesh_prepares_ordered_duplicate_memberships_once(self):
        """Retain a bound mesh and preserve its ordered duplicate material paths."""
        # Arrange
        plugin = MaterialBindingsFilterPlugin()
        plugin.set_context_name("ingestcraft")
        item = StageManagerItem("/World/Mesh", data=_make_prim("/World/Mesh", UsdGeom.Mesh))
        materials = [_make_material("/Materials/B"), _make_material("/Materials/A"), _make_material("/Materials/B")]

        with mock.patch.object(
            material_prims, "get_materials_from_prim_paths", return_value=materials
        ) as get_materials:
            predicate = plugin.build_filter_predicate(mock.Mock())

            # Act
            result = predicate(item)

        # Assert
        self.assertTrue(result)
        get_materials.assert_called_once_with([Sdf.Path("/World/Mesh")], context_name="ingestcraft")
        self.assertEqual(("/Materials/B", "/Materials/A", "/Materials/B"), item.prepared_group_memberships)

    async def test_filter_predicate_with_material_unbound_mesh_or_unrelated_prim_matches_bound_domain(self):
        """Retain materials and bound meshes while rejecting other candidates."""
        cases = (
            ("material", UsdShade.Material, [], True, False),
            ("unbound_mesh", UsdGeom.Mesh, [], False, True),
            ("unrelated", UsdGeom.Xform, [], False, False),
        )

        for title, schema, materials, expected_result, expects_binding_query in cases:
            with self.subTest(title=title):
                # Arrange
                plugin = MaterialBindingsFilterPlugin()
                item = StageManagerItem(f"/World/{title}", data=_make_prim(f"/World/{title}", schema))

                with mock.patch.object(
                    material_prims, "get_materials_from_prim_paths", return_value=materials
                ) as get_materials:
                    # Act
                    result = plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected_result, result)
                if expects_binding_query:
                    get_materials.assert_called_once_with([Sdf.Path(f"/World/{title}")], context_name="")
                else:
                    get_materials.assert_not_called()
                with self.assertRaises(RuntimeError):
                    _ = item.prepared_group_memberships
