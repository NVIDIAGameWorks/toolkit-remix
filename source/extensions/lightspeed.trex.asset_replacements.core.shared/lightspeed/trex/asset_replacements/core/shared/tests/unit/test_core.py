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

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.asset_replacements.core.shared import usd_copier as _usd_copier
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from pxr import Sdf, Usd, UsdGeom


class TestAssetReplacementsCore(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await open_stage(_get_test_data("usd/project_example/combined.usda"))
        self.context = omni.usd.get_context()

    # After running each test
    async def tearDown(self):
        self.stage = None

    async def test_filter_transformable(self):
        # setup
        core = _AssetReplacementsCore("")

        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/lights")]), [])
        self.assertEqual(
            core.filter_transformable_prims([Sdf.Path("/RootNode/lights/light_9907D0B07D040077")]),
            ["/RootNode/lights/light_9907D0B07D040077"],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [
                    Sdf.Path("/RootNode"),
                    Sdf.Path("/RootNode/lights/light_9907D0B07D040077"),
                ]
            ),
            ["/RootNode/lights/light_9907D0B07D040077"],
        )

        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/meshes")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A/mesh")]), [])

        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da")]
            ),
            [],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube")]
            ),
            [],
        )

        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/instances")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0")]), [])
        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da")]
            ),
            ["/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da"],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [
                    Sdf.Path(
                        "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"
                    )
                ]
            ),
            ["/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [
                    Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0"),
                    Sdf.Path(
                        "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"
                    ),
                ]
            ),
            ["/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"],
        )

    async def test_filter_transformable_stage_light(self):
        core = _AssetReplacementsCore("")
        # create random light under light
        omni.kit.commands.execute(
            "CreatePrim",
            prim_type="CylinderLight",
            prim_path="/RootNode/lights/light_9907D0B07D040077/Cylinder01",
            select_new_prim=False,
        )
        # create random light under mesh
        omni.kit.commands.execute(
            "CreatePrim",
            prim_type="CylinderLight",
            prim_path="/RootNode/meshes/mesh_BAC90CAA733B0859/Cylinder02",
            select_new_prim=False,
        )
        # create random light under instance
        omni.kit.commands.execute(
            "CreatePrim",
            prim_type="CylinderLight",
            prim_path="/RootNode/instances/inst_BAC90CAA733B0859_0/Cylinder03",
            select_new_prim=False,
        )

        # under light
        self.assertEqual(
            core.filter_transformable_prims([Sdf.Path("/RootNode/lights/light_9907D0B07D040077/Cylinder01")]),
            ["/RootNode/lights/light_9907D0B07D040077/Cylinder01"],
        )

        # under mesh, we can't move a light directly from under the mesh
        self.assertEqual(
            core.filter_transformable_prims([Sdf.Path("/RootNode/meshes/mesh_BAC90CAA733B0859/Cylinder02")]),
            [],
        )

        # under mesh but we can move the one from the instance
        self.assertEqual(
            core.filter_transformable_prims([Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0/Cylinder02")]),
            ["/RootNode/meshes/mesh_BAC90CAA733B0859/Cylinder02"],
        )

        # under instance but this wrong because there is not corresponding light in the mesh_
        self.assertEqual(
            core.filter_transformable_prims([Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0/Cylinder03")]),
            [],
        )

    async def test_asset_is_in_proj_dir(self):
        # Arrange
        core = _AssetReplacementsCore("")
        layer = self.context.get_stage().GetRootLayer()
        mock_project_root = _get_test_data("usd/project_example/")

        for path, scenario, expected_result in [
            (f"{mock_project_root}/example_mesh.usd", "USD directly in project dir", True),
            (f"{mock_project_root}/example_texture.n.rtex.dds", "Texture directly in project dir", True),
            (f"{mock_project_root}/some_subdir/example_mesh.usd", "USD in project subdir", True),
            (f"{mock_project_root}/assets/example_mesh.usd", "USD in assets subdir", True),
            (f"{mock_project_root}/assets/models/example_mesh.usd", "USD in assets/models subdir", True),
            (f"{mock_project_root}/assets/textures/example_texture.n.rtex.dds", "Texture in textures subdir", True),
            (f"{mock_project_root}/deps/example_symlinked_mesh.usd", "USD in deps symlink dir", False),
            (f"{mock_project_root}/deps/captures/meshes/example_symlinked_mesh.usd", "USD in deps subdir", False),
            (f"{mock_project_root}/deps/captures/textures/example_texture.n.rtex.dds", "Texture in deps subdir", False),
            ("C:/some_other_dir/assets/textures/example_mesh.usd", "USD outside of project dir", False),
            ("C:/some_other_dir/assets/textures/example_texture.n.rtex.dds", "Texture outside of project dir", False),
            ("C:/deps/captures/meshes/example_symlinked_mesh.usd", "USD outside of project dir and in deps", False),
            ("C:/deps/captures/meshes/example_texture.n.rtex.dds", "Texture outside of project dir and in deps", False),
        ]:
            with self.subTest(name=f"Test path: {path}     Test layer: {layer}     Scenario: {scenario}"):
                # Act
                result = core.asset_is_in_project_dir(path, layer)

                # Assert
                self.assertEqual(result, expected_result)

    async def test_copy_usd_asset(self):
        # Arrange
        test_prim_path = _get_test_data("usd/project_example/assets/ingested/test_asset.usd")
        test_callback_func = MagicMock()

        with patch.object(_usd_copier, "copy_usd_asset") as mock_copy_usd_asset:
            # Act
            _usd_copier.copy_usd_asset(
                context=self.context,
                prim_path=test_prim_path,
                callback_func=test_callback_func,
            )
            # Assert
            mock_copy_usd_asset.assert_called_once_with(
                context=self.context,
                prim_path=test_prim_path,
                callback_func=test_callback_func,
            )

    async def test_copy_non_usd_asset(self):
        # Arrange
        test_prim_path = _get_test_data("usd/project_example/assets/ingested/test_asset.usd")
        test_callback_func = MagicMock()

        with patch.object(_usd_copier, "copy_non_usd_asset") as mock_copy_non_usd_asset:
            # Act
            _usd_copier.copy_non_usd_asset(
                context=self.context, prim_path=test_prim_path, callback_func=test_callback_func
            )
            # Assert
            mock_copy_non_usd_asset.assert_called_once_with(
                context=self.context, prim_path=test_prim_path, callback_func=test_callback_func
            )

    def _find_replacement_layer(self):
        stage = self.context.get_stage()
        for layer_path in stage.GetRootLayer().subLayerPaths:
            layer = Sdf.Layer.FindRelativeToLayer(stage.GetRootLayer(), layer_path)
            if layer and layer.customLayerData.get("lightspeed_layer_type") == "replacement":
                return layer
        return None

    def _mark_replacement_specs(self, replacement_layer: Sdf.Layer, *paths: Sdf.Path) -> None:
        for p in paths:
            prim_spec = Sdf.CreatePrimInLayer(replacement_layer, p)
            prim_spec.specifier = Sdf.SpecifierOver

    async def test_remove_prim_reference_overrides_clears_references(self):
        """Reference list edits on a replacement-layer prim spec are cleared."""
        # Arrange
        core = _AssetReplacementsCore("")
        replacement_layer = self._find_replacement_layer()
        test_path = "/RootNode/meshes/test_ref_clear"
        prim_spec = Sdf.CreatePrimInLayer(replacement_layer, test_path)
        prim_spec.specifier = Sdf.SpecifierOver
        prim_spec.referenceList.Append(Sdf.Reference("./some_asset.usd"))

        # Act
        core.remove_prim_reference_overrides(test_path)

        # Assert
        prim_spec = replacement_layer.GetPrimAtPath(test_path)
        self.assertIsNotNone(prim_spec)
        self.assertFalse(prim_spec.hasReferences)

    async def test_remove_prim_reference_overrides_preserves_attributes(self):
        """Attribute opinions survive when reference overrides are removed."""
        # Arrange
        core = _AssetReplacementsCore("")
        replacement_layer = self._find_replacement_layer()
        test_path = "/RootNode/meshes/test_ref_preserve_attrs"
        prim_spec = Sdf.CreatePrimInLayer(replacement_layer, test_path)
        prim_spec.specifier = Sdf.SpecifierOver
        prim_spec.referenceList.Append(Sdf.Reference("./some_asset.usd"))
        attr_spec = Sdf.AttributeSpec(prim_spec, "testAttr", Sdf.ValueTypeNames.Float)
        attr_spec.default = 42.0

        # Act
        core.remove_prim_reference_overrides(test_path)

        # Assert
        prim_spec = replacement_layer.GetPrimAtPath(test_path)
        self.assertFalse(prim_spec.hasReferences)
        self.assertIsNotNone(prim_spec.properties.get("testAttr"))
        self.assertEqual(prim_spec.properties.get("testAttr").default, 42.0)

    async def test_remove_prim_reference_overrides_recurses_sublayers(self):
        """Reference overrides in sublayers of the replacement layer are also cleared."""
        # Arrange
        core = _AssetReplacementsCore("")
        replacement_layer = self._find_replacement_layer()
        sublayer = Sdf.Layer.CreateAnonymous()
        replacement_layer.subLayerPaths.append(sublayer.identifier)
        test_path = "/RootNode/meshes/test_ref_sublayer"
        prim_spec = Sdf.CreatePrimInLayer(sublayer, test_path)
        prim_spec.specifier = Sdf.SpecifierOver
        prim_spec.referenceList.Append(Sdf.Reference("./deep_asset.usd"))

        # Act
        core.remove_prim_reference_overrides(test_path)

        # Assert
        prim_spec = sublayer.GetPrimAtPath(test_path)
        self.assertIsNotNone(prim_spec)
        self.assertFalse(prim_spec.hasReferences)

    async def test_remove_prim_reference_overrides_skips_prim_without_references(self):
        """Calling on a prim spec with no references does not crash or alter the spec."""
        # Arrange
        core = _AssetReplacementsCore("")
        replacement_layer = self._find_replacement_layer()
        test_path = "/RootNode/meshes/test_ref_noop"
        prim_spec = Sdf.CreatePrimInLayer(replacement_layer, test_path)
        prim_spec.specifier = Sdf.SpecifierOver
        attr_spec = Sdf.AttributeSpec(prim_spec, "keepMe", Sdf.ValueTypeNames.Bool)
        attr_spec.default = True

        # Act
        core.remove_prim_reference_overrides(test_path)

        # Assert
        prim_spec = replacement_layer.GetPrimAtPath(test_path)
        self.assertIsNotNone(prim_spec)
        self.assertFalse(prim_spec.hasReferences)
        self.assertEqual(prim_spec.properties.get("keepMe").default, True)

    async def test_remove_prim_reference_overrides_accepts_sdf_path(self):
        """The method accepts Sdf.Path in addition to str."""
        # Arrange
        core = _AssetReplacementsCore("")
        replacement_layer = self._find_replacement_layer()
        test_path = Sdf.Path("/RootNode/meshes/test_ref_sdf_path")
        prim_spec = Sdf.CreatePrimInLayer(replacement_layer, test_path)
        prim_spec.specifier = Sdf.SpecifierOver
        prim_spec.referenceList.Append(Sdf.Reference("./asset.usd"))

        # Act
        core.remove_prim_reference_overrides(test_path)

        # Assert
        prim_spec = replacement_layer.GetPrimAtPath(test_path)
        self.assertFalse(prim_spec.hasReferences)

    async def test_clear_reference_list_edits_command_clears_references(self):
        """ClearReferenceListEditsCommand removes reference list edits from the target prim spec."""
        # Arrange
        replacement_layer = self._find_replacement_layer()
        test_path = "/RootNode/meshes/test_cmd_clear"
        prim_spec = Sdf.CreatePrimInLayer(replacement_layer, test_path)
        prim_spec.specifier = Sdf.SpecifierOver
        prim_spec.referenceList.Append(Sdf.Reference("./some_asset.usd"))

        # Act
        omni.kit.commands.execute(
            "ClearReferenceListEditsCommand",
            layer_identifier=replacement_layer.identifier,
            prim_spec_path=test_path,
        )

        # Assert
        prim_spec = replacement_layer.GetPrimAtPath(test_path)
        self.assertIsNotNone(prim_spec)
        self.assertFalse(prim_spec.hasReferences)

    async def test_clear_reference_list_edits_command_undo_restores_references(self):
        """Undoing ClearReferenceListEditsCommand restores the original reference list."""
        # Arrange
        replacement_layer = self._find_replacement_layer()
        test_path = "/RootNode/meshes/test_cmd_undo"
        prim_spec = Sdf.CreatePrimInLayer(replacement_layer, test_path)
        prim_spec.specifier = Sdf.SpecifierOver
        prim_spec.referenceList.Append(Sdf.Reference("./some_asset.usd"))
        omni.kit.commands.execute(
            "ClearReferenceListEditsCommand",
            layer_identifier=replacement_layer.identifier,
            prim_spec_path=test_path,
        )

        # Act
        omni.kit.undo.undo()

        # Assert
        prim_spec = replacement_layer.GetPrimAtPath(test_path)
        self.assertIsNotNone(prim_spec)
        self.assertTrue(prim_spec.hasReferences)
        self.assertEqual(len(prim_spec.referenceList.appendedItems), 1)
        self.assertEqual(prim_spec.referenceList.appendedItems[0].assetPath, "./some_asset.usd")

    async def test_remove_reference_skips_child_cleanup_for_cross_layer_refs(self):
        """remove_reference skips child cleanup when intro_layer differs from edit target."""
        # Arrange
        core = _AssetReplacementsCore("")
        stage = self.context.get_stage()
        edit_target_layer = stage.GetEditTarget().GetLayer()
        external_layer = Sdf.Layer.CreateAnonymous()
        stage.GetRootLayer().subLayerPaths.append(external_layer.identifier)

        test_path = "/RootNode/meshes/test_cross_layer_ref"
        prim_spec = Sdf.CreatePrimInLayer(external_layer, test_path)
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "Xform"
        ref = Sdf.Reference("./some_asset.usd")
        prim_spec.referenceList.Append(ref)

        child_path = test_path + "/child_prim"
        child_spec = Sdf.CreatePrimInLayer(edit_target_layer, child_path)
        child_spec.specifier = Sdf.SpecifierOver

        # Act
        core.remove_reference(stage, test_path, ref, external_layer)

        # Assert
        self.assertIsNotNone(edit_target_layer.GetPrimAtPath(test_path))
        self.assertIsNotNone(edit_target_layer.GetPrimAtPath(child_path))

    async def test_is_valid_usd_file_throws(self):
        # Arrange
        temp_dir = TemporaryDirectory()
        invalid_prim_paths = [
            Path(temp_dir.name),
            Path(temp_dir.name) / " ",
            Path(temp_dir.name) / ".",
            Path(temp_dir.name) / "asset",
            Path(temp_dir.name) / "asset.",
            Path(temp_dir.name) / "asset.u",
            Path(temp_dir.name) / "asset.txt",
            Path(temp_dir.name) / "asset.zip",
            Path(temp_dir.name) / "asset.usr",
            Path(temp_dir.name) / "asset.uusd",
            Path(temp_dir.name) / "asset.usdd",
            "C:\\..\\..my\\invalid\\path",
        ]

        for invalid_prim_path in invalid_prim_paths:
            # Act
            with self.assertRaises(ValueError) as cm:
                _usd_copier.is_valid_usd_file(invalid_prim_path)

            # Assert
            self.assertEqual(f"'{invalid_prim_path}' is not a valid USD path", str(cm.exception))

        temp_dir.cleanup()

    async def test_copy_overrides_in_layer_copies_attributes_to_dest_prims(self):
        """_copy_overrides_in_layer copies the replacement-layer prim spec to the dest path via Sdf.CopySpec."""
        stage = self.context.get_stage()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)
        source_root = "/RootNode/meshes/test_copy_layer_src"
        dest_root = "/RootNode/meshes/test_copy_layer_dst"
        child_path = Sdf.Path(f"{source_root}/child_scope")
        dest_child_path = Sdf.Path(f"{dest_root}/child_scope")
        UsdGeom.Scope.Define(stage, source_root)
        UsdGeom.Scope.Define(stage, dest_root)
        UsdGeom.Scope.Define(stage, str(child_path))
        UsdGeom.Scope.Define(stage, str(dest_child_path))
        attr_name = "copyReplaceTestAttr"

        # Author the attribute in the replacement-layer spec so Sdf.CopySpec has content to copy.
        self._mark_replacement_specs(replacement_layer, child_path)
        child_spec = replacement_layer.GetPrimAtPath(child_path)
        Sdf.AttributeSpec(child_spec, attr_name, Sdf.ValueTypeNames.Float).default = 88.5

        # Pre-create only the dest parent spec (not dest_child_path itself) so
        # Sdf.CopySpec can create the child spec fresh — same-layer CopySpec
        # does not copy attributes if the destination spec already exists.
        self._mark_replacement_specs(replacement_layer, Sdf.Path(dest_root))

        # Pre-author all source attributes on the dest prim in the root layer so
        # _copy_overrides_in_layer's CreateAttribute branch (which targets the active
        # edit layer) cannot implicitly create a replacement-layer spec for
        # dest_child_path before Sdf.CopySpec runs.
        dest_prim = stage.GetPrimAtPath(str(dest_child_path))
        src_prim = stage.GetPrimAtPath(str(child_path))
        for src_attr in src_prim.GetAttributes():
            if src_attr and src_attr.IsValid() and not dest_prim.GetAttribute(src_attr.GetName()).IsValid():
                dest_prim.CreateAttribute(src_attr.GetName(), src_attr.GetTypeName(), custom=src_attr.IsCustom())

        # Set the edit target to replacement_layer so _copy_overrides_in_layer's
        # Sdf.CopySpec writes into the replacement layer, not the root layer.
        with Usd.EditContext(stage, replacement_layer):
            _AssetReplacementsCore._copy_overrides_in_layer(
                stage,
                replacement_layer,
                Sdf.Path(source_root),
                Sdf.Path(dest_root),
                [child_path],
            )

        dest_spec = replacement_layer.GetPrimAtPath(dest_child_path)
        self.assertIsNotNone(dest_spec)
        copied_attr = dest_spec.attributes.get(attr_name)
        self.assertIsNotNone(copied_attr)
        self.assertAlmostEqual(copied_attr.default, 88.5, places=5)

    async def test_copy_overrides_in_layer_recurse_sublayers(self):
        """Specs on a sublayer of the replacement stack are copied within that sublayer."""
        stage = self.context.get_stage()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)
        sublayer = Sdf.Layer.CreateAnonymous()
        replacement_layer.subLayerPaths.append(sublayer.identifier)

        source_root = "/RootNode/meshes/test_copy_sublayer_src"
        dest_root = "/RootNode/meshes/test_copy_sublayer_dst"
        child_path = Sdf.Path(f"{source_root}/sub_child")
        dest_child_path = Sdf.Path(f"{dest_root}/sub_child")
        UsdGeom.Scope.Define(stage, source_root)
        UsdGeom.Scope.Define(stage, dest_root)
        UsdGeom.Scope.Define(stage, str(child_path))
        UsdGeom.Scope.Define(stage, str(dest_child_path))
        attr_name = "copyReplaceTestAttrSub"

        # Author attribute in the sublayer spec; pre-create only the dest root spec (not
        # dest_child_path itself) so Sdf.CopySpec can create the child spec fresh.
        self._mark_replacement_specs(sublayer, child_path)
        child_spec = sublayer.GetPrimAtPath(child_path)
        Sdf.AttributeSpec(child_spec, attr_name, Sdf.ValueTypeNames.Float).default = 12.0
        self._mark_replacement_specs(sublayer, Sdf.Path(dest_root))

        # Pre-author all source attributes on the dest prim in the root layer so
        # _copy_overrides_in_layer's CreateAttribute branch cannot implicitly create
        # a sublayer spec for dest_child_path before Sdf.CopySpec runs.
        dest_prim = stage.GetPrimAtPath(str(dest_child_path))
        src_prim = stage.GetPrimAtPath(str(child_path))
        for src_attr in src_prim.GetAttributes():
            if src_attr and src_attr.IsValid() and not dest_prim.GetAttribute(src_attr.GetName()).IsValid():
                dest_prim.CreateAttribute(src_attr.GetName(), src_attr.GetTypeName(), custom=src_attr.IsCustom())

        # Set the edit target to sublayer so _copy_overrides_in_layer's Sdf.CopySpec
        # writes into the sublayer (where the source spec lives), not the root layer.
        with Usd.EditContext(stage, sublayer):
            _AssetReplacementsCore._copy_overrides_in_layer(
                stage,
                replacement_layer,
                Sdf.Path(source_root),
                Sdf.Path(dest_root),
                [child_path],
            )

        dest_spec = sublayer.GetPrimAtPath(dest_child_path)
        self.assertIsNotNone(dest_spec)
        copied_attr = dest_spec.attributes.get(attr_name)
        self.assertIsNotNone(copied_attr)
        self.assertAlmostEqual(copied_attr.default, 12.0, places=5)

    async def test_copy_replacement_overrides_to_path_copies_descendant_overrides(self):
        """copy_replacement_overrides_to_path copies child/descendant attribute and material overrides (not the root)."""
        core = _AssetReplacementsCore("")
        stage = self.context.get_stage()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)
        source_root = "/RootNode/meshes/test_copy_api_src"
        dest_root = "/RootNode/meshes/test_copy_api_dst"
        child_path = Sdf.Path(f"{source_root}/api_child")
        grand_path = Sdf.Path(f"{source_root}/api_child/grand_scope")
        dest_grand_path = Sdf.Path(f"{dest_root}/api_child/grand_scope")
        UsdGeom.Scope.Define(stage, source_root)
        UsdGeom.Scope.Define(stage, dest_root)
        UsdGeom.Scope.Define(stage, str(child_path))
        UsdGeom.Scope.Define(stage, str(grand_path))
        UsdGeom.Scope.Define(stage, f"{dest_root}/api_child")
        UsdGeom.Scope.Define(stage, str(dest_grand_path))
        attr_name = "copyReplaceTestAttrApi"

        # Author attribute and material override in the replacement-layer spec.
        self._mark_replacement_specs(replacement_layer, child_path, grand_path)
        grand_spec = replacement_layer.GetPrimAtPath(grand_path)
        Sdf.AttributeSpec(grand_spec, attr_name, Sdf.ValueTypeNames.Float).default = 55.0
        mat_target = Sdf.Path("/RootNode/Looks/mat_BC868CE5A075ABB1")
        Sdf.RelationshipSpec(grand_spec, "material:binding", custom=False).targetPathList.Prepend(mat_target)

        # Pre-create only the dest root spec so Sdf.CopySpec can create child/grandchild
        # specs fresh — same-layer CopySpec does not copy attributes into existing specs.
        self._mark_replacement_specs(replacement_layer, Sdf.Path(dest_root))

        # Pre-author the custom attribute on dest_grand_path in the root layer so
        # _copy_overrides_in_layer's CreateAttribute branch cannot implicitly create a
        # replacement-layer spec for dest_grand_path before Sdf.CopySpec runs.
        stage.GetPrimAtPath(str(dest_grand_path)).CreateAttribute(attr_name, Sdf.ValueTypeNames.Float, custom=True)

        # Set the edit target to replacement_layer so _copy_overrides_in_layer's
        # Sdf.CopySpec writes into the replacement layer, not the root layer.
        with Usd.EditContext(stage, replacement_layer):
            core.copy_replacement_overrides_to_path(source_root, dest_root)

        # Attribute was copied via Sdf.CopySpec into the replacement-layer dest spec.
        dest_grand_spec = replacement_layer.GetPrimAtPath(dest_grand_path)
        copied_attr = dest_grand_spec.attributes.get(attr_name)
        self.assertIsNotNone(copied_attr)
        self.assertAlmostEqual(copied_attr.default, 55.0, places=5)
        # Material override was copied via SetRelationshipTargetsCommand.
        dst_mat = stage.GetPrimAtPath(str(dest_grand_path)).GetRelationship("material:binding")
        self.assertTrue(dst_mat.IsValid())
        self.assertEqual(dst_mat.GetTargets(), [mat_target])

    async def test_copy_replacement_overrides_to_path_undo_restores_destination_values(self):
        """SetRelationshipTargetsCommand issued by _copy_material_overrides is undoable in isolation.

        _copy_material_overrides is called directly (not through copy_replacement_overrides_to_path)
        so that Sdf.CopySpec does not run first and overwrite the dest spec non-undoably.
        With CopySpec out of the picture, SetRelationshipTargetsCommand captures mat_dest_before as
        its prev state, and a single undo correctly restores the original binding.
        """
        stage = self.context.get_stage()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)
        source_root = "/RootNode/meshes/test_copy_undo_src"
        dest_root = "/RootNode/meshes/test_copy_undo_dst"
        child_path = Sdf.Path(f"{source_root}/undo_child")
        dest_child_path = Sdf.Path(f"{dest_root}/undo_child")
        UsdGeom.Scope.Define(stage, source_root)
        UsdGeom.Scope.Define(stage, dest_root)
        UsdGeom.Scope.Define(stage, str(child_path))
        UsdGeom.Scope.Define(stage, str(dest_child_path))

        # Source spec: material:binding override.
        self._mark_replacement_specs(replacement_layer, child_path)
        child_spec = replacement_layer.GetPrimAtPath(child_path)
        mat_from_source = Sdf.Path("/RootNode/Looks/mat_BC868CE5A075ABB1")
        Sdf.RelationshipSpec(child_spec, "material:binding", custom=False).targetPathList.Prepend(mat_from_source)

        # Dest spec: pre-existing binding so we can verify undo restores it.
        self._mark_replacement_specs(replacement_layer, dest_child_path)
        dest_spec = replacement_layer.GetPrimAtPath(dest_child_path)
        mat_dest_before = Sdf.Path("/RootNode/meshes/test_copy_undo_dst/placeholder_mat_binding")
        Sdf.RelationshipSpec(dest_spec, "material:binding", custom=False).targetPathList.Prepend(mat_dest_before)

        dest_mat_before = list(
            stage.GetPrimAtPath(str(dest_child_path)).GetRelationship("material:binding").GetTargets()
        )

        # Call _copy_material_overrides directly to avoid Sdf.CopySpec pre-empting the undo state.
        _AssetReplacementsCore._copy_material_overrides(
            stage,
            replacement_layer,
            Sdf.Path(source_root),
            Sdf.Path(dest_root),
            [child_path],
        )
        self.assertEqual(
            list(stage.GetPrimAtPath(str(dest_child_path)).GetRelationship("material:binding").GetTargets()),
            [mat_from_source],
        )

        max_undos = 128
        for _ in range(max_undos):
            cur = list(stage.GetPrimAtPath(str(dest_child_path)).GetRelationship("material:binding").GetTargets())
            if cur == dest_mat_before:
                break
            omni.kit.undo.undo()
        else:
            self.fail("undo did not restore material:binding targets")

        self.assertEqual(
            list(stage.GetPrimAtPath(str(dest_child_path)).GetRelationship("material:binding").GetTargets()),
            dest_mat_before,
        )

    async def test_copy_material_overrides_copies_relationship_to_dest(self):
        """_copy_material_overrides copies an authored relationship override to the dest prim.

        A material:binding relationship spec authored in the replacement layer for a source
        child prim is replicated on the corresponding dest child prim.  External targets
        (those outside the source sub-hierarchy) are copied as-is.
        """
        core = _AssetReplacementsCore("")
        stage = self.context.get_stage()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)

        source_root = "/RootNode/meshes/test_mat_copy_src"
        dest_root = "/RootNode/meshes/test_mat_copy_dst"
        child_path = Sdf.Path(f"{source_root}/rel_child")
        dest_child_path = Sdf.Path(f"{dest_root}/rel_child")

        UsdGeom.Scope.Define(stage, source_root)
        UsdGeom.Scope.Define(stage, dest_root)
        UsdGeom.Scope.Define(stage, str(child_path))
        UsdGeom.Scope.Define(stage, str(dest_child_path))

        # Author a material:binding relationship override in the replacement layer.
        self._mark_replacement_specs(replacement_layer, child_path)
        child_spec = replacement_layer.GetPrimAtPath(child_path)
        rel_spec = Sdf.RelationshipSpec(child_spec, "material:binding", custom=False)
        mat_target = Sdf.Path("/RootNode/Looks/mat_BC868CE5A075ABB1")
        rel_spec.targetPathList.Prepend(mat_target)

        self._mark_replacement_specs(replacement_layer, dest_child_path)

        core.copy_replacement_overrides_to_path(source_root, dest_root)

        dest_prim = stage.GetPrimAtPath(str(dest_child_path))
        dest_rel = dest_prim.GetRelationship("material:binding")
        self.assertTrue(dest_rel.IsValid())
        self.assertEqual(dest_rel.GetTargets(), [mat_target])

    async def test_copy_material_overrides_remaps_internal_targets(self):
        """Relationship targets within the source sub-hierarchy are remapped to dest.

        When a material:binding target path starts with source_path, the copied
        relationship must point to the equivalent path under dest_path.
        """
        core = _AssetReplacementsCore("")
        stage = self.context.get_stage()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)

        source_root = "/RootNode/meshes/test_mat_remap_src"
        dest_root = "/RootNode/meshes/test_mat_remap_dst"
        child_path = Sdf.Path(f"{source_root}/remap_child")
        dest_child_path = Sdf.Path(f"{dest_root}/remap_child")

        UsdGeom.Scope.Define(stage, source_root)
        UsdGeom.Scope.Define(stage, dest_root)
        UsdGeom.Scope.Define(stage, str(child_path))
        UsdGeom.Scope.Define(stage, str(dest_child_path))

        # Target lives inside the source sub-hierarchy and must be remapped.
        source_mat_target = Sdf.Path(f"{source_root}/Looks/CubeMaterial")
        expected_target = Sdf.Path(f"{dest_root}/Looks/CubeMaterial")

        self._mark_replacement_specs(replacement_layer, child_path)
        child_spec = replacement_layer.GetPrimAtPath(child_path)
        rel_spec = Sdf.RelationshipSpec(child_spec, "material:binding", custom=False)
        rel_spec.targetPathList.Prepend(source_mat_target)

        self._mark_replacement_specs(replacement_layer, dest_child_path)

        core.copy_replacement_overrides_to_path(source_root, dest_root)

        dest_prim = stage.GetPrimAtPath(str(dest_child_path))
        self.assertEqual(dest_prim.GetRelationship("material:binding").GetTargets(), [expected_target])

    async def test_copy_material_overrides_recurses_sublayers(self):
        """Relationship overrides authored only in a sublayer are also copied.

        _copy_material_overrides recurses into sublayers of the replacement layer,
        so a material:binding spec found only in a sublayer is still replicated on
        the corresponding dest prim.
        """
        core = _AssetReplacementsCore("")
        stage = self.context.get_stage()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)

        sublayer = Sdf.Layer.CreateAnonymous()
        replacement_layer.subLayerPaths.append(sublayer.identifier)

        source_root = "/RootNode/meshes/test_mat_sub_src"
        dest_root = "/RootNode/meshes/test_mat_sub_dst"
        child_path = Sdf.Path(f"{source_root}/sub_rel_child")
        dest_child_path = Sdf.Path(f"{dest_root}/sub_rel_child")

        UsdGeom.Scope.Define(stage, source_root)
        UsdGeom.Scope.Define(stage, dest_root)
        UsdGeom.Scope.Define(stage, str(child_path))
        UsdGeom.Scope.Define(stage, str(dest_child_path))

        # Author the override in the sublayer only.
        self._mark_replacement_specs(sublayer, child_path)
        child_spec = sublayer.GetPrimAtPath(child_path)
        rel_spec = Sdf.RelationshipSpec(child_spec, "material:binding", custom=False)
        mat_target = Sdf.Path("/RootNode/Looks/mat_BC868CE5A075ABB1")
        rel_spec.targetPathList.Prepend(mat_target)

        # Dest must have parent specs in both replacement layer AND sublayer so Sdf.CopySpec
        # succeeds when _copy_overrides_in_layer recurses into the sublayer.
        self._mark_replacement_specs(replacement_layer, dest_child_path)
        self._mark_replacement_specs(sublayer, dest_child_path)

        core.copy_replacement_overrides_to_path(source_root, dest_root)

        dest_prim = stage.GetPrimAtPath(str(dest_child_path))
        self.assertEqual(dest_prim.GetRelationship("material:binding").GetTargets(), [mat_target])
