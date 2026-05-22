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

__all__ = ("TestFieldBuilderBounds",)

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.field_builders.aperture_pbr import MATERIAL_FIELD_BUILDERS
from omni.flux.property_widget_builder.model.usd.field_builders.lights import LIGHT_FIELD_BUILDERS
from omni.flux.property_widget_builder.model.usd.items import USDAttributeItem
from pxr import Sdf, Usd


def _make_attribute_item(attr_name: str) -> USDAttributeItem:
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/FieldBuilderBounds")
    attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float)
    attr.Set(0.0)

    # These tests exercise field-builder claim logic, which only needs the real USD attribute path.
    item = USDAttributeItem.__new__(USDAttributeItem)
    item._attribute_paths = [attr.GetPath()]
    return item


class TestFieldBuilderBounds(omni.kit.test.AsyncTestCase):
    """Unit tests for hardcoded USD field-builder bound policies."""

    def _claimed_field(self, builder_list, attr_name: str):
        item = _make_attribute_item(attr_name)
        claimed_fields = []
        for field_builder in builder_list:
            claim_result = field_builder.claim_func([item])
            if item in claim_result.primary:
                claimed_fields.append(field_builder.build_func)
        self.assertEqual(len(claimed_fields), 1)
        return claimed_fields[0]

    async def test_light_field_builders_use_explicit_soft_and_hard_bounds(self):
        # Arrange
        fields = {
            attr_name: self._claimed_field(LIGHT_FIELD_BUILDERS, attr_name)
            for attr_name in (
                "inputs:colorTemperature",
                "inputs:exposure",
                "inputs:intensity",
                "inputs:radius",
                "inputs:shaping:cone:angle",
                "inputs:shaping:cone:softness",
                "inputs:shaping:focus",
                "inputs:volumetric_radiance_scale",
            )
        }

        # Act / Assert
        self.assertEqual(fields["inputs:colorTemperature"].min_value, 2500.0)
        self.assertEqual(fields["inputs:colorTemperature"].max_value, 8500.0)
        self.assertIsNone(fields["inputs:colorTemperature"].hard_min_value)
        self.assertIsNone(fields["inputs:colorTemperature"].hard_max_value)
        self.assertAlmostEqual(fields["inputs:colorTemperature"].step, 30.0)

        self.assertIsNone(fields["inputs:radius"].min_value)
        self.assertEqual(fields["inputs:radius"].max_value, 65000.0)
        self.assertEqual(fields["inputs:radius"].hard_min_value, 0.0)
        self.assertIsNone(fields["inputs:radius"].hard_max_value)
        self.assertAlmostEqual(fields["inputs:radius"].step, 325.0)

        self.assertIsNone(fields["inputs:shaping:cone:angle"].min_value)
        self.assertIsNone(fields["inputs:shaping:cone:angle"].max_value)
        self.assertEqual(fields["inputs:shaping:cone:angle"].hard_min_value, 0.0)
        self.assertEqual(fields["inputs:shaping:cone:angle"].hard_max_value, 360.0)
        self.assertAlmostEqual(fields["inputs:shaping:cone:angle"].step, 1.8)

        for attr_name, soft_max in (
            ("inputs:exposure", 10.0),
            ("inputs:intensity", 65000.0),
            ("inputs:shaping:cone:softness", 10.0),
            ("inputs:shaping:focus", 10.0),
            ("inputs:volumetric_radiance_scale", 10.0),
        ):
            self.assertIsNone(fields[attr_name].min_value)
            self.assertEqual(fields[attr_name].max_value, soft_max)
            self.assertEqual(fields[attr_name].hard_min_value, 0.0)
            self.assertIsNone(fields[attr_name].hard_max_value)
            self.assertAlmostEqual(fields[attr_name].step, soft_max * 0.005)

    async def test_aperture_pbr_field_builders_use_explicit_soft_and_hard_bounds(self):
        # Arrange
        fields = {
            attr_name: self._claimed_field(MATERIAL_FIELD_BUILDERS, attr_name)
            for attr_name in (
                "inputs:opacity_constant",
                "inputs:reflection_roughness_constant",
                "inputs:metallic_constant",
                "inputs:thin_film_thickness_constant",
                "inputs:emissive_intensity",
                "inputs:displace_in",
                "inputs:displace_out",
                "inputs:subsurface_measurement_distance",
                "inputs:subsurface_volumetric_anisotropy",
                "inputs:subsurface_radius_scale",
            )
        }

        # Act / Assert
        for attr_name in (
            "inputs:opacity_constant",
            "inputs:reflection_roughness_constant",
            "inputs:metallic_constant",
        ):
            self.assertIsNone(fields[attr_name].min_value)
            self.assertIsNone(fields[attr_name].max_value)
            self.assertEqual(fields[attr_name].hard_min_value, 0.0)
            self.assertEqual(fields[attr_name].hard_max_value, 1.0)
            self.assertAlmostEqual(fields[attr_name].step, 0.005)

        for attr_name, hard_min, soft_max in (
            ("inputs:thin_film_thickness_constant", 0.0010000000474974513, 1500.0),
            ("inputs:emissive_intensity", 0.0, 65504.0),
            ("inputs:displace_in", 0.0, 2.0),
            ("inputs:displace_out", 0.0, 2.0),
            ("inputs:subsurface_measurement_distance", 0.0, 16.0),
            ("inputs:subsurface_radius_scale", 0.0, 16.0),
        ):
            self.assertIsNone(fields[attr_name].min_value)
            self.assertEqual(fields[attr_name].max_value, soft_max)
            self.assertEqual(fields[attr_name].hard_min_value, hard_min)
            self.assertIsNone(fields[attr_name].hard_max_value)
            self.assertAlmostEqual(fields[attr_name].step, (soft_max - hard_min) * 0.005)

        anisotropy = fields["inputs:subsurface_volumetric_anisotropy"]
        self.assertIsNone(anisotropy.min_value)
        self.assertIsNone(anisotropy.max_value)
        self.assertEqual(anisotropy.hard_min_value, -0.9900000095367432)
        self.assertEqual(anisotropy.hard_max_value, 0.9900000095367432)
        self.assertAlmostEqual(anisotropy.step, 0.009900000095367432)
