"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.usd
import lightspeed.trex.comfyui.core.texture as texture
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdGeom, UsdShade


class TestTextureE2E(AsyncTestCase):
    """Tests texture discovery through a live USD context and native schemas."""

    async def setUp(self) -> None:
        """Create a fresh stage in the product USD context."""
        self._context = omni.usd.get_context()
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        await self._context.new_stage_async()

    async def tearDown(self) -> None:
        """Close the live test stage."""
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()

    async def test_iter_texture_paths_follows_binding_connections(self):
        """Prim extraction follows the USD-computed material binding."""
        stage = self._context.get_stage()
        mesh = UsdGeom.Mesh.Define(stage, "/World/Mesh")
        material = UsdShade.Material.Define(stage, "/World/Looks/Material")
        shader = UsdShade.Shader.Define(stage, "/World/Looks/Material/Shader")
        shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("C:/textures/albedo.png"))
        shader_output = shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput("mdl").ConnectToSource(shader_output)
        UsdShade.MaterialBindingAPI(mesh).Bind(material)

        # Ask the production resolver to follow the composed mesh-to-material-to-shader connections.
        paths = list(texture.iter_texture_paths_for_prim("/World/Mesh", context_name=""))

        self.assertEqual(paths, ["C:/textures/albedo.png"])

    async def test_iter_texture_paths_returns_empty_for_unbound_prim(self):
        """Prim extraction returns no paths for empty material bindings."""
        stage = self._context.get_stage()
        UsdGeom.Mesh.Define(stage, "/World/Unbound")

        # Resolve an authored mesh that has no material binding or texture inputs.
        paths = list(texture.iter_texture_paths_for_prim("/World/Unbound", context_name=""))

        self.assertEqual(paths, [])
