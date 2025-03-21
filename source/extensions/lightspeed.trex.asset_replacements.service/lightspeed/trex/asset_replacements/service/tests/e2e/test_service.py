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

import omni.usd
from omni.flux.service.factory import get_instance as get_service_factory_instance
from omni.flux.utils.common.api import send_request
from omni.flux.utils.widget.resources import get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.services.core import main


class TestAssetReplacementsService(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.project_path = get_test_data("usd/project_example/combined.usda")

        self.context = omni.usd.get_context()
        await open_stage(self.project_path)

        factory = get_service_factory_instance()

        # Register the service in the app
        self.service = factory.get_plugin_from_name("AssetReplacementsService")()
        main.register_router(router=self.service.router, prefix=self.service.prefix)

    # After running each test
    async def tearDown(self):
        main.deregister_router(router=self.service.router, prefix=self.service.prefix)

        self.service = None

        if self.context.can_close_stage():
            await self.context.close_stage_async()

        self.context = None
        self.project_path = None

    async def test_get_default_model_asset_path_directory_returns_expected_response(self):
        # Arrange
        expected_value = (Path(get_test_data("usd/project_example")) / "assets" / "models").as_posix()

        # Act
        response = await send_request("GET", f"{self.service.prefix}/default-directory/models")

        # Assert
        self.assertEqual(str(response).lower(), str({"asset_path": expected_value}).lower())

    async def test_get_default_texture_asset_path_directory_returns_expected_response(self):
        # Arrange
        expected_value = (Path(get_test_data("usd/project_example/")) / "assets" / "textures").as_posix()

        # Act
        response = await send_request("GET", f"{self.service.prefix}/default-directory/textures")

        # Assert
        self.assertEqual(str(response).lower(), str({"asset_path": expected_value}).lower())

    async def test_get_default_ingested_asset_path_directory_returns_expected_response(self):
        # Arrange
        expected_value = (Path(get_test_data("usd/project_example")) / "assets" / "ingested").as_posix()

        # Act
        response = await send_request("GET", f"{self.service.prefix}/default-directory")

        # Assert
        self.assertEqual(str(response).lower(), str({"asset_path": expected_value}).lower())

    async def test_get_assets_returns_expected_response(self):
        for index, test_data in enumerate(
            [
                (
                    "",
                    {
                        "asset_paths": [
                            "/RootNode/lights/light_9907D0B07D040077",
                            "/RootNode/lights/light_EDF9B59568FD1142",
                            "/RootNode/lights/light_0FBF0D906770A019",
                            "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh",
                            "/RootNode/meshes/mesh_CED45075A077A49A/mesh",
                            "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube",
                            "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube_01",
                            "/RootNode/Looks/mat_BC868CE5A075ABB1",
                        ]
                    },
                ),
                (
                    "asset_hashes=CED45075A077A49A&asset_hashes=BAC90CAA733B0859",
                    {
                        "asset_paths": [
                            "/RootNode/meshes/mesh_CED45075A077A49A/mesh",
                            "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube",
                            "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube_01",
                        ]
                    },
                ),
                (
                    "asset_types=lights",
                    {
                        "asset_paths": [
                            "/RootNode/lights/light_9907D0B07D040077",
                            "/RootNode/lights/light_EDF9B59568FD1142",
                            "/RootNode/lights/light_0FBF0D906770A019",
                        ]
                    },
                ),
            ]
        ):
            params, expected_response = test_data
            with self.subTest(name=f"test_{index}"):
                # Arrange
                pass

                # Act
                response = await send_request("GET", f"{self.service.prefix}/?{params}")

                # Assert
                self.assertEqual(response, expected_response)

    async def test_get_model_instances_returns_expected_response(self):
        # Arrange
        pass

        # Act
        response = await send_request(
            "GET", f"{self.service.prefix}/%2FRootNode%2Fmeshes%2Fmesh_CED45075A077A49A%2Fmesh/instances"
        )

        # Assert
        self.assertEqual(response, {"asset_paths": ["/RootNode/instances/inst_CED45075A077A49A_0/mesh"]})

    async def test_get_material_textures_returns_expected_response(self):
        # Arrange
        expected_diffuse_value = str(
            Path(get_test_data("usd/project_example"))
            / ".deps"
            / "captures"
            / "materials"
            / "textures"
            / "BC868CE5A075ABB1.dds"
        )
        expected_metallic_value = str(
            Path(get_test_data("usd/project_example"))
            / "sources"
            / "textures"
            / "T_MetalPanelWall_HeavyRust_metallic.png"
        )
        expected_normal_value = str(
            Path(get_test_data("usd/project_example"))
            / "sources"
            / "textures"
            / "T_MetalPanelWall_HeavyRust_normal.png"
        )
        expected_roughness_value = str(
            Path(get_test_data("usd/project_example"))
            / "sources"
            / "textures"
            / "T_MetalPanelWall_HeavyRust_roughness.png"
        )

        # Act
        response = await send_request(
            "GET", f"{self.service.prefix}/%2FRootNode%2FLooks%2Fmat_BC868CE5A075ABB1/textures"
        )

        # Assert
        self.assertEqual(
            str(response).lower(),
            str(
                {
                    "textures": [
                        ["/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture", expected_diffuse_value],
                        [
                            "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:metallic_texture",
                            expected_metallic_value,
                        ],
                        ["/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:normalmap_texture", expected_normal_value],
                        [
                            "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:reflectionroughness_texture",
                            expected_roughness_value,
                        ],
                    ]
                }
            ).lower(),
        )

    async def test_get_material_textures_args_returns_expected_response(self):
        # Arrange
        expected_diffuse_value = str(
            Path(get_test_data("usd/project_example"))
            / ".deps"
            / "captures"
            / "materials"
            / "textures"
            / "BC868CE5A075ABB1.dds"
        )
        expected_normal_value = str(
            Path(get_test_data("usd/project_example"))
            / "sources"
            / "textures"
            / "T_MetalPanelWall_HeavyRust_normal.png"
        )

        # Act
        response = await send_request(
            "GET",
            f"{self.service.prefix}/%2FRootNode%2FLooks%2Fmat_BC868CE5A075ABB1/textures?texture_types=DIFFUSE&texture_types=NORMAL_OGL",  # noqa E501
        )

        # Assert
        self.assertEqual(
            str(response).lower(),
            str(
                {
                    "textures": [
                        ["/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture", expected_diffuse_value],
                        ["/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:normalmap_texture", expected_normal_value],
                    ]
                }
            ).lower(),
        )

    async def test_get_asset_file_paths_returns_expected_response(self):
        # Arrange
        expected_relative_path = str(Path("meshes") / "mesh_CED45075A077A49A.usda")
        expected_layer_path = str(Path(get_test_data("usd/project_example")) / ".deps" / "captures" / "capture.usda")

        # Act
        response = await send_request(
            "GET",
            f"{self.service.prefix}/%2FRootNode%2Fmeshes%2Fmesh_CED45075A077A49A%2Fmesh/file-paths",
        )

        # Assert
        self.assertEqual(
            str(response).lower(),
            str(
                {
                    "reference_paths": [
                        ["/RootNode/meshes/mesh_CED45075A077A49A", [expected_relative_path, expected_layer_path]]
                    ]
                }
            ).lower(),
        )

    async def test_append_asset_file_path_should_add_new_reference(self):
        # Arrange
        append_asset_path = str(Path(get_test_data("usd/project_example/ingested_assets/output/good/cube.usda")))
        mod_layer = str(Path(get_test_data("usd/project_example/combined.usda"))).replace("\\", "\\\\")

        # Act
        response = await send_request(
            "PUT",
            f"{self.service.prefix}/%2FRootNode%2Fmeshes%2Fmesh_CED45075A077A49A%2Fmesh/file-paths",
            json={
                "asset_file_path": append_asset_path,
                "force": False,
            },
        )

        # Assert
        self.assertRegex(
            str(response).replace("\\\\", "\\").lower(),
            f"{{'reference_paths': \\[\\['/RootNode/meshes/mesh_CED45075A077A49A/ref_[0-9a-z]{{32}}', "
            f"\\['ingested_assets\\\\output\\\\good\\\\cube.usda', '{mod_layer}'\\]\\]\\]}}".lower(),
        )

        # Make sure the stage has the appended the reference
        ref_path = response["reference_paths"][0][0]
        self.assertTrue(self.context.get_stage().GetPrimAtPath(f"{ref_path}/Cube_01").IsValid())

    async def test_replace_asset_file_path_no_ref_should_replace_first_ref(self):
        # Arrange
        replace_asset_path = str(Path(get_test_data("usd/project_example/ingested_assets/output/good/cube.usda")))
        mod_layer = str(Path(get_test_data("usd/project_example/combined.usda"))).replace("\\", "\\\\")

        # Act
        response = await send_request(
            "PUT",
            f"{self.service.prefix}/%2FRootNode%2Fmeshes%2Fmesh_0AB745B8BEE1F16B%2Fmesh/file-paths",
            json={
                "asset_file_path": replace_asset_path,
                "force": False,
            },
        )

        # Assert
        self.assertRegex(
            str(response).replace("\\\\", "\\").lower(),
            f"{{'reference_paths': \\[\\['/RootNode/meshes/mesh_0AB745B8BEE1F16B/ref_[0-9a-z]{{32}}', "
            f"\\['ingested_assets\\\\output\\\\good\\\\cube.usda', '{mod_layer}'\\]\\]\\]}}".lower(),
        )

        # Make sure the stage has the appended the reference
        ref_path = response["reference_paths"][0][0]
        self.assertTrue(self.context.get_stage().GetPrimAtPath(f"{ref_path}/Cube_01").IsValid())

    async def test_replace_asset_file_path_with_ref_should_replace_expected_ref(self):
        # Arrange
        original_asset_path = "sources\\\\cube.usda"
        original_layer = str(Path(get_test_data("usd/project_example/replacements.usda"))).replace("\\", "\\\\")

        replace_asset_path = str(Path(get_test_data("usd/project_example/ingested_assets/output/good/cube.usda")))
        mod_layer = str(Path(get_test_data("usd/project_example/combined.usda"))).replace("\\", "\\\\")

        # Act
        response = await send_request(
            "PUT",
            f"{self.service.prefix}/%2FRootNode%2Fmeshes%2Fmesh_BAC90CAA733B0859%2Fref_c89e0497f4ff4dc4a7b70b79c85692da%2FCube_01/file-paths",  # noqa: E501
            json={
                "existing_asset_file_path": original_asset_path,
                "existing_asset_layer_id": original_layer,
                "asset_file_path": replace_asset_path,
                "force": False,
            },
        )

        # Assert
        self.assertRegex(
            str(response).replace("\\\\", "\\").lower(),
            f"{{'reference_paths': \\[\\['/RootNode/meshes/mesh_BAC90CAA733B0859/ref_[0-9a-z]{{32}}', "
            f"\\['ingested_assets\\\\output\\\\good\\\\cube.usda', '{mod_layer}'\\]\\]\\]}}".lower(),
        )

        # Make sure the stage has the appended the reference
        ref_path = response["reference_paths"][0][0]
        self.assertTrue(self.context.get_stage().GetPrimAtPath(f"{ref_path}/Cube_01").IsValid())

    async def test_set_selection_updates_stage_selection(self):
        # Arrange
        pass

        # Act
        response = await send_request(
            "PUT", f"{self.service.prefix}/selection/%2FRootNode%2Flights%2Flight_9907D0B07D040077"
        )

        # Assert
        self.assertEqual(response, "OK")
        self.assertEqual(
            self.context.get_selection().get_selected_prim_paths(), ["/RootNode/lights/light_9907D0B07D040077"]
        )
