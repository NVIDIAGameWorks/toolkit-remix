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
from unittest.mock import patch
from urllib.parse import quote

import omni.usd
from lightspeed.trex.texture_replacements.core.shared import setup as texture_replacements_setup
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP
from omni.flux.service.factory import get_instance as get_service_factory_instance
from omni.flux.utils.common.api import send_request
from omni.flux.utils.widget.resources import get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.services.core import main
from pxr import Sdf


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
                                    / "deps"
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
                # Query the live service both with and without type filters.
                response = await send_request("GET", f"{self.service.prefix}/?{params}")

                # Compare the paths case-insensitively because Windows path casing is not stable.
                self.assertEqual(str(response).lower(), str(expected_response).lower())

    async def test_get_texture_types_returns_expected_response(self):
        # Ask the registered service for the texture types exposed to clients.
        response = await send_request("GET", f"{self.service.prefix}/types")

        # Keep the public response synchronized with every supported replacement type.
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
        prim_path = quote("/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:metallic_texture", safe="")
        expected_material = "/RootNode/Looks/mat_BC868CE5A075ABB1"

        # Resolve the owning material through the running HTTP service.
        response = await send_request("GET", f"{self.service.prefix}/{prim_path}/material")

        self.assertEqual(response, {"prim_paths": [expected_material]})

    async def test_get_texture_material_inputs_no_args_returns_all_inputs(self):
        base_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader."
        prim_path = quote(f"{base_path}inputs:metallic_texture", safe="")

        expected_inputs = sorted({f"{base_path}{i}" for i in TEXTURE_TYPE_INPUT_MAP.values()})

        # Omitting a type filter returns every supported input on the material.
        response = await send_request("GET", f"{self.service.prefix}/{prim_path}/material/inputs")

        self.assertListEqual(sorted(response.get("prim_paths", [])), expected_inputs)

    async def test_get_texture_material_inputs_texture_type_returns_expected_inputs(self):
        base_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader."
        prim_path = quote(f"{base_path}inputs:metallic_texture", safe="")

        expected_inputs = [f"{base_path}inputs:reflectionroughness_texture"]

        # A texture-type filter narrows the response to the matching material input.
        response = await send_request(
            "GET", f"{self.service.prefix}/{prim_path}/material/inputs?texture_type=ROUGHNESS"
        )

        self.assertEqual(response, {"prim_paths": expected_inputs})

    async def test_override_textures_overrides_expected_inputs(self):
        stage = self.context.get_stage()
        diffuse_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        metallic_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:metallic_texture"

        asset_relative_path = "/ingested_assets/output/good/Bricks092-PNG_Color.a.rtex.dds"
        prim_path = str(get_test_data(f"usd/project_example{asset_relative_path}"))

        # Replace two existing shader inputs through the public service endpoint.
        response = await send_request(
            "PUT",
            f"{self.service.prefix}/",
            json={
                "force": False,
                "textures": [
                    [diffuse_input_path, prim_path],
                    [metallic_input_path, prim_path],
                ],
            },
        )

        self.assertEqual(response, "OK")

        # The live stage authors project-relative paths for both replacements.
        diffuse_input = stage.GetAttributeAtPath(diffuse_input_path)
        metallic_input = stage.GetAttributeAtPath(metallic_input_path)

        self.assertEqual(diffuse_input.Get().path, f".{asset_relative_path}")
        self.assertEqual(metallic_input.Get().path, f".{asset_relative_path}")

    async def test_override_textures_new_texture_creates_expected_input(self):
        stage = self.context.get_stage()
        diffuse_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        emissive_input_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:emissive_mask_texture"

        asset_relative_path = "/ingested_assets/output/good/Bricks092-PNG_Color.a.rtex.dds"
        prim_path = str(get_test_data(f"usd/project_example{asset_relative_path}"))

        # Submit one existing input and one missing input in the same replacement request.
        response = await send_request(
            "PUT",
            f"{self.service.prefix}/",
            json={
                "force": False,
                "textures": [
                    [diffuse_input_path, prim_path],  # Existing
                    [emissive_input_path, prim_path],  # New
                ],
            },
        )

        self.assertEqual(response, "OK")

        # The service updates the existing input and creates the missing shader input.
        diffuse_input = stage.GetAttributeAtPath(diffuse_input_path)
        emissive_input = stage.GetAttributeAtPath(emissive_input_path)

        self.assertEqual(diffuse_input.Get().path, f".{asset_relative_path}")
        self.assertEqual(emissive_input.Get().path, f".{asset_relative_path}")

    async def test_force_override_requires_and_forwards_exact_current_layer_value(self):
        """A forced service write succeeds only with the exact current edit-layer baseline."""
        # Read the current authored value from the live edit layer and send it through the HTTP API.
        stage = self.context.get_stage()
        texture_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        edit_layer = stage.GetEditTarget().GetLayer()
        attribute_spec = edit_layer.GetAttributeAtPath(texture_path)
        current_value = attribute_spec.default.path if attribute_spec is not None else None

        response = await send_request(
            "PUT",
            f"{self.service.prefix}/",
            json={
                "force": True,
                "textures": [[texture_path, "C:/missing/confirmed-original.dds"]],
                "expected_current_textures": [[texture_path, current_value]],
            },
        )

        # The service accepts the compare-and-set request and authors the replacement.
        self.assertEqual(response, "OK")
        self.assertTrue(edit_layer.GetAttributeAtPath(texture_path).default.path.endswith("confirmed-original.dds"))

    async def test_force_override_preserves_exact_nucleus_baseline(self):
        """The request model preserves an authored Nucleus URL byte-for-byte for CAS."""
        # Author a Nucleus URL on the live stage and use that exact value as the HTTP baseline.
        stage = self.context.get_stage()
        texture_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        edit_layer = stage.GetEditTarget().GetLayer()
        nucleus_value = "omniverse://server/share/current.dds"
        stage.GetAttributeAtPath(texture_path).Set(Sdf.AssetPath(nucleus_value))

        response = await send_request(
            "PUT",
            f"{self.service.prefix}/",
            json={
                "force": True,
                "textures": [[texture_path, "C:/missing/confirmed-original.dds"]],
                "expected_current_textures": [[texture_path, nucleus_value]],
            },
        )

        # The service preserves the URL through transport and accepts the replacement.
        self.assertEqual(response, "OK")
        self.assertTrue(edit_layer.GetAttributeAtPath(texture_path).default.path.endswith("confirmed-original.dds"))

    async def test_force_override_rejects_stale_current_layer_value(self):
        """A stale forced service write returns a validation response without mutating the layer."""
        # Snapshot the live edit layer before sending a stale compare-and-set baseline.
        stage = self.context.get_stage()
        texture_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        edit_layer = stage.GetEditTarget().GetLayer()
        before = edit_layer.ExportToString()

        response = await send_request(
            "PUT",
            f"{self.service.prefix}/",
            raw_response=True,
            json={
                "force": True,
                "textures": [[texture_path, "C:/missing/confirmed-original.dds"]],
                "expected_current_textures": [[texture_path, "C:/stale/value.dds"]],
            },
        )

        # The HTTP request is rejected and the layer remains byte-for-byte unchanged.
        self.assertEqual(response.status_code, 422)
        self.assertEqual(edit_layer.ExportToString(), before)

    async def test_force_override_maps_command_boundary_race_to_conflict(self):
        """A target edit between core preflight and command execution remains a client conflict."""
        # Reproduce a competing author by applying a real layer edit at the command boundary.
        stage = self.context.get_stage()
        texture_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
        edit_layer = stage.GetEditTarget().GetLayer()
        attribute_spec = edit_layer.GetAttributeAtPath(texture_path)
        current_value = attribute_spec.default.path if attribute_spec is not None else None
        external_value = Sdf.AssetPath("C:/external/raced.dds")
        execute_command = texture_replacements_setup.commands.execute

        def execute_after_external_edit(*args, **kwargs):
            stage.GetAttributeAtPath(texture_path).Set(external_value)
            return execute_command(*args, **kwargs)

        # Send the public HTTP request while the competing edit lands between validation and authoring.
        with patch.object(texture_replacements_setup.commands, "execute", side_effect=execute_after_external_edit):
            response = await send_request(
                "PUT",
                f"{self.service.prefix}/",
                raw_response=True,
                json={
                    "force": True,
                    "textures": [[texture_path, "C:/missing/confirmed-original.dds"]],
                    "expected_current_textures": [[texture_path, current_value]],
                },
            )

        # The client receives a conflict and the external edit remains authoritative.
        self.assertEqual(response.status_code, 422)
        self.assertEqual(edit_layer.GetAttributeAtPath(texture_path).default, external_value)
