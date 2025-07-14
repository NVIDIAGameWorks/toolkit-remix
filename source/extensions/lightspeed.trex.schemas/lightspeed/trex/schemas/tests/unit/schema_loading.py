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
from pxr import Sdf, Usd


class TestSchemaLoading(AsyncTestCase):
    def test_remix_particle_system_schema_is_loading(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()

        # Act
        prim = stage.DefinePrim("/TestParticles", "RemixParticleSystem")

        # Assert
        self.assertEqual(prim.GetTypeName(), "RemixParticleSystem")
        expected_attrs = [
            "gravityForce",
            "initialVelocityFromNormal",
            "maxNumParticles",
            "maxParticleSize",
            "maxSpawnColor",
            "maxSpeed",
            "maxTtl",
            "minParticleSize",
            "minSpawnColor",
            "minTtl",
            "opacityMultiplier",
            "purpose",
            "turbulenceAmplitude",
            "turbulenceFrequency",
            "useTurbulence",
            "visibility",
            "xformOpOrder",
        ]
        for attr in expected_attrs:
            self.assertTrue(prim.HasAttribute(attr), f"Missing attribute: {attr}")

    def test_remix_particle_system_schema_authoring_assets_to_usda(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/TestParticles", "RemixParticleSystem")

        # Act
        prim.CreateAttribute("gravityForce", Sdf.ValueTypeNames.Float).Set(12.34)
        prim.CreateAttribute("maxNumParticles", Sdf.ValueTypeNames.Int).Set(12345)
        prim.CreateAttribute("opacityMultiplier", Sdf.ValueTypeNames.Float).Set(0.5)
        prim.CreateAttribute("useTurbulence", Sdf.ValueTypeNames.Bool).Set(True)

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
        self.assertEqual(prim.GetTypeName(), "RemixParticleSystem")
        self.assertAlmostEqual(prim.GetAttribute("gravityForce").Get(), 12.34, places=2)
        self.assertAlmostEqual(prim.GetAttribute("maxNumParticles").Get(), 12345, places=2)
        self.assertAlmostEqual(prim.GetAttribute("opacityMultiplier").Get(), 0.5, places=2)
        self.assertEqual(prim.GetAttribute("useTurbulence").Get(), True)
