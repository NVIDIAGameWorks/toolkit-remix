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

from typing import Any, cast

import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem, USDAttrListItem, VirtualUSDAttributeItem
from pxr import Gf, Sdf


class TestUSDAttributeValueTooltips(omni.kit.test.AsyncTestCase):
    context: Any
    stage: Any

    async def setUp(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        self.context = cast(Any, omni.usd.get_context())
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    def _create_item(
        self,
        attr_name: str,
        value_type_name: Sdf.ValueTypeName,
        value,
        display_name: str | None = None,
        prim_path: str = "/TooltipTestPrim",
    ) -> USDAttributeItem:
        prim = self.stage.DefinePrim(prim_path)
        attr = prim.CreateAttribute(attr_name, value_type_name)
        attr.Set(value)
        display_attr_names = [display_name] if display_name else None
        return USDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path(f"{prim_path}.{attr_name}")],
            display_attr_names=display_attr_names,
        )

    async def test_scalar_tooltip_includes_display_name_and_value(self):
        # Arrange
        item = self._create_item(
            "minimumRotationSpeed",
            Sdf.ValueTypeNames.Double,
            4.53,
            display_name="Minimum Rotation Speed",
        )

        # Act
        tooltip = item.value_models[0].get_tool_tip()

        # Assert
        self.assertEqual(tooltip, "Minimum Rotation Speed: 4.53")

    async def test_bool_tooltip_includes_display_name_and_value(self):
        # Arrange
        item = self._create_item(
            "visibleInPrimaryRay",
            Sdf.ValueTypeNames.Bool,
            True,
            display_name="Visible in Primary Ray",
        )

        # Act
        tooltip = item.value_models[0].get_tool_tip()

        # Assert
        self.assertEqual(tooltip, "Visible in Primary Ray: True")

    async def test_vector2_tooltip_includes_xy_channel_names(self):
        # Arrange
        item = self._create_item(
            "minimumParticleSize",
            Sdf.ValueTypeNames.Double2,
            Gf.Vec2d(1.0, 2.0),
            display_name="Minimum Particle Size",
        )

        # Act
        x_tooltip = item.value_models[0].get_tool_tip()
        y_tooltip = item.value_models[1].get_tool_tip()

        # Assert
        self.assertEqual(x_tooltip, "Minimum Particle Size X: 1.0")
        self.assertEqual(y_tooltip, "Minimum Particle Size Y: 2.0")

    async def test_vector3_tooltip_includes_xyz_channel_names(self):
        # Arrange
        item = self._create_item(
            "maximumVelocity",
            Sdf.ValueTypeNames.Double3,
            Gf.Vec3d(0.0, 1.0, 0.5),
            display_name="Maximum Velocity",
        )

        # Act
        x_tooltip = item.value_models[0].get_tool_tip()
        y_tooltip = item.value_models[1].get_tool_tip()
        z_tooltip = item.value_models[2].get_tool_tip()

        # Assert
        self.assertEqual(x_tooltip, "Maximum Velocity X: 0.0")
        self.assertEqual(y_tooltip, "Maximum Velocity Y: 1.0")
        self.assertEqual(z_tooltip, "Maximum Velocity Z: 0.5")

    async def test_vector4_tooltip_includes_w_channel_name(self):
        # Arrange
        item = self._create_item(
            "clipPlane",
            Sdf.ValueTypeNames.Double4,
            Gf.Vec4d(1.0, 2.0, 3.0, 4.0),
            display_name="Clip Plane",
        )

        # Act
        tooltip = item.value_models[3].get_tool_tip()

        # Assert
        self.assertEqual(tooltip, "Clip Plane W: 4.0")

    async def test_color_tooltip_remains_single_attribute_value(self):
        # Arrange
        item = self._create_item(
            "emissionColor",
            Sdf.ValueTypeNames.Color3d,
            Gf.Vec3d(1.0, 0.4, 0.1),
            display_name="Emission Color",
        )

        # Act
        tooltip = cast(str, item.value_models[0].get_tool_tip())

        # Assert
        self.assertTrue(tooltip.startswith("Emission Color: "))
        self.assertNotIn("Emission Color X:", tooltip)
        self.assertEqual(len(item.value_models), 1)

    async def test_fallback_tooltip_uses_attribute_name(self):
        # Arrange
        item = self._create_item("testFallback", Sdf.ValueTypeNames.Double, 7.0)

        # Act
        tooltip = item.value_models[0].get_tool_tip()

        # Assert
        self.assertEqual(tooltip, "testFallback: 7.0")

    async def test_list_model_tooltip_includes_display_name_and_value(self):
        # Arrange
        prim = self.stage.DefinePrim("/ListTooltipPrim")
        attr = prim.CreateAttribute("mode", Sdf.ValueTypeNames.Token)
        attr.Set("On")
        item = USDAttrListItem(
            context_name="",
            attribute_paths=[Sdf.Path("/ListTooltipPrim.mode")],
            default_value="On",
            display_attr_names=["Mode"],
            options=["On", "Off"],
        )

        # Act
        tooltip = item.value_models[0].get_tool_tip()

        # Assert
        self.assertEqual(tooltip, "Mode: On")

    async def test_virtual_attribute_tooltip_includes_display_name_and_default_value(self):
        # Arrange
        self.stage.DefinePrim("/VirtualTooltipPrim")
        item = VirtualUSDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path("/VirtualTooltipPrim.virtualValue")],
            value_type_name=Sdf.ValueTypeNames.Double,
            default_value=8.5,
            display_attr_names=["Virtual Value"],
        )

        # Act
        tooltip = item.value_models[0].get_tool_tip()

        # Assert
        self.assertEqual(tooltip, "Virtual Value: 8.5")

    async def test_mixed_value_tooltip_preserves_mixed_value_details(self):
        # Arrange
        prim_a = self.stage.DefinePrim("/MixedA")
        attr_a = prim_a.CreateAttribute("translate", Sdf.ValueTypeNames.Double3)
        attr_a.Set(Gf.Vec3d(1.0, 2.0, 3.0))
        prim_b = self.stage.DefinePrim("/MixedB")
        attr_b = prim_b.CreateAttribute("translate", Sdf.ValueTypeNames.Double3)
        attr_b.Set(Gf.Vec3d(4.0, 5.0, 6.0))
        item = USDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path("/MixedA.translate"), Sdf.Path("/MixedB.translate")],
            display_attr_names=["Translate"],
        )

        # Act
        tooltip = cast(str, item.value_models[0].get_tool_tip())

        # Assert
        self.assertTrue(tooltip.startswith("Translate X: Mixed Values:"))
        self.assertIn("(1, 2, 3)", tooltip)
        self.assertIn("(4, 5, 6)", tooltip)
