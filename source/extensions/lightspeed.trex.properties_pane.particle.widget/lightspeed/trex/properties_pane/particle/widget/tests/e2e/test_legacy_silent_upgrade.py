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
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME
from lightspeed.common.constants import PROPERTIES_NAMES_COLUMN_WIDTH
from lightspeed.trex.properties_pane.particle.widget import ParticleSystemPropertyWidget
from omni.kit import ui_test
from pxr import Gf, Sdf


class TestLegacySilentUpgrade(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        self._prim = self._stage.DefinePrim("/Particle", "Mesh")
        self._prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
        self._context.get_selection().set_selected_prim_paths([str(self._prim.GetPath())], False)

    async def tearDown(self):
        if self._context:
            await self._context.close_stage_async()
        self._context = None
        self._stage = None
        self._prim = None

    async def _setup_particle_widget(self):
        window = ui.Window("Legacy Silent Upgrade Full Flow", height=900, width=700)
        with window.frame:
            widget = ParticleSystemPropertyWidget(
                context_name="",
                tree_column_widths=[PROPERTIES_NAMES_COLUMN_WIDTH, ui.Fraction(1)],
                right_aligned_labels=False,
                columns_resizable=True,
            )
            widget.show(True)
        widget.refresh([str(self._prim.GetPath())])
        await ui_test.human_delay(human_delay_speed=5)
        return window, widget

    def _get_or_create_attr(self, attr_name, value_type_name):
        attr = self._prim.GetAttribute(attr_name)
        if not attr or not attr.IsValid():
            attr = self._prim.CreateAttribute(attr_name, value_type_name)
        return attr

    def _author_size_legacy_values(self):
        min_spawn_attr = self._get_or_create_attr("primvars:particle:minSpawnSize", Sdf.ValueTypeNames.Float2)
        min_target_attr = self._get_or_create_attr("primvars:particle:minTargetSize", Sdf.ValueTypeNames.Float2)
        max_spawn_attr = self._get_or_create_attr("primvars:particle:maxSpawnSize", Sdf.ValueTypeNames.Float2)
        max_target_attr = self._get_or_create_attr("primvars:particle:maxTargetSize", Sdf.ValueTypeNames.Float2)
        min_spawn_attr.Set(Gf.Vec2f(11.0, 12.0))
        min_target_attr.Set(Gf.Vec2f(21.0, 22.0))
        max_spawn_attr.Set(Gf.Vec2f(31.0, 32.0))
        max_target_attr.Set(Gf.Vec2f(41.0, 42.0))

    async def test_particle_size_button_silently_upgrades_all_size_channels(self):
        # Arrange
        self._author_size_legacy_values()
        window, widget = await self._setup_particle_widget()
        action_window = ui.Window("Legacy Silent Upgrade Action Button", height=100, width=360)
        action_widgets = []

        # Act
        try:
            visible_item_names = [
                "".join(model.get_value_as_string() for model in item.name_models)
                for item in widget.property_model.get_all_items()
            ]
            self.assertNotIn("Minimum Spawn Size", visible_item_names)
            self.assertNotIn("Maximum Target Size", visible_item_names)

            size_item = next(
                item
                for item in widget.property_model.get_all_items(include_hidden=True)
                if "".join(model.get_value_as_string() for model in item.name_models) == "Particle Size"
            )
            widget._property_delegate.resolve_claims(widget.property_model)
            size_builder = widget._property_delegate.get_widget_builder(size_item)
            with action_window.frame:
                with ui.VStack(height=0):
                    ui.Spacer(height=ui.Pixel(12))
                    with ui.HStack(height=ui.Pixel(32)):
                        ui.Spacer(width=ui.Pixel(12))
                        action_widgets.extend(size_builder(size_item))
                        ui.Spacer(width=ui.Pixel(12))
                    ui.Spacer(height=ui.Pixel(12))
            await ui_test.human_delay(human_delay_speed=3)
            size_button = ui_test.find(f"{action_window.title}//Frame/**/Button[*].text=='Particle Size'")
            self.assertIsNotNone(size_button, "Expected Particle Size button to be visible.")
            await size_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            # Assert
            expected_values = {
                "primvars:particle:minSize:x": [11.0, 21.0],
                "primvars:particle:minSize:y": [12.0, 22.0],
                "primvars:particle:maxSize:x": [31.0, 41.0],
                "primvars:particle:maxSize:y": [32.0, 42.0],
            }
            for animated_attr_name, expected_curve_values in expected_values.items():
                times = self._prim.GetAttribute(f"{animated_attr_name}:times").Get()
                values = self._prim.GetAttribute(f"{animated_attr_name}:values").Get()
                self.assertEqual(list(times), [0.0, 1.0])
                self.assertEqual(list(values), expected_curve_values)
            self.assertIsNone(ui_test.find("Upgrade Legacy Particle Attributes//Frame/**/Button[*]"))
        finally:
            widget.destroy()
            window.destroy()
            action_window.destroy()
