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

__all__ = ["TestMaterialSnapshot"]

import json
import tempfile
from pathlib import Path

import numpy as np
import omni.client
from lightspeed.trex.alpha_cutout.core.material_snapshot import ALPHA_TEST_ALWAYS, define_material, snapshot_material
from omni.kit.test import AsyncTestCase
from pxr import Gf, Sdf, Usd, UsdShade

from .fixtures import MATERIAL_PATH, build_capture_stage, write_alpha_texture

_DESTINATION_PATH = "/Root/Looks/AlphaCutoutMaterial"


class TestMaterialSnapshot(AsyncTestCase):
    """Test capturing a material as data and rebuilding it."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._texture = write_alpha_texture(Path(self._temp_dir.name) / "alpha.png", np.full((4, 4), 255, np.uint8))
        self._stage = build_capture_stage(self._texture)
        self._material = UsdShade.Material(self._stage.GetPrimAtPath(MATERIAL_PATH))
        shader = UsdShade.Shader(self._stage.GetPrimAtPath(f"{MATERIAL_PATH}/Shader"))
        shader.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.5, 0.25, 1.0))
        shader.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(0.75)

    def tearDown(self):
        self._stage = None
        self._temp_dir.cleanup()

    async def test_snapshot_material_is_json_serializable_with_absolute_texture_and_bare_mdl(self):
        # Act
        snapshot = snapshot_material(self._material)

        # Assert
        json.dumps(snapshot)
        by_name = {entry["name"]: entry for entry in snapshot["attributes"]}
        self.assertEqual(by_name["info:mdl:sourceAsset"]["value"], {"asset": "AperturePBR_Opacity.mdl"})
        self.assertEqual(
            by_name["inputs:diffuse_texture"]["value"]["asset"].lower(),
            omni.client.normalize_url(self._texture).lower(),
        )
        self.assertEqual(by_name["inputs:diffuse_texture"]["color_space"], "auto")
        self.assertEqual(by_name["inputs:diffuse_color_constant"]["value"], [0.5, 0.25, 1.0])
        self.assertEqual(snapshot["outputs"], [{"name": "mdl:surface", "type": "token", "source": "out"}])

    async def test_snapshot_material_without_surface_shader_returns_none(self):
        # Arrange
        material = UsdShade.Material.Define(self._stage, "/RootNode/Looks/empty")

        # Act
        snapshot = snapshot_material(material)

        # Assert
        self.assertIsNone(snapshot)

    async def test_define_material_rebuilds_shader_inputs_module_and_surface_output(self):
        # Arrange
        snapshot = json.loads(json.dumps(snapshot_material(self._material)))
        destination = Usd.Stage.CreateInMemory()

        # Act
        material = define_material(destination, _DESTINATION_PATH, snapshot, False)

        # Assert
        shader = UsdShade.Shader(destination.GetPrimAtPath(f"{_DESTINATION_PATH}/Shader"))
        self.assertEqual(shader.GetSourceAsset("mdl").path, "AperturePBR_Opacity.mdl")
        self.assertEqual(shader.GetSourceAssetSubIdentifier("mdl"), "AperturePBR_Opacity")
        self.assertEqual(shader.GetImplementationSource(), UsdShade.Tokens.sourceAsset)
        self.assertEqual(shader.GetInput("diffuse_color_constant").Get(), Gf.Vec3f(0.5, 0.25, 1.0))
        self.assertAlmostEqual(shader.GetInput("reflection_roughness_constant").Get(), 0.75)
        self.assertEqual(shader.GetInput("diffuse_texture").GetAttr().GetColorSpace(), "auto")
        self.assertIsNone(shader.GetInput("alpha_test_type").Get())
        source, name, _ = material.GetSurfaceOutput("mdl").GetConnectedSource()
        self.assertEqual((source.GetPrim(), name), (shader.GetPrim(), "out"))

    async def test_define_material_with_disable_alpha_test_authors_opaque_state(self):
        # Arrange
        snapshot = snapshot_material(self._material)
        destination = Usd.Stage.CreateInMemory()

        # Act
        define_material(destination, _DESTINATION_PATH, snapshot, True)

        # Assert
        shader = UsdShade.Shader(destination.GetPrimAtPath(f"{_DESTINATION_PATH}/Shader"))
        self.assertEqual(shader.GetInput("alpha_test_type").Get(), ALPHA_TEST_ALWAYS)
        self.assertFalse(shader.GetInput("blend_enabled").Get())
        self.assertFalse(shader.GetInput("use_legacy_alpha_state").Get())
