"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from lightspeed.trex.utils.common.prim_utils import (
    find_prim_with_references,
    get_prototype,
    has_replacement_ref_edits,
    is_ghost_prim,
    is_empty_mesh_prim,
)
from pxr import Sdf, Usd

_MODULE = "lightspeed.trex.utils.common.prim_utils"


class TestGetPrototype(omni.kit.test.AsyncTestCase):
    def setUp(self):
        self.stage = Usd.Stage.CreateInMemory()
        self.stage.DefinePrim("/RootNode", "Xform")
        self.stage.DefinePrim("/RootNode/meshes", "Xform")
        self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF", "Xform")
        self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft", "Mesh")

    def test_get_prototype_of_prim_within_instance_path_should_return_equivalent_prototype_prim(self):
        # Arrange
        self.stage.DefinePrim("/RootNode/instances", "Xform")
        inst_prim = self.stage.DefinePrim("/RootNode/instances/inst_0123456789ABCDEF_0", "Xform")

        # Act
        result = get_prototype(inst_prim)

        # Assert
        self.assertIsNotNone(result)
        prototype_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0123456789ABCDEF")
        self.assertEqual(result, prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF")

    def test_get_prototype_of_child_prim_within_instance_path_should_return_equivalent_prototype_child_prim(self):
        # Arrange
        self.stage.DefinePrim("/RootNode/instances", "Xform")
        self.stage.DefinePrim("/RootNode/instances/inst_0123456789ABCDEF_0", "Xform")
        child_prim = self.stage.DefinePrim("/RootNode/instances/inst_0123456789ABCDEF_0/hovercraft", "Xform")

        # Act
        result = get_prototype(child_prim)

        # Assert
        self.assertIsNotNone(result)
        expected_prototype_child = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")
        self.assertEqual(result, expected_prototype_child)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")

    def test_get_prototype_of_prototype_prim_should_return_itself_idempotent(self):
        # Arrange
        prototype_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0123456789ABCDEF")

        # Act
        result = get_prototype(prototype_prim)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result, prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF")

    def test_get_prototype_of_child_prim_within_prototype_path_should_return_itself_idempotent(self):
        # Arrange
        child_prototype_prim = self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft", "Xform")

        # Act
        result = get_prototype(child_prototype_prim)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result, child_prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")

    def test_get_prototype_of_invalid_prim_should_return_none(self):
        # Arrange
        invalid_prim = self.stage.GetPrimAtPath("/InvalidPath")

        # Act
        result = get_prototype(invalid_prim)

        # Assert
        self.assertIsNone(result)

    def test_get_prototype_of_non_matching_prim_should_return_itself(self):
        # Arrange
        non_matching_prim = self.stage.DefinePrim("/RootNode/SomeOtherPath", "Xform")

        # Act
        result = get_prototype(non_matching_prim)

        # Assert
        self.assertEqual(non_matching_prim, result)

    def test_get_prototype_of_inst_prim_without_prototype_equivalent_should_return_none(self):
        # Arrange
        self.stage.DefinePrim("/RootNode/instances", "Xform")
        inst_prim = self.stage.DefinePrim("/RootNode/instances/inst_DEADBEEF0BADC0DE_0", "Xform")

        # Act
        result = get_prototype(inst_prim)

        # Assert
        self.assertIsNone(result)


class TestIsGhostPrim(omni.kit.test.AsyncTestCase):
    async def test_non_instance_returns_false(self):
        # Arrange
        prim = Mock()

        # Act
        with patch(f"{_MODULE}.is_instance", return_value=False):
            result = is_ghost_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_instance_with_prototype_returns_false(self):
        # Arrange
        prim = Mock()

        # Act
        with (
            patch(f"{_MODULE}.is_instance", return_value=True),
            patch(f"{_MODULE}.get_prototype", return_value=Mock()),
        ):
            result = is_ghost_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_instance_without_prototype_valid_typeless_returns_true(self):
        # Arrange
        prim = Mock()
        prim.IsValid.return_value = True
        prim.GetTypeName.return_value = ""

        # Act
        with (
            patch(f"{_MODULE}.is_instance", return_value=True),
            patch(f"{_MODULE}.get_prototype", return_value=None),
        ):
            result = is_ghost_prim(prim)

        # Assert
        self.assertTrue(result)

    async def test_instance_without_prototype_but_typed_returns_false(self):
        # Arrange
        prim = Mock()
        prim.IsValid.return_value = True
        prim.GetTypeName.return_value = "Mesh"

        # Act
        with (
            patch(f"{_MODULE}.is_instance", return_value=True),
            patch(f"{_MODULE}.get_prototype", return_value=None),
        ):
            result = is_ghost_prim(prim)

        # Assert
        self.assertFalse(result)


class TestFindPrimWithReferences(omni.kit.test.AsyncTestCase):
    async def test_prim_with_direct_refs_returns_prim_and_refs(self):
        # Arrange
        prim = Mock()
        prim.IsValid.return_value = True
        prim.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")
        ref_items = [(prim, Mock(), Mock(), 0)]

        # Act
        with patch(f"{_MODULE}.get_reference_file_paths", return_value=(ref_items, 1)):
            result_prim, result_refs = find_prim_with_references(prim)

        # Assert
        self.assertIs(result_prim, prim)
        self.assertEqual(result_refs, ref_items)

    async def test_instance_prim_falls_back_to_prototype(self):
        # Arrange
        prim = Mock()
        prim.IsValid.return_value = True
        prim.GetPath.return_value = Sdf.Path("/RootNode/instances/inst_ABC_0")

        proto = Mock()
        ref_items = [(proto, Mock(), Mock(), 0)]

        # Act
        with (
            patch(f"{_MODULE}.get_reference_file_paths", side_effect=[([], 0), (ref_items, 1)]),
            patch(f"{_MODULE}.get_prototype", return_value=proto),
        ):
            result_prim, result_refs = find_prim_with_references(prim)

        # Assert
        self.assertIs(result_prim, proto)
        self.assertEqual(result_refs, ref_items)

    async def test_walks_parent_when_no_refs_found(self):
        # Arrange
        parent = Mock()
        parent.IsValid.return_value = True
        parent.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")

        child = Mock()
        child.IsValid.return_value = True
        child.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC/child")
        child.GetParent.return_value = parent

        ref_items = [(parent, Mock(), Mock(), 0)]

        # Act
        with (
            patch(
                f"{_MODULE}.get_reference_file_paths",
                side_effect=[([], 0), (ref_items, 1)],
            ),
            patch(f"{_MODULE}.get_prototype", return_value=None),
        ):
            result_prim, result_refs = find_prim_with_references(child)

        # Assert
        self.assertIs(result_prim, parent)
        self.assertEqual(result_refs, ref_items)

    async def test_returns_original_prim_and_empty_list_when_none_found(self):
        # Arrange
        root = Mock()
        root.IsValid.return_value = True
        root.GetPath.return_value = Sdf.Path("/")

        prim = Mock()
        prim.IsValid.return_value = True
        prim.GetPath.return_value = Sdf.Path("/RootNode")
        prim.GetParent.return_value = root

        # Act
        with (
            patch(f"{_MODULE}.get_reference_file_paths", return_value=([], 0)),
            patch(f"{_MODULE}.get_prototype", return_value=None),
        ):
            result_prim, result_refs = find_prim_with_references(prim)

        # Assert
        self.assertIs(result_prim, prim)
        self.assertEqual(result_refs, [])

    async def test_none_prim_returns_none_and_empty_list(self):
        # Arrange / Act
        result_prim, result_refs = find_prim_with_references(None)

        # Assert
        self.assertIsNone(result_prim)
        self.assertEqual(result_refs, [])


class TestHasReplacementRefEdits(omni.kit.test.AsyncTestCase):
    async def test_returns_true_when_layer_has_explicit_ref_list(self):
        # Arrange
        prim = Mock()
        prim.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")

        layer = Mock()
        prim_spec = Mock()
        ref_list = Mock()
        ref_list.isExplicit = True
        ref_list.addedItems = []
        ref_list.deletedItems = []
        ref_list.prependedItems = []
        ref_list.appendedItems = []
        prim_spec.referenceList = ref_list
        layer.GetPrimAtPath.return_value = prim_spec

        # Act
        with patch(f"{_MODULE}.get_prototype", return_value=None):
            result = has_replacement_ref_edits(prim, {layer})

        # Assert
        self.assertTrue(result)

    async def test_returns_false_when_no_ref_list_edits(self):
        # Arrange
        prim = Mock()
        prim.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")

        layer = Mock()
        prim_spec = Mock()
        ref_list = Mock()
        ref_list.isExplicit = False
        ref_list.addedItems = []
        ref_list.deletedItems = []
        ref_list.prependedItems = []
        ref_list.appendedItems = []
        prim_spec.referenceList = ref_list
        layer.GetPrimAtPath.return_value = prim_spec

        # Act
        with patch(f"{_MODULE}.get_prototype", return_value=None):
            result = has_replacement_ref_edits(prim, {layer})

        # Assert
        self.assertFalse(result)

    async def test_returns_false_when_no_prim_spec_in_layer(self):
        # Arrange
        prim = Mock()
        prim.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")

        layer = Mock()
        layer.GetPrimAtPath.return_value = None

        # Act
        with patch(f"{_MODULE}.get_prototype", return_value=None):
            result = has_replacement_ref_edits(prim, {layer})

        # Assert
        self.assertFalse(result)

    async def test_resolves_instance_to_prototype(self):
        # Arrange
        proto = Mock()
        proto.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")

        prim = Mock()
        prim.GetPath.return_value = Sdf.Path("/RootNode/instances/inst_ABC_0")

        layer = Mock()
        prim_spec = Mock()
        ref_list = Mock()
        ref_list.isExplicit = True
        ref_list.addedItems = []
        ref_list.deletedItems = []
        ref_list.prependedItems = []
        ref_list.appendedItems = []
        prim_spec.referenceList = ref_list
        layer.GetPrimAtPath.return_value = prim_spec

        # Act
        with patch(f"{_MODULE}.get_prototype", return_value=proto):
            result = has_replacement_ref_edits(prim, {layer})

        # Assert
        self.assertTrue(result)
        layer.GetPrimAtPath.assert_called_once_with(Sdf.Path("/RootNode/meshes/mesh_ABC"))

    async def test_returns_true_when_layer_has_deleted_items(self):
        # Arrange
        prim = Mock()
        prim.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")

        layer = Mock()
        prim_spec = Mock()
        ref_list = Mock()
        ref_list.isExplicit = False
        ref_list.addedItems = []
        ref_list.deletedItems = [Mock()]
        ref_list.prependedItems = []
        ref_list.appendedItems = []
        prim_spec.referenceList = ref_list
        layer.GetPrimAtPath.return_value = prim_spec

        # Act
        with patch(f"{_MODULE}.get_prototype", return_value=None):
            result = has_replacement_ref_edits(prim, {layer})

        # Assert
        self.assertTrue(result)

    async def test_returns_false_for_empty_layer_set(self):
        # Arrange
        prim = Mock()
        prim.GetPath.return_value = Sdf.Path("/RootNode/meshes/mesh_ABC")

        # Act
        with patch(f"{_MODULE}.get_prototype", return_value=None):
            result = has_replacement_ref_edits(prim, set())

        # Assert
        self.assertFalse(result)

    async def test_none_prim_returns_false(self):
        # Arrange / Act
        result = has_replacement_ref_edits(None, {Mock()})

        # Assert
        self.assertFalse(result)


class TestIsEmptyMeshPrim(omni.kit.test.AsyncTestCase):
    def setUp(self):
        self.stage = Usd.Stage.CreateInMemory()
        self.stage.DefinePrim("/RootNode", "Xform")
        self.stage.DefinePrim("/RootNode/meshes", "Xform")

    async def test_returns_false_for_none_prim(self):
        # Arrange / Act
        result = is_empty_mesh_prim(None)

        # Assert
        self.assertFalse(result)

    async def test_returns_true_for_mesh_hash_prim_with_no_mesh_children(self):
        # Arrange
        prim = self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF", "Xform")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertTrue(result)

    async def test_returns_false_for_mesh_hash_prim_with_mesh_child(self):
        # Arrange
        prim = self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF", "Xform")
        self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF/mesh", "Mesh")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_false_for_mesh_hash_prim_with_geom_subset_child(self):
        # Arrange
        prim = self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF", "Xform")
        self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF/subset", "GeomSubset")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_false_for_non_mesh_path(self):
        # Arrange
        prim = self.stage.DefinePrim("/RootNode/meshes", "Xform")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_false_for_instance_path(self):
        # Arrange
        prim = self.stage.DefinePrim("/RootNode/instances/inst_0123456789ABCDEF_0", "Xform")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_true_for_mesh_hash_with_only_non_mesh_children(self):
        # Arrange
        prim = self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF", "Xform")
        self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF/RemixLogicGraph", "OmniGraph")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertTrue(result)
