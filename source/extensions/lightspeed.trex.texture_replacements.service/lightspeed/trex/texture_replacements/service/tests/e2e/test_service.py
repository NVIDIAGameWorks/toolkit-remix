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
from urllib.parse import quote

import omni.usd
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP
from omni.flux.service.factory import get_instance as get_service_factory_instance
from omni.flux.utils.common.api import send_request
from omni.flux.utils.widget.resources import get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.services.core import main


class TestTextureReplacementsService(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.project_path = get_test_data("usd/project_example/combined.usda")

        self.context = omni.usd.get_context()
        await open_stage(self.project_path)

        factory = get_service_factory_instance()

        # Register the service in the app
        self.service = factory.get_plugin_from_name("TextureReplacementsService")()
        main.register_router(router=self.service.router, prefix=self.service.prefix)

    # After running each test
    async def tearDown(self):
        main.deregister_router(router=self.service.router, prefix=self.service.prefix)

        self.service = None

        if self.context.can_close_stage():
            await self.context.close_stage_async()

        self.context = None
        self.project_path = None

    async def test_get_textures_returns_expected_response(self):
        project_dir = Path(get_test_data("usd/project_example"))

        for index, test_data in enumerate(
            [
                (
                    "",
                    {
                        "textures": [
                            [
                                "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture",
                                str(
                                    project_dir
                                    / ".deps"
                                    / "captures"
                                    / "materials"
                                    / "textures"
                                    / "BC868CE5A075ABB1.dds"
                                ),
                            ],
                            [
                                "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:metallic_texture",
                                str(project_dir / "sources" / "textures" / "T_MetalPanelWall_HeavyRust_metallic.png"),
                            ],
                            [
                                "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:normalmap_texture",
                                str(project_dir / "sources" / "textures" / "T_MetalPanelWall_HeavyRust_normal.png"),
                            ],
                            [
                                "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:reflectionroughness_texture",
                                str(project_dir / "sources" / "textures" / "T_MetalPanelWall_HeavyRust_roughness.png"),
                            ],
                        ]
                    },
                ),
                (
                    "texture_types=METALLIC&texture_types=ROUGHNESS",
                    {
                        "textures": [
                            [
                                "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:metallic_texture",
                                str(project_dir / "sources" / "textures" / "T_MetalPanelWall_HeavyRust_metallic.png"),
                            ],
                            [
                                "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:reflectionroughness_texture",
                                str(project_dir / "sources" / "textures" / "T_MetalPanelWall_HeavyRust_roughness.png"),
                            ],
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
                self.assertEqual(str(response).lower(), str(expected_response).lower())

    async def test_get_texture_types_returns_expected_response(self):
        # Arrange
        pass

        # Act
        response = await send_request("GET", f"{self.service.prefix}/types")

        # Assert
        self.assertEqual(
            response,
            {
                "texture_types": [
                    "DIFFUSE",
                    "ROUGHNESS",
                    "ANISOTROPY",
                    "METALLIC",
                    "EMISSIVE",
                    "NORMAL_OGL",
                    "NORMAL_DX",
                    "NORMAL_OTH",
                    "HEIGHT",
                    "TRANSMITTANCE",
                    "MEASUREMENT_DISTANCE",
                    "SINGLE_SCATTERING",
                    "OTHER",
                ]
            },
        )

    async def test_get_texture_material_returns_expected_response(self):
        # Arrange
        asset_path = quote("/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:metallic_texture", safe="")
        expected_material = "/RootNode/Looks/mat_BC868CE5A075ABB1"

        # Act
        response = await send_request("GET", f"{self.service.prefix}/{asset_path}/material")

        # Assert
        self.assertEqual(response, {"asset_paths": [expected_material]})

    async def test_get_texture_material_inputs_no_args_returns_all_inputs(self):
        # Arrange
        base_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader."
        asset_path = quote(f"{base_path}inputs:metallic_texture", safe="")

        expected_inputs = sorted({f"{base_path}{i}" for i in TEXTURE_TYPE_INPUT_MAP.values()})

        # Act
        response = await send_request("GET", f"{self.service.prefix}/{asset_path}/material/inputs")

        # Assert
        self.assertListEqual(sorted(response.get("asset_paths", [])), expected_inputs)

    async def test_get_texture_material_inputs_texture_type_returns_expected_inputs(self):
        # Arrange
        base_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader."
        asset_path = quote(f"{base_path}inputs:metallic_texture", safe="")

        expected_inputs = [f"{base_path}inputs:reflectionroughness_texture"]

        # Act
        response = await send_request(
            "GET", f"{self.service.prefix}/{asset_path}/material/inputs?texture_type=ROUGHNESS"
        )

        # Assert
        self.assertEqual(response, {"asset_paths": expected_inputs})

    async def test_override_textures_overrides_expected_inputs(self):
        # Arrange
        stage = self.context.get_stage()
        diffuse_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        metallic_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:metallic_texture"

        asset_relative_path = "/ingested_assets/output/good/Bricks092-PNG_Color.a.rtex.dds"
        asset_path = str(get_test_data(f"usd/project_example{asset_relative_path}"))

        # Act
        response = await send_request(
            "PUT",
            f"{self.service.prefix}/",
            json={
                "force": False,
                "textures": [
                    [diffuse_input_path, asset_path],
                    [metallic_input_path, asset_path],
                ],
            },
        )

        # Assert
        self.assertEqual(response, "OK")

        diffuse_input = stage.GetAttributeAtPath(diffuse_input_path)
        metallic_input = stage.GetAttributeAtPath(metallic_input_path)

        self.assertEqual(diffuse_input.Get().path, f".{asset_relative_path}")
        self.assertEqual(metallic_input.Get().path, f".{asset_relative_path}")

    async def test_override_textures_new_texture_creates_expected_input(self):
        # Arrange
        stage = self.context.get_stage()
        diffuse_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        emissive_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:emissive_mask_texture"

        asset_relative_path = "/ingested_assets/output/good/Bricks092-PNG_Color.a.rtex.dds"
        asset_path = str(get_test_data(f"usd/project_example{asset_relative_path}"))

        # Act
        response = await send_request(
            "PUT",
            f"{self.service.prefix}/",
            json={
                "force": False,
                "textures": [
                    [diffuse_input_path, asset_path],  # Existing
                    [emissive_input_path, asset_path],  # New
                ],
            },
        )

        # Assert
        self.assertEqual(response, "OK")

        diffuse_input = stage.GetAttributeAtPath(diffuse_input_path)
        emissive_input = stage.GetAttributeAtPath(emissive_input_path)

        self.assertEqual(diffuse_input.Get().path, f".{asset_relative_path}")
        self.assertEqual(emissive_input.Get().path, f".{asset_relative_path}")
