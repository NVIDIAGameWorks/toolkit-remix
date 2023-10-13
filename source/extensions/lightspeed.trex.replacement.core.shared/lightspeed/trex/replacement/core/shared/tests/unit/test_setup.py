import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import omni.client
import omni.kit.test
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCore
from pxr import Sdf, Usd, UsdGeom


class MockListEntry:
    def __init__(self, path: str, size: int = 0, access: int = 0, flags=omni.client.ItemFlags.READABLE_FILE):
        self.relative_path = path
        self.size = size
        self.access = access
        self.flags = flags
        self.modified_time = datetime.now()


class TestSetup(omni.kit.test.AsyncTestCase):

    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()

    async def test_is_path_valid_existing_file_valid_usd(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usd")), True, True)

    async def test_is_path_valid_existing_file_valid_usda(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usda")), True, True)

    async def test_is_path_valid_existing_file_valid_usdc(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usdc")), True, True)

    async def test_is_path_valid_new_file_valid_usd(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usd")), False, True)

    async def test_is_path_valid_new_file_valid_usda(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usda")), False, True)

    async def test_is_path_valid_new_file_valid_usdc(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.usdc")), False, True)

    async def test_is_path_valid_invalid_path_empty(self):
        await self.__run_test_is_path_valid("", False, False)

    async def test_is_path_valid_invalid_not_usd(self):
        await self.__run_test_is_path_valid(str(Path(f"{self.temp_dir.name}/replacements.abc")), False, False)

    async def test_is_path_valid_invalid_is_in_capture_dir(self):
        await self.__run_test_is_path_valid(
            str(Path(f"{self.temp_dir.name}/capture/subdir/replacements.usd")), False, False
        )

    async def test_is_path_valid_invalid_is_in_gamereadyassets_dir(self):
        await self.__run_test_is_path_valid(
            str(Path(f"{self.temp_dir.name}/gameReadyAssets/subdir/replacements.usd")), False, False
        )

    async def test_is_path_valid_invalid_not_writable(self):
        # Arrange
        path = Path(f"{self.temp_dir.name}/replacements.usd")

        with patch.object(omni.client, "stat") as mocked:
            read_only_entry = MockListEntry(str(path), flags=omni.client.ItemFlags.READABLE_FILE)
            mocked.return_value = (omni.client.Result.OK, read_only_entry)

            # Act
            is_valid = _ReplacementCore.is_path_valid(str(path), True)

            # Assert
            self.assertEqual(False, is_valid)

    async def test_is_path_valid_invalid_cannot_have_children(self):
        # Arrange
        path = Path(f"{self.temp_dir.name}/replacements.usd")

        with patch.object(omni.client, "stat") as mocked:
            read_only_entry = MockListEntry(str(path), flags=omni.client.ItemFlags.READABLE_FILE)
            mocked.return_value = (omni.client.Result.OK, read_only_entry)

            # Act
            is_valid = _ReplacementCore.is_path_valid(str(path), False)

            # Assert
            self.assertEqual(False, is_valid)

    async def __run_test_is_path_valid(self, path: str, existing: bool, expected_result: bool):
        # Arrange
        if path and existing:
            os.makedirs(Path(path).parent, exist_ok=True)
            with open(path, "xb"):
                pass

        # Act
        is_valid = _ReplacementCore.is_path_valid(path, existing)

        # Assert
        self.assertEqual(expected_result, is_valid)

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

    async def __create_setup_01(self):
        """
        Create a basic setup with 3 meshes, 3 materials and 3 lights
        """
        stage, layer_replacement, layer_sub_replacement, layer_capture = await self.__create_basic_layers()

        # create 3 meshes, 3 materials, 3 lights
        mesh_base_path = "/RootNode/meshes/mesh_BAC90CAA733B085"
        with Usd.EditContext(stage, layer_capture):
            for i in range(3):
                prim_path = f"{mesh_base_path}{i}"
                UsdGeom.Cube.Define(stage, prim_path)

                prim_path2 = f"{prim_path}/cube_{i}"
                UsdGeom.Cube.Define(stage, prim_path2)

                mat_path = f"/RootNode/Looks/mat_BC868CE5A075ABB{i}"
                omni.kit.commands.execute(
                    "CreateMdlMaterialPrim", mtl_url="OmniPBR.mdl", mtl_name="OmniPBR", mtl_path=mat_path
                )
                omni.kit.commands.execute("BindMaterialCommand", prim_path=prim_path, material_path=mat_path)

                light_path = f"/RootNode/lights/light_9907D0B07D04007{i}"
                omni.kit.commands.execute("CreatePrim", prim_type="RectLight", prim_path=light_path)
        return stage, layer_replacement, layer_sub_replacement

    async def test_get_replaced_hashes_layer_doesnt_exist(self):
        core = _ReplacementCore("")
        self.assertEqual(core.get_replaced_hashes(path="123456789"), {})

    async def test_get_replaced_hashes_from_path(self):
        stage, layer_replacement, _layer_sub_replacement = await self.__create_setup_01()
        layer_manager = _LayerManagerCore()
        self.assertEqual(layer_manager.get_layer(_LayerType.replacement).identifier, layer_replacement.identifier)

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        # import it
        core = _ReplacementCore("")
        self.assertFalse(Path(replacement_01_path).exists())
        core.import_replacement_layer(replacement_01_path, use_existing_layer=False)

        # grab the new layer
        layer_manager = _LayerManagerCore()
        layer = layer_manager.get_layer(_LayerType.replacement)

        with Usd.EditContext(stage, layer):
            mesh_base_path = "/RootNode/meshes/mesh_BAC90CAA733B0850"
            prim0 = stage.GetPrimAtPath(mesh_base_path)
            prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

        self.assertEqual(list(core.get_replaced_hashes(path=replacement_01_path)[layer].keys()), ["BAC90CAA733B0850"])

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_get_replaced_hashes_layer_deleted(self):
        _stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()
        layer_manager = _LayerManagerCore()
        self.assertEqual(layer_manager.get_layer(_LayerType.replacement).identifier, layer_replacement.identifier)

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/sub_replacement_01.usd"
        # import it
        stage_sub_replacement = Usd.Stage.CreateNew(replacement_01_path)
        layer_sub_replacement = stage_sub_replacement.GetRootLayer()
        layer_replacement.subLayerPaths.insert(0, layer_sub_replacement.identifier)

        core = _ReplacementCore("")
        with patch("pxr.Sdf.Layer.FindOrOpen") as mock_find:
            mock_find.return_value = False
            self.assertEqual(core.get_replaced_hashes(), {})

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_get_replaced_hashes_one_sub_mesh(self):
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                mesh_base_path = "/RootNode/meshes/mesh_BAC90CAA733B0850/cube_0"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer):
                    prim0 = stage.GetPrimAtPath(mesh_base_path)
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(list(core.get_replaced_hashes()[layer_replacement].keys()), ["BAC90CAA733B0850"])

    async def test_get_replaced_hashes_one_mesh(self):
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                mesh_base_path = "/RootNode/meshes/mesh_BAC90CAA733B085"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer_replacement):
                    prim0 = stage.GetPrimAtPath(f"{mesh_base_path}0")
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(list(core.get_replaced_hashes()[layer_replacement].keys()), ["BAC90CAA733B0850"])

    async def test_get_replaced_hashes_two_meshes(self):
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                mesh_base_path = "/RootNode/meshes/mesh_BAC90CAA733B085"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer_replacement):
                    prim0 = stage.GetPrimAtPath(f"{mesh_base_path}0")
                    prim1 = stage.GetPrimAtPath(f"{mesh_base_path}1")
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
                    prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(
                    sorted(core.get_replaced_hashes()[layer_replacement].keys()),
                    ["BAC90CAA733B0850", "BAC90CAA733B0851"],
                )

    async def test_get_replaced_hashes_one_material(self):
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                mat_path = "/RootNode/Looks/mat_BC868CE5A075ABB"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer_replacement):
                    prim0 = stage.GetPrimAtPath(f"{mat_path}0")
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(list(core.get_replaced_hashes()[layer_replacement].keys()), ["BC868CE5A075ABB0"])

    async def test_get_replaced_hashes_two_material(self):
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                mat_path = "/RootNode/Looks/mat_BC868CE5A075ABB"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer_replacement):
                    prim0 = stage.GetPrimAtPath(f"{mat_path}0")
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
                    prim1 = stage.GetPrimAtPath(f"{mat_path}1")
                    prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(
                    sorted(core.get_replaced_hashes()[layer_replacement].keys()),
                    ["BC868CE5A075ABB0", "BC868CE5A075ABB1"],
                )

    async def test_get_replaced_hashes_one_light(self):
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                light_path = "/RootNode/lights/light_9907D0B07D04007"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer_replacement):
                    prim0 = stage.GetPrimAtPath(f"{light_path}0")
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(list(core.get_replaced_hashes()[layer_replacement].keys()), ["9907D0B07D040070"])

    async def test_get_replaced_hashes_two_light(self):
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                light_path = "/RootNode/lights/light_9907D0B07D04007"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer_replacement):
                    prim0 = stage.GetPrimAtPath(f"{light_path}0")
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
                    prim1 = stage.GetPrimAtPath(f"{light_path}1")
                    prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(
                    sorted(core.get_replaced_hashes()[layer_replacement].keys()),
                    ["9907D0B07D040070", "9907D0B07D040071"],
                )

    async def test_get_replaced_hashes_random_override_01(self):
        """Add a random override that is not on a mesh or material or light. We should not return any replaced hash"""
        stage, layer_replacement, layer_sub_replacement = await self.__create_setup_01()

        for layer in [layer_replacement, layer_sub_replacement]:
            with self.subTest(name=f"Test on layer {layer}"):
                core = _ReplacementCore("")

                meshes_base_path = "/RootNode/meshes"
                # create 2 random override on 2 first meshes
                with Usd.EditContext(stage, layer_replacement):
                    prim0 = stage.GetPrimAtPath(meshes_base_path)
                    prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)

                self.assertEqual(list(core.get_replaced_hashes()[layer_replacement].keys()), [])

    async def test_import_replacement_layer_default(self):
        _stage, layer_replacement, _layer_sub_replacement = await self.__create_setup_01()
        layer_manager = _LayerManagerCore()
        self.assertEqual(layer_manager.get_layer(_LayerType.replacement).identifier, layer_replacement.identifier)

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        stage_replacement_01 = Usd.Stage.CreateNew(replacement_01_path)
        # import it
        core = _ReplacementCore("")
        core.import_replacement_layer(stage_replacement_01.GetRootLayer().realPath)

        self.assertEqual(
            layer_manager.get_layer(_LayerType.replacement).identifier, stage_replacement_01.GetRootLayer().identifier
        )

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_import_replacement_layer_no_capture(self):
        _stage, layer_replacement, _layer_sub_replacement = await self.__create_setup_01()
        layer_manager = _LayerManagerCore()
        self.assertEqual(layer_manager.get_layer(_LayerType.replacement).identifier, layer_replacement.identifier)

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        stage_replacement_01 = Usd.Stage.CreateNew(replacement_01_path)
        # import it
        core = _ReplacementCore("")

        with patch.object(core._layer_manager, "get_layer") as mock_get_layer, patch("carb.log_error"):  # NOQA
            mock_get_layer.return_value = False
            core.import_replacement_layer(stage_replacement_01.GetRootLayer().realPath)
        self.assertNotEqual(
            layer_manager.get_layer(_LayerType.replacement).identifier, stage_replacement_01.GetRootLayer().identifier
        )
        self.assertEqual(layer_manager.get_layer(_LayerType.replacement).identifier, layer_replacement.identifier)

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_import_replacement_layer_create(self):
        _stage, layer_replacement, _layer_sub_replacement = await self.__create_setup_01()
        layer_manager = _LayerManagerCore()
        self.assertEqual(layer_manager.get_layer(_LayerType.replacement).identifier, layer_replacement.identifier)

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        # import it
        core = _ReplacementCore("")

        self.assertFalse(Path(replacement_01_path).exists())
        core.import_replacement_layer(replacement_01_path, use_existing_layer=False)

        self.assertTrue(Path(replacement_01_path).exists())
        self.assertEqual(
            Path(layer_manager.get_layer(_LayerType.replacement).realPath).as_posix(),
            Path(replacement_01_path).as_posix(),
        )

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_import_replacement_layer_create_existing(self):
        _stage, layer_replacement, _layer_sub_replacement = await self.__create_setup_01()
        layer_manager = _LayerManagerCore()
        self.assertEqual(layer_manager.get_layer(_LayerType.replacement).identifier, layer_replacement.identifier)

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        # import it
        core = _ReplacementCore("")

        self.assertFalse(Path(replacement_01_path).exists())
        Usd.Stage.CreateNew(replacement_01_path)
        self.assertTrue(Path(replacement_01_path).exists())
        core.import_replacement_layer(str(Path(replacement_01_path).resolve()), use_existing_layer=False)

        self.assertTrue(Path(replacement_01_path).exists())
        self.assertEqual(
            Path(layer_manager.get_layer(_LayerType.replacement).realPath).as_posix(),
            Path(replacement_01_path).resolve().as_posix(),
        )

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_is_mod_file_doesnt_exist(self):
        await self.__create_setup_01()

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        # import it
        core = _ReplacementCore("")

        # the file doesnt exist
        self.assertFalse(core.is_mod_file(replacement_01_path))
        Usd.Stage.CreateNew(replacement_01_path)

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_is_mod_file_exist_but_false(self):
        await self.__create_setup_01()

        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        # import it
        core = _ReplacementCore("")
        Usd.Stage.CreateNew(replacement_01_path)
        self.assertFalse(core.is_mod_file(replacement_01_path))

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_is_mod_file_exist_but_true(self):
        await self.__create_setup_01()
        # create another replacement layer
        replacement_01_path = f"{self.temp_dir.name}/replacement_01.usd"
        # import it
        core = _ReplacementCore("")
        Usd.Stage.CreateNew(replacement_01_path)
        core.import_replacement_layer(replacement_01_path, use_existing_layer=False)
        self.assertTrue(core.is_mod_file(replacement_01_path))

        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_group_replaced_hashes_two_mesh(self):
        stage, layer_replacement, _layer_sub_replacement = await self.__create_setup_01()

        # import it
        core = _ReplacementCore("")

        mesh_base_path = "/RootNode/meshes/mesh_BAC90CAA733B085"
        light_path = "/RootNode/lights/light_9907D0B07D04007"
        # create 2 random override on 2 first meshes
        with Usd.EditContext(stage, layer_replacement):
            prim0 = stage.GetPrimAtPath(f"{mesh_base_path}0")
            prim0.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
            prim1 = stage.GetPrimAtPath(f"{mesh_base_path}1")
            prim1.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
            prim2 = stage.GetPrimAtPath(f"{light_path}0")
            prim2.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(True)
            hashes = core.get_replaced_hashes()
            grouped_replaced_hashes = core.group_replaced_hashes((layer_replacement, hashes[layer_replacement]))

            self.assertEqual(grouped_replaced_hashes, {"BAC90CAA733B0850", "BAC90CAA733B0851", "9907D0B07D040070"})

    async def test_group_replaced_hashes_one_material_two_meshes(self):
        """We override 2 meshes with 1 new material, so we would have only 1 override"""
        stage, layer_replacement, _layer_sub_replacement = await self.__create_setup_01()

        # import it
        core = _ReplacementCore("")

        mesh_base_path = "/RootNode/meshes/mesh_BAC90CAA733B085"
        mat_path = "/RootNode/Looks/mat_BC868CE5A075ABB"
        # create 2 random override on 2 first meshes
        with Usd.EditContext(stage, layer_replacement):
            omni.kit.commands.execute(
                "BindMaterialCommand", prim_path=f"{mesh_base_path}0", material_path=f"{mat_path}0"
            )
            omni.kit.commands.execute(
                "BindMaterialCommand", prim_path=f"{mesh_base_path}1", material_path=f"{mat_path}0"
            )
            hashes = core.get_replaced_hashes()
            grouped_replaced_hashes = core.group_replaced_hashes((layer_replacement, hashes[layer_replacement]))

            self.assertEqual(grouped_replaced_hashes, {"BC868CE5A075ABB0"})
