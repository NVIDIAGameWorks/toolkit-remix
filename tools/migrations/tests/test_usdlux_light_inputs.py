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

import unittest

from tools.migrations.usdlux_light_inputs import migrate_usdlux_light_inputs_text


class TestUsdLuxLightInputsMigration(unittest.TestCase):
    def test_migrate_usdlux_light_inputs_legacy_light_attrs_updates_light_prims_only(self):
        source = """#usda 1.0

def Xform "Root"
{
    def SphereLight "Lamp"
    {
        float intensity = 1200
        asset texture:file = @./lamp.exr@
        float shaping:cone:angle = 45
    }

    def Mesh "Panel"
    {
        float width = 2
    }

    def DistantLight "Sun"
    {
        float inputs:intensity = 2
    }
}
"""

        migrated, replacement_count = migrate_usdlux_light_inputs_text(source)

        self.assertEqual(3, replacement_count)
        self.assertIn("float inputs:intensity = 1200", migrated)
        self.assertIn("asset inputs:texture:file = @./lamp.exr@", migrated)
        self.assertIn("float inputs:shaping:cone:angle = 45", migrated)
        self.assertIn("float width = 2", migrated)
        self.assertIn("float inputs:intensity = 2", migrated)
        self.assertNotIn("float intensity = 1200", migrated)

    def test_migrate_usdlux_light_inputs_legacy_attr_names_in_values_and_comments_unchanged(self):
        source = """#usda 1.0

def SphereLight "Lamp"
{
    string notes = "adjust intensity and width"
    float intensity = 1200 # set intensity
}
"""

        migrated, replacement_count = migrate_usdlux_light_inputs_text(source)

        self.assertEqual(1, replacement_count)
        self.assertIn('string notes = "adjust intensity and width"', migrated)
        self.assertIn("float inputs:intensity = 1200 # set intensity", migrated)
        self.assertNotIn("inputs:width", migrated)

    def test_migrate_usdlux_light_inputs_prim_spec_text_in_string_does_not_open_light_scope(self):
        source = """#usda 1.0

def Xform "Root"
{
    string label = "see def SphereLight above {"
    float width = 2
}
"""

        migrated, replacement_count = migrate_usdlux_light_inputs_text(source)

        self.assertEqual(0, replacement_count)
        self.assertIn('string label = "see def SphereLight above {"', migrated)
        self.assertIn("float width = 2", migrated)


if __name__ == "__main__":
    unittest.main()
