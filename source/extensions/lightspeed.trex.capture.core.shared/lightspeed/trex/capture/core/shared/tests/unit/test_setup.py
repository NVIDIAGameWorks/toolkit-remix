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
import omni.client
import omni.kit.test
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from pxr import Sdf, Usd, UsdGeom


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

    async def test_is_capture_file_true(self):
        _stage, _layer_replacement, _layer_sub_replacement, layer_capture = await self.__create_setup_01()
        core = _CaptureCoreSetup("")
        result = core.is_capture_file(layer_capture.identifier)
        self.assertTrue(result)

    async def test_is_capture_file_false_wrong_customdata(self):
        _stage, layer_replacement, _layer_sub_replacement, _layer_capture = await self.__create_setup_01()
        core = _CaptureCoreSetup("")
        result = core.is_capture_file(layer_replacement.identifier)
        self.assertFalse(result)

    async def test_is_capture_file_false_no_customdata(self):
        _stage, _layer_replacement, layer_sub_replacement, _layer_capture = await self.__create_setup_01()
        core = _CaptureCoreSetup("")
        result = core.is_capture_file(layer_sub_replacement.identifier)
        self.assertFalse(result)

    async def test_is_capture_file_false_no_layer(self):
        core = _CaptureCoreSetup("")
        result = core.is_capture_file("123456789")
        self.assertFalse(result)

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
