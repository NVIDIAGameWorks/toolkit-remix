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

from types import SimpleNamespace
from unittest.mock import Mock, patch

import omni.kit.test
from lightspeed.trex.utils.common.prim_utils import (
    find_prim_with_references,
    get_reference_file_paths,
    get_prototype,
    get_transferable_prim_specs,
    get_transferable_property_specs,
    get_transferable_reference_specs,
    has_replacement_ref_edits,
    is_ghost_prim,
    is_empty_mesh_prim,
)
from pxr import Sdf

_MODULE = "lightspeed.trex.utils.common.prim_utils"


class TestTransferableSpecs(omni.kit.test.AsyncTestCase):
    def _create_layer(self, display_name: str) -> Sdf.Layer:
        return Mock(identifier=display_name)

    def _create_property_spec(
        self, layer_identifier: str, property_path: str, specifier: Sdf.Specifier = Sdf.SpecifierOver
    ):
        layer = self._create_layer(layer_identifier)
        layer.GetPrimAtPath.return_value = Mock(specifier=specifier)
        return SimpleNamespace(layer=layer, path=Sdf.Path(property_path))

    def _create_prim_spec(
        self,
        layer_identifier: str,
        specifier: Sdf.Specifier = Sdf.SpecifierDef,
        has_particle_schema: bool = False,
        reference=None,
    ):
        api_schemas = Mock()
        api_schemas.HasItem.return_value = has_particle_schema
        references = Mock()
        references.HasItem.return_value = reference is not None
        prim_spec = Mock(
            layer=self._create_layer(layer_identifier),
            specifier=specifier,
            hasReferences=reference is not None,
        )
        prim_spec.HasInfo.return_value = has_particle_schema
        prim_spec.GetInfo.side_effect = lambda key: references if key == Sdf.PrimSpec.ReferencesKey else api_schemas
        return prim_spec

    def _create_prim(self, prim_specs):
        prim = Mock()
        prim.IsValid.return_value = True
        prim.GetPrimStack.return_value = prim_specs
        return prim

    def test_get_transferable_property_specs_should_return_valid_layer_property_specs(self):
        # Arrange
        property_specs = [
            self._create_property_spec("mod.usda", "/World/Test.visibility"),
            self._create_property_spec("overrides.usda", "/World/Test.visibility"),
            self._create_property_spec("capture.usda", "/World/Test.visibility"),
        ]

        # Act
        transferable_specs = get_transferable_property_specs(property_specs, {"mod.usda", "overrides.usda"})

        # Assert
        self.assertEqual(
            ["mod.usda", "overrides.usda"],
            [spec.layer.identifier for spec in transferable_specs],
        )

    def test_get_transferable_property_specs_should_prefer_override_specs_over_definition_specs(self):
        # Arrange
        definition_spec = self._create_property_spec(
            "mod.usda", "/World/Particle.primvars:particle:maxNumParticles", Sdf.SpecifierDef
        )
        override_spec = self._create_property_spec(
            "overrides.usda", "/World/Particle.primvars:particle:maxNumParticles"
        )

        # Act
        transferable_specs = get_transferable_property_specs(
            (override_spec, definition_spec), {"mod.usda", "overrides.usda"}
        )

        # Assert
        self.assertEqual(["overrides.usda"], [spec.layer.identifier for spec in transferable_specs])

    def test_get_transferable_property_specs_should_include_particle_property_on_definition_layer(self):
        # Arrange
        definition_layer_property_spec = self._create_property_spec(
            "mod.usda", "/World/Particle.primvars:particle:minSpawnColor"
        )
        override_property_spec = self._create_property_spec(
            "overrides.usda", "/World/Particle.primvars:particle:minSpawnColor"
        )

        # Act
        transferable_specs = get_transferable_property_specs(
            (definition_layer_property_spec, override_property_spec),
            {"mod.usda", "overrides.usda"},
        )

        # Assert
        self.assertEqual(
            ["mod.usda", "overrides.usda"],
            [spec.layer.identifier for spec in transferable_specs],
        )

    def test_get_transferable_prim_specs_should_return_valid_layer_definition_specs(self):
        # Arrange
        prim_specs = [
            self._create_prim_spec("mod.usda"),
            self._create_prim_spec("overrides.usda"),
            self._create_prim_spec("capture.usda"),
        ]
        prim = self._create_prim(prim_specs)

        # Act
        transferable_specs = get_transferable_prim_specs(prim, {"mod.usda", "overrides.usda"})

        # Assert
        self.assertEqual(
            ["mod.usda", "overrides.usda"],
            [spec.layer.identifier for spec in transferable_specs],
        )

    def test_get_transferable_prim_specs_should_exclude_property_override_specs(self):
        # Arrange
        definition_spec = self._create_prim_spec("mod.usda")
        override_spec = self._create_prim_spec("overrides.usda", Sdf.SpecifierOver)
        prim = self._create_prim([definition_spec, override_spec])

        # Act
        transferable_specs = get_transferable_prim_specs(prim, {"mod.usda", "overrides.usda"})

        # Assert
        self.assertEqual(["mod.usda"], [spec.layer.identifier for spec in transferable_specs])

    def test_get_transferable_prim_specs_should_include_particle_api_definition_specs(self):
        # Arrange
        definition_spec = self._create_prim_spec("mod.usda", Sdf.SpecifierOver, has_particle_schema=True)
        override_spec = self._create_prim_spec("overrides.usda", Sdf.SpecifierOver)
        prim = self._create_prim([definition_spec, override_spec])

        # Act
        transferable_specs = get_transferable_prim_specs(prim, {"mod.usda", "overrides.usda"})

        # Assert
        self.assertEqual(["mod.usda"], [spec.layer.identifier for spec in transferable_specs])

    def test_get_transferable_prim_specs_should_include_particle_api_authored_as_prepended_schema(self):
        # Arrange
        definition_spec = self._create_prim_spec("mod.usda", Sdf.SpecifierOver, has_particle_schema=True)
        prim = self._create_prim([definition_spec])

        # Act
        transferable_specs = get_transferable_prim_specs(prim, {"mod.usda"})

        # Assert
        self.assertEqual(["mod.usda"], [spec.layer.identifier for spec in transferable_specs])

    def test_get_transferable_prim_specs_should_require_particle_api_schema_on_over_specs(self):
        # Arrange
        prim_spec = self._create_prim_spec("mod.usda", Sdf.SpecifierOver)
        prim = self._create_prim([prim_spec])

        # Act
        transferable_specs = get_transferable_prim_specs(prim, {"mod.usda"})

        # Assert
        self.assertEqual([], [spec.layer.identifier for spec in transferable_specs])

    def test_get_transferable_reference_specs_should_return_matching_valid_layer_specs(self):
        # Arrange
        reference = Sdf.Reference("", Sdf.Path("/Asset"))
        prim_specs = [
            self._create_prim_spec("mod.usda", reference=reference),
            self._create_prim_spec("overrides.usda", reference=reference),
            self._create_prim_spec("capture.usda", reference=reference),
        ]
        prim = self._create_prim(prim_specs)

        # Act
        transferable_specs = get_transferable_reference_specs(prim, reference, {"mod.usda", "overrides.usda"})

        # Assert
        self.assertEqual(
            ["mod.usda", "overrides.usda"],
            [spec.layer.identifier for spec in transferable_specs],
        )


class TestGetPrototype(omni.kit.test.AsyncTestCase):
    def _create_prim(self, path: str, is_valid: bool = True, stage=None):
        prim = Mock()
        prim.IsValid.return_value = is_valid
        prim.GetPath.return_value = Sdf.Path(path)
        prim.GetStage.return_value = stage
        return prim

    def test_get_prototype_of_prim_within_instance_path_should_return_equivalent_prototype_prim(self):
        # Arrange
        prototype_prim = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF")
        stage = Mock()
        stage.GetPrimAtPath.return_value = prototype_prim
        inst_prim = self._create_prim("/RootNode/instances/inst_0123456789ABCDEF_0", stage=stage)

        # Act
        result = get_prototype(inst_prim)

        # Assert
        self.assertEqual(result, prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF")

    def test_get_prototype_of_child_prim_within_instance_path_should_return_equivalent_prototype_child_prim(self):
        # Arrange
        expected_prototype_child = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")
        stage = Mock()
        stage.GetPrimAtPath.return_value = expected_prototype_child
        child_prim = self._create_prim("/RootNode/instances/inst_0123456789ABCDEF_0/hovercraft", stage=stage)

        # Act
        result = get_prototype(child_prim)

        # Assert
        self.assertEqual(result, expected_prototype_child)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")

    def test_get_prototype_of_prototype_prim_should_return_itself_idempotent(self):
        # Arrange
        prototype_prim = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF")

        # Act
        with patch(f"{_MODULE}.is_a_prototype", return_value=True):
            result = get_prototype(prototype_prim)

        # Assert
        self.assertEqual(result, prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF")

    def test_get_prototype_of_child_prim_within_prototype_path_should_return_itself_idempotent(self):
        # Arrange
        child_prototype_prim = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")

        # Act
        with patch(f"{_MODULE}.is_a_prototype", return_value=True):
            result = get_prototype(child_prototype_prim)

        # Assert
        self.assertEqual(result, child_prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")

    def test_get_prototype_of_invalid_prim_should_return_none(self):
        # Arrange
        invalid_prim = self._create_prim("/InvalidPath", is_valid=False)

        # Act
        result = get_prototype(invalid_prim)

        # Assert
        self.assertIsNone(result)

    def test_get_prototype_of_non_matching_prim_should_return_itself(self):
        # Arrange
        stage = Mock()
        non_matching_prim = self._create_prim("/RootNode/SomeOtherPath", stage=stage)
        stage.GetPrimAtPath.return_value = non_matching_prim

        # Act
        result = get_prototype(non_matching_prim)

        # Assert
        self.assertEqual(non_matching_prim, result)

    def test_get_prototype_of_inst_prim_without_prototype_equivalent_should_return_none(self):
        # Arrange
        stage = Mock()
        stage.GetPrimAtPath.return_value = self._create_prim("/RootNode/meshes/mesh_DEADBEEF0BADC0DE", is_valid=False)
        inst_prim = self._create_prim("/RootNode/instances/inst_DEADBEEF0BADC0DE_0", stage=stage)

        # Act
        result = get_prototype(inst_prim)

        # Assert
        self.assertIsNone(result)


class TestGetReferenceFilePaths(omni.kit.test.AsyncTestCase):
    def test_get_reference_file_paths_returns_composed_references_only(self):
        # Arrange
        prim = Mock()
        prim.GetFilteredChildren.return_value = []
        composed_layer = Mock(identifier="capture.usda")
        composed_ref = SimpleNamespace(assetPath="./capture.usda")

        # Act
        with patch(
            f"{_MODULE}.omni.usd.get_composed_references_from_prim", return_value=[(composed_ref, composed_layer)]
        ):
            result, count = get_reference_file_paths(prim)

        # Assert
        self.assertEqual(count, 1)
        self.assertEqual(
            [(ref.assetPath, layer.identifier, index) for _prim, ref, layer, index in result],
            [
                ("./capture.usda", composed_layer.identifier, 0),
            ],
        )

    def test_get_reference_file_paths_keeps_references_with_different_offsets_and_custom_data(self):
        # Arrange
        prim = Mock()
        prim.GetFilteredChildren.return_value = []
        authored_layer = Mock(identifier="replacement.usda")
        first_ref = SimpleNamespace(
            assetPath="./replacement.usda",
            layerOffset=SimpleNamespace(offset=1.0, scale=1.0),
            customData={"variant": "first"},
        )
        second_ref = SimpleNamespace(
            assetPath="./replacement.usda",
            layerOffset=SimpleNamespace(offset=2.0, scale=1.0),
            customData={"variant": "second"},
        )

        # Act
        with patch(
            f"{_MODULE}.omni.usd.get_composed_references_from_prim",
            return_value=[(first_ref, authored_layer), (second_ref, authored_layer)],
        ):
            result, count = get_reference_file_paths(prim)

        # Assert
        self.assertEqual(count, 2)
        self.assertEqual(
            [
                (ref.layerOffset.offset, ref.customData["variant"], layer.identifier, index)
                for _prim, ref, layer, index in result
            ],
            [
                (1.0, "first", authored_layer.identifier, 0),
                (2.0, "second", authored_layer.identifier, 1),
            ],
        )


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
    def _create_prim(self, path: str, children: list[Mock] | None = None):
        prim = Mock()
        prim.GetPath.return_value = Sdf.Path(path)
        prim.GetChildren.return_value = children or []
        return prim

    async def test_returns_false_for_none_prim(self):
        # Arrange / Act
        result = is_empty_mesh_prim(None)

        # Assert
        self.assertFalse(result)

    async def test_returns_true_for_mesh_hash_prim_with_no_mesh_children(self):
        # Arrange
        prim = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertTrue(result)

    async def test_returns_false_for_mesh_hash_prim_with_mesh_child(self):
        # Arrange
        mesh_child = Mock()
        mesh_child.IsA.return_value = True
        prim = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF", [mesh_child])

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_false_for_mesh_hash_prim_with_geom_subset_child(self):
        # Arrange
        subset_child = Mock()
        subset_child.IsA.side_effect = [False, True]
        prim = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF", [subset_child])

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_false_for_non_mesh_path(self):
        # Arrange
        prim = self._create_prim("/RootNode/meshes")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_false_for_instance_path(self):
        # Arrange
        prim = self._create_prim("/RootNode/instances/inst_0123456789ABCDEF_0")

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertFalse(result)

    async def test_returns_true_for_mesh_hash_with_only_non_mesh_children(self):
        # Arrange
        logic_child = Mock()
        logic_child.IsA.return_value = False
        prim = self._create_prim("/RootNode/meshes/mesh_0123456789ABCDEF", [logic_child])

        # Act
        result = is_empty_mesh_prim(prim)

        # Assert
        self.assertTrue(result)
