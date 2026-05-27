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

import omni.kit.test
from lightspeed.trex.properties_pane.particle.widget.setup_ui import (
    PARTICLE_ATTR_GROUP_FALLBACK,
    PARTICLE_ATTR_GROUP_ORDER,
    ParticleSystemPropertyWidget,
    _resolve_edit_group_outlet_group,
)
from lightspeed.trex.properties_pane.particle.widget.particle_edit_groups import (
    PARTICLE_CURVE_LOOKUP,
)
from pxr import Sdf
from unittest.mock import Mock


class _SchemaAttr:
    def __init__(self, display_group: str | None):
        self.GetInfo = Mock(side_effect=lambda key: display_group if key == Sdf.AttributeSpec.DisplayGroupKey else None)


class _SchemaPrim:
    def __init__(self, properties: dict):
        self.properties = properties


class TestParticleSetupUi(omni.kit.test.AsyncTestCase):
    async def test_general_group_is_first_particle_group(self):
        self.assertEqual(PARTICLE_ATTR_GROUP_ORDER[0], "General")

    async def test_resolve_edit_group_outlet_group_first_curve_values_group_wins(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x:values": _SchemaAttr("Spawn"),
                "primvars:particle:minSize:y:values": _SchemaAttr("Visual"),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, "Spawn")

    async def test_resolve_edit_group_outlet_group_empty_first_group_uses_next_curve(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x:values": _SchemaAttr(" "),
                "primvars:particle:minSize:y:values": _SchemaAttr("Visual"),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, "Visual")

    async def test_resolve_edit_group_outlet_group_no_curve_values_group_uses_fallback(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x:values": _SchemaAttr(None),
                "primvars:particle:minSize:y:values": _SchemaAttr(""),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, PARTICLE_ATTR_GROUP_FALLBACK)

    async def test_resolve_edit_group_outlet_group_empty_curve_map_returns_none(self):
        # Arrange
        schema_prim = _SchemaPrim({})
        edit_group_layout = {"curve_map": {}}

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertIsNone(result)

    async def test_resolve_edit_group_outlet_group_ignores_unsuffixed_curve_metadata(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x": _SchemaAttr("Ignored"),
                "primvars:particle:minSize:y:values": _SchemaAttr("Visual"),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, "Visual")

    async def test_particle_curve_lookup_tracks_raw_curve_control_rows_only(self):
        for attr_name in PARTICLE_CURVE_LOOKUP:
            with self.subTest(attr_name=attr_name):
                self.assertTrue(attr_name.startswith("primvars:particle"))
                self.assertNotIn(":values", attr_name)
                self.assertNotIn(":times", attr_name)

    async def test_particle_curve_lookup_excludes_curve_storage_attrs(self):
        for attr_name in PARTICLE_CURVE_LOOKUP:
            for suffix in (
                ":values",
                ":times",
                ":inTangentValues",
                ":outTangentValues",
                ":preInfinity",
                ":postInfinity",
            ):
                with self.subTest(attr_name=attr_name, suffix=suffix):
                    self.assertNotIn(f"{attr_name}{suffix}", PARTICLE_CURVE_LOOKUP)

    async def test_particle_curve_lookup_excludes_non_curve_particle_attrs(self):
        self.assertNotIn("primvars:particle:applyGravity", PARTICLE_CURVE_LOOKUP)

    async def test_extract_curve_id_handles_curve_editor_infinity_attrs(self):
        self.assertEqual(
            ParticleSystemPropertyWidget._extract_curve_id("primvars:particle:minRotationSpeed:preInfinity"),
            "primvars:particle:minRotationSpeed",
        )
        self.assertEqual(
            ParticleSystemPropertyWidget._extract_curve_id("primvars:particle:minRotationSpeed:postInfinity"),
            "primvars:particle:minRotationSpeed",
        )

    async def test_extract_curve_id_ignores_unsuffixed_curve_controller_attrs(self):
        self.assertIsNone(ParticleSystemPropertyWidget._extract_curve_id("primvars:particle:minRotationSpeed"))
