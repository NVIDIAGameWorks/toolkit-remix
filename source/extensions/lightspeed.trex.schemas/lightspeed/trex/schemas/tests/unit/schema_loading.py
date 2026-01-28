"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import pathlib

from lightspeed.trex.schemas.utils import get_schema_prim
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom

TEST_PARTICLE_SCHEMA_NAME = "RemixParticleSystemAPI"
TEST_PARTICLE_PRIMVAR_PREFIX = "primvars:particle:"


class TestSchemaLoading(AsyncTestCase):
    def test_remix_particle_system_schema_is_loading(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = UsdGeom.Mesh.Define(stage, "/TestParticles").GetPrim()

        # Act
        prim.ApplyAPI(TEST_PARTICLE_SCHEMA_NAME)

        # Assert
        self.assertEqual(prim.GetTypeName(), "Mesh")
        # test essential attributes only, or ones that we use in toolkit implementation
        expected_attrs = [
            TEST_PARTICLE_PRIMVAR_PREFIX + "gravityForce",  # key attribute
            TEST_PARTICLE_PRIMVAR_PREFIX + "maxNumParticles",  # key attribute
            TEST_PARTICLE_PRIMVAR_PREFIX + "useTurbulence",  # key attribute
            TEST_PARTICLE_PRIMVAR_PREFIX + "hideEmitter",  # toolkit: checked for gizmo visibility
            TEST_PARTICLE_PRIMVAR_PREFIX + "spawnRatePerSecond",  # key attribute, important to see effect
        ]
        for attr in expected_attrs:
            self.assertTrue(prim.HasAttribute(attr), f"Missing attribute: {attr}")

    def test_remix_particle_system_schema_authoring_assets_to_usda(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = UsdGeom.Mesh.Define(stage, "/TestParticles").GetPrim()
        prim.ApplyAPI(TEST_PARTICLE_SCHEMA_NAME)

        # Act
        prim.CreateAttribute(TEST_PARTICLE_PRIMVAR_PREFIX + "gravityForce", Sdf.ValueTypeNames.Float).Set(12.34)
        prim.CreateAttribute(TEST_PARTICLE_PRIMVAR_PREFIX + "maxNumParticles", Sdf.ValueTypeNames.Int).Set(12345)
        prim.CreateAttribute(TEST_PARTICLE_PRIMVAR_PREFIX + "useTurbulence", Sdf.ValueTypeNames.Bool).Set(True)

        # Assert
        usda_result = stage.GetRootLayer().ExportToString()
        fixture_path = pathlib.Path(__file__).parent / "fixtures" / "remix_particle_system.usda"
        with open(fixture_path, encoding="utf-8") as f:
            expected_usda = f.read()

        self.assertEqual(usda_result.strip(), expected_usda.strip())

    def test_remix_particle_system_schema_loading_scene_from_usda(self):
        # Act
        stage = Usd.Stage.Open(str(pathlib.Path(__file__).parent / "fixtures" / "remix_particle_system.usda"))
        prim = stage.GetPrimAtPath("/TestParticles")

        # Assert
        self.assertEqual(prim.HasAPI(TEST_PARTICLE_SCHEMA_NAME), True)
        self.assertAlmostEqual(prim.GetAttribute(TEST_PARTICLE_PRIMVAR_PREFIX + "gravityForce").Get(), 12.34, places=2)
        self.assertAlmostEqual(
            prim.GetAttribute(TEST_PARTICLE_PRIMVAR_PREFIX + "maxNumParticles").Get(), 12345, places=2
        )
        self.assertEqual(prim.GetAttribute(TEST_PARTICLE_PRIMVAR_PREFIX + "useTurbulence").Get(), True)

    def test_remix_particle_system_attribute_default_values(self):
        # Arrange
        schema_layer, schema_prim = get_schema_prim(TEST_PARTICLE_SCHEMA_NAME)
        if not schema_layer or not schema_prim:
            raise ValueError("Schema prim not found")

        # Act
        default_value = schema_prim.properties.get(TEST_PARTICLE_PRIMVAR_PREFIX + "billboardType").default
        options = schema_prim.properties.get(TEST_PARTICLE_PRIMVAR_PREFIX + "billboardType").allowedTokens

        # Assert
        self.assertEqual(default_value, "FaceCamera_Spherical")
        self.assertTrue(len(options) > 1)
