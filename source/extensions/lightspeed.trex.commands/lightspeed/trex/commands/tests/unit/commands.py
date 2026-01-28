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

import omni.kit.commands
import omni.kit.test
import omni.kit.undo
import omni.usd
from lightspeed.common.constants import PARTICLE_CPP_SCHEMA_NAME, PARTICLE_SCHEMA_NAME
from pxr import Sdf, Usd, UsdGeom


class TestParticleSystemCommands(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def __create_test_prim(self, prim_type="Mesh") -> "Usd.Prim":
        """Helper method to create a test prim."""
        test_path = omni.usd.get_stage_next_free_path(self.stage, "/World/TestPrim", False)
        if prim_type == "Mesh":
            return UsdGeom.Mesh.Define(self.stage, test_path).GetPrim()
        return self.stage.DefinePrim(test_path, prim_type)

    async def __create_test_attributes(self, prim: "Usd.Prim") -> dict:
        """Helper method to create test particle system attributes."""
        test_attrs = {}

        # Apply the API first to ensure attributes are available
        prim.ApplyAPI(PARTICLE_SCHEMA_NAME)

        # Create some common particle system attributes with test values
        gravity_attr = prim.CreateAttribute("primvars:particle:gravityForce", Sdf.ValueTypeNames.Float)
        gravity_attr.Set(9.8)
        test_attrs["primvars:particle:gravityForce"] = 9.8

        max_particles_attr = prim.CreateAttribute("primvars:particle:maxNumParticles", Sdf.ValueTypeNames.Int)
        max_particles_attr.Set(1000)
        test_attrs["primvars:particle:maxNumParticles"] = 1000

        turbulence_attr = prim.CreateAttribute("primvars:particle:useTurbulence", Sdf.ValueTypeNames.Bool)
        turbulence_attr.Set(True)
        test_attrs["primvars:particle:useTurbulence"] = True

        spawn_rate_attr = prim.CreateAttribute("primvars:particle:spawnRatePerSecond", Sdf.ValueTypeNames.Float)
        spawn_rate_attr.Set(50.0)
        test_attrs["primvars:particle:spawnRatePerSecond"] = 50.0

        return test_attrs

    # Tests for CreateParticleSystemCommand

    async def test_create_particle_system_command_do_apply_api(self):
        """Test that CreateParticleSystemCommand applies the particle system API."""
        # Arrange
        test_prim = await self.__create_test_prim()
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("CreateParticleSystemCommand", prim=test_prim)

        # Assert
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    async def test_create_particle_system_command_do_already_has_api(self):
        """Test that CreateParticleSystemCommand doesn't duplicate API if already applied."""
        # Arrange
        test_prim = await self.__create_test_prim()
        test_prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("CreateParticleSystemCommand", prim=test_prim)

        # Assert
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))
        # Verify the API is still applied but not duplicated
        api_schemas = test_prim.GetAppliedSchemas()
        # GetAppliedSchemas() returns the C++ schema names, not Python names
        particle_api_count = sum(1 for schema in api_schemas if schema == PARTICLE_CPP_SCHEMA_NAME)
        self.assertEqual(particle_api_count, 1)  # Should be at least 1

    async def test_create_particle_system_command_undo(self):
        """Test that CreateParticleSystemCommand undo removes the API."""
        # Arrange
        test_prim = await self.__create_test_prim()
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("CreateParticleSystemCommand", prim=test_prim)
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        omni.kit.undo.undo()

        # Assert
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    async def test_create_particle_system_command_undo_no_effect_when_api_existed(self):
        """Test that undo doesn't remove API that was already present before command."""
        # Arrange
        test_prim = await self.__create_test_prim()
        test_prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("CreateParticleSystemCommand", prim=test_prim)
        omni.kit.undo.undo()

        # Assert
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    async def test_create_particle_system_command_redo(self):
        """Test that CreateParticleSystemCommand redo works correctly."""
        # Arrange
        test_prim = await self.__create_test_prim()
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("CreateParticleSystemCommand", prim=test_prim)
        omni.kit.undo.undo()
        omni.kit.undo.redo()

        # Assert
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    # Tests for RemoveParticleSystemCommand

    async def test_remove_particle_system_command_do_remove_api(self):
        """Test that RemoveParticleSystemCommand removes the particle system API."""
        # Arrange
        test_prim = await self.__create_test_prim()
        test_prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("RemoveParticleSystemCommand", prim=test_prim)

        # Assert
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    async def test_remove_particle_system_command_do_remove_attributes(self):
        """Test that RemoveParticleSystemCommand removes particle system attributes."""
        # Arrange
        test_prim = await self.__create_test_prim()
        test_attrs = await self.__create_test_attributes(test_prim)

        # Verify attributes exist
        for attr_name in test_attrs:
            self.assertTrue(test_prim.HasAttribute(attr_name))

        # Act
        omni.kit.commands.execute("RemoveParticleSystemCommand", prim=test_prim)

        # Assert
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))
        for attr_name in test_attrs:
            self.assertFalse(test_prim.HasAttribute(attr_name))

    async def test_remove_particle_system_command_do_no_api_present(self):
        """Test that RemoveParticleSystemCommand handles case when no API is present."""
        # Arrange
        test_prim = await self.__create_test_prim()
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("RemoveParticleSystemCommand", prim=test_prim)

        # Assert
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    async def test_remove_particle_system_command_undo_restore_api(self):
        """Test that RemoveParticleSystemCommand undo restores the API."""
        # Arrange
        test_prim = await self.__create_test_prim()
        test_prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("RemoveParticleSystemCommand", prim=test_prim)
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        omni.kit.undo.undo()

        # Assert
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    async def test_remove_particle_system_command_undo_restore_attributes(self):
        """Test that RemoveParticleSystemCommand undo restores attributes and their values."""
        # Arrange
        test_prim = await self.__create_test_prim()
        test_attrs = await self.__create_test_attributes(test_prim)

        # Act
        omni.kit.commands.execute("RemoveParticleSystemCommand", prim=test_prim)
        omni.kit.undo.undo()

        # Assert
        self.assertTrue(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))
        for attr_name, expected_value in test_attrs.items():
            self.assertTrue(test_prim.HasAttribute(attr_name))
            actual_value = test_prim.GetAttribute(attr_name).Get()
            if isinstance(expected_value, float):
                self.assertAlmostEqual(actual_value, expected_value, places=6)
            else:
                self.assertEqual(actual_value, expected_value)

    async def test_remove_particle_system_command_undo_no_effect_when_no_api(self):
        """Test that undo has no effect when API wasn't present before command."""
        # Arrange
        test_prim = await self.__create_test_prim()
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

        # Act
        omni.kit.commands.execute("RemoveParticleSystemCommand", prim=test_prim)
        omni.kit.undo.undo()

        # Assert
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))

    async def test_remove_particle_system_command_redo(self):
        """Test that RemoveParticleSystemCommand redo works correctly."""
        # Arrange
        test_prim = await self.__create_test_prim()
        test_attrs = await self.__create_test_attributes(test_prim)

        # Act
        omni.kit.commands.execute("RemoveParticleSystemCommand", prim=test_prim)
        omni.kit.undo.undo()
        omni.kit.undo.redo()

        # Assert
        self.assertFalse(test_prim.HasAPI(PARTICLE_SCHEMA_NAME))
        for attr_name in test_attrs:
            self.assertFalse(test_prim.HasAttribute(attr_name))
