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
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import omni.kit.test
import omni.usd
from lightspeed.common.constants import CAPTURED_REMIX_CONFIG_ATTR as _NAMESPACED_ATTRIBUTE
from lightspeed.common.constants import CAPTURED_REMIX_CONFIG_LEGACY_ATTR as _LEGACY_ATTRIBUTE
from lightspeed.common.constants import CAPTURED_REMIX_SETTINGS as _REMIX_SETTINGS
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from pxr import Sdf, Tf, Usd, UsdGeom

from ... import setup as _setup

_CONFIG_A = ["rtx.sceneScale = 0.01", "rtx.zUp = True"]
_CONFIG_B = ["rtx.sceneScale = 1.0", "rtx.zUp = False"]
_CONFIG_OVERRIDE = ["rtx.sceneScale = 5.0"]


class TestSetup(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def __create_basic_layers(self):
        layer_manager = _LayerManagerCore()

        context = omni.usd.get_context()
        stage = Usd.Stage.CreateInMemory("test.usd")
        await context.attach_stage_async(stage)

        # create a fake replacement layer and add it
        stage_replacement = Usd.Stage.CreateInMemory("replacement.usd")
        layer_replacement = stage_replacement.GetRootLayer()
        layer_manager.set_custom_data_layer_type(layer_replacement, _LayerType.replacement)
        stage.GetRootLayer().subLayerPaths.insert(0, layer_replacement.identifier)

        # create a fake sub replacement layer and add it
        stage_sub_replacement = Usd.Stage.CreateInMemory("sub_replacement.usd")
        layer_sub_replacement = stage_sub_replacement.GetRootLayer()
        layer_replacement.subLayerPaths.insert(0, layer_sub_replacement.identifier)

        # create a fake capture layer and add it
        stage_capture = Usd.Stage.CreateInMemory("capture.usd")
        layer_capture = stage_capture.GetRootLayer()
        layer_manager.set_custom_data_layer_type(layer_capture, _LayerType.capture)
        stage.GetRootLayer().subLayerPaths.insert(1, layer_capture.identifier)

        return stage, layer_replacement, layer_sub_replacement, layer_capture

    async def __create_setup_01(self, share_material=False):
        """
        Create a basic setup with 3 meshes, 3 materials and 3 lights
        """
        stage, layer_replacement, layer_sub_replacement, layer_capture = await self.__create_basic_layers()

        # create 3 meshes, 3 materials, 3 lights
        with Usd.EditContext(stage, layer_capture):
            for i in range(3):
                mesh_path = "/RootNode/meshes/mesh_MESH0CAA733B085"
                prim_path = f"{mesh_path}{i}"
                UsdGeom.Cube.Define(stage, prim_path)

                prim_path2 = f"{prim_path}/cube_{i}"
                UsdGeom.Cube.Define(stage, prim_path2)

                mat_base_path = "/RootNode/Looks/mat_MAT68CE5A075ABB"
                mat_path = f"{mat_base_path}{i}"
                # if we have shared material, material 1 will be on mesh 1 and 2
                if share_material and i == 2:
                    omni.kit.commands.execute(
                        "BindMaterialCommand", prim_path=prim_path, material_path=f"{mat_base_path}1"
                    )
                else:
                    omni.kit.commands.execute(
                        "CreateMdlMaterialPrim", mtl_url="OmniPBR.mdl", mtl_name="OmniPBR", mtl_path=mat_path
                    )
                    omni.kit.commands.execute("BindMaterialCommand", prim_path=prim_path, material_path=mat_path)

                light_path = f"/RootNode/lights/light_LIGHT0B07D04007{i}"
                omni.kit.commands.execute("CreatePrim", prim_type="RectLight", prim_path=light_path)
        return stage, layer_replacement, layer_sub_replacement, layer_capture

    async def test_is_capture_file_with_capture_metadata_returns_true(self):
        """Return true when capture metadata identifies the layer."""
        # Arrange
        capture_path = "C:/captures/capture.usda"
        layer = MagicMock()
        layer.customLayerData.get.return_value = _LayerType.capture.value

        with patch.object(Sdf.Layer, "OpenAsAnonymous", return_value=layer) as open_layer:
            # Act
            result = _CaptureCoreSetup.is_capture_file(capture_path)

        # Assert
        self.assertTrue(result)
        open_layer.assert_called_once_with(capture_path, metadataOnly=True)

    async def test_is_layer_a_capture_file_with_wrong_layer_type_returns_false(self):
        """Return false when layer metadata identifies another layer type."""
        # Arrange
        layer = MagicMock()
        layer.customLayerData.get.return_value = _LayerType.replacement.value

        # Act
        result = _CaptureCoreSetup.is_layer_a_capture_file(layer)

        # Assert
        self.assertFalse(result)

    async def test_is_layer_a_capture_file_without_layer_type_returns_false(self):
        """Return false when layer metadata has no layer type."""
        # Arrange
        layer = MagicMock()
        layer.customLayerData.get.return_value = None

        # Act
        result = _CaptureCoreSetup.is_layer_a_capture_file(layer)

        # Assert
        self.assertFalse(result)

    async def test_is_capture_file_when_open_returns_none_returns_false(self):
        """Return false when USD metadata cannot be opened."""
        # Arrange
        capture_path = "C:/captures/missing.usda"

        with patch.object(Sdf.Layer, "OpenAsAnonymous", return_value=None) as open_layer:
            # Act
            result = _CaptureCoreSetup.is_capture_file(capture_path)

        # Assert
        self.assertFalse(result)
        open_layer.assert_called_once_with(capture_path, metadataOnly=True)

    async def test_is_capture_file_when_open_raises_tf_error_returns_false(self):
        """Return false when USD metadata opening raises an error."""
        # Arrange
        capture_path = "C:/captures/invalid.usda"

        with patch.object(Sdf.Layer, "OpenAsAnonymous", side_effect=Tf.ErrorException("open failed")) as open_layer:
            # Act
            result = _CaptureCoreSetup.is_capture_file(capture_path)

        # Assert
        self.assertFalse(result)
        open_layer.assert_called_once_with(capture_path, metadataOnly=True)

    async def test_get_capture_files_filters_and_sorts_capture_files(self):
        # Arrange
        core = _CaptureCoreSetup("")
        core.set_directory("C:/project/deps/captures")

        capture_a = MagicMock()
        capture_a.is_file.return_value = True
        capture_a.suffix = ".usda"
        capture_a.__str__.return_value = "C:/project/deps/captures/capture_a.usda"

        capture_b = MagicMock()
        capture_b.is_file.return_value = True
        capture_b.suffix = ".usda"
        capture_b.__str__.return_value = "C:/project/deps/captures/capture_b.usda"

        not_a_capture = MagicMock()
        not_a_capture.is_file.return_value = True
        not_a_capture.suffix = ".usda"
        not_a_capture.__str__.return_value = "C:/project/deps/captures/not_a_capture.usda"

        # Act
        with (
            patch(
                "lightspeed.trex.capture.core.shared.setup.Path.iterdir",
                return_value=[capture_a, not_a_capture, capture_b],
            ),
            patch.object(
                _CaptureCoreSetup,
                "is_capture_file",
                side_effect=lambda path: path != "C:/project/deps/captures/not_a_capture.usda",
            ),
        ):
            result = core.get_capture_files()

        # Assert
        self.assertEqual(
            [
                "C:/project/deps/captures/capture_b.usda",
                "C:/project/deps/captures/capture_a.usda",
            ],
            result,
        )

    async def test_get_capture_files_returns_empty_when_directory_disappears(self):
        # Arrange
        core = _CaptureCoreSetup("")
        core.set_directory("C:/project/deps/captures")

        # Act
        with patch("lightspeed.trex.capture.core.shared.setup.Path.iterdir", side_effect=FileNotFoundError):
            result = core.get_capture_files()

        # Assert
        self.assertEqual([], result)

    async def test_get_capture_files_with_thumbnails_mixed_entries_returns_accepted_files_in_listing_order(self):
        """Return readable capture USDs with thumbnails in client listing order."""
        # Arrange
        captures_directory = Path("C:/project/deps/captures")
        core = _CaptureCoreSetup("")
        valid_a = str(captures_directory / "valid_a.usda")
        invalid = str(captures_directory / "not_a_capture.usd")
        valid_b = str(captures_directory / "valid_b.usd")
        thumbnail = str(captures_directory / ".thumbs" / "valid_a.usda.dds")
        entries = [
            SimpleNamespace(relative_path="valid_a.usda", flags=omni.client.ItemFlags.READABLE_FILE),
            SimpleNamespace(relative_path="not_a_capture.usd", flags=omni.client.ItemFlags.READABLE_FILE),
            SimpleNamespace(relative_path="unreadable.usda", flags=omni.client.ItemFlags.WRITEABLE_FILE),
            SimpleNamespace(relative_path="ignored.txt", flags=omni.client.ItemFlags.READABLE_FILE),
            SimpleNamespace(relative_path="valid_b.usd", flags=omni.client.ItemFlags.READABLE_FILE),
        ]

        with (
            patch.object(_setup.omni.client, "list", return_value=(omni.client.Result.OK, entries)),
            patch.object(
                core, "is_capture_file", side_effect=lambda path: path in {valid_a, valid_b}
            ) as is_capture_file,
            patch.object(
                core, "get_capture_image", side_effect=lambda path: thumbnail if path == valid_a else None
            ) as get_capture_image,
            patch.object(_setup, "ThreadPoolExecutor", create=True) as executor_class,
        ):
            executor_class.return_value.__enter__.return_value.map.side_effect = map

            # Act
            result = core.get_capture_files_with_thumbnails(captures_directory=captures_directory)

        # Assert
        self.assertEqual([(valid_a, thumbnail), (valid_b, None)], result)
        executor_class.assert_called_once_with(max_workers=10)
        self.assertEqual([call(valid_a), call(invalid), call(valid_b)], is_capture_file.call_args_list)
        self.assertEqual([call(valid_a), call(valid_b)], get_capture_image.call_args_list)

    async def test_get_capture_files_with_thumbnails_failed_listing_returns_empty_without_processing(self):
        """Return no captures when the client directory listing fails."""
        # Arrange
        captures_directory = Path("C:/project/deps/captures")
        core = _CaptureCoreSetup("")

        with (
            patch.object(_setup.omni.client, "list", return_value=(omni.client.Result.ERROR_NOT_FOUND, [])),
            patch.object(core, "is_capture_file") as is_capture_file,
            patch.object(_setup, "ThreadPoolExecutor", create=True) as executor_class,
        ):
            # Act
            result = core.get_capture_files_with_thumbnails(captures_directory)

        # Assert
        self.assertEqual([], result)
        is_capture_file.assert_not_called()
        executor_class.assert_not_called()

    async def test_async_get_replaced_hashes_two_meshes(self):
        """We set an override on 2 meshes"""
        stage, layer_replacement, _layer_sub_replacement, layer_capture = await self.__create_setup_01()

        mesh_base_path = "/RootNode/meshes/mesh_MESH0CAA733B085"
        with Usd.EditContext(stage, layer_replacement):
            prim0 = stage.GetPrimAtPath(f"{mesh_base_path}0")
            prim1 = stage.GetPrimAtPath(f"{mesh_base_path}1")
            prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
            prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

        core = _CaptureCoreSetup("")
        result = await core.async_get_replaced_hashes(
            layer_capture.identifier, ["MESH0CAA733B0850", "MESH0CAA733B0851"]
        )
        # replaced assets are the meshes
        self.assertEqual(result[0], {"MESH0CAA733B0851", "MESH0CAA733B0850"})
        # all assets. We should only have 3 lights and 3 meshes. Materials are grouped with meshes
        self.assertEqual(
            result[1],
            {
                "LIGHT0B07D040072",
                "MESH0CAA733B0852",
                "LIGHT0B07D040070",
                "LIGHT0B07D040071",
                "MESH0CAA733B0851",
                "MESH0CAA733B0850",
            },
        )

    async def test_async_get_replaced_hashes_two_materials(self):
        """We set an override on 2 materials"""
        stage, layer_replacement, _layer_sub_replacement, layer_capture = await self.__create_setup_01()

        mat_path = "/RootNode/Looks/mat_MAT68CE5A075ABB"
        with Usd.EditContext(stage, layer_replacement):
            prim0 = stage.GetPrimAtPath(f"{mat_path}1")
            prim1 = stage.GetPrimAtPath(f"{mat_path}2")
            prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
            prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

        core = _CaptureCoreSetup("")
        result = await core.async_get_replaced_hashes(
            layer_capture.identifier, ["MAT68CE5A075ABB1", "MAT68CE5A075ABB2"]
        )
        # replaced assets are the meshes that have the materials (that have the overrides) assigned
        self.assertEqual(result[0], {"MESH0CAA733B0851", "MESH0CAA733B0852"})
        # all assets. We should only have 3 lights and 3 meshes. Materials are grouped with meshes
        self.assertEqual(
            result[1],
            {
                "LIGHT0B07D040072",
                "MESH0CAA733B0852",
                "LIGHT0B07D040070",
                "LIGHT0B07D040071",
                "MESH0CAA733B0851",
                "MESH0CAA733B0850",
            },
        )

    async def test_async_get_replaced_hashes_one_shared_materials(self):
        """We set an override on a shared material"""
        stage, layer_replacement, _layer_sub_replacement, layer_capture = await self.__create_setup_01(
            share_material=True
        )

        mat_path = "/RootNode/Looks/mat_MAT68CE5A075ABB"
        with Usd.EditContext(stage, layer_replacement):
            prim0 = stage.GetPrimAtPath(f"{mat_path}1")
            prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

        core = _CaptureCoreSetup("")
        result = await core.async_get_replaced_hashes(layer_capture.identifier, ["MAT68CE5A075ABB1"])
        # replaced assets are the two meshes that have the same shared materials (and the material has overrides)
        self.assertEqual(result[0], {"MESH0CAA733B0851", "MESH0CAA733B0852"})
        # all assets. We should only have 3 lights and 3 meshes. Materials are grouped with meshes
        self.assertEqual(
            result[1],
            {
                "LIGHT0B07D040072",
                "MESH0CAA733B0852",
                "LIGHT0B07D040070",
                "LIGHT0B07D040071",
                "MESH0CAA733B0851",
                "MESH0CAA733B0850",
            },
        )

    async def test_async_get_replaced_hashes_one_shared_materials_one_material(self):
        """We set an override on a shared material + a regular material"""
        stage, layer_replacement, _layer_sub_replacement, layer_capture = await self.__create_setup_01(
            share_material=True
        )

        mat_path = "/RootNode/Looks/mat_MAT68CE5A075ABB"
        with Usd.EditContext(stage, layer_replacement):
            prim0 = stage.GetPrimAtPath(f"{mat_path}0")
            prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
            prim1 = stage.GetPrimAtPath(f"{mat_path}1")
            prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

        core = _CaptureCoreSetup("")
        result = await core.async_get_replaced_hashes(
            layer_capture.identifier, ["MAT68CE5A075ABB0", "MAT68CE5A075ABB1"]
        )
        # replaced assets are the two meshes that have the same shared materials (and the material has overrides)
        # + the mesh with the material that has the override
        self.assertEqual(result[0], {"MESH0CAA733B0850", "MESH0CAA733B0851", "MESH0CAA733B0852"})
        # all assets. We should only have 3 lights and 3 meshes. Materials are grouped with meshes
        self.assertEqual(
            result[1],
            {
                "LIGHT0B07D040072",
                "MESH0CAA733B0852",
                "LIGHT0B07D040070",
                "LIGHT0B07D040071",
                "MESH0CAA733B0851",
                "MESH0CAA733B0850",
            },
        )

    async def test_async_get_replaced_hashes_one_shared_materials_same_mesh(self):
        """We set an override on a shared material and a mesh (that has this shared material assigned)"""
        stage, layer_replacement, _layer_sub_replacement, layer_capture = await self.__create_setup_01(
            share_material=True
        )

        mesh_base_path = "/RootNode/meshes/mesh_MESH0CAA733B085"
        mat_path = "/RootNode/Looks/mat_MAT68CE5A075ABB"
        with Usd.EditContext(stage, layer_replacement):
            prim0 = stage.GetPrimAtPath(f"{mat_path}1")
            prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
            prim1 = stage.GetPrimAtPath(f"{mesh_base_path}1")
            prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

        core = _CaptureCoreSetup("")
        result = await core.async_get_replaced_hashes(
            layer_capture.identifier, ["MAT68CE5A075ABB1", "MESH0CAA733B0851"]
        )
        # replaced assets are the two meshes that have the same shared materials (and the material has overrides)
        # Even if we have an override on the mesh that has this shared material, this is counted as 1 override
        self.assertEqual(result[0], {"MESH0CAA733B0851", "MESH0CAA733B0852"})
        # all assets. We should only have 3 lights and 3 meshes. Materials are grouped with meshes
        self.assertEqual(
            result[1],
            {
                "LIGHT0B07D040072",
                "MESH0CAA733B0852",
                "LIGHT0B07D040070",
                "LIGHT0B07D040071",
                "MESH0CAA733B0851",
                "MESH0CAA733B0850",
            },
        )

    @staticmethod
    def __make_core(capture_attribute: str | None = None, capture_config=None, mod_action=None):
        """Build the capture core over a project stage shaped like a real one.

        The capture is the weakest sublayer, as `import_capture_layer` inserts it, and the mod
        layer above it stands in for a project-wide override -- `mod_action` receives that
        layer's attribute so a test can set it or block it. Both layers are kept alive by the
        stage that sublayers them: an anonymous layer expires with its last strong reference.
        """
        capture_stage = Usd.Stage.CreateInMemory()
        if capture_attribute is not None:
            prim = capture_stage.DefinePrim(_REMIX_SETTINGS, "RenderSettings")
            prim.CreateAttribute(capture_attribute, Sdf.ValueTypeNames.StringArray).Set(capture_config)
        capture_layer = capture_stage.GetRootLayer()

        mod_stage = Usd.Stage.CreateInMemory()
        if mod_action is not None:
            prim = mod_stage.OverridePrim(_REMIX_SETTINGS)
            mod_action(prim.CreateAttribute(_NAMESPACED_ATTRIBUTE, Sdf.ValueTypeNames.StringArray))

        stage = Usd.Stage.CreateInMemory()
        stage.GetRootLayer().subLayerPaths.insert(0, capture_layer.identifier)
        stage.GetRootLayer().subLayerPaths.insert(0, mod_stage.GetRootLayer().identifier)

        core = _CaptureCoreSetup("")
        core._context = MagicMock()
        core._context.get_stage.return_value = stage
        return core, stage, capture_layer

    @staticmethod
    def __get_composed_config(stage: Usd.Stage) -> list[str] | None:
        """Read what HdRemix would see: the composed namespaced attribute."""
        prim = stage.GetPrimAtPath(_REMIX_SETTINGS)
        if not prim.IsValid():
            return None
        attribute = prim.GetAttribute(_NAMESPACED_ATTRIBUTE)
        return list(attribute.Get()) if attribute and attribute.HasAuthoredValue() else None

    @staticmethod
    def __get_session_fallback(stage: Usd.Stage) -> list[str] | None:
        spec = stage.GetSessionLayer().GetAttributeAtPath(f"{_REMIX_SETTINGS}.{_NAMESPACED_ATTRIBUTE}")
        return list(spec.default) if spec is not None else None

    async def test_publish_remix_config_legacy_capture_reaches_namespaced_attribute(self):
        # Arrange
        core, stage, _capture_layer = self.__make_core(_LEGACY_ATTRIBUTE, _CONFIG_A)

        # Act
        core._publish_remix_config()

        # Assert
        self.assertEqual(self.__get_composed_config(stage), _CONFIG_A)

    async def test_publish_remix_config_namespaced_capture_authors_no_fallback(self):
        # Arrange
        core, stage, _capture_layer = self.__make_core(_NAMESPACED_ATTRIBUTE, _CONFIG_A)

        # Act
        core._publish_remix_config()

        # Assert
        self.assertIsNone(self.__get_session_fallback(stage))

    async def test_publish_remix_config_project_override_wins_over_legacy_capture(self):
        # Arrange
        core, stage, _capture_layer = self.__make_core(
            _LEGACY_ATTRIBUTE, _CONFIG_A, mod_action=lambda attribute: attribute.Set(_CONFIG_OVERRIDE)
        )

        # Act
        core._publish_remix_config()

        # Assert
        self.assertEqual(self.__get_composed_config(stage), _CONFIG_OVERRIDE)

    async def test_publish_remix_config_blocked_override_stops_the_fallback(self):
        # Arrange
        core, stage, _capture_layer = self.__make_core(
            _LEGACY_ATTRIBUTE, _CONFIG_A, mod_action=lambda attribute: attribute.Block()
        )

        # Act
        core._publish_remix_config()

        # Assert
        self.assertIsNone(self.__get_session_fallback(stage))

    async def test_publish_remix_config_legacy_capture_leaves_capture_layer_untouched(self):
        # Arrange
        core, _stage, capture_layer = self.__make_core(_LEGACY_ATTRIBUTE, _CONFIG_A)

        # Act
        core._publish_remix_config()

        # Assert
        self.assertIsNone(capture_layer.GetAttributeAtPath(f"{_REMIX_SETTINGS}.{_NAMESPACED_ATTRIBUTE}"))

    async def test_publish_remix_config_capture_swap_replaces_previous_config(self):
        # Arrange
        core, stage, capture_layer = self.__make_core(_LEGACY_ATTRIBUTE, _CONFIG_A)
        core._publish_remix_config()
        # A capture swap puts a different capture under the same session layer.
        capture_layer.GetAttributeAtPath(f"{_REMIX_SETTINGS}.{_LEGACY_ATTRIBUTE}").default = _CONFIG_B

        # Act
        core._publish_remix_config()

        # Assert
        self.assertEqual(self.__get_composed_config(stage), _CONFIG_B)

    async def test_publish_remix_config_capture_without_config_clears_previous_config(self):
        # Arrange
        core, stage, capture_layer = self.__make_core(_LEGACY_ATTRIBUTE, _CONFIG_A)
        core._publish_remix_config()
        del capture_layer.GetPrimAtPath(_REMIX_SETTINGS).properties[_LEGACY_ATTRIBUTE]

        # Act
        core._publish_remix_config()

        # Assert
        self.assertIsNone(self.__get_composed_config(stage))
