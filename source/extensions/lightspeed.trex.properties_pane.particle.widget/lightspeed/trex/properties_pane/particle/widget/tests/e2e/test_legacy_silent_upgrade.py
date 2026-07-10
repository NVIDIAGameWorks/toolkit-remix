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
from lightspeed.trex.properties_pane.particle.widget.legacy_support_helper import (
    seed_current_animated_attrs_from_legacy,
)
from omni.kit import ui_test
from omni.flux.property_widget_builder.model.usd.logical_group_constants import SCALAR_CURVE_LOGICAL_SUFFIXES
from pxr import Gf, Sdf


class TestLegacySilentUpgrade(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        self._prim = self._create_particle_prim("/Particle")
        self._context.get_selection().set_selected_prim_paths([str(self._prim.GetPath())], False)

    async def tearDown(self):
        if self._context:
            await self._context.close_stage_async()
        self._context = None
        self._stage = None
        self._prim = None

    def _create_particle_prim(self, prim_path):
        prim = self._stage.DefinePrim(prim_path, "Mesh")
        prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
        return prim

    async def _setup_particle_widget(self, prims=None):
        prims = prims or [self._prim]
        prim_paths = [str(prim.GetPath()) for prim in prims]
        self._context.get_selection().set_selected_prim_paths(prim_paths, False)
        window = ui.Window("Legacy Silent Upgrade Full Flow", height=900, width=700)
        with window.frame:
            widget = ParticleSystemPropertyWidget(
                context_name="",
                tree_column_widths=[PROPERTIES_NAMES_COLUMN_WIDTH, ui.Fraction(1)],
                right_aligned_labels=False,
                columns_resizable=True,
            )
            widget.show(True)
        widget.refresh(prim_paths)
        await ui_test.human_delay(human_delay_speed=5)
        return window, widget

    def _get_or_create_attr(self, prim, attr_name, value_type_name):
        attr = prim.GetAttribute(attr_name)
        if not attr or not attr.IsValid():
            attr = prim.CreateAttribute(attr_name, value_type_name)
        return attr

    def _author_size_legacy_values(
        self,
        prim,
        min_spawn=None,
        min_target=None,
        max_spawn=None,
        max_target=None,
    ):
        min_spawn = min_spawn or Gf.Vec2f(11.0, 12.0)
        min_target = min_target or Gf.Vec2f(21.0, 22.0)
        max_spawn = max_spawn or Gf.Vec2f(31.0, 32.0)
        max_target = max_target or Gf.Vec2f(41.0, 42.0)
        self._get_or_create_attr(prim, "primvars:particle:minSpawnSize", Sdf.ValueTypeNames.Float2).Set(min_spawn)
        self._get_or_create_attr(prim, "primvars:particle:minTargetSize", Sdf.ValueTypeNames.Float2).Set(min_target)
        self._get_or_create_attr(prim, "primvars:particle:maxSpawnSize", Sdf.ValueTypeNames.Float2).Set(max_spawn)
        self._get_or_create_attr(prim, "primvars:particle:maxTargetSize", Sdf.ValueTypeNames.Float2).Set(max_target)

    def _author_min_color_legacy_values(
        self,
        prim,
        spawn=None,
        target=None,
    ):
        spawn = spawn or Gf.Vec4f(1.0, 0.5, 0.25, 1.0)
        target = target or Gf.Vec4f(0.0, 0.25, 0.5, 0.75)
        self._get_or_create_attr(prim, "primvars:particle:minSpawnColor", Sdf.ValueTypeNames.Color4f).Set(spawn)
        self._get_or_create_attr(prim, "primvars:particle:minTargetColor", Sdf.ValueTypeNames.Color4f).Set(target)

    def _assert_no_authored_values(self, prim, base_name: str, suffixes: tuple[str, ...]) -> None:
        for suffix in suffixes:
            attr = prim.GetAttribute(f"{base_name}:{suffix}")
            self.assertTrue(attr and attr.IsValid(), f"Expected schema attr {base_name}:{suffix} to exist.")
            self.assertFalse(attr.HasAuthoredValueOpinion(), f"Expected no authored value for {base_name}:{suffix}")

    def _assert_curve_schema_ready(self, prim, animated_attr_names: tuple[str, ...]) -> None:
        for animated_attr_name in animated_attr_names:
            self._assert_no_authored_values(prim, animated_attr_name, SCALAR_CURVE_LOGICAL_SUFFIXES)

    def _assert_gradient_schema_ready(self, prim, base_name: str) -> None:
        self._assert_no_authored_values(prim, base_name, ("times", "values"))

    def _assert_curve_seeded(self, prim, expected_values_by_attr: dict[str, list[float]]) -> None:
        for animated_attr_name, expected_curve_values in expected_values_by_attr.items():
            for suffix in SCALAR_CURVE_LOGICAL_SUFFIXES:
                attr = prim.GetAttribute(f"{animated_attr_name}:{suffix}")
                self.assertTrue(attr and attr.IsValid(), f"Expected {animated_attr_name}:{suffix} to exist.")
            times = prim.GetAttribute(f"{animated_attr_name}:times").Get()
            values = prim.GetAttribute(f"{animated_attr_name}:values").Get()
            self.assertEqual(list(times), [0.0, 1.0])
            self.assertEqual(list(values), expected_curve_values)

    def _assert_gradient_seeded(self, prim, base_name: str, expected_values: list[list[float]]) -> None:
        times_attr = prim.GetAttribute(f"{base_name}:times")
        values_attr = prim.GetAttribute(f"{base_name}:values")
        self.assertTrue(times_attr and times_attr.IsValid(), f"Expected {base_name}:times to exist.")
        self.assertTrue(values_attr and values_attr.IsValid(), f"Expected {base_name}:values to exist.")
        self.assertEqual(list(times_attr.Get()), [0.0, 1.0])
        self.assertEqual(
            [[round(float(component), 6) for component in value] for value in values_attr.Get()],
            expected_values,
        )

    async def _click_particle_size_button(self, widget):
        action_window = ui.Window("Legacy Silent Upgrade Action Button", height=100, width=360)
        action_widgets = []
        try:
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
        finally:
            action_window.destroy()

    async def test_particle_size_button_silently_upgrades_all_size_channels(self):
        self._author_size_legacy_values(self._prim)
        for animated_attr_name in (
            "primvars:particle:minSize:x",
            "primvars:particle:minSize:y",
            "primvars:particle:maxSize:x",
            "primvars:particle:maxSize:y",
        ):
            self._assert_no_authored_values(self._prim, animated_attr_name, SCALAR_CURVE_LOGICAL_SUFFIXES)
        window, widget = await self._setup_particle_widget()

        try:
            visible_item_names = [
                "".join(model.get_value_as_string() for model in item.name_models)
                for item in widget.property_model.get_all_items()
            ]
            # The button row owns seeding, so the legacy scalar rows should stay hidden.
            self.assertNotIn("Minimum Spawn Size", visible_item_names)
            self.assertNotIn("Maximum Target Size", visible_item_names)

            await self._click_particle_size_button(widget)

            self._assert_curve_seeded(
                self._prim,
                {
                    "primvars:particle:minSize:x": [11.0, 21.0],
                    "primvars:particle:minSize:y": [12.0, 22.0],
                    "primvars:particle:maxSize:x": [31.0, 41.0],
                    "primvars:particle:maxSize:y": [32.0, 42.0],
                },
            )
            self.assertIsNone(ui_test.find("Upgrade Legacy Particle Attributes//Frame/**/Button[*]"))
        finally:
            widget.destroy()
            window.destroy()

    async def test_particle_size_button_silently_upgrades_multi_select_size_channels(self):
        other_prim = self._create_particle_prim("/OtherParticle")
        self._author_size_legacy_values(self._prim)
        self._author_size_legacy_values(
            other_prim,
            min_spawn=Gf.Vec2f(101.0, 102.0),
            min_target=Gf.Vec2f(201.0, 202.0),
            max_spawn=Gf.Vec2f(301.0, 302.0),
            max_target=Gf.Vec2f(401.0, 402.0),
        )
        self._assert_curve_schema_ready(
            self._prim,
            (
                "primvars:particle:minSize:x",
                "primvars:particle:minSize:y",
                "primvars:particle:maxSize:x",
                "primvars:particle:maxSize:y",
            ),
        )
        self._assert_curve_schema_ready(
            other_prim,
            (
                "primvars:particle:minSize:x",
                "primvars:particle:minSize:y",
                "primvars:particle:maxSize:x",
                "primvars:particle:maxSize:y",
            ),
        )
        window, widget = await self._setup_particle_widget([self._prim, other_prim])

        try:
            await self._click_particle_size_button(widget)

            self._assert_curve_seeded(
                self._prim,
                {
                    "primvars:particle:minSize:x": [11.0, 21.0],
                    "primvars:particle:minSize:y": [12.0, 22.0],
                    "primvars:particle:maxSize:x": [31.0, 41.0],
                    "primvars:particle:maxSize:y": [32.0, 42.0],
                },
            )
            self._assert_curve_seeded(
                other_prim,
                {
                    "primvars:particle:minSize:x": [101.0, 201.0],
                    "primvars:particle:minSize:y": [102.0, 202.0],
                    "primvars:particle:maxSize:x": [301.0, 401.0],
                    "primvars:particle:maxSize:y": [302.0, 402.0],
                },
            )
        finally:
            widget.destroy()
            window.destroy()

    async def test_legacy_gradient_seed_authors_single_selected_particle_color(self):
        self._author_min_color_legacy_values(self._prim)
        self._assert_gradient_schema_ready(self._prim, "primvars:particle:minColor")

        result = seed_current_animated_attrs_from_legacy("primvars:particle:minColor", "", [str(self._prim.GetPath())])

        self.assertTrue(result)
        self._assert_gradient_seeded(
            self._prim,
            "primvars:particle:minColor",
            [[1.0, 0.5, 0.25, 1.0], [0.0, 0.25, 0.5, 0.75]],
        )

    async def test_legacy_gradient_seed_authors_multi_selected_particle_colors(self):
        other_prim = self._create_particle_prim("/OtherParticle")
        self._author_min_color_legacy_values(self._prim)
        self._author_min_color_legacy_values(
            other_prim,
            spawn=Gf.Vec4f(0.1, 0.2, 0.3, 1.0),
            target=Gf.Vec4f(0.7, 0.8, 0.9, 0.5),
        )
        self._assert_gradient_schema_ready(self._prim, "primvars:particle:minColor")
        self._assert_gradient_schema_ready(other_prim, "primvars:particle:minColor")

        result = seed_current_animated_attrs_from_legacy(
            "primvars:particle:minColor", "", [str(self._prim.GetPath()), str(other_prim.GetPath())]
        )

        self.assertTrue(result)
        self._assert_gradient_seeded(
            self._prim,
            "primvars:particle:minColor",
            [[1.0, 0.5, 0.25, 1.0], [0.0, 0.25, 0.5, 0.75]],
        )
        self._assert_gradient_seeded(
            other_prim,
            "primvars:particle:minColor",
            [[0.1, 0.2, 0.3, 1.0], [0.7, 0.8, 0.9, 0.5]],
        )
