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

import omni.kit.test
from lightspeed.trex.properties_pane.particle.widget.particle_lookup_table import get_particle_lookup_table
from pxr import Usd


class TestSchemaDiscovery(omni.kit.test.AsyncTestCase):
    async def test_discover_actual_schema_attributes(self):
        """Test to discover the actual schema attributes and their display names"""
        # Arrange & Act
        lookup_table = get_particle_lookup_table()

        # Assert & Print for debugging
        print(f"\n=== ACTUAL SCHEMA ATTRIBUTES (Total: {len(lookup_table)}) ===")
        if len(lookup_table) == 0:
            print("WARNING: Lookup table is empty!")

            # Try to debug why the schema isn't loading
            temp_stage = Usd.Stage.CreateInMemory()
            temp_prim = temp_stage.DefinePrim("/DummyParticle", "Mesh")
            print(f"Created prim: {temp_prim}")

            success = temp_prim.ApplyAPI("RemixParticleSystemAPI")
            print(f"Applied RemixParticleSystemAPI: {success}")

            attributes = temp_prim.GetAttributes()
            print(f"Total attributes: {len(attributes)}")
            for attr in attributes:
                name = attr.GetName()
                print(f"  - {name} (starts with primvars:particle: {name.startswith('primvars:particle:')})")
        else:
            for attr_name, attr_info in lookup_table.items():
                print(f"Attribute: {attr_name}")
                print(f"  Display Name: '{attr_info['name']}'")
                print(f"  Group: '{attr_info['group']}'")
                print(f"  Tooltip: '{attr_info['tooltip']}'")
                print()

        # Basic validation - ensure we have particle attributes
        self.assertGreater(len(lookup_table), 0, "Should have at least some particle attributes")

        # Check that all attributes have the expected structure
        for attr_name, attr_info in lookup_table.items():
            self.assertIn("name", attr_info)
            self.assertIn("group", attr_info)
            self.assertIn("tooltip", attr_info)
            self.assertTrue(
                attr_name.startswith("primvars:particle:"),
                f"Attribute {attr_name} should start with 'primvars:particle:'",
            )

        # Test some specific attributes we expect
        expected_attrs = ["gravityForce", "maxNumParticles", "useTurbulence", "initialVelocityFromNormal"]
        missing_attrs = []
        for attr_name in expected_attrs:
            full_attr_name = f"primvars:particle:{attr_name}"
            if full_attr_name in lookup_table:
                print(f"✓ Found expected attribute: {full_attr_name} -> '{lookup_table[full_attr_name]['name']}'")
            else:
                print(f"✗ Missing expected attribute: {full_attr_name}")
                missing_attrs.append(full_attr_name)

        # Assert that all expected attributes are present
        self.assertEqual(missing_attrs, [], f"Missing expected particle attributes: {missing_attrs}")
