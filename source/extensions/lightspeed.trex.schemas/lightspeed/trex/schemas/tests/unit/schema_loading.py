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

import pathlib

from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom

PARTICLE_API_SCHEMA = "RemixParticleSystemAPI"
PARTICLE_PRIMVAR_PREFIX = "primvars:particle:"


class TestSchemaLoading(AsyncTestCase):
    def test_remix_particle_system_schema_is_loading(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = UsdGeom.Mesh.Define(stage, "/TestParticles").GetPrim()

        # Act
        prim.ApplyAPI(PARTICLE_API_SCHEMA)

        # Assert
        self.assertEqual(prim.GetTypeName(), "Mesh")
        expected_attrs = [
            PARTICLE_PRIMVAR_PREFIX + "alignParticlesToVelocity",
            PARTICLE_PRIMVAR_PREFIX + "collisionRestitution",
            PARTICLE_PRIMVAR_PREFIX + "collisionThickness",
            PARTICLE_PRIMVAR_PREFIX + "enableCollisionDetection",
            PARTICLE_PRIMVAR_PREFIX + "enableMotionTrail",
            PARTICLE_PRIMVAR_PREFIX + "gravityForce",
            PARTICLE_PRIMVAR_PREFIX + "hideEmitter",
            PARTICLE_PRIMVAR_PREFIX + "initialVelocityConeAngleDegrees",
            PARTICLE_PRIMVAR_PREFIX + "initialVelocityFromNormal",
            PARTICLE_PRIMVAR_PREFIX + "maxNumParticles",
            PARTICLE_PRIMVAR_PREFIX + "maxParticleSize",
            PARTICLE_PRIMVAR_PREFIX + "maxRotationSpeed",
            PARTICLE_PRIMVAR_PREFIX + "maxSpawnColor",
            PARTICLE_PRIMVAR_PREFIX + "maxSpeed",
            PARTICLE_PRIMVAR_PREFIX + "maxTimeToLive",
            PARTICLE_PRIMVAR_PREFIX + "minParticleSize",
            PARTICLE_PRIMVAR_PREFIX + "minRotationSpeed",
            PARTICLE_PRIMVAR_PREFIX + "minSpawnColor",
            PARTICLE_PRIMVAR_PREFIX + "minTimeToLive",
            PARTICLE_PRIMVAR_PREFIX + "motionTrailMultiplier",
            PARTICLE_PRIMVAR_PREFIX + "spawnRatePerSecond",
            PARTICLE_PRIMVAR_PREFIX + "turbulenceAmplitude",
            PARTICLE_PRIMVAR_PREFIX + "turbulenceFrequency",
            PARTICLE_PRIMVAR_PREFIX + "useSpawnTexcoords",
            PARTICLE_PRIMVAR_PREFIX + "useTurbulence",
        ]
        for attr in expected_attrs:
            self.assertTrue(prim.HasAttribute(attr), f"Missing attribute: {attr}")

    def test_remix_particle_system_schema_authoring_assets_to_usda(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = UsdGeom.Mesh.Define(stage, "/TestParticles").GetPrim()
        prim.ApplyAPI(PARTICLE_API_SCHEMA)

        # Act
        prim.CreateAttribute(PARTICLE_PRIMVAR_PREFIX + "gravityForce", Sdf.ValueTypeNames.Float).Set(12.34)
        prim.CreateAttribute(PARTICLE_PRIMVAR_PREFIX + "maxNumParticles", Sdf.ValueTypeNames.Int).Set(12345)
        prim.CreateAttribute(PARTICLE_PRIMVAR_PREFIX + "useTurbulence", Sdf.ValueTypeNames.Bool).Set(True)

        # Assert
        usda_result = stage.GetRootLayer().ExportToString()
        fixture_path = pathlib.Path(__file__).parent / "fixtures" / "remix_particle_system.usda"
        with open(fixture_path, "r", encoding="utf-8") as f:
            expected_usda = f.read()

        self.assertEqual(usda_result.strip(), expected_usda.strip())

    def test_remix_particle_system_schema_loading_scene_from_usda(self):
        # Act
        stage = Usd.Stage.Open(str(pathlib.Path(__file__).parent / "fixtures" / "remix_particle_system.usda"))
        prim = stage.GetPrimAtPath("/TestParticles")

        # Assert
        self.assertEqual(prim.HasAPI(PARTICLE_API_SCHEMA), True)
        self.assertAlmostEqual(prim.GetAttribute(PARTICLE_PRIMVAR_PREFIX + "gravityForce").Get(), 12.34, places=2)
        self.assertAlmostEqual(prim.GetAttribute(PARTICLE_PRIMVAR_PREFIX + "maxNumParticles").Get(), 12345, places=2)
        self.assertEqual(prim.GetAttribute(PARTICLE_PRIMVAR_PREFIX + "useTurbulence").Get(), True)
