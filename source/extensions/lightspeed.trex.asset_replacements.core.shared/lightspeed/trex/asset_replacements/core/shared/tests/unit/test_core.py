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
from pxr import Sdf


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
